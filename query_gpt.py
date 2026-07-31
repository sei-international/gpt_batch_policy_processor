from openai import OpenAI
from relevant_excerpts import get_model_token_limit
from server_env import get_secret
import ast
import json
import threading

# Documents smaller than this are sent to GPT whole, skipping embedding-based retrieval.
# Retrieval exists to control cost on long documents, not because short ones need it --
# sending a short document in full is both more accurate (nothing can be missed) and
# often cheaper than embedding it.
#
# This is the main cost/quality dial in the tool. Raising it sends more documents in
# full: better recall, higher spend. Lowering it pushes more documents through retrieval.
# ~120k chars is roughly 30k tokens, or a 60-page document.
FULL_TEXT_CHAR_LIMIT = 120000

# Retries cover transient rate limits and 5xx responses. Without these a single blip
# partway through a large batch takes down the whole run.
MAX_RETRIES = 5
REQUEST_TIMEOUT_SECS = 600.0

# Anthropic requires an explicit max_tokens on every request (OpenAI does not). Quote
# extraction can return long exhaustive lists, so this needs real headroom -- but staying
# at ~16k keeps non-streaming requests inside the SDK's HTTP timeout. A response that hits
# this ceiling is reported as a truncation warning rather than silently cut short.
CLAUDE_MAX_OUTPUT_TOKENS = 16000

# Models that run adaptive thinking unless told otherwise. Thinking is exactly the
# over-deliberation this tool should avoid on exhaustive extraction -- a reasoning pass
# tends to self-filter quotes for "relevance", which reads as a recall regression. Models
# not listed here do not think by default, and some reject an explicit disable, so the
# parameter is only sent where it is both needed and accepted.
CLAUDE_THINKING_ON_BY_DEFAULT = frozenset({"claude-sonnet-5", "claude-opus-5"})

_anthropic_client = None
_anthropic_client_lock = threading.Lock()


def is_claude_model(gpt_model):
    """True if this model ID routes to Anthropic rather than OpenAI."""
    return str(gpt_model or "").startswith("claude-")


def new_anthropic_session():
    """
    Returns a shared Anthropic client, built on first use.

    The `anthropic` package is imported here rather than at module scope on purpose.
    Claude is an optional feature, but this module is imported at startup by main.py,
    interface.py and batch_runner.py -- so a top-level import means a missing package
    takes down the whole app instead of just the Claude options. Importing at the point
    of use keeps every GPT path working on a server where the package is absent.

    The key is likewise read at the point of use rather than threaded through main() and
    extract_policy_doc_info(): embeddings always run on OpenAI, so the OpenAI key must
    keep flowing unchanged, and adding a second key to every signature buys nothing.
    The client is cached because the per-variable queries run concurrently.
    """
    try:
        from anthropic import Anthropic
    except ImportError as e:
        raise RuntimeError(
            "Claude models are unavailable on this server: the 'anthropic' package is "
            "not installed. GPT models are unaffected -- please choose one of those. "
            "(To enable Claude, ensure 'anthropic' from requirements.txt is installed "
            "in the deployed environment.)"
        ) from e

    global _anthropic_client
    if _anthropic_client is None:
        with _anthropic_client_lock:
            if _anthropic_client is None:
                api_key = get_secret("anthropic_apikey")
                if not api_key:
                    raise RuntimeError(
                        "Anthropic API key not configured. Add 'anthropic_apikey' to "
                        ".streamlit/secrets.toml for local runs, and as an Azure App "
                        "Service application setting for the deployed app."
                    )
                _anthropic_client = Anthropic(
                    api_key=api_key,
                    max_retries=MAX_RETRIES,
                    timeout=REQUEST_TIMEOUT_SECS,
                )
    return _anthropic_client


def strip_code_fences(text):
    """
    Removes a wrapping ```json ... ``` fence if present.

    OpenAI's response_format={"type": "json_object"} guarantees bare JSON. Anthropic has
    no equivalent unless you supply a full schema, and the prompt-level instruction the
    formatters use sometimes yields a fenced block. Stripping the fence here keeps the
    prompt byte-identical across providers, so the A/B compares models rather than
    prompts.
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return text
    lines = stripped.split("\n")
    lines = lines[1:]  # drop the opening ``` or ```json
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def slice_outermost_container(text):
    """Returns the widest {...} or [...] span in text, or None if there isn't one."""
    best = None
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            span = text[start : end + 1]
            if best is None or len(span) > len(best):
                best = span
    return best


