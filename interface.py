from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
from tempfile import NamedTemporaryFile, TemporaryDirectory
import base64
import os
import pandas as pd
import streamlit as st
import zipfile

def load_text():
    html_temp = """
    <div style="background-color:#00D29A;padding:10px;border-radius:10px;margin-bottom:20px;">
        <img src="https://tr2ail.org/img/SEI-Master-Logo-Extended-Charcoal-RGB.cd475ad5.png" alt="Logo" style="height:50px;width:auto;float:right;">
        <h2 style="color:white;text-align:center;">GPT Batch Policy Processor (beta)</h2>
        <h5 style="color:white;text-align:center;">This Tool allows users to analyze policy documents in bulk using the Large Language Models ChatGPT. 
    The Tool allows the user to define specific queries to extract qualitative information.</h5>
        <br>
    </div>
    """
    st.markdown(html_temp, unsafe_allow_html=True)
    #st.title("GPT Batch Policy Processor (beta)")
    instructions = """
## How to use
Reading through each uploaded policy document, this tool will ask ChatGPT the main query template for each data 'variable' specified below. 
- **Step 0:** IF YOU ARE A NEW USER, FIRST RUN A TEST ON ONE OR TWO DOCUMENTS.
- **Step 1:** Create a ZIP file containing all the policy documents you want to analyze. Beta version only accepts pdf documents, no subfolders allowed.
- **Step 2:** Upload the zipfile in the box below.
- **Step 3:** Specify a main query template (see specific instructions and template below).
- **Step 4:** For multiquery search, specify query variables (see specific instructions below).
- **Step 5:** hit “Run”.
- **Step 6:** DO NOT CLOSE SESSION until you have received or downloaded results."""
    st.markdown(instructions)
    st.warning("Please first run on a subset of PDF's to fine-tune functionality. Repeatedly running on many PDF's causes avoidable AI-borne GHG emissions.", icon="⚠️")
    st.markdown("""## Submit your processing request""")

def upload_zip(temp_dir):
    st.subheader("Upload ZIP-file of PDF's")
    uploaded_zip = st.file_uploader("Zip-file must have the same name as the folder. The folder must only contain PDF's; no subfolders allowed.", type="zip")
    if uploaded_zip is not None:
        st.success("File uploaded successfully!")
        pdfs = []
        with NamedTemporaryFile(delete=False, suffix='.zip') as temp_zip:
            temp_zip.write(uploaded_zip.getvalue())
            st.session_state["temp_zip_path"] = temp_zip.name
        with zipfile.ZipFile(st.session_state["temp_zip_path"], 'r') as zip_ref:
            zip_ref.extractall(temp_dir)
        for subdir in os.listdir(temp_dir):
            subdir_path = os.path.join(temp_dir, subdir)
            for filename in os.listdir(subdir_path):
                if filename.endswith(".pdf"):
                    file_path = os.path.join(subdir_path, filename)
                    pdfs.append(file_path)  
        st.session_state["pdfs"] = pdfs
        on = st.toggle('Run on subset', value=True, help="Do not turn this off until you are ready for your final run.", key="is_test_run")
        if on:
            fnames = [os.path.basename(p) for p in pdfs]
            st.session_state["selected_pdfs"] = st.multiselect("Select particular subfiles to run on", fnames, default=[fnames[0]])
        
def input_main_query():
    st.markdown("")
    st.subheader("Edit Main Query Template")
    qtemplate_instructions = ('Modify the generalized template query below. Please note curley brackets indicate '
                              'keywords. *{variable_name}* and *{variable_description}* will be replaced by each '
                              'of variable specification listed in the table below (i.e. [SDG1: End poverty in all '
                              'its forms everywhere, SDG2: End hunger, achieve food security..]). '
                              'Do not include any single quotation marks or apostraphes.') 
    #st.text(qtemplate_instructions)
    qtemplate = ('From the following text excerpts, extract any quote that includes a national action or plan that '
                 'addresses “{variable_name}” which we define as “{variable_description}”. ' 
                 'Only include direct quotation with the corresponding page number(s) with a brief explanation of the context of '
                 'this quote within the text. It is very important not to hallucinate.')
    st.session_state["main_query_input"] = st.text_area(qtemplate_instructions, value=qtemplate, height=150)

def input_email():
    st.session_state["email"] = st.text_input("Enter your email where you'd like to recieve the results:")

