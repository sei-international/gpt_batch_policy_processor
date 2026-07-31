"""
Pre-run cost estimate.

Gives the user a plausible range for what a run will cost before they start it, from
the things we can know up front: how many documents, how many pages in each, how many
variables, how long the query is, and which model is selected.

This is an estimate, not a quote. Two quantities are genuinely unknowable beforehand:

  * How much text is on a page. Varies with layout, font size and how much of the page
    is figures or tables.
  * How much the model writes back. A variable that appears fifty times in a document
    produces a far longer answer than one that appears twice.

Both are handled by carrying a low and a high figure through the whole calculation
rather than picking a midpoint, so the output is an honest range. The maths mirrors
main.py: one model call per variable per document section, with long documents split
into sections exactly as read_pdf.extract_text_chunks_from_pdf splits them.
"""

import os

# US$ per 1,000,000 tokens, as (input, output). Keep in step with the labels in
# interface.select_gpt_model -- there is a test asserting the two agree.
MODEL_PRICING = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-5.6-luna": (0.20, 1.20),
    "gpt-5.4-nano": (0.20, 1.25),
    "claude-haiku-4-5": (1.00, 5.00),
    "gpt-4.1": (2.00, 8.00),
    "claude-sonnet-5": (3.00, 15.00),
}

# text-embedding-3-small, used for step one regardless of which model is chosen.
EMBEDDING_PRICE_PER_1M = 0.02

CHARS_PER_TOKEN = 4

# The bundled 67-page sample works out at ~2,160 characters per page. Policy PDFs range
# from dense reports to slide-like layouts, so the band is deliberately wide -- it is
# the main driver of the spread in the final range.
CHARS_PER_PAGE_LOW = 1400
CHARS_PER_PAGE_HIGH = 3000

# Response length per variable, in tokens. The least certain part of this estimate: a
# term appearing once yields a short list, a common term yields a long one.
OUTPUT_TOKENS_LOW = 150
OUTPUT_TOKENS_HIGH = 1500

# Roughly what the output-format instructions add on top of the user's own query text.
FORMAT_INSTRUCTION_CHARS = 400

# Long documents are split into sections of at most this many pages, and every variable
# is asked again for each section. Mirrors read_pdf.extract_text_chunks_from_pdf.
PAGES_PER_SECTION = 250

# Batch processing is half price at both OpenAI and Anthropic.
BATCH_DISCOUNT = 0.5


def count_pdf_pages(pdf_paths):
    """
    Returns {path: page_count}, skipping anything that will not open.

    Reads only the page count, never the text, so this stays fast enough to run on
    every Streamlit rerun for a few hundred documents.
    """
    import pymupdf

    counts = {}
    for path in pdf_paths:
        try:
            with pymupdf.open(path) as doc:
                counts[path] = doc.page_count
        except Exception as e:
            print(f"Could not read page count for {os.path.basename(path)}: {e}")
    return counts


def split_into_sections(num_pages):
    """Page counts of the sections a document of this length is processed in."""
    if num_pages <= PAGES_PER_SECTION:
        return [num_pages]
    num_sections = num_pages // PAGES_PER_SECTION + 1
    per_section = num_pages / num_sections
    return [per_section] * num_sections


def input_chars_for_one_call(section_chars, num_excerpts, chunk_size, full_text_char_limit,
                             model_char_ceiling):
    """
    Characters of document text sent for a single variable on a single section.

    Short sections go to the model whole; longer ones send only the selected passages,
    capped by what the model can accept. Mirrors query_gpt.new_openai_session and
    relevant_excerpts.find_top_relevant_texts.
    """
    if section_chars < (full_text_char_limit - 1000):
        return section_chars
    return min(num_excerpts * chunk_size, model_char_ceiling)


def estimate_run_cost(
    page_counts,
    num_variables,
    query_chars,
    gpt_model,
    chunk_size,
    num_excerpts_for_pages,
    full_text_char_limit,
    model_char_ceiling,
    is_batch=False,
):
    """
    Returns a dict describing the expected cost range for one run.

    page_counts: iterable of per-document page counts.
    num_excerpts_for_pages: callable(pages) -> number of passages selected, taken from
        the chosen task's analyzer so this cannot drift from the real behaviour.
    """
    if gpt_model not in MODEL_PRICING:
        return None

    in_price, out_price = MODEL_PRICING[gpt_model]
    pages = [p for p in page_counts if p]
    if not pages or num_variables <= 0:
        return None

    instruction_chars = query_chars + FORMAT_INSTRUCTION_CHARS

    totals = {}
    for band, chars_per_page in (
        ("low", CHARS_PER_PAGE_LOW),
        ("high", CHARS_PER_PAGE_HIGH),
    ):
        input_chars = 0
        embedded_chars = 0
        num_calls = 0

        for num_pages in pages:
            doc_chars = num_pages * chars_per_page
            embedded_chars += doc_chars
            sections = split_into_sections(num_pages)
            for section_pages in sections:
                section_chars = section_pages * chars_per_page
                per_call = input_chars_for_one_call(
                    section_chars,
                    num_excerpts_for_pages(int(section_pages)),
                    chunk_size,
                    full_text_char_limit,
                    model_char_ceiling,
                )
                input_chars += (per_call + instruction_chars) * num_variables
                num_calls += num_variables

        input_tokens = input_chars / CHARS_PER_TOKEN
        output_tokens = num_calls * (
            OUTPUT_TOKENS_LOW if band == "low" else OUTPUT_TOKENS_HIGH
        )
        embedding_tokens = embedded_chars / CHARS_PER_TOKEN

        model_cost = (input_tokens / 1e6) * in_price + (output_tokens / 1e6) * out_price
        if is_batch:
            model_cost *= BATCH_DISCOUNT
        embedding_cost = (embedding_tokens / 1e6) * EMBEDDING_PRICE_PER_1M

        totals[band] = {
            "total": model_cost + embedding_cost,
            "model": model_cost,
            "embedding": embedding_cost,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "num_calls": num_calls,
        }

    return {
        "low": totals["low"]["total"],
        "high": totals["high"]["total"],
        "num_documents": len(pages),
        "total_pages": sum(pages),
        "num_variables": num_variables,
        "num_calls": totals["high"]["num_calls"],
        "passage_selection_cost": totals["high"]["embedding"],
        "is_batch": is_batch,
        "detail": totals,
    }


def format_money(amount):
    """
    Money for humans.

    Sub-cent amounts are shown to three decimals rather than as "less than $0.01":
    at gpt-4o-mini prices a single small document really is a fraction of a cent, and
    a concrete number is more useful than a floor when the point is to compare models.
    """
    if amount < 0.01:
        return f"${amount:.3f}"
    if amount < 100:
        return f"${amount:,.2f}"
    return f"${amount:,.0f}"


def escape_for_markdown(text):
    """
    Escapes dollar signs so Streamlit renders them as currency, not LaTeX.

    st.markdown treats text between two `$` as a maths expression, so
    "$0.01 to less than $0.02" silently becomes an equation with the spaces stripped.
    Every money string that reaches st.markdown / st.caption must go through this.
    """
    return text.replace("$", r"\$")


def format_money_range(low, high):
    """
    Formats a low-to-high span, collapsing it when both ends read the same.

    "$0.02 to $0.02" tells the user nothing a single "$0.02" does not.
    """
    low_text, high_text = format_money(low), format_money(high)
    if low_text == high_text:
        return low_text
    return f"{low_text} to {high_text}"
