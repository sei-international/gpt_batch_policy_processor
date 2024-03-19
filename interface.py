from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
from tempfile import NamedTemporaryFile, TemporaryDirectory
import base64
import pandas as pd
import streamlit as st

def load_text():
    st.title("GPT Batch Policy Processor (beta)")
    instructions = """
This tool allows users to bulk process collections of policy documents using Large Language Models like ChatGPT.

## How to use
Reading through each uploaded policy document, this tool will ask ChatGPT the main query template for each data 'column' specified below. 
- **Step 1:** Upload a zipfile of PDF's (policy documents). Please start with 2-4 documents before running in bulk (no subfolders allowed).
- **Step 2:** Specify a main query template. For each PDF, we will use this query template to request each particular piece of information specified in the table in step 3.
- **Step 3:** Specify each particular piece of information you are looking to extract from each policy document.

## Example: main query template
*From the following text excerpts, list any references to “{column_name}” which we define as “{column_description}”. 
Only include direct quotation with the corresponding page number(s) (seen in square brackets at the end of each excerpt) 
with a brief explanation of the context of this quote within the text. It is very important not to hallucinate.*

Please note curley brackets indicate keywords. *{column_name}* and *{column_description}* will be replaced by each 
of specification listed in the table below (i.e. [SDG1: End poverty in all its forms everywhere, SDG2: ...]). 
This query will be run iteratively for each document and for each data column.
Do not include any single quotation marks or apostraphes.

## Submit your processing request"""
    st.markdown(instructions)

def upload_zip():
    uploaded_zip = st.file_uploader("Upload zipfile of PDF's", type="zip")
    if uploaded_zip is not None:
        st.session_state['uploaded_zip'] = uploaded_zip
        st.success("File uploaded successfully!")
        
def input_main_query():
    st.session_state["main_query_input"] = st.text_area("Input main query template")

def input_email():
    st.session_state["email"] = st.text_input("Enter your email where you'd like to recieve the results:")

# Function to pre-populate the DataFrame with a template for 15 rows
def populate_with_SDGs():
    st.session_state["SDGs"] = [f"SDG {i+1}" for i in range(17)]
    st.session_state["SDG_defs"] = ["" for i in range(17)]
    st.session_state['num_rows'] = len(st.session_state["SDGs"])

def input_data_specs():
    tab1, tab2 = st.tabs(["Manual Entry", "Paste Table"])
    with tab1:
        st.session_state.tab_selection = 'manual_row_input'
        col1_label, col2_label = st.columns(2)
        with col1_label:
            st.markdown("**Column name**")
        with col2_label:
            st.markdown("**Column description**")

        if 'num_rows' not in st.session_state:
            st.session_state['num_rows'] = 1  # Starting with 1 row
        for i in range(st.session_state['num_rows']):
            col1, col2 = st.columns(2)
            with col1:
                val = ""
                if "SDGs" in st.session_state:
                    val = st.session_state["SDGs"][i] if i < len(st.session_state["SDGs"]) else ""
                st.text_input("Column name", key=f"col1_{i}", value=val, label_visibility='hidden')
            with col2:
                st.text_input("Column description", key=f"col2_{i}", label_visibility='hidden')
        def add_row():
            st.session_state['num_rows'] += 1
        def remove_row():
            if st.session_state['num_rows'] > 1:
                st.session_state['num_rows'] -= 1
        col1, col2, _, col3 = st.columns([1, 1, 1, 1])
        with col1:
            st.button("Add Row", on_click=add_row)
        with col2:
            st.button("Remove Row", on_click=remove_row)
        with col3:
            st.button("Populate with SDGs", on_click=populate_with_SDGs)
    with tab2:
        st.session_state.tab_selection = 'paste_table' 
        st.session_state["schema_table"] = st.text_area("Paste your Excel data here:", height=300)
    
def process_table():
    input_format = st.session_state['schema_input_format']
    if input_format == 'manual_row_input':
        column_specs =  {}
        for i in range(st.session_state['num_rows']):
            # Access each row's inputs using the keys
            col_name = st.session_state[f"col1_{i}"]
            col_desc = st.session_state[f"col2_{i}"]
            # Append the row's data to a list, or process it as needed
            if len(col_name) > 0 and col_name != '':
                column_specs[col_name] = col_desc
        return column_specs
    else:
        user_input= st.session_state["schema_table"] 
        data = [line.split('\t') for line in user_input.split('\n')]
        df = pd.DataFrame(data, columns=["column_name", "column_description"]) 
        df['column_name'].replace('', pd.NA, inplace=True)
        df.dropna(subset=['column_name'], inplace=True)
        df = df[df['column_name'].notnull()]
        return df.set_index('column_name')['column_description'].to_dict()
    

def build_interface():
    load_text()
    if 'schema_input_format' not in st.session_state:
        st.session_state['schema_input_format'] = 'manual_row_input'
    upload_zip()
    input_main_query()
    input_data_specs()
    st.divider()
    input_email()

def email_results(docx_fname, recipient_email):
    message = Mail(
        from_email=st.secrets["email"],
        to_emails=recipient_email,
        subject='Results: GPT Batch Policy Processor (Beta)',
        html_content='Attached is the document you requested.')
    with open(docx_fname, 'rb') as f:
        file_data = f.read()
        f.close()
    encoded_file = base64.b64encode(file_data).decode()
    attachedFile = Attachment(
        FileContent(encoded_file),
        FileName('results.docx'),
        FileType('application/docx'),
        Disposition('attachment')
    )
    message.attachment = attachedFile
    try:
        sg = SendGridAPIClient(st.secrets["sendgrid_apikey"])
        response = sg.send(message)
        print(response.status_code)
    except Exception as e:
        print(e)
        print(e.message)

    # subject = "Results: GPT Batch POlicy Processor (Beta)"
    # body = "Please find attached the document you generated."
    # keyring.set_password("yagmail", st.secrets["email"], st.secrets["password"])
    # yag = yagmail.SMTP(user=st.secrets["email"], password=st.secrets["password"])
    # yag.send(
    #     to=recipient_email,
    #     subject=subject,
    #     contents=body,
    #     attachments=docx_fname,
    # )

def get_user_inputs():
    main_query = st.session_state["main_query_input"]
    email = st.session_state["email"]
    column_specs = process_table()
    return main_query, column_specs, email

def display_output(docx_fname):
    with open(docx_fname, 'rb') as f:
        binary_file = f.read()
        st.download_button(label="Download Results",
                   data=binary_file,
                   file_name="results.docx",
                   mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