# Function to pre-populate the DataFrame with a template for 15 rows
def populate_with_SDGs():
    st.session_state["SDGs"] = [f"SDG {i+1}" for i in range(17)]
    st.session_state["SDG_defs"] = [
        "End poverty in all its forms everywhere",
        "End hunger, achieve food security and improved nutrition and promote sustainable agriculture",
        "Ensure healthy lives and promote well-being for all at all ages",
        "Ensure inclusive and equitable quality education and promote lifelong learning opportunities for all",
        "Achieve gender equality and empower all women and girls",
        "Ensure availability and sustainable management of water and sanitation for all",
        "Ensure access to affordable, reliable, sustainable and modern energy for all",
        "Promote sustained, inclusive and sustainable economic growth, full and productive employment and decent work for all",
        "Build resilient infrastructure, promote inclusive and sustainable industrialization and foster innovation",
        "Reduce inequality within and among countries",
        "Make cities and human settlements inclusive, safe, resilient and sustainable",
        "Ensure sustainable consumption and production patterns",
        "Take urgent action to combat climate change and its impacts",
        "Conserve and sustainably use the oceans, seas and marine resources for sustainable development",
        "Protect, restore and promote sustainable use of terrestrial ecosystems, sustainably manage forests, combat desertification, and halt and reverse land degradation and halt biodiversity loss",
        "Promote peaceful and inclusive societies for sustainable development, provide access to justice for all and build effective, accountable and inclusive institutions at all levels",
        "Strengthen the means of implementation and revitalize the Global Partnership for Sustainable Development"
    ]
    st.session_state['num_rows'] = len(st.session_state["SDGs"])

def input_data_specs():
    st.markdown("")
    st.subheader("Specify Variables to Extract from Policy Documents")
    hdr = ('For example, you may list particular SDGs as variables if you want to our tool to extract quotes '
           'from the policy documents that address an SDG. For example, your list of variable names and descriptions '
           'would be *[SDG1: End poverty in all its forms everywhere, SDG2: End hunger, achieve food security..]*. '
           'You may also click the "Populate with SDGs" button below.')
    st.markdown(hdr)
    selected_tab = st.radio(
        "Select Input Format",
        ["**Manual Entry**", "**Paste Table**"],
        key="schema_input_format",
        horizontal=True,
        label_visibility='collapsed',
        help="Insert variable information below. You may select your desired input format."
    )
    if selected_tab.replace("*","") == "Manual Entry":
        col1_label, col2_label = st.columns(2)
        with col1_label:
            st.markdown("*Variable name*")
        with col2_label:
            st.markdown("*Variable description*")

        if 'num_rows' not in st.session_state:
            st.session_state['num_rows'] = 1  # Starting with 1 row
        for i in range(st.session_state['num_rows']):
            col1, col2 = st.columns(2)
            def get_prepopulated_vals(key):
                val = ""
                if key in st.session_state:
                    val = st.session_state[key][i] if i < len(st.session_state[key]) else ""
                return val
            with col1:
                val = get_prepopulated_vals("SDGs")
                st.text_input("Variable name", key=f"col1_{i}", value=val, label_visibility='collapsed')
            with col2:
                val = get_prepopulated_vals("SDG_defs")
                st.text_input("Variable description", key=f"col2_{i}", value=val, label_visibility='collapsed')
        def add_row():
            st.session_state['num_rows'] += 1
        def remove_row():
            if st.session_state['num_rows'] > 1:
                st.session_state['num_rows'] -= 1
        col1, col2, _, col3 = st.columns([1, 1, 1, 1])
        with col1:
            st.button("Add Variable", on_click=add_row)
        with col2:
            st.button("Remove Variable", on_click=remove_row)
        with col3:
            st.button("Populate with SDGs", on_click=populate_with_SDGs)
    else:
        label = "Copy 2 columns (variable_name, variable_description) from an excel spreadsheet. Paste it below. Do not include headers."
        st.session_state["schema_table"] = st.text_area(label, height=300)
    
def process_table():
    input_format = st.session_state['schema_input_format'].replace("*", "")
    if input_format == 'Manual Entry':
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
        if 'schema_table' not in st.session_state:
            st.session_state['schema_table'] = ''
        user_input = st.session_state["schema_table"] 
        data = [line.split('\t') for line in user_input.split('\n')] 
        df = pd.DataFrame(data, columns=["column_name", "column_description"]) 
        df['column_name'].replace('', pd.NA, inplace=True)
        df.dropna(subset=['column_name'], inplace=True)
        df = df[df['column_name'].notnull()]
        return df.set_index('column_name')['column_description'].to_dict()
    

def build_interface(tmp_dir):
    load_text()
    upload_zip(tmp_dir)
    input_main_query()
    input_data_specs()
    st.divider()
    input_email()
    if 'schema_input_format' not in st.session_state:
        st.session_state['schema_input_format'] = 'Manual Entry'
    if 'is_test_run' not in st.session_state:
        st.session_state['is_test_run'] = True

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

def get_user_inputs():
    pdfs = st.session_state["pdfs"]
    if st.session_state["is_test_run"]:
        pdfs = st.session_state["selected_pdfs"]
    main_query = st.session_state["main_query_input"]
    email = st.session_state["email"]
    column_specs = process_table()
    return pdfs, main_query, column_specs, email

def display_output(docx_fname):
    with open(docx_fname, 'rb') as f:
        binary_file = f.read()
        st.download_button(label="Download Results",
                   data=binary_file,
                   file_name="results.docx",
                   mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
