"""
OpenAI Batch API path for processing large document collections.

The synchronous path in main.py sends every (document, variable) query as a live request
and waits. This module sends the same requests through OpenAI's Batch API instead: they
are queued and returned within 24 hours at half the per-token price. All the local work
(PDF parsing, embedding, excerpt selection, prompt construction) is identical -- only the
delivery mechanism differs, so batch results should match live results.

The flow is split in two because a batch cannot be waited on inside a web request:

  1) submit_batch_job()  -- does the local work, uploads the requests, records the batch
                            id and everything needed to assemble output on the job record.
  2) finalize_batch_job() -- called later (by polling), downloads the completed results
                            and builds the same spreadsheet the synchronous path builds.

Step 2 deliberately depends only on data persisted in the job file, never on in-memory
state or the original PDFs, so a completed batch can still be assembled after the web app
has restarted.
"""

from analysis import get_analyzer
from job_manager import get_job_manager
from query_gpt import build_variable_messages, build_request_body, new_openai_session
from read_pdf import extract_text_chunks_from_pdf
from relevant_excerpts import (
    generate_all_embeddings,
    embed_variable_specifications,
    select_text_chunks,
)
from results import format_output_doc, output_results, output_metrics
from openpyxl import Workbook
import io
import json
import traceback

BATCH_ENDPOINT = "/v1/chat/completions"
COMPLETION_WINDOW = "24h"

# Batch statuses that mean "no further progress will happen".
TERMINAL_BATCH_STATUSES = {"completed", "failed", "expired", "cancelled"}


def analyzer_to_config(gpt_analyzer):
    """
    Serializes the parts of a GPTAnalyzer needed to rebuild it at finalize time.

    The analyzer itself holds no state beyond these fields, and the PDFs are not needed
    once the excerpts are baked into the batch requests.
    """
    return {
        "task_type": gpt_analyzer.label,
        "output_fmt": gpt_analyzer.output_fmt,
        "main_query": gpt_analyzer.main_query,
        "variable_specs": gpt_analyzer.variable_specs,
        "email": gpt_analyzer.email,
        "additional_info": gpt_analyzer.additional_info,
        "gpt_model": gpt_analyzer.gpt_model,
        "pdfs": list(gpt_analyzer.pdfs),
    }


def analyzer_from_config(config):
    """Rebuilds a GPTAnalyzer from analyzer_to_config() output."""
    return get_analyzer(
        config["task_type"],
        config["output_fmt"],
        config["pdfs"],
        config["main_query"],
        config["variable_specs"],
        config["email"],
        config["additional_info"],
        config["gpt_model"],
    )


