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
Run "python -m streamlit run main.py" to start the Streamlit application.
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
from job_manager import get_job_manager, run_job_async, get_job_status, JobStatus
from openpyxl import Workbook
from tempfile import TemporaryDirectory, mkdtemp
import io
import json
import os
import requests
import shutil
import streamlit as st
import sys
import threading
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
    gpt_model,
    job_id=None,
    current_pdf_idx=None
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
        job_id: Optional job ID for progress tracking.
        current_pdf_idx: Current PDF index for progress tracking.

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

    total_vars = len(var_embeddings)
    for var_idx, var_name in enumerate(var_embeddings, 1):
        # Update progress if job_id is provided
        if job_id:
            job_manager = get_job_manager()
            job_manager.update_progress(
                job_id,
                message=f"Processing variable '{var_name}' ({var_idx}/{total_vars})",
                current_variable=var_idx,
                total_variables=total_vars
            )

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
                gpt_analyzer.gpt_model
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


def main(gpt_analyzer, openai_apikey, job_id=None):
    """
    Main function to process PDFs and generate an output document.

    Args:
        gpt_analyzer: The GPT analyzer object.
        openai_apikey: API key for OpenAI.
        job_id: Optional job ID for progress tracking.

    Returns:
        The total number of pages processed.
    """
    # Initialize progress tracking
    if job_id:
        job_manager = get_job_manager()
        job_manager.update_progress(
            job_id,
            message="Initializing document processing...",
            total_pdfs=len(gpt_analyzer.pdfs),
            current_pdf=0
        )

    output_doc = Workbook()
    format_output_doc(output_doc, gpt_analyzer)
    total_num_pages = 0
    total_start_time = time.time()
    failed_pdfs = []
    gpt_model = gpt_analyzer.get_gpt_model()

    for pdf_idx, pdf in enumerate(gpt_analyzer.pdfs, 1):
        if not isinstance(gpt_analyzer.pdfs, (list, tuple)):
            st.warning(f"Expected gpt_analyzer.pdfs to be a list; got {type(gpt_analyzer.pdfs)}. Coercing to list.")
            gpt_analyzer.pdfs = [gpt_analyzer.pdfs]
        pdf_path = get_resource_path(f"{pdf.replace('.pdf','')}.pdf")
        try:
            # Update progress for current PDF
            if job_id:
                job_manager.update_progress(
                    job_id,
                    message=f"Processing PDF {pdf_idx}/{len(gpt_analyzer.pdfs)}: {os.path.basename(pdf_path)}",
                    current_pdf=pdf_idx
                )

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
            # Most PDFs will only have 1 text_section: this is used to break up long documents (>250 pages)            
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
                try:
                    policy_info = extract_policy_doc_info(
                        gpt_analyzer,
                        pdf_text_chunks_w_embs,
                        char_count,
                        var_embeddings,
                        num_excerpts,
                        openai_apikey,
                        gpt_model,
                        job_id=job_id,
                        current_pdf_idx=pdf_idx
                    )
                except Exception as e:
                    print(f"[DEBUG] Failure inside extract_policy_doc_info for pdf {pdf}: {e}")
                    traceback.print_exc()
                    print(f"[DEBUG] var_embeddings keys: {list(var_embeddings.keys()) if isinstance(var_embeddings, dict) else repr(var_embeddings)}")
                    print(f"[DEBUG] pdf_text_chunks_w_embs sample: {pdf_text_chunks_w_embs[:3] if hasattr(pdf_text_chunks_w_embs, '__len__') else repr(pdf_text_chunks_w_embs)}")
                    raise
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
            # Raise the exception so job_manager marks it as failed
            raise e

    output_metrics(
        output_doc,
        len(gpt_analyzer.pdfs),
        time.time() - total_start_time,
        total_num_pages,
        failed_pdfs,
    )

    # Update progress - finalizing
    if job_id:
        job_manager.update_progress(
            job_id,
            message="Finalizing output document and sending email..."
        )

    buffer = io.BytesIO()
    output_doc.save(buffer)
    buffer.seek(0)
    output_file_contents = buffer.read()

    # Calculate file size for result
    file_size_mb = len(output_file_contents) / (1024 * 1024)

    # Email results - this handles splitting if needed
    email_results(output_file_contents, gpt_analyzer.email)

    buffer.seek(0)
    output_file_contents = buffer.read()

    # Store result for job completion
    result = {
        "total_num_pages": total_num_pages,
        "output_file_size_mb": round(file_size_mb, 2),
        "num_pdfs": len(gpt_analyzer.pdfs),
        "failed_pdfs": failed_pdfs,
        "email_sent_to": gpt_analyzer.email
    }

    # Only display output if not running async (no job_id means synchronous)
    if not job_id:
        display_output(output_file_contents)

    # Return JSON-serializable result for job manager
    return result

