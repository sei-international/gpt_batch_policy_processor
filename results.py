from datetime import datetime
from docx.shared import Pt
import os
import pandas as pd

def get_output_fname(path_fxn, filetype="docx"):
    return path_fxn(f"results.{filetype}")

def create_word_table(doc, pdf_path, col_names, gpt_row, output_headers, manual_row=None):
    numcols, gpt_col_num = 2, 1
    if manual_row:
        numcols, gpt_col_num = 3, 2
    fname = os.path.basename(pdf_path)
    doc.add_heading(f"{fname}", 2)
    num_cols = len(col_names)
    table = doc.add_table(rows=num_cols+2, cols=numcols)
    table.cell(0, 0).text = output_headers[0]
    table.cell(0, 0).paragraphs[0].runs[0].font.bold = True
    table.cell(0, gpt_col_num).text = output_headers[1]
    table.cell(0, gpt_col_num).paragraphs[0].runs[0].font.bold = True
    if manual_row:
        table.cell(0, 1).text = "Manually Extracted"
        table.cell(0, 1).paragraphs[0].runs[0].font.bold = True
    for col_i in range(num_cols):
        table.cell(col_i+1, 0).text = col_names[col_i]
        if manual_row:
            table.cell(col_i+1, 1).text = str(manual_row[col_i]) if not pd.isna(manual_row[col_i]) else ""
        if col_i < len(gpt_row):
            table.cell(col_i+1, gpt_col_num).text = str(gpt_row[col_i])

def get_manually_extracted_df():
    xlsx_path = f"manual_results.xlsx"
    sheet_name = 'Policies'
    return pd.read_excel(xlsx_path, sheet_name=sheet_name)

def get_manually_extracted_row(country, pdf_path, col_names, df):
    pass
    """tmp_doc_codes = os.path.basename(pdf_path).split("-")
    doc_code = f"{tmp_doc_codes[0]}-{tmp_doc_codes[1]}"
    row = df[(df['Country '] == country) & (df['Document Code'] == doc_code)].iloc[0]
    manually_extracted_row = []
    for col_name in col_names:
        if col_name == "Policy Date":
            d, m, y = row["Policy date day (if applicable)"], row["Policy date month (if applicable)"], row["Policy date year"]
            manually_extracted_datum = f"{d}/{m}/{y}" if not pd.isna(d) else f"{m}/{y}" if pd.isna(m) else f"{y}"
        elif col_name == "Scenario":
            manually_extracted_datum = f"{row['Name of Scenario']}: {row['choice of scenario_reason']}"
        else:
            manually_extracted_datum = row[col_name] if not pd.isna(row[col_name]) else ""
        manually_extracted_row.append(manually_extracted_datum)
    return manually_extracted_row"""

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
    row_ids, rows = gpt_analyzer.get_results(policy_info)
    output_headers = gpt_analyzer.get_output_headers()
    create_word_table(output_doc, pdf_path, row_ids, rows, output_headers)

def output_metrics(doc, num_docs, t, num_pages):
    doc.add_heading(f"{num_docs} documents ({num_pages} total pages) processed in {t:.2f} seconds", 4)