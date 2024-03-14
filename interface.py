from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
from tempfile import NamedTemporaryFile, TemporaryDirectory
import base64
import streamlit as st

def upload_zip():
    uploaded_zip = st.file_uploader("Upload zipfile of PDF's", type="zip")
    if uploaded_zip is not None:
        st.session_state['uploaded_zip'] = uploaded_zip
        st.success("File uploaded successfully!")
        
def input_main_query():
    query_descr = ('In the following textbox, insert your master query which will be asked to ChatGPT '
                   'for each of the "columns" listed in the table below. Please note that the keywords '
                   '"{column_name}", "{column_description}", and "{excerpts}" will be replaced by the '
                   'values found in the table below and the relevant text excerpts from each uploaded document. '
                   'This query will be run iteratively for each document and for each data column. \n\n '
                   'Example query: From the following text excerpts, list any references to “{column_name}” '
                   'which we define as “{column_description}”. Only include direct quotation '
                   'with the corresponding page number(s) (seen in square brackets at the end '
                   'of each excerpt) with a brief explanation of the context of this quote within '
                   'the text. It is very important not to hallucinate. '
                   'Text: {excerpts} \n\n'
                    'NOTE: Do not include any single quotation marks or apostraphes'
                    )
    st.session_state["main_query_input"] = st.text_input(query_descr)

def input_email():
    st.session_state["email"] = st.text_input("Enter your email where you'd like to recieve the results:")

def input_data_specs():
    if 'num_rows' not in st.session_state:
        st.session_state['num_rows'] = 1  # Starting with 1 row
    for i in range(st.session_state['num_rows']):
        col1, col2 = st.columns(2)
        with col1:
            st.text_input(f"Column name", key=f"col1_{i}")
        with col2:
            st.text_input(f"Column description", key=f"col2_{i}")
    def add_row():
        st.session_state['num_rows'] += 1
    st.button("Add Row", on_click=add_row)
    
def process_table():
    column_specs =  {}
    for i in range(st.session_state['num_rows']):
        # Access each row's inputs using the keys
        col_name = st.session_state[f"col1_{i}"]
        col_desc = st.session_state[f"col2_{i}"]
        # Append the row's data to a list, or process it as needed
        column_specs[col_name] = col_desc
    return column_specs

def build_interface():
    upload_zip()
    input_main_query()
    input_data_specs()
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
