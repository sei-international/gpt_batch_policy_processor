from analysis import get_analyzer, get_task_types
from formatter import get_formatter_type_with_labels
from results import split_workbook_by_sheets
from server_env import get_apikey_ids, get_secret
import re
import resend
from tempfile import NamedTemporaryFile
import base64
import json
import os
import pandas as pd
import streamlit as st
import zipfile

def get_site_content_path(fname, type="jsons"):
    return os.path.join(os.path.dirname(__file__), f"site_content/{type}", fname)

def load_header():
    logo_path = get_site_content_path("logo.png", "imgs")
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
                    apikey_ids = get_apikey_ids()
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
    var_info_path = os.path.join(os.path.dirname(__file__), "site_content/jsons", json_fname)
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
    dic = {}
    for c in st.session_state["variables_df"].columns:
        dic[c] = None
    empty_df = pd.DataFrame([dic])
    st.session_state["variables_df"] = empty_df

@st.dialog("Preview output format", width="large")
def display_output_fmt_preview(selected_output_fmt):
    if selected_output_fmt == "Custom output format":
        st.text("For 'Custom output format', the output will depend on your specification below. Use the text area below to descibe each output column you'd like. Use the table to below to reiterate the column names.")
        st.text("The 'Variable name' column will be included by default. Do not mention it in the text area below. If you specified a 'Variable description' or 'context' above, those will be included in a separate tab. Do not include those columns below.")
    else:
        preview_img_path = get_site_content_path(f"{selected_output_fmt}.png", "imgs")
        st.image(preview_img_path, caption=f"Selected: {selected_output_fmt}", use_container_width=True)

def update_var_spec_df_from_csv():
    csv_file = st.session_state["csv_upload"]
    if csv_file is not None:
        try:
            df = pd.read_csv(csv_file)
            required_cols = ["variable_name", "variable_description"]
            optional_cols = ["context",  "variable_group"]
            improper_csv = False
            if len([c for c in df.columns if c in required_cols]) < len(required_cols):
                improper_csv = True
            if len([c for c in df.columns if c not in required_cols + optional_cols]) > 0:
                improper_csv = True
            if improper_csv:
                st.warning("Improper format: CSV must include a header row and include the required columns: {required_cols}.")
            else:
                if "variable_group" in list(df.columns):
                    if st.session_state["variable_groups_included"] == False:
                        st.session_state["variable_groups_included"] = True
                else:
                    if st.session_state["variable_groups_included"] == True: 
                        st.session_state["variable_groups_included"] = False 
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
    if "variable_specification_parameters" not in st.session_state:
        st.session_state["variable_specification_parameters"] = [
            "variable_name",
            "variable_description",
            "context",
        ]
    variables_df = st.session_state["variables_df"]
    variables_df_cols = st.session_state["variable_specification_parameters"]
    div = st.container()
    btn1, btn2, btn3, btn4 = st.columns([1, 1, 1, 1])
    with btn1:
        st.button("Clear", on_click=clear_variables)
    with btn2:
        with st.popover("Populate with..."):
            st.button("SDGs", on_click=populate_with_SDGs)
            st.button("Just-Transition Themes", on_click=populate_with_just_transition)
    with btn3:
        with st.popover("Add grouping column"):
            st.markdown("Add an initial column to the variable specification table above for grouping variables. " \
                "This column cannot be used in the AI query or main query template above. It is mainly used for organizing the inputs and formatting the output.")
            show_group = st.checkbox("Include variable groupings", key="variable_groups_included")
            group_col_name = "variable_group"
            if show_group and group_col_name not in variables_df.columns:
                variables_df.insert(0, group_col_name, ['']*len(variables_df))
                if group_col_name not in variables_df_cols:
                    variables_df_cols.insert(0, group_col_name)
                st.session_state["variable_specification_parameters"] = variables_df_cols
                st.session_state["variables_df"] = variables_df
            elif not show_group and group_col_name in variables_df.columns:
                if group_col_name in list(variables_df.columns):
                    variables_df = variables_df.drop(columns=[group_col_name])
                if group_col_name in variables_df_cols:
                    variables_df_cols.remove(group_col_name)
                st.session_state["variable_specification_parameters"] = variables_df_cols
                st.session_state["variables_df"] = variables_df
    with btn4:
        with st.popover("📤 Upload CSV"):
            st.file_uploader(
                "Choose a CSV file (headers optional, 2 or 3 columns):",
                type=["csv"],
                key="csv_upload",
                on_change=update_var_spec_df_from_csv
            )
    for c in variables_df.columns:
        if c not in variables_df_cols:
            variables_df_cols.append(c)
            st.session_state["variable_specification_parameters"] = variables_df_cols
    with div:
        st.session_state["schema_table"] = st.data_editor(
            variables_df,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_order=st.session_state["variable_specification_parameters"],
        )
    with st.expander("Advanced settings"):
        st.selectbox(
            "Optional: specify the overall operation type",
            list(get_task_types().keys()),
            key="task_type",
        )
        var_names = list(st.session_state["schema_table"]["variable_name"].to_list())
        col_output_fmt_select_1, col_output_fmt_select_2 = st.columns([7,1])
        with col_output_fmt_select_1:
            options = get_formatter_type_with_labels(st.session_state["task_type"])
            if "output_format" not in st.session_state:
                st.session_state["output_format"] = list(options.keys())[1]
            st.selectbox(
                "Optional: select format of output table for each document",
                options.keys(),
                key="output_format",
            )
        with col_output_fmt_select_2:
            st.markdown("<div style='padding-top:24px'></div>", unsafe_allow_html=True)
            if st.button("🛈"):
                display_output_fmt_preview(st.session_state["output_format"])
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
        elif output_fmt_selected == "custom_output_fmt":
            st.session_state["custom_output_fmt_instructions"] = st.text_area(
                "Enter your custom output instructions. 'Variable name' (from the table above) will automatically be included. Don't mention it here.", height=100
            )
            if 'custom_output_columns' not in st.session_state:
                # Create the initial DataFrame with 2 columns and 1 data row
                initial_data = {
                    "Output Column 1": ["Variable name"],
                    "Output Column 2": ["Response"],
                }
                st.session_state["custom_output_columns"] = pd.DataFrame(initial_data)
            st.text("Enter the custom column names described in the text area above.")
            custom_output_col_table_div = st.container()              
            col1, col2 = st.columns(2)
            with col1:
                with st.form("add_output_column_form"):
                    new_column_name = st.text_input("Enter new column name")
                    submitted = st.form_submit_button("➕ Add Column")
                if submitted:
                    if new_column_name and new_column_name not in st.session_state["custom_output_columns"].iloc[0].tolist():
                        id_col = len(st.session_state["custom_output_columns"].keys()) + 1
                        f"Output Column {id_col}"
                        st.session_state["custom_output_columns"][f"Output Column {id_col}"] = new_column_name
                    elif not new_column_name:
                        st.warning("Please enter a name for the new column.")
                    else:
                        st.warning(f"Column '{new_column_name}' already exists.")
            with col2:
                with st.form("remove_column_form"):
                    disable_remove = len(st.session_state["custom_output_columns"].columns) <= 2
                    columns_to_remove = st.selectbox(
                        "Select columns to remove",
                        options=[""] + st.session_state["custom_output_columns"].columns[1:],
                        help="You cannot remove columns if only two remain.",
                        disabled=disable_remove
                    )
                    submitted = st.form_submit_button(
                        "➖ Remove Column",
                        disabled=disable_remove,
                    )
                    if submitted:
                        if not columns_to_remove:
                            st.warning("Please select one or more columns to remove.")
                        else:
                            st.session_state["custom_output_columns"] = st.session_state["custom_output_columns"].drop(columns=columns_to_remove)
                            edited_df = st.session_state["custom_output_columns"]
                            new_df = {}
                            for i, col_name in enumerate(edited_df):
                                new_df[f"Column Name {i+1}"] = edited_df[col_name]
                            edited_df = pd.DataFrame(new_df)
                            st.session_state["custom_output_columns"] = edited_df
            with custom_output_col_table_div:
                edited_df = st.data_editor(
                    st.session_state["custom_output_columns"],
                    hide_index=True,
                    disabled=["Output Column 1"],
                    use_container_width=True
                )  
                st.session_state["custom_output_columns"] = edited_df  
            if not edited_df.equals(st.session_state["custom_output_columns"]):
                st.session_state["custom_output_columns"] = edited_df
                st.toast("Changes saved!")
            """
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
            """


