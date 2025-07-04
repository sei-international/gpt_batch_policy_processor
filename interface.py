from analysis import get_analyzer, get_task_types
import re
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Mail,
    Attachment,
    FileContent,
    FileName,
    FileType,
    Disposition,
)
from tempfile import NamedTemporaryFile
import base64
import json
import os
import pandas as pd
import streamlit as st
import zipfile


def load_header():
    logo_path = os.path.join(os.path.dirname(__file__), "public", "logo.png")
    with open(logo_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read()).decode()

    html_temp = f"""
    <div style="background-color:#00D29A;padding:10px;border-radius:10px;margin-bottom:20px;">
        <img src="data:image/png;base64,{encoded_string}" alt="logo" style="height:50px;width:auto;float:right;">
        <h2 style="color:white;text-align:center;">AI Policy Reader (beta)</h2>
        <h5 style="color:white;text-align:center;">This Tool allows users to analyze policy documents in bulk using the Large Language Model ChatGPT.\n
Users can define specific queries to extract targeted information from any collection of PDF's.</h5>
        <br>
    </div>
    """
    st.markdown(html_temp, unsafe_allow_html=True)


def load_instructions():
    with st.expander("ℹ️ Instructions", expanded=True):

        instructions = """
## How to use
Reading through each uploaded policy document, this tool will ask ChatGPT the main query template for each data 'variable' specified below. 
- **Step 0:** IF YOU ARE A NEW USER, FIRST TEST FUNCTIONALITY ON 1-3 DOCUMENTS.
- **Step 1:** Create a folder containing all the policy documents you want to analyze; then compress the folder into a zip-file. Beta version only accepts pdf documents, no subfolders allowed.
- **Step 2:** Upload the zipfile in the box below.
- **Step 3:** Select 1-4 PDFs to analyze at first.
- **Step 4:** Specify a main query template (see specific instructions and template below).
- **Step 5:** For multiquery search, specify query variables (see specific instructions below).
- **Step 6:** Hit “Run”. DO NOT CLOSE SESSION until you have received or downloaded results.
- **Step 7:** Assess results, change parameters as needed, and repeat steps 1-6.
- **Step 8:** Once results are satisfactory, contact aipolicyreader@sei.org for access to full batch-processing functionality.
- **Step 9:** Re-run once more on all policy documents."""

        st.markdown(instructions)
        # st.warning("Please first run on a subset of PDF's to fine-tune functionality. Repeatedly running on many PDF's causes avoidable AI-borne GHG emissions.", icon="⚠️")


