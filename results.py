from datetime import datetime
from docx.shared import Pt
import os
import pandas as pd

def get_output_fname(path_fxn, filetype="docx"):
    return path_fxn(f"results.{filetype}")

# rows_dict: {row_id: {"col_name": val, ...}}
def create_word_table(doc, pdf_path, rows_dict, output_headers):
    fname = os.path.basename(pdf_path)
    doc.add_heading(f"{fname}", 2)
    num_rows = len(rows_dict.keys())
    table = doc.add_table(rows=num_rows+2, cols=len(output_headers))
    for i in range(len(output_headers)):
        table.cell(0, i).text = output_headers[i]
        table.cell(0, i).paragraphs[0].runs[0].font.bold = True
    for row_i, row_key in enumerate(list(rows_dict.keys())):
        table.cell(row_i+1, 0).text = row_key
        row_dict = rows_dict[row_key]
        for col_i, col_nm in enumerate(output_headers[1:]):
            table.cell(row_i+1, col_i+1).text = str(row_dict[col_nm])

def get_manually_extracted_df():
    xlsx_path = f"manual_results.xlsx"
    sheet_name = 'Policies'
    return pd.read_excel(xlsx_path, sheet_name=sheet_name)

def format_output_doc(output_doc, gpt_analyzer):
    main_query, variable_specs = gpt_analyzer.main_query, gpt_analyzer.variable_specs
    title = output_doc.add_heading(level=0)
    title_run = title.add_run('Results: GPT Batch Policy Processor (beta)')
    title_run.font.size = Pt(24)  
    output_doc.add_heading(f"{datetime.today().strftime('%B %d, %Y')}", 1)
    output_doc.add_heading(f"Query info", 2)
    output_doc.add_paragraph("The following query is run for each of the column specifications listed below:")
    query_paragraph = output_doc.add_paragraph()
    query_text = main_query.replace("Text: {excerpts}", "")
    query_run = query_paragraph.add_run(query_text)
    query_run.italic = True
    schema_col_names = list(variable_specs.keys())
    num_schema_cols = len(schema_col_names)
    table = output_doc.add_table(rows=num_schema_cols+1, cols=3)
    table.style = 'Table Grid'
    table.cell(0, 0).text = "Variable name"
    table.cell(0, 0).paragraphs[0].runs[0].font.bold = True
    table.cell(0, 1).text = "Variable description (optional)"
    table.cell(0, 1).paragraphs[0].runs[0].font.bold = True
    table.cell(0, 2).text = "Context (optional)"
    table.cell(0, 2).paragraphs[0].runs[0].font.bold = True
    try:
        for col_i in range(num_schema_cols):
            col_name = schema_col_names[col_i]
            if len(col_name) > 0:
                table.cell(col_i+1, 0).text = col_name
                if "column_description" in variable_specs[col_name]:
                    descr = variable_specs[col_name]["column_description"]
                    table.cell(col_i+1, 1).text = descr
                if "context" in variable_specs[col_name]:
                    if len(variable_specs[col_name]["context"])>0:
                        context = f"Context: {variable_specs[col_name]['context']}"
                        table.cell(col_i+1, 2).text = context
    except Exception as e:
        print(f"Error (format_output_doc()): {e}")

def output_results(gpt_analyzer, output_doc, pdf_path, policy_info):
    rows_dict = gpt_analyzer.get_results(policy_info)
    output_headers = gpt_analyzer.get_output_headers()
    create_word_table(output_doc, pdf_path, rows_dict, output_headers)

def output_metrics(doc, num_docs, t, num_pages, failed_pdfs):
    doc.add_heading(f"{num_docs} documents ({num_pages} total pages) processed in {t:.2f} seconds", 4)
    if len(failed_pdfs) > 0:
        doc.add_heading(f"Unable to process the following PDFs: {failed_pdfs}", 4)