def coerce_json_text(text, gpt_model, stop_reason):
    """
    Normalizes a Claude response into text that json.loads() will accept.

    The formatters ask for JSON in the prompt but illustrate the shape with
    str(python_dict) -- single-quoted, and therefore not valid JSON. OpenAI's
    json_object response format overrode that malformed example and returned
    well-formed JSON anyway; Anthropic has no such constraint, so it reasonably
    follows the example as written, or wraps the object in a sentence of prose.

    Three recoveries, cheapest first: parse as-is, parse the outermost {...}/[...]
    span (drops any preamble or trailing commentary), then parse as a Python literal
    and re-serialize (handles the single-quoted case). All are post-processing --
    the prompt stays byte-identical across providers so the A/B still compares models.
    """
    candidate = strip_code_fences(text)

    if not candidate.strip():
        raise RuntimeError(
            f"{gpt_model} returned an empty response (stop_reason={stop_reason!r}). "
            "Nothing to parse -- if stop_reason is 'refusal' the request was declined; "
            "if 'max_tokens' the ceiling is too low."
        )

    attempts = [candidate]
    sliced = slice_outermost_container(candidate)
    if sliced is not None and sliced != candidate:
        attempts.append(sliced)

    for attempt in attempts:
        try:
            json.loads(attempt)
            return attempt
        except ValueError:
            pass
    # Python-literal fallback: safe (literal_eval evaluates literals only, never code).
    for attempt in attempts:
        try:
            return json.dumps(ast.literal_eval(attempt))
        except (ValueError, SyntaxError):
            pass

    preview = candidate[:300].replace("\n", " ")
    raise RuntimeError(
        f"{gpt_model} did not return parseable JSON (stop_reason={stop_reason!r}). "
        f"First 300 chars of the response: {preview!r}"
    )


def claude_query(gpt_model, resp_fmt, msgs):
    """
    Sends one request to Anthropic, mirroring the OpenAI path's inputs and output.

    Takes the same message list the OpenAI path builds and adapts it to the Messages API:
    the system prompt is a top-level parameter there, not a messages[0] entry. Returns the
    response text so callers cannot tell which provider answered.
    """
    system_prompt = "".join(m["content"] for m in msgs if m["role"] == "system")
    user_messages = [
        {"role": m["role"], "content": m["content"]} for m in msgs if m["role"] != "system"
    ]

    kwargs = {
        "model": gpt_model,
        "max_tokens": CLAUDE_MAX_OUTPUT_TOKENS,
        "system": system_prompt,
        "messages": user_messages,
    }
    if gpt_model in CLAUDE_THINKING_ON_BY_DEFAULT:
        kwargs["thinking"] = {"type": "disabled"}
    # Deliberately no temperature: a non-default value is rejected outright on Sonnet 5,
    # and the OpenAI path only sets it for gpt-4.1.

    response = new_anthropic_session().messages.create(**kwargs)

    if response.stop_reason == "max_tokens":
        print(
            f"Warning: {gpt_model} response hit the {CLAUDE_MAX_OUTPUT_TOKENS}-token "
            "ceiling and was truncated. Results for this variable may be incomplete."
        )

    text = "".join(block.text for block in response.content if block.type == "text")
    if resp_fmt == "json_object":
        text = coerce_json_text(text, gpt_model, response.stop_reason)
    return text