def upload_file(temp_dir):
    st.subheader("I. Upload Policy Document(s)")

    # Single uploader for both PDF and ZIP files
    uploaded_file = st.file_uploader(
        "Upload a **single PDF** or a **ZIP file** containing multiple PDFs.",
        type=["pdf", "zip"],
    )

    st.markdown(
        "*Please note: uploaded documents will be processed by OpenAI and may be used to train further models. "
        "If you are concerned about the confidentiality of your documents, please contact us before use.*"
    )

    pdfs = []  # Store uploaded PDF file paths

    if uploaded_file is not None:
        file_name = uploaded_file.name

        if file_name.endswith(".pdf"):
            # Save the single uploaded PDF to a temporary location
             file_path = os.path.join(temp_dir, file_name)
             with open(file_path, "wb") as f:
                f.write(uploaded_file.getvalue())
             pdfs.append(file_path)

        elif file_name.endswith(".zip"):
            with NamedTemporaryFile(delete=False, suffix=".zip") as temp_zip:
                temp_zip.write(uploaded_file.getvalue())
                st.session_state["temp_zip_path"] = temp_zip.name

            with zipfile.ZipFile(st.session_state["temp_zip_path"], "r") as zip_ref:
                zip_ref.extractall(temp_dir)

            for subdir in os.listdir(temp_dir):
                subdir_path = os.path.join(temp_dir, subdir)
                for filename in os.listdir(subdir_path):
                    if filename.endswith(".pdf"):
                        file_path = os.path.join(subdir_path, filename)
                        pdfs.append(file_path)

    if pdfs:
        st.session_state["pdfs"] = pdfs
        st.success(f"Uploaded {len(pdfs)} document(s) successfully! Please first run on a subset of PDFs to fine-tune functionality. Careless processing causes avoidable AI-borne GHG emissions.", icon="✅")

        if len(pdfs) == 1:
            # Disable the subset checkbox if only one PDF is uploaded
            st.session_state["max_files"] = None
            st.session_state["file_select_label"] = "No need to select subset for analysis."
            checked = False  # Automatically set the "Run on subset" checkbox to off
        else:
            if "max_files" not in st.session_state:
                st.session_state["max_files"] = 3
            if "file_select_label" not in st.session_state:
                st.session_state["file_select_label"] = "Select 1-3 subfiles to run on"

            checked = st.checkbox(
                "Run on subset",
                value=True,
                help="Do not turn this off until you are ready for your final run.",
            )

        if checked:
            st.session_state["run_disabled"] = False  # Enable run if subset is selected
            fnames = {os.path.basename(p): p for p in pdfs}
            first = os.path.basename(pdfs[0])
            selected_fnames = st.multiselect(
                st.session_state["file_select_label"],
                fnames.keys(),
                default=[first],
                max_selections=st.session_state["max_files"],
            )
            st.session_state["selected_pdfs"] = [
                fnames[selected_fname] for selected_fname in selected_fnames
            ]
        else:
            if len(pdfs) > 1: # If not checked to run on subset and there is more than 1 PDF
                passcode = st.text_input("Enter passcode", type="password")
                if passcode:
                    apikey_ids = {
                        st.secrets["access_password"]: "openai_apikey",
                        st.secrets["access_password_adis"]: "openai_apikey_adis",
                        st.secrets["access_password_urbanadaptation"]: "openai_apikey_adaptation",
                        st.secrets["access_password_bb"]: "openai_apikey_bb",
                    }
                    if passcode in apikey_ids:
                        st.session_state["apikey_id"] = apikey_ids[passcode]
                        st.session_state["is_test_run"] = False
                        st.session_state["max_files"] = None
                        st.session_state["file_select_label"] = (
                            "Select any number of PDFs to analyze. Or, uncheck 'Run on Subset' to analyze all uploaded PDFs"
                        )
                        st.session_state["run_disabled"] = False  # Enable Run button
                        st.success("Access granted. All PDFs in the zip-file will be processed. Please proceed.", icon="✅")
                    else:
                        st.session_state["run_disabled"] = True  # Disable Run button
                        st.error("Incorrect password. Click 'Run on subset' above. The 1-3 documents specified will be processed.", icon="❌")
                else:
                    st.session_state["run_disabled"] = True  # Disable Run button
                    st.error("You need a passcode to proceed. If you do not have one, please select 'Run on subset' above.", icon="❌")
            else: # If not checks and there is 1 PDF, we don't need a passcode
                st.session_state["selected_pdfs"] = [pdfs[0]]
                st.session_state["run_disabled"] = False  # Enable Run if only one PDF
    else:
        st.warning("Please upload a **PDF** or a **ZIP file** containing PDFs.", icon="⚠️")



def input_main_query():
    st.markdown("")
    st.subheader("II. Edit Main Query Template")
    qtemplate_instructions = (
        "Modify the generalized template query below. Please note curly brackets indicate "
        "keywords. *{variable_name}*, *{variable_description}*, and *{context}* will be replaced by each "
        "of variable specification listed in the table below (i.e. [SDG1: End poverty in all "
        "its forms everywhere, SDG2: End hunger, achieve food security..])."
    )
    qtemplate = (
        "Extract any quote that addresses “{variable_name}” which we define as “{variable_description}”. "
        "Only include direct quotations with the corresponding page number(s)."
    )
    st.session_state["main_query_input"] = st.text_area(
        qtemplate_instructions, value=qtemplate, height=150
    )
    qtemplate_tips = (
        "**Some Query Design Tips:** Be clear and concise. Do not include unneeded background information."
        ' Start your query with a verb, an action word, or a command i.e. ("extract", "find", "determine").'
    )
    st.markdown(qtemplate_tips)


