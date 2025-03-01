import fitz
import re


def extract_text_chunks_from_pdf(pdf_path, max_chunk_size):
    """
    Extracts text chunks from a PDF file.

    Args:
        pdf_path (str): The path to the PDF file.
        max_chunk_size (int): The maximum size of each text chunk.

    Returns:
        list: A list of dicrtionaries containing text chunks, number of pages, character count, and section number
        for each section of the PDF (most PDFs will only have one section; if less than 250 pages).
    """
    text_chunks = []
    curr_chunk = ""
    curr_page = 1
    total_char_count = 0

    try:
        # Open the PDF file
        with fitz.open(pdf_path) as pdf:
            num_pages = len(pdf)

            # Iterate through each page in the PDF
            for page_num, page in enumerate(pdf, start=1):
                page_text = page.get_text()
                total_char_count += len(page_text)

                if page_text:  # i.e. if there's text to read on this page
                    # Basic text cleaning
                    page_text = re.sub(
                        r"\s+", " ", page_text
                    )  # Remove extra whitespace
                    page_text = re.sub(r"\n", "", page_text)  # Remove new lines

                    # Split text into sentences
                    sentences = re.split(r"(?<=[.!?]) +", page_text)

                    # Create text chunks
                    for sentence in sentences:
                        if len(curr_chunk) + len(sentence) < max_chunk_size:
                            curr_chunk += sentence + " "
                        else:
                            text_chunks.append(
                                f"• {curr_chunk.strip()} [page {curr_page}] /n"
                            )
                            curr_chunk = sentence + " "
                            curr_page = page_num

                    # Append the last chunk for the page if it's not empty
                    if curr_chunk.strip():
                        text_chunks.append(
                            f"• {curr_chunk.strip()} [page {page_num}] \n"
                        )
                        curr_chunk = ""  # Reset curr_chunk for the next page

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

            return text_sections
        else:
            return [
                {
                    "text_chunks": text_chunks,
                    "num_pages": num_pages,
                    "num_chars": total_char_count,
                    "section_num": None,
                }
            ]
    except Exception as e:
        return [
            {
                "text_chunks": None,
                "num_pages": None,
                "num_chars": None,
                "section_num": None,
                "error": e,
            }
        ]