def new_openai_session(openai_apikey, gpt_model=None):
    """
    Returns an OpenAI client and the char count below which a document is sent in full.

    The key is passed to the client directly rather than written to os.environ: the
    per-variable queries run concurrently, and mutating global process state from
    worker threads is a race waiting to happen.
    """
    client = OpenAI(
        api_key=openai_apikey,
        max_retries=MAX_RETRIES,
        timeout=REQUEST_TIMEOUT_SECS,
    )
    max_num_chars = FULL_TEXT_CHAR_LIMIT
    if gpt_model:
        # Never promise a full-text run larger than the model can actually accept.
        # 4 chars/token, with headroom reserved for instructions and the response.
        # The reserve scales with the window: a flat reserve would exceed the whole
        # context of a small model like gpt-3.5-turbo and drive the budget to zero.
        token_limit = get_model_token_limit(gpt_model)
        reserve = min(20000, token_limit // 4)
        max_num_chars = min(max_num_chars, (token_limit - reserve) * 4)
    return client, max_num_chars


def create_gpt_messages(query, run_on_full_text):
    text_label = "collection of text excerpts"
    if run_on_full_text:
        text_label = "document"
    system_command = (
        "Use the provided "
        + text_label
        + " delimited by triple quotes to respond to instructions delimited with XML tags. Be precise. Be accurate. Be exhaustive: do not truncate your response if response is incomplete. Proceed progressively through all text provided. Do not stop processing until all text has been read. Do not be redundant. Be consistent with your responses to the same query."
    )
    return [
        {"role": "system", "content": system_command},
        {"role": "user", "content": query},
    ]


def build_request_body(gpt_model, resp_fmt, msgs):
    """
    Builds the chat.completions request body.

    Shared by the synchronous path and the Batch API path so both send identical
    requests -- batch results should differ from live results only in latency.
    """
    body = {
        "model": gpt_model,
        "response_format": {"type": resp_fmt},
        "messages": msgs,
    }
    if gpt_model == "gpt-4.1":
        body["temperature"] = 0
    return body


def chat_gpt_query(gpt_client, gpt_model, resp_fmt, msgs):
    """
    Sends one query to whichever provider owns this model ID.

    gpt_client is the OpenAI client; the Anthropic path builds its own from the
    separately-configured key and ignores it.
    """
    if is_claude_model(gpt_model):
        return claude_query(gpt_model, resp_fmt, msgs)
    response = gpt_client.chat.completions.create(
        **build_request_body(gpt_model, resp_fmt, msgs)
    )
    return response.choices[0].message.content

def fetch_variable_info(gpt_client, gpt_model, query, resp_fmt, run_on_full_text):
    msgs = create_gpt_messages(query, run_on_full_text)
    return chat_gpt_query(gpt_client, gpt_model, resp_fmt, msgs)
    """msgs.append({"role": "assistant", "content": init_response})
    follow_up_prompt = "<instructions>Based on the previous instructions, ensure that your response has included all correct answers and/or text excerpts. If your previous resposne is correct, return the same response. If there is more to add to your previous response, return the same format with the complete, correct response.</instructions>"
    msgs.append({"role": "user", "content": follow_up_prompt})
    follow_up_response = chat_gpt_query(gpt_client, gpt_model, resp_fmt, msgs)
    return follow_up_response"""


def build_variable_prompt(gpt_analyzer, variable_name, var_spec, context, relevant_excerpts):
    """
    Builds the user prompt for one variable.

    Split out from query_gpt_for_variable_specification so the Batch API path builds
    byte-identical prompts without duplicating the templating logic.
    """
    query_template = gpt_analyzer.main_query
    main_query = f"{query_template.format(variable_name=variable_name, variable_description=var_spec, context=context)} \n\n"
    main_query = gpt_analyzer.optional_add_categorization(variable_name, main_query)
    output_prompt = gpt_analyzer.output_fmt_prompt(variable_name)
    if len(output_prompt) > 1:
        output_prompt = " " + output_prompt
    return f'<instructions>{main_query}.{output_prompt}</instructions> \n\n """{relevant_excerpts}"""'


def build_variable_messages(
    gpt_analyzer, variable_name, var_spec, context, relevant_excerpts, run_on_full_text
):
    """Builds the full message list for one variable."""
    prompt = build_variable_prompt(
        gpt_analyzer, variable_name, var_spec, context, relevant_excerpts
    )
    return create_gpt_messages(prompt, run_on_full_text)


def query_gpt_for_variable_specification(
    gpt_analyzer,
    variable_name,
    var_spec,
    context,
    relevant_excerpts,
    run_on_full_text,
    gpt_client,
    gpt_model="gpt-4.1",
):
    prompt = build_variable_prompt(
        gpt_analyzer, variable_name, var_spec, context, relevant_excerpts
    )
    resp_fmt = gpt_analyzer.resp_format_type()
    return fetch_variable_info(
        gpt_client, gpt_model, prompt, resp_fmt, run_on_full_text
    )
