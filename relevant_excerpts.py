from read_pdf import format_quotes_by_section
import hashlib
import json
import numpy as np
import os
import tiktoken

EMBEDDINGS_MODEL = "text-embedding-3-small"


def get_cache_fname(pdf_path, path_fxn, chunk_size=None, embeddings_model=EMBEDDINGS_MODEL):
    """
    Returns the cache filename for a PDF's chunk embeddings.

    The cache key includes the chunk size and embedding model, not just the filename.
    Different task types chunk the same PDF differently (e.g. 1000 chars for quote
    extraction vs 100 for summaries), so keying on filename alone would silently return
    embeddings computed at the wrong granularity.
    """
    pdf_fname = os.path.basename(pdf_path)
    cache_dir = path_fxn("embeddings_cache")
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)
    key = f"{pdf_fname}|{chunk_size}|{embeddings_model}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    stem = os.path.splitext(pdf_fname)[0]
    return f"{cache_dir}/{stem}.{digest}.json"


def cache_embeddings(text_chunks, pdf_file_path, path_fxn, chunk_size=None):
    json_file_path = get_cache_fname(pdf_file_path, path_fxn, chunk_size)
    output_dict = {"text_chunks_w_embeddings": text_chunks}
    with open(json_file_path, "w", encoding="utf-8") as f:
        json.dump(output_dict, f)


def generate_embeddings(openai_client, text, model="text-embedding-3-small"):
    response = openai_client.embeddings.create(model=model, input=text)
    return response


def generate_embedding(openai_client, text):
    r = generate_embeddings(openai_client, text)
    return r.data[0].embedding


def generate_all_embeddings(openai_client, pdf_path, text_chunks, path_fxn, chunk_size=None):
    embeddings_model, token_limit = EMBEDDINGS_MODEL, 6000
    cache_fname = get_cache_fname(pdf_path, path_fxn, chunk_size, embeddings_model)
    if os.path.exists(cache_fname):
        with open(cache_fname, "r", encoding="utf-8") as f:
            cached_embeddings = json.load(f)
            return cached_embeddings["text_chunks_w_embeddings"]
    else:
        batches = []
        current_batch = []
        current_tokens = 0
        enc = tiktoken.encoding_for_model(embeddings_model)
        for text_chunk_dict in text_chunks:
            text = text_chunk_dict["text_chunk"]
            tokens = len(enc.encode(text))
            if current_tokens + tokens > token_limit:
                batches.append(current_batch)
                current_batch = [text]
                current_tokens = tokens
            else:
                current_batch.append(text)
                current_tokens += tokens
        if len(current_batch) > 0:
            batches.append(current_batch)

        embeddings = []
        for batch in batches:
            try:
                response = generate_embeddings(openai_client, batch, embeddings_model)
                embeddings.extend([r.embedding for r in response.data])
            except Exception as e:
                try:
                    for text in batch:
                        response = generate_embedding(openai_client, text)
                        embeddings.append(response)
                except Exception as e2:
                    print(f"Error generating embeddings for batch: {e}, {e2}")

        # A batch that fails both the batched and per-text paths yields fewer embeddings
        # than chunks. Drop the unembedded tail rather than raising IndexError, which
        # would otherwise take down the whole document.
        if len(embeddings) < len(text_chunks):
            print(
                f"Warning: embedded {len(embeddings)}/{len(text_chunks)} chunks for "
                f"{os.path.basename(pdf_path)}; dropping the remainder."
            )
            text_chunks = text_chunks[: len(embeddings)]
        for i in range(len(text_chunks)):
            text_chunks[i]["embedding"] = embeddings[i]
        cache_embeddings(text_chunks, pdf_path, path_fxn, chunk_size)
        return text_chunks


def embed_one_variable_specification(openai_client, prompt):
    return generate_embedding(openai_client, prompt)


def embed_variable_specifications(openai_client, variables):
    var_embeddings = {}
    for var in variables:
        prompt = var
        spec_dict = {"variable_description": "", "context": ""}
        if "variable_description" in variables[var]:
            var_desc = variables[var]["variable_description"]
            if len(var_desc) > 1:
                prompt = f"{var}: '{var_desc}'"
                spec_dict["variable_description"] = var_desc
        if "context" in variables[var]:
            context = variables[var]["context"]
            if len(context) > 1:
                prompt += f". Context: {context}"
                spec_dict["context"] = context
        spec_dict["embedding"] = embed_one_variable_specification(openai_client, prompt)
        var_embeddings[var] = spec_dict
    return var_embeddings