def build_batch_requests(gpt_analyzer, openai_apikey, job_id=None):
    """
    Runs all local processing and returns the batch requests plus a manifest.

    Returns:
        requests: list of Batch API request dicts
        manifest: custom_id -> {"doc_key": ..., "var_name": ...}, used to reassemble
                  responses into the output spreadsheet
        stats: dict with page counts and any documents that failed locally
    """
    job_manager = get_job_manager() if job_id else None
    gpt_model = gpt_analyzer.get_gpt_model()
    openai_client, max_num_chars = new_openai_session(openai_apikey, gpt_model)

    requests = []
    manifest = {}
    doc_order = []
    failed_pdfs = []
    total_num_pages = 0

    for pdf_idx, pdf in enumerate(gpt_analyzer.pdfs, 1):
        pdf_path = f"{pdf.replace('.pdf', '')}.pdf"
        try:
            if job_manager:
                job_manager.update_progress(
                    job_id,
                    message=f"Preparing PDF {pdf_idx}/{len(gpt_analyzer.pdfs)}",
                    current_pdf=pdf_idx,
                    total_pdfs=len(gpt_analyzer.pdfs),
                )

            text_chunk_size = gpt_analyzer.get_chunk_size()
            _, text_sections = extract_text_chunks_from_pdf(pdf_path, text_chunk_size)
            if "error" in text_sections[0]:
                failed_pdfs.append(pdf)
                print(f"Failed: {pdf} with {text_sections[0]['error']}")
                continue

            num_sections = len(text_sections)
            for text_section in text_sections:
                text_chunks, num_pages, char_count, section = [
                    text_section[k]
                    for k in ["text_chunks", "num_pages", "num_chars", "section_num"]
                ]
                if num_sections > 1:
                    doc_key = f"{pdf_path} ({section} of {num_sections})"
                else:
                    doc_key = pdf_path
                total_num_pages += num_pages
                doc_order.append(doc_key)

                pdf_text_chunks_w_embs = generate_all_embeddings(
                    openai_client, doc_key, text_chunks, lambda p: p, text_chunk_size
                )
                var_embeddings = embed_variable_specifications(
                    openai_client, gpt_analyzer.variable_specs
                )
                num_excerpts = gpt_analyzer.get_num_excerpts(num_pages)
                run_on_full_text = char_count < (max_num_chars - 1000)

                for var_name in var_embeddings:
                    var_embedding, var_desc, context = (
                        var_embeddings[var_name]["embedding"],
                        var_embeddings[var_name]["variable_description"],
                        var_embeddings[var_name]["context"],
                    )
                    excerpts = select_text_chunks(
                        gpt_analyzer,
                        pdf_text_chunks_w_embs,
                        var_embedding,
                        var_name,
                        num_excerpts,
                        run_on_full_text,
                    )
                    messages = build_variable_messages(
                        gpt_analyzer,
                        var_name,
                        var_desc,
                        context,
                        excerpts,
                        run_on_full_text,
                    )
                    # custom_id is capped at 64 chars by the API, so use a positional id
                    # and keep the real mapping in the manifest.
                    custom_id = f"r{len(requests)}"
                    requests.append(
                        {
                            "custom_id": custom_id,
                            "method": "POST",
                            "url": BATCH_ENDPOINT,
                            "body": build_request_body(
                                gpt_model, gpt_analyzer.resp_format_type(), messages
                            ),
                        }
                    )
                    manifest[custom_id] = {"doc_key": doc_key, "var_name": var_name}
        except Exception as e:
            failed_pdfs.append(pdf)
            print(f"Failed: {pdf} with {e}")
            traceback.print_exc()
            continue

    stats = {
        "total_num_pages": total_num_pages,
        "failed_pdfs": failed_pdfs,
        "doc_order": doc_order,
    }
    return requests, manifest, stats


def submit_batch_job(gpt_analyzer, openai_apikey, job_id):
    """
    Prepares and submits a batch, then returns immediately.

    The job is left in RUNNING state; finalize_batch_job() completes it once OpenAI
    finishes processing.
    """
    job_manager = get_job_manager()
    job_manager.update_progress(
        job_id,
        message="Preparing documents for batch submission...",
        total_pdfs=len(gpt_analyzer.pdfs),
    )

    requests, manifest, stats = build_batch_requests(
        gpt_analyzer, openai_apikey, job_id
    )

    if not requests:
        raise RuntimeError(
            "No batch requests could be built -- every document failed to process. "
            f"Failed: {', '.join(str(p) for p in stats['failed_pdfs'])}"
        )

    job_manager.update_progress(
        job_id, message=f"Uploading {len(requests)} requests to OpenAI Batch API..."
    )

    client, _ = new_openai_session(openai_apikey, gpt_analyzer.get_gpt_model())
    jsonl = "\n".join(json.dumps(r) for r in requests).encode("utf-8")
    upload = client.files.create(
        file=("batch_requests.jsonl", jsonl), purpose="batch"
    )
    batch = client.batches.create(
        input_file_id=upload.id,
        endpoint=BATCH_ENDPOINT,
        completion_window=COMPLETION_WINDOW,
        metadata={"job_id": job_id},
    )

    job_manager.update_job(
        job_id,
        {
            "mode": "batch",
            "batch_id": batch.id,
            "batch_status": batch.status,
            "batch_manifest": manifest,
            "analyzer_config": analyzer_to_config(gpt_analyzer),
            "batch_stats": stats,
        },
    )
    job_manager.update_progress(
        job_id,
        message=(
            f"Batch submitted ({len(requests)} requests). Results are typically ready "
            "within a few hours and are guaranteed within 24 hours."
        ),
    )
    return batch.id