def process_table():
    df = st.session_state["schema_table"]
    df = df.fillna("")
    num_cols = df.shape[1]
    df["variable_name"] = df["variable_name"].replace("", pd.NA)
    df.dropna(subset=["variable_name"], inplace=True)
    df = df[df["variable_name"].notnull()]
    return {
        row["variable_name"]: {
            "variable_description": row["variable_description"],
            **({"context": row["context"]} if "context" in df.columns else {}),
            **({"variable_group": row["variable_group"]} if "variable_group" in df.columns else {}),
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
        st.session_state["gpt_model"] = "gpt-4.1"  # Default model
    model_options = {
        "gpt-4.1": "GPT-4.1 (recommended - fast)",
        "gpt-4o": "GPT-4o (fast and capable)",
        "gpt-4o-mini": "GPT-4o mini (faster, cheaper)",
        "gpt-4-turbo": "GPT-4 Turbo",
        "gpt-3.5-turbo": "GPT-3.5 Turbo (fastest, cheapest)",
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
        st.session_state["output_format_options"] = get_formatter_type_with_labels(st.session_state["task_type"])
    if "pdfs" not in st.session_state:
        st.session_state["pdfs"] = "no_upload"
    if "schema_input_format" not in st.session_state:
        st.session_state["schema_input_format"] = "Manual Entry"
    if "output_format" not in st.session_state:
        st.session_state["output_format"] = list(
            st.session_state["output_format_options"].keys()
        )[1]
    if "custom_output_fmt_instructions" not in st.session_state:
        st.session_state["custom_output_fmt_instructions"] = None
    if "output_detail_df" not in st.session_state:
        st.session_state["output_detail_df"] = None
    input_data_specs()
    st.divider()
    st.markdown(
        "For variables with short descriptions, processing time will be about 1 minute per 100 PDF pages per variable (with default model selection)."
    )
    select_gpt_model()
    input_email()

def check_file_size(file_contents: bytes):
    """
    Check file size and estimate encoded size.

    Returns:
        tuple: (size_mb, encoded_size_mb, is_too_large)
    """
    size_bytes = len(file_contents)
    size_mb = size_bytes / (1024 * 1024)
    # Base64 encoding increases size by ~33%
    encoded_size_mb = size_mb * 1.33
    # Use 25 MB threshold (Resend limit is 40 MB, leaves buffer)
    is_too_large = encoded_size_mb > 25
    return size_mb, encoded_size_mb, is_too_large


def send_single_email(file_contents: bytes, recipient_email: str, filename="results.xlsx", subject_suffix=""):
    """
    Send a single email with attachment.

    Returns:
        tuple: (success: bool, error_message: str or None)
    """
    resend.api_key = get_secret("resend_apikey")
    encoded = base64.b64encode(file_contents).decode("utf-8")

    try:
        resp = resend.Emails.send({
            "from": get_secret("email"),
            "to": [recipient_email],
            "subject": f"Results: GPT Batch Policy Processor (Beta){subject_suffix}",
            "html": "Attached is the document you requested.",
            "attachments": [
                {
                    "filename": filename,
                    "content": encoded,
                    "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                }
            ],
        })
        print(f"Email sent successfully, id: {resp.get('id')}")
        return True, None
    except Exception as e:
        error_msg = str(e)
        print(f"Error sending email: {error_msg}")
        return False, error_msg


def email_results(output_file_contents: bytes, recipient_email: str):
    """
    Email results to user. Handles large files by splitting if needed.
    Priority: Ensure user receives SOMETHING even if full data can't be sent.
    """
    print(f"Preparing to email results to {recipient_email}")

    # Check file size
    size_mb, encoded_size_mb, is_too_large = check_file_size(output_file_contents)
    print(f"File size: {size_mb:.2f} MB (encoded: {encoded_size_mb:.2f} MB)")

    if not is_too_large:
        # Simple case: file is small enough, send as-is
        print("File is within size limit, sending single email")
        success, error = send_single_email(output_file_contents, recipient_email)
        if not success:
            print(f"CRITICAL: Failed to send email: {error}")
            print("User will NOT receive results via email")
        return

    # File is too large - need to split
    print(f"WARNING: File is too large ({encoded_size_mb:.2f} MB). Attempting to split...")

    try:
        # Attempt to split workbook
        split_parts = split_workbook_by_sheets(output_file_contents)
        total_parts = len(split_parts)

        print(f"Split workbook into {total_parts} part(s)")

        # Send each part
        successful_parts = []
        failed_parts = []

        for part_num, (part_bytes, description) in enumerate(split_parts, 1):
            part_size_mb, part_encoded_mb, part_too_large = check_file_size(part_bytes)

            print(f"Part {part_num}/{total_parts} ({description}): {part_size_mb:.2f} MB")

            if part_too_large:
                print(f"WARNING: Part {part_num} is still too large ({part_encoded_mb:.2f} MB)")
                # Try to send anyway - Resend will reject if truly too large

            subject_suffix = f" - Part {part_num} of {total_parts}"
            filename = f"results_part_{part_num}_of_{total_parts}.xlsx"

            success, error = send_single_email(part_bytes, recipient_email, filename, subject_suffix)

            if success:
                successful_parts.append((part_num, description))
                print(f"✓ Part {part_num} sent successfully")
            else:
                failed_parts.append((part_num, description, error))
                print(f"✗ Part {part_num} FAILED: {error}")

        # Summary
        print(f"\n=== EMAIL SUMMARY ===")
        print(f"Total parts: {total_parts}")
        print(f"Successful: {len(successful_parts)}")
        print(f"Failed: {len(failed_parts)}")

        if successful_parts:
            print(f"User will receive {len(successful_parts)} email(s) with partial results")

        if failed_parts:
            print(f"WARNING: {len(failed_parts)} part(s) failed to send:")
            for part_num, desc, error in failed_parts:
                print(f"  - Part {part_num} ({desc}): {error}")
            print("User will NOT receive complete results")

    except Exception as e:
        # If splitting completely fails, try sending original file anyway
        print(f"CRITICAL: Failed to split workbook: {e}")
        import traceback
        traceback.print_exc()

        print("Attempting to send original file as fallback...")
        success, error = send_single_email(output_file_contents, recipient_email)

        if success:
            print("Fallback successful: Original large file sent (may fail at Resend)")
        else:
            print(f"CRITICAL FAILURE: Cannot send email at all: {error}")
            print("User will NOT receive any results via email")


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
    elif output_fmt == "custom_output_fmt":
        additional_info = {
            "custom_output_fmt_instructions": st.session_state["custom_output_fmt_instructions"],
            "custom_output_columns": st.session_state["custom_output_columns"].iloc[0].tolist(),
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
