from segtok.segmenter import split_single
import pymupdf
import pymupdf4llm
import re

def pdf_to_markdown(pdf_path: str, max_toc_levels: int = 6):
    import warnings

    # Suppress MuPDF warnings about corrupted images - we only need text
    warnings.filterwarnings('ignore', category=UserWarning, module='pymupdf')

    doc = pymupdf.open(pdf_path)
    try:
        headers = pymupdf4llm.TocHeaders(doc, max_levels=max_toc_levels)
        if not headers:  # no TOC entries found
            raise ValueError("Empty TOC")
        print(f"Using embedded TOC with up to {max_toc_levels} levels.")
    except Exception:
        headers = pymupdf4llm.IdentifyHeaders(doc, max_levels=max_toc_levels)
        print("No TOC found – falling back to font-based header identification.")

    try:
        return headers, pymupdf4llm.to_markdown(
            doc,
            page_chunks=True,
            hdr_info=headers
        )
    except Exception as e:
        # If markdown conversion fails due to image issues, try without page chunks
        print(f"Warning: Error during markdown conversion: {e}")
        print("Retrying with simpler conversion...")
        try:
            return headers, pymupdf4llm.to_markdown(doc, hdr_info=headers, page_chunks=True)
        except Exception as e2:
            print(f"Second attempt also failed: {e2}")
            raise


def add_text_chunks(text_chunks_tmp, curr_chunk, curr_page_nums, headers, sentence, page_num):
    if len(curr_chunk) > 1:
        text_chunk_id = len(text_chunks_tmp)
        text_chunks_tmp.append({
            "text_chunk":f"{curr_chunk.strip()}",
            "page_nums": list(curr_page_nums),
            "headers": headers,
            "id": text_chunk_id
        })
        curr_page_nums = set([])
        curr_page_nums.add(page_num)
        curr_chunk = sentence + " "
    return text_chunks_tmp, curr_chunk, curr_page_nums


def extract_text_chunks_from_pdf(pdf_path, max_chunk_size):
    """
    Extracts text chunks from a PDF file.

    Args:
        pdf_path (str): The path to the PDF file.
        max_chunk_size (int): The maximum size of each text chunk.

    Returns:
        document title: str
        list: A list of dictionaries containing text chunks, number of pages, character count, and section number
        for each section of the PDF (most PDFs will only have one section; if less than 250 pages).
    """
    text_chunks = []
    curr_chunk = ""
    total_char_count = 0
    doc_title = None
    try:
        # Open the PDF file
        headers, doc_md = pdf_to_markdown(pdf_path)
        doc_title = doc_md[0]["metadata"]["title"]
        num_pages = len(doc_md)
        curr_headers = {}
        curr_page_nums = set([])
        header_re = re.compile(r'^(?P<level>#{1,6})\s+(?P<title>.+)$')
        for page_num, page in enumerate(doc_md, start=1):
            page_text = page["text"]
            total_char_count += len(page_text)
            curr_page_nums = set([])
            paragraph = ""
            for line in page["text"].splitlines(keepends=True):
                m = header_re.match(line)
                if m:
                    # Before updating headers, process any accumulated paragraph
                    if paragraph.strip():
                        sentences = list(split_single(paragraph))
                        for sentence in sentences:
                            if len(curr_chunk) + len(sentence) < max_chunk_size:
                                curr_chunk += sentence + " "
                                curr_page_nums.add(page_num)
                            else:
                                text_chunks, curr_chunk, curr_page_nums = add_text_chunks(
                                    text_chunks, curr_chunk, curr_page_nums, dict(curr_headers), sentence, page_num
                                )
                        paragraph = ""
                    lvl = len(m.group("level"))
                    h_title = m.group("title").strip()
                    curr_headers = {k: v for k, v in curr_headers.items() if k <= lvl - 1}
                    curr_headers[lvl] = h_title
                    continue
                paragraph += line.strip() + " "
            # After all lines, process any remaining paragraph
            if paragraph.strip():
                sentences = list(split_single(paragraph))
                for sentence in sentences:
                    if len(curr_chunk) + len(sentence) < max_chunk_size:
                        curr_chunk += sentence + " "
                        curr_page_nums.add(page_num)
                    else:
                        text_chunks, curr_chunk, curr_page_nums = add_text_chunks(
                            text_chunks, curr_chunk, curr_page_nums, dict(curr_headers), sentence, page_num
                )
        # If the PDF has more than 250 pages, split the text into sections
        # Otherwise we may exceed OpenAI's token limit (even when only including relevant text chunks)
        if num_pages > 250:
            num_iters = num_pages // 250 + 1
            text_sections = []
            i_prev = 0
            size = len(text_chunks) // num_iters
            i_next = i_prev + size
            sub_num_pages, sub_num_chars = (
                num_pages // num_iters,
                total_char_count // num_iters,
            )

            # Create sections of text chunks
            for j in range(num_iters):
                text_section = {
                    "text_chunks": text_chunks[i_prev:i_next],
                    "num_pages": sub_num_pages,
                    "num_chars": sub_num_chars,
                    "section_num": j + 1,
                }
                text_sections.append(text_section)
                i_prev = i_next
                i_next = i_next + size
                if i_next >= len(text_chunks):
                    i_next = -1

            return doc_title, text_sections
        else:
            return doc_title, [
                {
                    "text_chunks": text_chunks,
                    "num_pages": num_pages,
                    "num_chars": total_char_count,
                    "section_num": None,
                }
            ]
    except Exception as e:
        print("ERROR:", e)
        return doc_title, [
            {
                "text_chunks": None,
                "num_pages": None,
                "num_chars": None,
                "section_num": None,
                "error": e,
            }
        ]
    

def format_quotes_by_section(text_chunks_dicts: list[dict]) -> str:
    output_lines = []
    last_headers = []

    for item in text_chunks_dicts:
        quote = f"{item['text_chunk']} [page(s) {item['page_nums']}]"
        # Ensure headers are sorted by level (0, 1, 2...)
        current_headers = [item["headers"][k] for k in sorted(item["headers"].keys())]

        # Find the first level at which the header has changed
        first_diff_index = 0
        while (
            first_diff_index < len(last_headers) and
            first_diff_index < len(current_headers) and
            last_headers[first_diff_index] == current_headers[first_diff_index]
        ):
            first_diff_index += 1

        # Add a blank line for spacing when a major section (level 0 or 1) changes
        if first_diff_index < 2 and output_lines:
            output_lines.append("")

        # Add any new headers that haven't been printed yet for this quote's section
        for i in range(first_diff_index, len(current_headers)):
            output_lines.append(f"{'#' * (i + 1)} {current_headers[i]}")

        # Add the quote, formatted as a list item
        output_lines.append(f"• {quote} \n")

        # Remember the headers for this quote to compare with the next one
        last_headers = current_headers

    return "Relevant text excerpts organized by headings:\n\n" + '\n'.join(output_lines)