def check_batch_job(job_id, openai_apikey):
    """
    Polls the batch once and finalizes it if it has completed.

    Returns:
        dict: the refreshed job record
    """
    job_manager = get_job_manager()
    job_data = job_manager.get_job(job_id)
    if not job_data or not job_data.get("batch_id"):
        return job_data

    client, _ = new_openai_session(openai_apikey)
    batch = client.batches.retrieve(job_data["batch_id"])
    job_manager.update_job(job_id, {"batch_status": batch.status})

    counts = getattr(batch, "request_counts", None)
    if counts is not None:
        completed = getattr(counts, "completed", 0) or 0
        total = getattr(counts, "total", 0) or 0
        job_manager.update_progress(
            job_id,
            message=f"Batch {batch.status}: {completed}/{total} requests complete",
        )

    if batch.status == "completed":
        finalize_batch_job(job_id, openai_apikey)
    elif batch.status in TERMINAL_BATCH_STATUSES:
        job_manager.mark_failed(
            job_id, f"Batch ended with status '{batch.status}'."
        )

    return job_manager.get_job(job_id)


def parse_batch_output(raw_text):
    """Parses batch output JSONL into custom_id -> response content (or None on error)."""
    responses = {}
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        custom_id = record.get("custom_id")
        if record.get("error"):
            print(f"Batch request {custom_id} errored: {record['error']}")
            responses[custom_id] = None
            continue
        try:
            body = record["response"]["body"]
            responses[custom_id] = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            print(f"Malformed batch response for {custom_id}: {e}")
            responses[custom_id] = None
    return responses


def finalize_batch_job(job_id, openai_apikey):
    """
    Downloads a completed batch and assembles the output spreadsheet.

    Rebuilds the analyzer from the persisted config rather than any in-memory object, so
    this works even if the app restarted between submission and completion.
    """
    from interface import email_results

    job_manager = get_job_manager()
    job_data = job_manager.get_job(job_id)
    client, _ = new_openai_session(openai_apikey)
    batch = client.batches.retrieve(job_data["batch_id"])

    if not batch.output_file_id:
        job_manager.mark_failed(job_id, "Batch completed but produced no output file.")
        return

    job_manager.update_progress(job_id, message="Downloading batch results...")
    raw_text = client.files.content(batch.output_file_id).text
    responses = parse_batch_output(raw_text)

    gpt_analyzer = analyzer_from_config(job_data["analyzer_config"])
    manifest = job_data["batch_manifest"]
    stats = job_data.get("batch_stats", {})

    # Regroup flat responses back into {doc_key: {var_name: parsed_response}}.
    by_doc = {}
    failed_requests = 0
    for custom_id, meta in manifest.items():
        content = responses.get(custom_id)
        if content is None:
            failed_requests += 1
            continue
        try:
            parsed = gpt_analyzer.format_gpt_response(content)
        except Exception as e:
            print(f"Could not parse response for {custom_id}: {e}")
            failed_requests += 1
            continue
        by_doc.setdefault(meta["doc_key"], {})[meta["var_name"]] = parsed

    output_doc = Workbook()
    format_output_doc(output_doc, gpt_analyzer)
    # Preserve the original document order rather than dict insertion order.
    for doc_key in stats.get("doc_order", list(by_doc)):
        if doc_key in by_doc:
            output_results(gpt_analyzer, output_doc, doc_key, by_doc[doc_key])

    output_metrics(
        output_doc,
        len(stats.get("doc_order", [])),
        0,
        stats.get("total_num_pages", 0),
        stats.get("failed_pdfs", []),
    )

    buffer = io.BytesIO()
    output_doc.save(buffer)
    buffer.seek(0)
    output_file_contents = buffer.read()

    job_manager.update_progress(job_id, message="Emailing results...")
    email_results(output_file_contents, gpt_analyzer.email)

    job_manager.mark_completed(
        job_id,
        {
            "total_num_pages": stats.get("total_num_pages", 0),
            "output_file_size_mb": round(len(output_file_contents) / (1024 * 1024), 2),
            "num_pdfs": len(stats.get("doc_order", [])),
            "failed_pdfs": stats.get("failed_pdfs", []),
            "failed_requests": failed_requests,
            "email_sent_to": gpt_analyzer.email,
            "mode": "batch",
        },
    )