def cleanup_temp_dir(temp_dir_path, max_retries=3, delay=1):
    """
    Safely cleanup temp directory with retry logic for Windows file locking issues.

    Args:
        temp_dir_path: Path to temporary directory to clean up
        max_retries: Number of times to retry deletion
        delay: Delay in seconds between retries
    """
    if not temp_dir_path or not os.path.exists(temp_dir_path):
        return

    for attempt in range(max_retries):
        try:
            shutil.rmtree(temp_dir_path, ignore_errors=False)
            print(f"Successfully cleaned up temp directory: {temp_dir_path}")
            return
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"Cleanup attempt {attempt + 1} failed, retrying in {delay}s: {e}")
                time.sleep(delay)
            else:
                print(f"Failed to cleanup temp directory after {max_retries} attempts: {e}")
                # Use ignore_errors as last resort
                shutil.rmtree(temp_dir_path, ignore_errors=True)


def log_error(e, gpt_analyzer):
    st.error(f"Error processing PDFs: {e}")
    partial_email = "unknown_email"
    msg = f"{e}\n{traceback.format_exc()}\n"
    if gpt_analyzer:
        partial_email = gpt_analyzer.email[:5] + "*"*len(gpt_analyzer.email[5:])
        msg = msg + f"ERROR: {e} --> {gpt_analyzer}\n"
    st.error(f"Error generating output document: {e}")
    log(
        f"{partial_email}: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} GMT \n {msg}"
    )

