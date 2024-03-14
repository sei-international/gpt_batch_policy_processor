import fitz 
import re

def extract_text_chunks_from_pdf(pdf_path, max_chunk_size=800):
    text_chunks = []
    curr_chunk = ""
    curr_page = 1

    with fitz.open(pdf_path) as pdf:
        num_pages = len(pdf)
        for page_num, page in enumerate(pdf, start=1):
            page_text = page.get_text()
            if page_text:
                # Basic text cleaning
                page_text = re.sub(r'\s+', ' ', page_text)  # Remove extra whitespace
                page_text = re.sub(r'\n', '', page_text)    # Remove new lines
                sentences = re.split(r'(?<=[.!?]) +', page_text)
                for sentence in sentences:
                    if len(curr_chunk) + len(sentence) < max_chunk_size:
                        curr_chunk += sentence + " "
                    else:
                        text_chunks.append(f"{curr_chunk.strip()} [page {curr_page}]")
                        curr_chunk = sentence + " "
                        curr_page = page_num
                # Append the last chunk for the page if it's not empty
                if curr_chunk.strip():
                    # This condition prevents the last chunk of the current page from being appended without the page number
                    text_chunks.append(f"{curr_chunk.strip()} [page {page_num}]")
                    curr_chunk = ""  # Reset curr_chunk for the next page
    return text_chunks, num_pages