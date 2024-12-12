import fitz 
import re

def extract_text_chunks_from_pdf(pdf_path, max_chunk_size):
    text_chunks = []
    curr_chunk = ""
    curr_page = 1
    char_count = 0
    try:
        with fitz.open(pdf_path) as pdf:
            num_pages = len(pdf)
            for page_num, page in enumerate(pdf, start=1):
                page_text = page.get_text()
                char_count += len(page_text)
                if page_text:
                    # Basic text cleaning
                    page_text = re.sub(r'\s+', ' ', page_text)  # Remove extra whitespace
                    page_text = re.sub(r'\n', '', page_text)    # Remove new lines
                    sentences = re.split(r'(?<=[.!?]) +', page_text)
                    for sentence in sentences:
                        if len(curr_chunk) + len(sentence) < max_chunk_size:
                            curr_chunk += sentence + " "
                        else:
                            text_chunks.append(f"• {curr_chunk.strip()} [page {curr_page}] /n")
                            curr_chunk = sentence + " "
                            curr_page = page_num
                    # Append the last chunk for the page if it's not empty
                    if curr_chunk.strip():
                        # This condition prevents the last chunk of the current page from being appended without the page number
                        text_chunks.append(f"• {curr_chunk.strip()} [page {page_num}] \n")
                        curr_chunk = ""  # Reset curr_chunk for the next page
        if num_pages > 250:
            num_iters = num_pages // 250 + 1
            text_sections = []
            i_prev = 0
            size = len(text_chunks) // num_iters
            i_next = i_prev + size
            sub_num_pages, sub_num_chars = num_pages // num_iters, char_count // num_iters
            for j in range(num_iters):
                text_section = (text_chunks[i_prev:i_next], sub_num_pages, sub_num_chars, j+1)
                text_sections.append(text_section)
                i_prev = i_next
                i_next = i_next + size
                if i_next >= len(text_chunks):
                    i_next = -1
            return text_sections
        else:
            return [(text_chunks, num_pages, char_count, None)]
    except Exception as e:
        return [(None, e, None, None)]