if __name__ == "__main__":
    gpt_analyzer = None
    try:
        # Initialize temp_dir in session state to persist across reruns
        # This prevents the temp directory from being deleted while background jobs are running
        if "temp_dir" not in st.session_state:
            st.session_state["temp_dir"] = mkdtemp(prefix="pdf_processor_")

        temp_dir = st.session_state["temp_dir"]

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

                # Job lookup section at the top
                with st.expander("🔍 Check Job Status by ID or Email", expanded=False):
                    st.markdown("**Lost your job? Look it up here:**")

                    lookup_method = st.radio("Search by:", ["Job ID", "Email"], horizontal=True)

                    if lookup_method == "Job ID":
                        lookup_job_id = st.text_input("Enter Job ID:", placeholder="e.g., 550e8400-e29b-41d4-a716-446655440000")
                        if st.button("Load Job", key="load_by_id"):
                            if lookup_job_id:
                                job_data = get_job_status(lookup_job_id)
                                if job_data:
                                    st.session_state["active_job_id"] = lookup_job_id
                                    st.success(f"✓ Job found! Status: {job_data.get('status')}")
                                    st.rerun()
                                else:
                                    st.error("❌ Job not found. Check your Job ID.")
                            else:
                                st.warning("Please enter a Job ID")

                    else:  # Email search
                        lookup_email = st.text_input("Enter Email:", placeholder="your@email.com")
                        if st.button("Search Jobs", key="search_by_email"):
                            if lookup_email:
                                job_manager = get_job_manager()
                                jobs = job_manager.find_jobs_by_email(lookup_email)
                                if jobs:
                                    st.success(f"Found {len(jobs)} job(s)")
                                    for job in jobs[:5]:  # Show max 5 recent jobs
                                        col1, col2, col3 = st.columns([3, 2, 1])
                                        with col1:
                                            st.text(f"Job: {job['job_id'][:8]}...")
                                        with col2:
                                            st.text(f"Status: {job['status']}")
                                        with col3:
                                            if st.button("Load", key=f"load_{job['job_id']}"):
                                                st.session_state["active_job_id"] = job['job_id']
                                                st.rerun()
                                else:
                                    st.error("❌ No jobs found for this email")
                            else:
                                st.warning("Please enter an email")

                # Check if we have an active job and show status
                if "active_job_id" in st.session_state and st.session_state["active_job_id"]:
                    job_id = st.session_state["active_job_id"]
                    job_status_data = get_job_status(job_id)

                    if job_status_data:
                        # Display Job ID prominently
                        st.info(f"**Your Job ID:** `{job_id}`")
                        st.caption("💡 Copy this ID to check your job status later if you close this tab")

                        status = job_status_data.get("status")
                        progress = job_status_data.get("progress", {})

                        if status == JobStatus.RUNNING or status == JobStatus.PENDING:
                            # Show progress
                            st.info(f"**Job Status:** {status.upper()}")
                            st.write(f"**Progress:** {progress.get('message', 'Processing...')}")

                            # Show progress bars if we have the data
                            if progress.get("total_pdfs", 0) > 0:
                                pdf_progress = progress.get("current_pdf", 0) / progress.get("total_pdfs", 1)
                                st.progress(pdf_progress, text=f"PDFs: {progress.get('current_pdf', 0)}/{progress.get('total_pdfs', 0)}")

                            if progress.get("total_variables", 0) > 0:
                                var_progress = progress.get("current_variable", 0) / progress.get("total_variables", 1)
                                st.progress(var_progress, text=f"Variables: {progress.get('current_variable', 0)}/{progress.get('total_variables', 0)}")

                            # Auto-refresh every 2 seconds
                            time.sleep(2)
                            st.rerun()

                        elif status == JobStatus.COMPLETED:
                            st.success("✅ Processing complete! Results have been emailed to you.")
                            result = job_status_data.get("result", {})
                            if result:
                                st.write(f"**Total pages processed:** {result.get('total_num_pages', 'N/A')}")
                                st.write(f"**Documents processed:** {result.get('num_pdfs', 'N/A')}")

                                # Show file size info
                                file_size = result.get('output_file_size_mb', 0)
                                if file_size > 25:
                                    st.info(f"📧 **Result file size:** {file_size} MB (large file - you may receive multiple emails)")
                                else:
                                    st.write(f"**Result file size:** {file_size} MB")

                                st.write(f"**Email sent to:** {result.get('email_sent_to', 'N/A')}")

                                if result.get('failed_pdfs'):
                                    st.warning(f"**Failed PDFs:** {', '.join(result['failed_pdfs'])}")

                            # Keep job active to prevent "Run" button from showing
                            # Only clear when user clicks "Process Another Batch"
                            if st.button("Process Another Batch"):
                                # Clean up old temp directory before starting new batch
                                if "temp_dir" in st.session_state:
                                    old_temp_dir = st.session_state["temp_dir"]
                                    st.session_state["temp_dir"] = mkdtemp(prefix="pdf_processor_")
                                    # Cleanup old directory in background
                                    threading.Thread(target=cleanup_temp_dir, args=(old_temp_dir,), daemon=True).start()
                                # Clear the job so user can start a new one
                                st.session_state["active_job_id"] = None
                                st.rerun()

                        elif status == JobStatus.FAILED:
                            st.error("❌ Processing failed. Please check the error below:")
                            st.code(job_status_data.get("error", "Unknown error"))

                            # Keep job active to prevent "Run" button from showing
                            # Only clear when user clicks "Try Again"
                            if st.button("Try Again"):
                                # Clean up old temp directory before trying again
                                if "temp_dir" in st.session_state:
                                    old_temp_dir = st.session_state["temp_dir"]
                                    st.session_state["temp_dir"] = mkdtemp(prefix="pdf_processor_")
                                    # Cleanup old directory in background
                                    threading.Thread(target=cleanup_temp_dir, args=(old_temp_dir,), daemon=True).start()
                                # Clear the job so user can start a new one
                                st.session_state["active_job_id"] = None
                                st.rerun()

                # Show run button only if no active job
                if not st.session_state.get("active_job_id"):
                    if st.button("Run", disabled=st.session_state.get("run_disabled", False)):
                        gpt_analyzer = get_user_inputs()
                        if gpt_analyzer:  # Ensure inputs are valid
                            try:
                                # Show immediate feedback
                                with st.spinner("Starting job..."):
                                    # Create a new job with user email
                                    job_manager = get_job_manager()
                                    job_id = job_manager.create_job(user_email=gpt_analyzer.email)
                                    st.session_state["active_job_id"] = job_id

                                    # Get API key
                                    apikey_id = "openai_apikey"
                                    if "apikey_id" in st.session_state:
                                        apikey_id = st.session_state["apikey_id"]
                                    openai_apikey = get_secret(apikey_id)

                                    # Start the job asynchronously
                                    run_job_async(
                                        job_id,
                                        main,
                                        args=(gpt_analyzer, openai_apikey, job_id)
                                    )

                                    # Log job start
                                    partial_email = gpt_analyzer.email[:5] + "*"*len(gpt_analyzer.email[5:])
                                    log(
                                        f"{partial_email}: {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} GMT \n {gpt_analyzer}"
                                    )

                                    # Clean up temp files
                                    if "temp_zip_path" in st.session_state:
                                        try:
                                            os.unlink(st.session_state["temp_zip_path"])
                                        except Exception:
                                            pass

                                # Rerun to show progress
                                st.rerun()

                            except Exception as e:
                                log_error(e, gpt_analyzer)
                                if "active_job_id" in st.session_state:
                                    del st.session_state["active_job_id"]
                with tab2:
                    about_tab()
                with tab3:
                    FAQ()
    except Exception as e:
        a = None
        if gpt_analyzer:
            a = gpt_analyzer
        log_error(e, gpt_analyzer)
