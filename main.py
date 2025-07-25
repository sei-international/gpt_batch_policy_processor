"""
This script processes PDF documents to extract relevant policy information using OpenAI's GPT API.
It reads the PDFs, extracts text chunks, generates embeddings, and queries GPT for specific variables.
The results are formatted and saved in a Word document, which can be emailed to the user.

Modules:
- analysis: Contains classes that define different ways of analyzing documents.
    - Note: the analyzer module is ont directly referenced in this file (it is in interface.py)
- interface: Handles the user interface and interactions.
- query_gpt: Manages the GPT session and queries.
- read_pdf: Extracts text chunks from PDF documents.
- relevant_excerpts: Generates embeddings and finds relevant text excerpts for each variable.
- results: Formats and outputs the results.

Functions:
- get_resource_path: Returns the resource path for a given relative path.
- extract_policy_doc_info: Extracts policy document information by querying GPT for each variable.
- print_milestone: Prints a milestone with the elapsed time and additional information.
- fetch_gist_content: Fetches the content of a gist from GitHub.
- log: Logs new content to a GitHub gist.
- main: Main function to process PDFs and generate an output document.

Usage:
Run "python -m streamlit run .\main.py" to start the Streamlit application.
"""

from interface import (
    about_tab,
    FAQ,
    build_interface,
    display_output,
    email_results,
    get_user_inputs,
    load_header,
)
from query_gpt import new_openai_session, query_gpt_for_variable_specification
from read_pdf import extract_text_chunks_from_pdf, format_quotes_by_section
from relevant_excerpts import (
    generate_all_embeddings,
    embed_variable_specifications,
    find_top_relevant_texts,
)
from results import format_output_doc, get_output_fname, output_results, output_metrics
from server_env import get_secret

from openpyxl import Workbook
from tempfile import TemporaryDirectory
import io
import json
import os
import requests
import streamlit as st
import sys
import time
import traceback


def get_resource_path(relative_path):
    """
    Returns the resource path for a given relative path.
    """
    return relative_path


def extract_policy_doc_info(
    gpt_analyzer,
    pdf_text_chunks_w_embs,
    char_count,
    var_embeddings,
    num_excerpts,
    openai_apikey,
    gpt_model
):
    """
    Extracts policy document information by querying GPT for each variable specified.

    Args:
        gpt_analyzer: The GPT analyzer object .
        pdf_text_chunks_w_embs: List of text chunks from the input document.
        char_count: Character count of the text.
        var_embeddings: Embeddings for the variables.
        num_excerpts: Number of excerpts to extract.
        openai_apikey: API key for OpenAI.

    Returns:
        A dictionary listing for each variable the response from GPT.
        The response format depends on the Analyzer class selected.
    """
    policy_doc_data = {}
    client, max_num_chars = new_openai_session(openai_apikey)
    gpt_model = gpt_analyzer.get_gpt_model()
    # If the text is short, we don't need to generate embeddings to find "relevant texts"
    # If the text is long, text_chunks (defined above) will be replaced with the top relevant texts
    run_on_full_text = char_count < (max_num_chars - 1000)
    for var_name in var_embeddings:
        var_embedding, var_desc, context = (
            var_embeddings[var_name]["embedding"],
            var_embeddings[var_name]["variable_description"],
            var_embeddings[var_name]["context"],
        )
        if not run_on_full_text:
            top_text_chunks_w_emb = find_top_relevant_texts(
                pdf_text_chunks_w_embs,
                var_embedding,
                num_excerpts,
                var_name,
            )
            #text_chunks = [chunk_tuple[1] for chunk_tuple in top_text_chunks_w_emb]
            if gpt_analyzer.organize_text_chunks_by_section is True:
                text_chunks = format_quotes_by_section(top_text_chunks_w_emb)
            else:
                text_chunks = [f"{t['text_chunk']} [page(s) {','.join(str(t['page_nums']))}]" for t in top_text_chunks_w_emb]
        else:
            text_chunks = [f"{t['text_chunk']} [page(s) {','.join(str(t['page_nums']))}]" for t in pdf_text_chunks_w_embs]

        resp = query_gpt_for_variable_specification(
            gpt_analyzer,
            var_name,
            var_desc,
            context,
            text_chunks,
            run_on_full_text,
            client,
            gpt_model,
        )
        policy_doc_data[var_name] = gpt_analyzer.format_gpt_response(resp)
    return policy_doc_data


