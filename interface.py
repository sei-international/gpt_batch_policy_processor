from analysis import get_analyzer, get_task_types

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
from tempfile import NamedTemporaryFile
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
        <h5 style="color:white;text-align:center;">This Tool allows users to analyze policy documents in bulk using the Large Language Model ChatGPT.\n 
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
    #st.warning("Please first run on a subset of PDF's to fine-tune functionality. Repeatedly running on many PDF's causes avoidable AI-borne GHG emissions.", icon="⚠️")
    st.markdown("""## Submit your processing request""")

def upload_zip(temp_dir):
    st.subheader("I. Upload ZIP-file of PDF's")
    uploaded_zip = st.file_uploader("Zip-file must have the same name as the folder. The folder must only contain PDF's; no subfolders allowed.", type="zip")
    if uploaded_zip is not None:
        st.success("""Zip-file uploaded successfully! \n
Please first run on a subset of PDF's to fine-tune functionality. Careless processing causes avoidable AI-borne GHG emissions.""", icon="✅")
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
        if 'is_test_run' not in st.session_state:
            st.session_state['is_test_run'] = True
        checked = st.checkbox('Run on subset', value=True, help="Do not turn this off until you are ready for your final run.")
        if checked:
            fnames = {os.path.basename(p): p for p in pdfs}
            first = os.path.basename(pdfs[0])      
            selected_fnames = st.multiselect("Select 1-3 subfiles to run on", fnames.keys(), default=[first], max_selections=3)
            st.session_state['selected_pdfs'] = [fnames[selected_fname] for selected_fname in selected_fnames]
        else:
            st.markdown("After fine-tuning the main query template and variable definitions below, you may run the "
                        "Tool for all policy documents of interest. Please contact william.babis@sei.org for access.")
            passcode = st.text_input("Enter passcode")
            if passcode:
                if passcode == st.secrets["access_password"]:
                    st.session_state['is_test_run'] = False
                    st.success("Access granted. All PDFs in the zip-file will be processed. Please proceed.", icon="✅")
                else:
                    st.error("Incorrect password. Click 'Run on subset' above. The 1-3 documents specified will be processed.", icon="❌")

        # with div_left:
        #     # Refer directly to session state for the checkbox value
        #     st.session_state['is_test_run'] = st.checkbox('Run on subset', value=True,
        #                     disabled=st.session_state['accesss_restricted'], 
        #                     help="Do not turn this off until you are ready for your final run.")
        #     if st.session_state['is_test_run']:
        #         fnames = {os.path.basename(p): p for p in pdfs}
        #         first = os.path.basename(pdfs[0])      
        #         selected_fnames = st.multiselect("Select 1-3 subfiles to run on", fnames.keys(), default=[first], max_selections=3)
        #         st.session_state['selected_pdfs'] = [fnames[selected_fname] for selected_fname in selected_fnames]
        # with div_right:
        #     with st.popover("Run on all PDF's (restricted access)"):
        #         st.markdown("After fine-tuning the main query template and variable definitions below, you may run the "
        #                     "Tool for all policy documents of interest. Please contact william.babis@sei.org for access.")
        #         passcode = st.text_input("Enter passcode")
        #         if passcode == st.secrets["access_password"]:
        #             st.session_state['accesss_restricted'] = False
        #             st.session_state['is_test_run'] = False

                    
        
def input_main_query():
    st.markdown("")
    st.subheader("II. Edit Main Query Template")
    qtemplate_instructions = ('Modify the generalized template query below. Please note curly brackets indicate '
                              'keywords. *{variable_name}*, *{variable_description}*, and *{context}* will be replaced by each '
                              'of variable specification listed in the table below (i.e. [SDG1: End poverty in all '
                              'its forms everywhere, SDG2: End hunger, achieve food security..]). '
                              'Do not include any single quotation marks or apostrophes.') 
    #st.text(qtemplate_instructions)
    qtemplate = ('Extract any quote that includes a national action or plan that '
                 'addresses “{variable_name}” which we define as “{variable_description}”. ' 
                 'Only include direct quotation with the corresponding page number(s) with a brief explanation of the context of '
                 'this quote within the text. It is very important not to hallucinate.')
    st.session_state["main_query_input"] = st.text_area(qtemplate_instructions, value=qtemplate, height=150)

def populate_with_SDGs():
    sdg_df = pd.DataFrame([
        {"variable_name": "SDG 1", "variable_description": "End poverty in all its forms everywhere", "context": ""},
        {"variable_name": "SDG 2", "variable_description": "End hunger, achieve food security and improved nutrition and promote sustainable agriculture", "context": ""},
        {"variable_name": "SDG 3", "variable_description": "Ensure healthy lives and promote well-being for all at all ages", "context": ""},
        {"variable_name": "SDG 4", "variable_description": "Ensure inclusive and equitable quality education and promote lifelong learning opportunities for all", "context": ""},
        {"variable_name": "SDG 5", "variable_description": "Achieve gender equality and empower all women and girls", "context": ""},
        {"variable_name": "SDG 6", "variable_description": "Ensure availability and sustainable management of water and sanitation for all", "context": ""},
        {"variable_name": "SDG 7", "variable_description": "Ensure access to affordable, reliable, sustainable and modern energy for all", "context": ""},
        {"variable_name": "SDG 8", "variable_description": "Promote sustained, inclusive and sustainable economic growth, full and productive employment and decent work for all", "context": ""},
        {"variable_name": "SDG 9", "variable_description": "Build resilient infrastructure, promote inclusive and sustainable industrialization and foster innovation", "context": ""},
        {"variable_name": "SDG 10", "variable_description": "Reduce inequality within and among countries", "context": ""},
        {"variable_name": "SDG 11", "variable_description": "Make cities and human settlements inclusive, safe, resilient and sustainable", "context": ""},
        {"variable_name": "SDG 12", "variable_description": "Ensure sustainable consumption and production patterns", "context": ""},
        {"variable_name": "SDG 13", "variable_description": "Take urgent action to combat climate change and its impacts", "context": ""},
        {"variable_name": "SDG 14", "variable_description": "Conserve and sustainably use the oceans, seas and marine resources for sustainable development", "context": ""},
        {"variable_name": "SDG 15", "variable_description": "Protect, restore and promote sustainable use of terrestrial ecosystems, sustainably manage forests, combat desertification, and halt and reverse land degradation and halt biodiversity loss", "context": ""},
        {"variable_name": "SDG 16", "variable_description": "Promote peaceful and inclusive societies for sustainable development, provide access to justice for all and build effective, accountable and inclusive institutions at all levels", "context": ""},
        {"variable_name": "SDG 17", "variable_description": "Strengthen the means of implementation and revitalize the Global Partnership for Sustainable Development", "context": ""}
    ])
    st.session_state["variables_df"] = sdg_df

