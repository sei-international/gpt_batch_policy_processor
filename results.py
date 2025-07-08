from datetime import datetime
from docx.shared import Pt
import os
import pandas as pd


def get_output_fname(path_fxn, filetype="xlsx"):
    return path_fxn(f"results.{filetype}")

#var_spec = {var_name: {var_descr: .., context: ...}, var_name2: ...}
def format_output_doc(output_doc, gpt_analyzer):
    try:
        main_query, variable_specs = gpt_analyzer.main_query, gpt_analyzer.variable_specs
        ws1 = output_doc.active
        ws1.title = "Query"
        ws1.append(["Main query template:"])
        ws1.append([main_query])
        ws2 = output_doc.create_sheet(title="Variables")
        headers = ["variable_name", "variable_description", "context"]
        ws2.append(headers)   
        for var_name, var_spec in variable_specs.items():
            row = [var_name]
            for header in [h for h in headers if h != "variable_name"]:
                if header in var_spec:
                    row.append(var_spec[header])
            ws2.append(row)
    except Exception as e:
        print(f"Error (format_output_doc()): {e}")

def add_row(row_key, output_headers, row_dict, ws, i=None):
    row = [row_key]
    for col_nm in output_headers[1:]:
        if col_nm in row_dict:                   
            cell = row_dict[col_nm]
            if i!= None: 
                if not isinstance(row_dict[col_nm], list):
                    if i == 0:
                        cell = row_dict[col_nm]
                    else:
                        cell = ""
                else:
                    cell = row_dict[col_nm][i]
            row.append(cell)
    ws.append(row)

#policy_info = {var_name: {resp: .., any_other_col: ...}, var_name2: ...}
def output_results(gpt_analyzer, output_doc, output_pdf_path, policy_info):
    rows_dict = gpt_analyzer.get_results(policy_info)
    output_headers = gpt_analyzer.get_output_headers()
    fname = os.path.basename(output_pdf_path)
    ws = output_doc.create_sheet(title=fname[:31])
    ws.append(output_headers)
    for row_key, row_dict in rows_dict.items():
        if isinstance(row_dict[output_headers[1]], list):
            for i in range(len(row_dict[output_headers[1]])):
                add_row(row_key, output_headers, row_dict, ws, i)
        else:
            add_row(row_key, output_headers, row_dict, ws)


# Function to output metrics to a Word document. It adds one line at the end of the file.
# doc: The Word document object
# num_docs: Number of documents processed
# t: Time taken to process the documents
# num_pages: Total number of pages processed
# failed_pdfs: List of PDFs that failed to process
def output_metrics(doc, num_docs, t, num_pages, failed_pdfs):
    ws = doc.create_sheet("metrics")
    t = f"{num_docs} documents ({num_pages} total pages) processed in {t:.2f} seconds"
    ws.append([t])
    if len(failed_pdfs) > 0:
        f = f"Unable to process the following PDFs: {failed_pdfs}"
        ws.append([f])