def var_json_to_df(json_fname):
    var_info_path = os.path.join(os.path.dirname(__file__), "site_text", json_fname)
    with open(var_info_path, "r", encoding="utf-8") as file:
        sdg_var_specs = json.load(file)
        return pd.DataFrame(sdg_var_specs)


def populate_with_SDGs():
    sdg_df = var_json_to_df("SDG_var_specs.json")
    st.session_state["variables_df"] = sdg_df


def populate_with_just_transition():
    just_transition_df = var_json_to_df("just_trans_var_specs.json")
    st.session_state["variables_df"] = just_transition_df

def clear_variables():
    empty_df = pd.DataFrame(
        [{"variable_name": None, "variable_description": None, "context": None}]
    )
    st.session_state["variables_df"] = empty_df

def update_var_spec_df_from_csv():
    csv_file = st.session_state["csv_upload"]
    if csv_file is None:
        return  # Don't do anything if no file is uploaded
    try:
        df = pd.read_csv(csv_file)
        if list(df.columns) != ["variable_name", "variable_description"] and list(df.columns) != ["variable_name", "variable_description", "context"]:
            df = pd.read_csv(csv_file, header=None)
            if df.shape[1] == 2:
                df.columns = ["variable_name", "variable_description"]
                df["context"] = None  # Add a context column with None values
            elif df.shape[1] == 3:
                df.columns = ["variable_name", "variable_description", "context"]
        st.session_state["variables_df"] = df
    except Exception as e:
        st.error(f"Error reading CSV: {e}")

def input_data_specs():
    st.markdown("")
    st.subheader("III. Specify Variables to Extract from Policy Documents")
    hdr = (
        "For example, you may list particular SDGs as variables if you want to our tool to extract quotes "
        "from the policy documents that address an SDG. In this case, your list of variable names and descriptions "
        "would be *[SDG1: End poverty in all its forms everywhere, SDG2: End hunger, achieve food security..]*. "
        'You may also click the "Populate with SDGs" button below.'
    )
    st.markdown(hdr)
    st.markdown(
        "**Type-in variable details, upload a csv, or copy-and-paste from an excel spreadsheet (3 columns, no headers).**"
    )
    if "variables_df" not in st.session_state:
        st.session_state["variables_df"] = var_json_to_df("default_var_specs.json")
    variable_specification_parameters = [
        "variable_name",
        "variable_description",
        "context",
    ]
    variables_df = st.session_state["variables_df"]
    st.session_state["schema_table"] = st.data_editor(
        variables_df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_order=variable_specification_parameters,
    )
    btn1, btn2, _, btn4 = st.columns([5, 5, 2, 3])
    with btn1:
        st.button("Clear", on_click=clear_variables)
    with btn2:
        with st.popover("Populate with..."):
            st.button("SDGs", on_click=populate_with_SDGs)
            st.button("Just-Transition Themes", on_click=populate_with_just_transition)
    with btn4:
        with st.popover("📤 Upload CSV"):
            st.file_uploader(
                "Choose a CSV file (headers optional, 2 or 3 columns):",
                type=["csv"],
                key="csv_upload",
                on_change=update_var_spec_df_from_csv
            )
    with st.expander("Advanced settings"):
        st.selectbox(
            "Optional: specify the overall operation type",
            list(get_task_types().keys()),
            key="task_type",
        )
        var_names = list(st.session_state["schema_table"]["variable_name"].to_list())
        if st.session_state["task_type"] == "Quote extraction":
            options = st.session_state["output_format_options"]
            if "output_format" not in st.session_state:
                st.session_state["output_format"] = list(options.keys())[1]
            st.selectbox(
                "Optional: select format of output table for each document",
                options.keys(),
                key="output_format",
            )
            output_fmt_selected = st.session_state["output_format_options"][
                st.session_state["output_format"]
            ]
            if output_fmt_selected == "quotes_sorted_and_labelled":
                subcat_div1, subcat_div2 = st.columns([1, 1])
                with subcat_div1:
                    subcat1 = st.text_input(
                        "1st categorization label:",
                        value="SDG Targets",
                        key="subcat1_label",
                    )
                with subcat_div2:
                    subcat2 = st.text_input(
                        "2nd categorization label (optional):",
                        value="Climate Actions",
                        key="subcat2_label",
                    )
                subcats_df_dic = {
                    "variable_name": var_names,
                    st.session_state["subcat1_label"]: [None] * len(var_names),
                }
                if subcat1:
                    if subcat2:
                        subcats_df_dic[st.session_state["subcat2_label"]] = [
                            None
                        ] * len(var_names)
                    subcats_df = pd.DataFrame(subcats_df_dic)
                    st.session_state["subcategories_df"] = st.data_editor(
                        subcats_df,
                        hide_index=True,
                        disabled=["variable_name"],
                        use_container_width=True,
                    )
                else:
                    st.warning(
                        "Please enter at least one subcategorization label or choose a different output format."
                    )
        elif st.session_state["task_type"] == "Custom output format":
            st.session_state["custom_output_fmt"] = st.text_area(
                "Enter your custom output instructions", height=100
            )
            st.markdown(
                "Optional: include specific output instructions for each variable using {output_detail} above"
            )
            init_output_detail_df = pd.DataFrame(
                {"variable_name": var_names, "output_detail": [None] * len(var_names)}
            )
            st.session_state["output_detail_df"] = st.data_editor(
                init_output_detail_df,
                hide_index=True,
                disabled=["variable_name"],
                use_container_width=True,
            )