def print_milestone(milestone_desc, last_milestone_time, extras={}, mins=True):
    """
    Prints a milestone with the elapsed time and additional information.

    Args:
        milestone_desc: Description of the milestone.
        last_milestone_time: Time of the last milestone.
        extras: Additional information to print.
        mins: Whether to print the elapsed time in minutes or seconds.
    """
    unit = "minutes" if mins else "seconds"
    elapsed = time.time() - last_milestone_time
    elapsed = elapsed / 60.0 if mins else elapsed
    print(f"{milestone_desc}: {elapsed:.2f} {unit}")
    for extra in extras:
        print(f"{extra}: {extras[extra]}")


def fetch_gist_content(gist_url, headers, log_fname):
    """
    Fetches the content of a gist from GitHub.
    This is used to update our log file with the latest run information.

    Args:
        gist_url: URL of the gist.
        headers: Headers for the request.
        log_fname: Filename of the log file in the gist.

    Returns:
        The content of the gist file if successful, None otherwise.
    """
    response = requests.get(gist_url, headers=headers)
    if response.status_code == 200:
        gist_data = response.json()
        return gist_data["files"][log_fname]["content"]
    else:
        print("Failed to fetch gist content.")
        return None


def log(new_content):
    """
    Logs new activity to a GitHub gist.

    Args:
        new_content: The new content to log.
    """
    github_token = get_secret("github_token")
    log_fname = "ai-tool-log"
    gist_base_url = "https://api.github.com/gists"
    gist_url = f"{gist_base_url}/cdc9929b3a24b3fc4150579b2b2bb2b3"
    headers = {
        "Authorization": f"token {github_token}",
        "Accept": "application/vnd.github.v3+json",
    }
    current_content = fetch_gist_content(gist_url, headers, log_fname)
    if current_content is not None:
        updated_content = f"{current_content} \n {new_content}"
        updated_content = updated_content + "\n ----------------------------------------------------------------------------"
        data = {"files": {log_fname: {"content": updated_content}}}
        requests.patch(gist_url, headers=headers, data=json.dumps(data))


