from interface import build_interface, email_results, get_user_inputs
from query_gpt import new_openai_session, query_gpt_for_column
from read_pdf import extract_text_chunks_from_pdf
from relevant_excerpts import generate_all_embeddings, embed_schema, find_top_relevant_texts
from results import get_output_fname, output_results, output_metrics

from docx import Document
from tempfile import NamedTemporaryFile, TemporaryDirectory
import csv
import os
import streamlit as st
import time
import zipfile


def get_resource_path(relative_path):
    return relative_path

def get_schema():
    filepath = get_resource_path("instructions.docx")
    doc = Document(filepath)
    schema = {}
    if doc.tables:
        main_query = doc.tables[0].cell(0,0).text 
        for info_spec in  doc.tables[1].rows:
            key = info_spec.cells[0].text
            value = info_spec.cells[1].text
            schema[key] = value 
    return schema, main_query, False

def extract_policy_doc_info(main_query, text_embeddings, text_chunks, col_embeddings):
    policy_doc_data = {}
    client, gpt_model, max_num_chars = new_openai_session()
    for col_name in col_embeddings:
        col_embedding, col_spec = col_embeddings[col_name]["embedding"], col_embeddings[col_name]["prompt"]
        top_text_chunks_w_emb = find_top_relevant_texts(text_embeddings, text_chunks, col_embedding)
        top_text_chunks = [chunk_tuple[1] for chunk_tuple in top_text_chunks_w_emb]
        resp = query_gpt_for_column(main_query, col_name, col_spec, top_text_chunks, client, gpt_model)
        policy_doc_data[col_name] = resp
    return policy_doc_data

def print_milestone(milestone_desc, last_milestone_time, extras={}, mins=True):
    unit = "minutes" if mins else "seconds"
    elapsed = time.time() - last_milestone_time
    elapsed = elapsed/60.0 if mins else elapsed
    print(f"{milestone_desc}: {elapsed:.2f} {unit}")
    for extra in extras:
        print(f"{extra}: {extras[extra]}")
    return time.time()

def main(pdfs, main_query, column_specs, email):
    compare_output_bool = False
    output_doc = Document()
    total_num_pages = 0
    total_start_time = time.time()
    for pdf in pdfs:
        pdf_path = get_resource_path(f"{pdf.replace('.pdf','')}.pdf")
        try:
            country_start_time = time.time()
            # 1) read pdf
            text_chunks, num_pages = extract_text_chunks_from_pdf(pdf_path)
            total_num_pages += num_pages
            openai_client, _, _ = new_openai_session()
            pdf_embeddings, pdf_text_chunks = generate_all_embeddings(openai_client, pdf_path, text_chunks, get_resource_path)

            # 2) Prepare embeddings to grab most relevant text excerpts for each column
            #schema, main_query, compare_output_bool = get_schema()
            openai_client, _, _ = new_openai_session()
            col_embeddings = embed_schema(openai_client, column_specs) # i.e. {"col_name": {"prompt": <...>, "embedding": <...>}, ..., ...}

            # 3) Iterate through each column to grab relevant texts and query
            policy_info = extract_policy_doc_info(main_query, pdf_embeddings, pdf_text_chunks, col_embeddings)
            # 4) Output Results
            output_results(output_doc, pdf_path, compare_output_bool, policy_info, get_resource_path)

            print_milestone("Done", country_start_time, {"Number of pages in PDF": num_pages})
        except Exception as e:
            print(f"Error for {pdf}: {e}")
    output_metrics(output_doc, len(pdfs), time.time() - total_start_time, total_num_pages)
    output_fname = get_output_fname(get_resource_path)
    output_doc.save(output_fname)
    email_results(output_fname, email)
    #display_output(output_fname)


if __name__ == "__main__":
    build_interface()
    if st.button("Run"):
        uploaded_zip = st.session_state['uploaded_zip']
        with TemporaryDirectory() as temp_dir:
            pdfs = []
            with NamedTemporaryFile(delete=False, suffix='.zip') as temp_zip:
                temp_zip.write(uploaded_zip.getvalue())
                temp_zip_path = temp_zip.name
            with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            for subdir in os.listdir(temp_dir):
                subdir_path = os.path.join(temp_dir, subdir)
                for filename in os.listdir(subdir_path):
                    if filename.endswith(".pdf"):
                        file_path = os.path.join(subdir_path, filename)
                        pdfs.append(file_path)  
            main_query, column_specs, email = get_user_inputs()  
            with st.spinner('Generating output document...'):
                main(pdfs, main_query, column_specs, email)
            st.success('Document generated!')
            os.unlink(temp_zip_path)