def process_table():
    df = st.session_state["schema_table"]
    df = df.fillna("")
    num_cols = df.shape[1]
    df.columns = ["variable_name", "variable_description", "context"][:num_cols]
    df["variable_name"] = df["variable_name"].replace("", pd.NA)
    df.dropna(subset=["variable_name"], inplace=True)
    df = df[df["variable_name"].notnull()]
    return {
        row["variable_name"]: {
            "variable_description": row["variable_description"],
            **({"context": row["context"]} if "context" in df.columns else {}),
        }
        for _, row in df.iterrows()
    }

# Validate email, since it is required
def is_valid_email(email):
    # Expression for validating an email
    email_regex = r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"
    validated = re.match(email_regex, email) is not None
    return validated

def select_gpt_model():
    if "gpt_model" not in st.session_state:
        st.session_state["gpt_model"] = "4.1"  # Default model
    model_options = {
        "gpt-4.1": "4.1",
        "o4-mini": "o4-mini", 
        "o3": "o3 (slower, smarter, more expensive)",
    }  
    st.session_state["gpt_model"] = st.selectbox(
        "Select the OpenAI model to use for processing:",
        options=list(model_options.keys()),
        format_func=lambda x: model_options[x],
    )

def input_email():
    email = st.text_input("Enter your email where'd like to receive the results:")
    if "email" not in st.session_state:
        st.session_state["email"] = None  # Set to None if email is empty, for warning to user
    if not is_valid_email(email):
        st.session_state["email"] = None # Set to None if email is invalid, for warning to user
    else:
        st.session_state["email"] = email  # Store the email entered in the session state if there are no errors



