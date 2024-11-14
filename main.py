from interface import about_tab, FAQ, build_interface, display_output, email_results, get_user_inputs, load_header
from query_gpt import new_openai_session, query_gpt_for_column
from read_pdf import extract_text_chunks_from_pdf
from relevant_excerpts import generate_all_embeddings, embed_schema, find_top_relevant_texts
from results import format_output_doc, get_output_fname, output_results, output_metrics

from docx import Document
from tempfile import NamedTemporaryFile, TemporaryDirectory
import json
import os
import requests
import streamlit as st
import time
import traceback


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

def extract_policy_doc_info(gpt_analyzer, text_embeddings, input_text_chunks, char_count, var_embeddings, num_excerpts, openai_apikey):
    policy_doc_data = {}
    text_chunks = input_text_chunks
    client, gpt_model, max_num_chars = new_openai_session(openai_apikey)
    run_on_full_text = char_count < (max_num_chars - 1000)
    for var_name in var_embeddings:
        col_embedding, col_desc, context = var_embeddings[var_name]["embedding"], var_embeddings[var_name]["column_description"], var_embeddings[var_name]["context"], 
        if not run_on_full_text: 
            top_text_chunks_w_emb = find_top_relevant_texts(text_embeddings, input_text_chunks, col_embedding, num_excerpts, var_name)
            text_chunks = [chunk_tuple[1] for chunk_tuple in top_text_chunks_w_emb]
            print("HERE")
        resp = query_gpt_for_column(gpt_analyzer, var_name, col_desc, context, text_chunks, run_on_full_text, client, gpt_model)
        policy_doc_data[var_name] = gpt_analyzer.format_gpt_response(resp)
    return policy_doc_data

def print_milestone(milestone_desc, last_milestone_time, extras={}, mins=True):
    unit = "minutes" if mins else "seconds"
    elapsed = time.time() - last_milestone_time
    elapsed = elapsed/60.0 if mins else elapsed
    print(f"{milestone_desc}: {elapsed:.2f} {unit}")
    for extra in extras:
        print(f"{extra}: {extras[extra]}")
    return time.time()

def fetch_gist_content(gist_url, headers, log_fname):
    response = requests.get(gist_url, headers=headers)
    if response.status_code == 200:
        gist_data = response.json()
        return gist_data['files'][log_fname]['content']
    else:
        print('Failed to fetch gist content.')
        return None

def log(new_content):
    github_token = st.secrets["github_token"]
    log_fname = 'log'
    gist_base_url = 'https://api.github.com/gists'
    gist_url = f'{gist_base_url}/47029f286297a129a654110ebe420f5f'
    headers = {'Authorization': f'token {github_token}', 'Accept': 'application/vnd.github.v3+json'}
    current_content = fetch_gist_content(gist_url, headers, log_fname)
    if current_content is not None:
        updated_content = f"{current_content} \n {new_content}"
        data = {'files': {log_fname: {'content': updated_content}}}
        requests.patch(gist_url, headers=headers, data=json.dumps(data))

def main(gpt_analyzer, openai_apikey):
    compare_output_bool = False
    output_doc = Document()
    format_output_doc(output_doc, gpt_analyzer)
    total_num_pages = 0
    total_start_time = time.time()
    for pdf in gpt_analyzer.pdfs:
        pdf_path = get_resource_path(f"{pdf.replace('.pdf','')}.pdf")
        try:
            country_start_time = time.time()
            # 1) read pdf
            text_chunk_size = gpt_analyzer.get_chunk_size()
            text_chunks, num_pages, char_count = extract_text_chunks_from_pdf(pdf_path, text_chunk_size)
            total_num_pages += num_pages
            openai_client, _, _ = new_openai_session(openai_apikey)
            pdf_embeddings, pdf_text_chunks = generate_all_embeddings(openai_client, pdf_path, text_chunks, get_resource_path) 

            # 2) Prepare embeddings to grab most relevant text excerpts for each column
            #schema, main_query, compare_output_bool = get_schema()
            openai_client, _, _ = new_openai_session(openai_apikey)
            var_embeddings = embed_schema(openai_client, gpt_analyzer.variable_specs) # i.e. {"col_name": {"embedding": <...>", "column_description": <...>, "context": <...>},  ...}
            # 3) Iterate through each column to grab relevant texts and query
            num_excerpts = gpt_analyzer.get_num_excerpts(num_pages)
            policy_info = extract_policy_doc_info(gpt_analyzer, pdf_embeddings, pdf_text_chunks, char_count, var_embeddings, num_excerpts, openai_apikey)
            # 4) Output Results
            output_results(gpt_analyzer, output_doc, pdf_path, policy_info)

            print_milestone("Done", country_start_time, {"Number of pages in PDF": num_pages})
        except Exception as e:
            log(f"Error for {pdf}: {e}")
            log(traceback.format_exc())
    output_metrics(output_doc, len(gpt_analyzer.pdfs), time.time() - total_start_time, total_num_pages)
    output_fname = get_output_fname(get_resource_path)
    output_doc.save(output_fname)
    email_results(output_fname, gpt_analyzer.email)
    display_output(output_fname)
    return total_num_pages

if __name__ == "__main__":
    try: 
        with TemporaryDirectory() as temp_dir:
            st.set_page_config(layout="wide")
            load_header()
            _, centered_div, _ = st.columns([1, 3, 1])
            with centered_div:
                tab1, tab2, tab3 = st.tabs(["Tool", "About", "FAQ"])
                with tab1:
                    build_interface(temp_dir)
                    if st.button("Run"):
                        gpt_analyzer = get_user_inputs()
                        with st.spinner('Generating output document...'):
                            apikey_id = "openai_apikey"
                            if "apikey_id" in st.session_state:
                                apikey_id = st.session_state["apikey_id"]
                            openai_apikey = st.secrets[apikey_id]
                            num_pages = main(gpt_analyzer, openai_apikey)
                            log(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} GMT --> apikey_id; {num_pages} pages; {gpt_analyzer}")
                        st.success('Document generated!')
                        os.unlink(st.session_state["temp_zip_path"])
                with tab2:
                    about_tab()
                with tab3:
                    FAQ()
    except Exception as e:
        log(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} GMT --> apikey_id:{e}")
        log(traceback.format_exc())
        