MAX_TOKENS_PER_MODEL = {
    # OpenAI
    "gpt-4.1": 1047576,
    "gpt-5": 400000,
    "gpt-5.6-sol": 1047576,
    "gpt-5.6-terra": 1047576,
    "gpt-5.6-luna": 1047576,
    "gpt-5.4-nano": 272000,
    "gpt-4o": 128000,
    "o4-mini": 200000,
    "o3": 200000,
    "gpt-4o-mini": 128000,
    "gpt-4-turbo": 128000,
    "gpt-3.5-turbo": 16385,
    # Anthropic -- context windows only; these route through a different client
    # (see query_gpt.claude_query) but share the same excerpt-budget maths.
    "claude-opus-5": 1000000,
    "claude-sonnet-5": 1000000,
    "claude-haiku-4-5": 200000,
}
# Conservative default for a model we don't have an entry for.
DEFAULT_MAX_TOKENS = 128000


def get_model_token_limit(gpt_model):
    return MAX_TOKENS_PER_MODEL.get(gpt_model, DEFAULT_MAX_TOKENS)


def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def all_cosine_similarities(chunk_embeddings, var_embedding):
    """
    Cosine similarity of one variable embedding against every chunk embedding.

    Equivalent to calling cosine_similarity() per chunk, but as a single matrix
    operation instead of thousands of Python-level numpy calls.
    """
    matrix = np.asarray(chunk_embeddings, dtype=np.float32)
    vec = np.asarray(var_embedding, dtype=np.float32)
    matrix_norms = np.linalg.norm(matrix, axis=1)
    vec_norm = np.linalg.norm(vec)
    denom = matrix_norms * vec_norm
    # Guard against zero-vectors so a degenerate embedding yields 0.0, not NaN.
    denom[denom == 0] = np.finfo(np.float32).eps
    return (matrix @ vec) / denom


def find_top_relevant_texts(
    pdf_text_chunks_w_embeddings, var_embedding, min_num_excerpts, var_name, gpt_model
):
    """
    Selects the chunks to send to GPT for one variable.

    Selection is a union of two signals, both of which matter:
      1) literal mentions of the variable name (case-insensitive substring match), and
      2) semantic neighbours by embedding similarity.

    (1) is what makes topic/mention counting work -- a user asking about "equity" needs
    every literal occurrence, not just the most semantically similar passages. (2) is what
    catches related wording the user didn't enumerate. Excerpts are returned in document
    order so the model reads them as a narrative and cites pages coherently.
    """
    if not pdf_text_chunks_w_embeddings:
        return []

    max_chars_total = get_model_token_limit(gpt_model) * 4
    max_chars_for_excerpts = max_chars_total - 20000

    similarities = all_cosine_similarities(
        [c["embedding"] for c in pdf_text_chunks_w_embeddings], var_embedding
    )

    indeces = set()
    total_excerpt_num_chars = 0
    var_name_lower = var_name.lower()

    def try_add(i):
        """Add chunk i if new and still within the character budget."""
        nonlocal total_excerpt_num_chars
        if i in indeces:
            return True
        size = len(pdf_text_chunks_w_embeddings[i]["text_chunk"])
        if total_excerpt_num_chars + size > max_chars_for_excerpts:
            return False
        indeces.add(i)
        total_excerpt_num_chars += size
        return True

    # 1) Literal mentions first -- these get priority on the character budget.
    for i, chunk in enumerate(pdf_text_chunks_w_embeddings):
        if var_name_lower in chunk["text_chunk"].lower():
            if not try_add(i):
                break

    # 2) Semantic matches above the similarity threshold, strongest first.
    ranked = sorted(
        range(len(pdf_text_chunks_w_embeddings)),
        key=lambda i: similarities[i],
        reverse=True,
    )
    for i in ranked:
        if similarities[i] > 0.7:
            if not try_add(i):
                break
        else:
            break

    # 3) Top up to min_num_excerpts so short/low-similarity documents still get context.
    for i in ranked:
        if len(indeces) >= min_num_excerpts:
            break
        if not try_add(i):
            break

    return [pdf_text_chunks_w_embeddings[i] for i in sorted(indeces)]


def format_chunks_with_pages(text_chunks):
    return [
        f"{t['text_chunk']} [page(s) {','.join(str(t['page_nums']))}]" for t in text_chunks
    ]


def select_text_chunks(
    gpt_analyzer,
    pdf_text_chunks_w_embs,
    var_embedding,
    var_name,
    num_excerpts,
    run_on_full_text,
):
    """
    Chooses the text sent to GPT for one variable: the whole document if it is short
    enough, otherwise the most relevant excerpts.

    Shared by the synchronous and Batch API paths so both select identical context.
    """
    if run_on_full_text:
        return format_chunks_with_pages(pdf_text_chunks_w_embs)

    top_text_chunks_w_emb = find_top_relevant_texts(
        pdf_text_chunks_w_embs,
        var_embedding,
        num_excerpts,
        var_name,
        gpt_analyzer.gpt_model,
    )
    if gpt_analyzer.organize_text_chunks_by_section is True:
        return format_quotes_by_section(top_text_chunks_w_emb)
    return format_chunks_with_pages(top_text_chunks_w_emb)