def populate_with_just_transition():
    just_transition_df = pd.DataFrame([
        {"variable_name": "gender", "variable_description": "", "context": ""},
        {"variable_name": "jobs", "variable_description": "", "context": ""},
        {"variable_name": "local communities and co-benefits", "variable_description": "", "context": ""},
        {"variable_name": "indigenous peoples", "variable_description": "", "context": ""},
        {"variable_name": "prior informed consent", "variable_description": "", "context": ""},
        {"variable_name": "human rights", "variable_description": "", "context": ""}
    ])
    st.session_state["variables_df"] = just_transition_df

def clear_variables():
    empty_df = pd.DataFrame([{"variable_name": "", "variable_description": "", "context": ""}])
    st.session_state["variables_df"] = empty_df

def input_data_specs():
    st.markdown("")
    st.subheader("III. Specify Variables to Extract from Policy Documents")
    hdr = ('For example, you may list particular SDGs as variables if you want to our tool to extract quotes '
           'from the policy documents that address an SDG. In this case, your list of variable names and descriptions '
           'would be *[SDG1: End poverty in all its forms everywhere, SDG2: End hunger, achieve food security..]*. '
           'You may also click the "Populate with SDGs" button below.')
    st.markdown(hdr)
    st.markdown("**Type-in variable details or copy-and-paste from an excel spreadsheetc (no headers).**")
    if "variables_df" not in st.session_state:
        st.session_state["variables_df"] = pd.DataFrame([
            {"variable_name": "SDG 1", "variable_description": "End poverty in all its forms everywhere.", "context": ""},
            {"variable_name": "SDG 2", "variable_description": "End hunger, achieve food security and improved nutrition and promote sustainable agriculture.", "context": ""},
        ])
    col_order = ["variable_name", "variable_description", "context"]
    variables_df = st.session_state["variables_df"]
    st.session_state["schema_table"]  = st.data_editor(variables_df, num_rows="dynamic", use_container_width=True, hide_index=True, column_order=col_order)
    btn1, btn2, btn3 = st.columns([1, 1, 1])
    with btn1:
        st.button("Clear", on_click=clear_variables)
    with btn2:
        st.button("Populate with SDGs", on_click=populate_with_SDGs)
    with btn3:
        st.button("Use Just-Transition Themes", on_click=populate_with_just_transition, use_container_width=True)
    with st.expander("Advanced settings"):
        st.selectbox(
            'Optional: specify the overall operation type',
            list(get_task_types().keys()),
            key='task_type'
        )
        if st.session_state["task_type"] == "Quote extraction":
            options = st.session_state["output_format_options"]
            if 'output_format' not in st.session_state:
                st.session_state['output_format'] = list(options.keys())[0]
            st.selectbox(
                'Optional: select format of output table for each document',
                options.keys(),
                key='output_format'
            )

def process_table():
    df = st.session_state["schema_table"]
    num_cols = df.shape[1]
    df.columns = ["column_name", "column_description", "context"][:num_cols] 
    df['column_name'] = df['column_name'].replace('', pd.NA)
    df.dropna(subset=['column_name'], inplace=True)
    df = df[df['column_name'].notnull()]
    return {row['column_name']: {'column_description': row['column_description'], **({'context': row['context']} if 'context' in df.columns else {})} for _, row in df.iterrows()}

def input_email():
    st.markdown("For variables with short descriptions, processing time will be about 1 minute per 100 pdf-pages per variable.")
    st.session_state["email"] = st.text_input("Enter your email where you'd like to recieve the results:")

def build_interface(tmp_dir):
    load_text()
    upload_zip(tmp_dir)
    input_main_query()
    input_data_specs()
    st.divider()
    if "output_format_options" not in st.session_state:
        st.session_state["output_format_options"] = {
            'Simply return GPT responses for each variable': 0,
            'Sort by quotes; each quote will be one row': 1
        }
    input_email()
    if 'schema_input_format' not in st.session_state:
        st.session_state['schema_input_format'] = 'Manual Entry'
    if 'task_type' not in st.session_state:
        st.session_state['task_type'] = 'Targeted inquiries'
    if 'output_format' not in st.session_state:
        st.session_state['output_format'] = list(st.session_state["output_format_options"].keys())[0]

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
    task_type = st.session_state["task_type"]
    output_fmt = st.session_state["output_format_options"][st.session_state["output_format"]]
    return get_analyzer(task_type, output_fmt, pdfs, main_query, column_specs, email)

def display_output(docx_fname):
    with open(docx_fname, 'rb') as f:
        binary_file = f.read()
        st.download_button(label="Download Results",
                   data=binary_file,
                   file_name="results.docx",
                   mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