def main(gpt_analyzer, openai_apikey):
    """
    Main function to process PDFs and generate an output document.

    Args:
        gpt_analyzer: The GPT analyzer object.
        openai_apikey: API key for OpenAI.

    Returns:
        The total number of pages processed.
    """
    output_doc = Workbook()
    format_output_doc(output_doc, gpt_analyzer)
    total_num_pages = 0
    total_start_time = time.time()
    failed_pdfs = []
    gpt_model = gpt_analyzer.get_gpt_model()
    for pdf in gpt_analyzer.pdfs:
        pdf_path = get_resource_path(f"{pdf.replace('.pdf','')}.pdf")
        try:
            country_start_time = time.time()
            # 1) read pdf
            text_chunk_size = gpt_analyzer.get_chunk_size()
            doc_title, text_sections = extract_text_chunks_from_pdf(pdf_path, text_chunk_size)
            if "error" in text_sections[0]:
                failed_pdfs.append(pdf)
                print(f"Failed: {pdf} with {text_sections[0]['error']}")
                continue
            num_pages_in_pdf = 0
            num_sections = len(text_sections)
            ## Most PDFs will only have 1 text_section: this is used to break up long documents (>250 pages)            
            for text_section in text_sections:
                text_chunks, num_pages, char_count, section = [
                    text_section[k]
                    for k in ["text_chunks", "num_pages", "num_chars", "section_num"]
                ]
                if num_sections > 1:
                    output_pdf_path = f"{pdf_path} ({section} of {len(text_sections)})"
                else:
                    output_pdf_path = f"{pdf_path}"
                num_pages_in_pdf += num_pages
                total_num_pages += num_pages
                openai_client, _ = new_openai_session(openai_apikey)
                pdf_text_chunks_w_embs = generate_all_embeddings(
                    openai_client, output_pdf_path, text_chunks, get_resource_path
                )
                # 2) Prepare embeddings to grab most relevant text excerpts for each variable
                openai_client, _ = new_openai_session(openai_apikey)
                var_embeddings = embed_variable_specifications(
                    openai_client, gpt_analyzer.variable_specs
                )  # i.e. {"var_name": {"embedding": <...>", "variable_description": <...>, "context": <...>},  ...}

                # 3) Iterate through each variable specification to grab relevant texts and query
                num_excerpts = gpt_analyzer.get_num_excerpts(num_pages)
                policy_info = extract_policy_doc_info(
                    gpt_analyzer,
                    pdf_text_chunks_w_embs,
                    char_count,
                    var_embeddings,
                    num_excerpts,
                    openai_apikey,
                    gpt_model
                )
                # 4) Output Results
                output_results(gpt_analyzer, output_doc, output_pdf_path, policy_info)
            print_milestone(
                "Done", country_start_time, {"Number of pages in PDF": num_pages_in_pdf}
            )
        except Exception as e:
            try:
                output_metrics(
                    output_doc,
                    len(gpt_analyzer.pdfs),
                    time.time() - total_start_time,
                    total_num_pages,
                    failed_pdfs,
                )
            except Exception as e2:
                print("Error in output_metrics:", e2)
            return total_num_pages, output_doc, e

    output_metrics(
        output_doc,
        len(gpt_analyzer.pdfs),
        time.time() - total_start_time,
        total_num_pages,
        failed_pdfs,
    )
    buffer = io.BytesIO()
    output_doc.save(buffer)
    buffer.seek(0)
    output_file_contents = buffer.read()
    #email_results(output_file_contents, gpt_analyzer.email)
    buffer.seek(0)
    output_file_contents = buffer.read()
    display_output(output_file_contents)
    return total_num_pages, output_doc, None

def log_error(e, gpt_analyzer):
    st.error(f"Error processing PDFs: {e}")
    partial_email = "unknown_email"
    msg = f"{e}\n{traceback.format_exc()}\n"
    if gpt_analyzer:
        partial_email = gpt_analyzer.email[:5] + "*"*len(gpt_analyzer.email[5:])
        msg = msg + f"ERROR --> {gpt_analyzer}\n"
    st.error(f"Error generating output document: {e}")
    log(
        f"{partial_email}: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} GMT \n {msg}"
    )

if __name__ == "__main__":
    try:
        with TemporaryDirectory() as temp_dir:
            logo_path = os.path.join(os.path.dirname(__file__), "public", "logo2.jpg")
            st.set_page_config(
                layout="wide", page_title="AI Policy Reader", page_icon=logo_path
            )
            load_header()
            _, centered_div, _ = st.columns([1, 6, 1])
            with centered_div:
                tab1, tab2, tab3 = st.tabs(["Tool", "About", "FAQ"])
                with tab1:
                    build_interface(temp_dir)
                    if st.button("Run", disabled=st.session_state.get("run_disabled", False)):
                        gpt_analyzer = get_user_inputs()
                        try:
                            with st.spinner("Generating output document..."):
                                apikey_id = "openai_apikey"
                                if "apikey_id" in st.session_state:
                                    apikey_id = st.session_state["apikey_id"]
                                openai_apikey = get_secret(apikey_id)
                                num_pages, output_doc, e = main(gpt_analyzer, openai_apikey)
                                if e is not None:
                                    log_error(e, gpt_analyzer)
                                    sys.exit(1)
                                partial_email = gpt_analyzer.email[:5] + "*"*len(gpt_analyzer.email[5:])
                                log(
                                    f"{partial_email}: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} GMT \n {gpt_analyzer}"
                                )
                            st.success("Document generated!")
                            os.unlink(st.session_state["temp_zip_path"])
                        except Exception as e:
                            log_error(e, gpt_analyzer)
                with tab2:
                    about_tab()
                with tab3:
                    FAQ()
    except Exception as e:
        a = None
        if gpt_analyzer:
            a = gpt_analyzer
        log_error(e, gpt_analyzer)