def build_interface(tmp_dir):
    if "task_type" not in st.session_state:
        st.session_state["task_type"] = "Quote extraction"
    if "is_test_run" not in st.session_state:
        st.session_state["is_test_run"] = True
    load_instructions()
    st.markdown("""## Submit your processing request""")
    upload_file(tmp_dir)
    input_main_query()
    if "output_format_options" not in st.session_state:
        st.session_state["output_format_options"] = {
            "Return list of quotes per variable": "quotes_structured",
            "Return raw GPT responses for each variable": "quotes_gpt_resp",
            "Sort by quotes; each quote will be one row": "quotes_sorted",
            "Sort by quotes labelled with variable_name and subcategories": "quotes_sorted_and_labelled",
        }
    if "pdfs" not in st.session_state:
        st.session_state["pdfs"] = "no_upload"
    if "schema_input_format" not in st.session_state:
        st.session_state["schema_input_format"] = "Manual Entry"
    if "output_format" not in st.session_state:
        st.session_state["output_format"] = list(
            st.session_state["output_format_options"].keys()
        )[1]
    if "custom_output_fmt" not in st.session_state:
        st.session_state["custom_output_fmt"] = None
    if "output_detail_df" not in st.session_state:
        st.session_state["output_detail_df"] = None
    input_data_specs()
    st.divider()
    st.markdown(
        "For variables with short descriptions, processing time will be about 1 minute per 100 PDF pages per variable (with default model selection)."
    )
    select_gpt_model()
    input_email()


def email_results(output_file_contents, recipient_email):
    message = Mail(
        from_email=st.secrets["email"],
        to_emails=recipient_email,
        subject="Results: GPT Batch Policy Processor (Beta)",
        html_content="Attached is the document you requested.",
    )
    encoded_output_file = base64.b64encode(output_file_contents).decode()
    message.attachment = Attachment(
        FileContent(encoded_output_file),
        FileName("results.xlsx"),
        FileType("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        Disposition("attachment"),
    )
    try:
        sg = SendGridAPIClient(st.secrets["sendgrid_apikey"])
        response = sg.send(message)
        print("Email sent, status code:", response.status_code)
    except Exception as e:
        print("Error sending email:", e)
        print(e.message)


def get_user_inputs():
    pdfs = st.session_state["pdfs"]
    if st.session_state["is_test_run"]:
        pdfs = st.session_state["selected_pdfs"]
    main_query = st.session_state["main_query_input"]
    email = st.session_state["email"]
    if not email:
        st.error("⚠️ A valid email is required. Please enter your email to proceed.")
        return
    variable_specs = process_table()
    task_type = st.session_state["task_type"]
    output_fmt = st.session_state["output_format_options"][
        st.session_state["output_format"]
    ]
    additional_info = None
    if task_type == "Quote extraction" and output_fmt == "quotes_sorted_and_labelled":
        additional_info = st.session_state["subcategories_df"]
    elif task_type == "Custom output format":
        additional_info = {
            "custom_output_fmt": st.session_state["custom_output_fmt"],
            "output_detail": st.session_state["output_detail_df"],
        }
    gpt_model = st.session_state["gpt_model"]
    return get_analyzer(
        task_type, output_fmt, pdfs, main_query, variable_specs, email, additional_info, gpt_model
    )


def display_output(output_file_contents):
    st.download_button(
        label="Download Results",
        data=output_file_contents,
        file_name="results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def about_tab():
    text = """
## Terms of use
**Open access to the data sets** \n
The GPT-Batch Policy Processor (beta) tool has been published on May 1st, 2024.
\n
**The GPT-Batch Policy Processor (beta) tool** \n
Babis, William / Munoz Cabre, Miquel / Dzebo, Adis / Martelo, Camilo / Salzano, Cora / Torres Morales, Eileen / Arsadita, Ferosa (2024): GPT-Batch Policy Processor (beta). Stockholm Environment Institute (SEI).
\n
**Referring to GPT-Batch Policy Processor (beta) tool analysis** \n
 The Stockholm Environment Institute (SEI) hold the copyright of the GPT-Batch Policy Processor (beta) tool. It is 
 licensed under Creative Commons and you are free to copy and redistribute material derived from the  GPT-Batch Policy 
 Processor (beta) tool by following the guideline of the Creative Commons License. [CC BY-NC-NA](https://creativecommons.org/licenses/by-nc-sa/4.0/) (Attribution, NonCommercial, ShareAlike).
"""
    st.markdown(text)


def FAQ():
    text = """
# Frequently asked questions \n

## Coming soon \n

"""
    st.markdown(text)
