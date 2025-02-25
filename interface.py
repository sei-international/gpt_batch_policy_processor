from analysis import get_analyzer, get_task_types

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


def load_text():
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
    st.markdown("""## Submit your processing request""")


def upload_zip(temp_dir):
    st.subheader("I. Upload Zipfile of PDF's")
    uploaded_zip = st.file_uploader(
        "Compress a folder with your documents into a zip-file. The zip-file must have the same name as the folder. The folder must only contain PDF's; no subfolders allowed.",
        type="zip",
    )
    st.markdown(
        "*Please note: uploaded documents will be procesed by OpenAI and may be used to train futher models. If you are concerned about the confidentiality of your documents, please contact us before use.*"
    )
    if uploaded_zip is not None:
        st.success(
            """Zip-file uploaded successfully! \n
Please first run on a subset of PDF's to fine-tune functionality. Careless processing causes avoidable AI-borne GHG emissions.""",
            icon="✅",
        )
        pdfs = []
        with NamedTemporaryFile(delete=False, suffix=".zip") as temp_zip:
            temp_zip.write(uploaded_zip.getvalue())
            st.session_state["temp_zip_path"] = temp_zip.name
        with zipfile.ZipFile(st.session_state["temp_zip_path"], "r") as zip_ref:
            zip_ref.extractall(temp_dir)
        for subdir in os.listdir(temp_dir):
            subdir_path = os.path.join(temp_dir, subdir)
            for filename in os.listdir(subdir_path):
                if filename.endswith(".pdf"):
                    file_path = os.path.join(subdir_path, filename)
                    pdfs.append(file_path)
        st.session_state["pdfs"] = pdfs
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
            st.markdown(
                "After fine-tuning the main query template and variable definitions below, you may run the "
                "Tool for all policy documents of interest. Please contact william.babis@sei.org for access."
            )
            passcode = st.text_input("Enter passcode")
            if passcode:
                apikey_ids = {
                    st.secrets["access_password"]: "openai_apikey",
                    st.secrets["access_password_adis"]: "openai_apikey_adis",
                    st.secrets["access_password_sharone"]: "openai_apikey_sharone",
                    st.secrets["access_password_bb"]: "openai_apikey_bb",
                }
                if passcode in apikey_ids:
                    st.session_state["apikey_id"] = apikey_ids[passcode]
                    st.session_state["is_test_run"] = False
                    st.session_state["max_files"] = None
                    st.session_state["file_select_label"] = (
                        "Select any number of PDFs to analyze. Or, uncheck 'Run on Subset' to analyze all uploaded PDFs"
                    )
                    st.success(
                        "Access granted. All PDFs in the zip-file will be processed. Please proceed.",
                        icon="✅",
                    )
                else:
                    st.error(
                        "Incorrect password. Click 'Run on subset' above. The 1-3 documents specified will be processed.",
                        icon="❌",
                    )


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
        "**Type-in variable details or copy-and-paste from an excel spreadsheet (3 columns, no headers).**"
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
    btn1, btn2, btn3 = st.columns([1, 1, 1])
    with btn1:
        st.button("Clear", on_click=clear_variables)
    with btn2:
        st.button("Populate with SDGs", on_click=populate_with_SDGs)
    with btn3:
        st.button(
            "Use Just-Transition Themes",
            on_click=populate_with_just_transition,
            use_container_width=True,
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


def input_email():
    st.markdown(
        "For variables with short descriptions, processing time will be about 1 minute per 100 pdf-pages per variable."
    )
    st.session_state["email"] = st.text_input(
        "Enter your email where you'd like to recieve the results:"
    )


def build_interface(tmp_dir):
    if "task_type" not in st.session_state:
        st.session_state["task_type"] = "Quote extraction"
    if "is_test_run" not in st.session_state:
        st.session_state["is_test_run"] = True
    load_text()
    upload_zip(tmp_dir)
    input_main_query()
    if "output_format_options" not in st.session_state:
        st.session_state["output_format_options"] = {
            "Sort by quotes; each quote will be one row": "quotes_sorted",
            "Simply return GPT responses for each variable": "quotes_gpt_resp",
            "Sort by quotes labelled with variable_name and subcategories": "quotes_sorted_and_labelled",
            "Return list of quotes per variable": "quotes_structured",
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
    input_email()


def email_results(docx_fname, recipient_email):
    message = Mail(
        from_email=st.secrets["email"],
        to_emails=recipient_email,
        subject="Results: GPT Batch Policy Processor (Beta)",
        html_content="Attached is the document you requested.",
    )
    with open(docx_fname, "rb") as f:
        file_data = f.read()
        f.close()
    encoded_file = base64.b64encode(file_data).decode()
    attachedFile = Attachment(
        FileContent(encoded_file),
        FileName("results.docx"),
        FileType("application/docx"),
        Disposition("attachment"),
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
    return get_analyzer(
        task_type, output_fmt, pdfs, main_query, variable_specs, email, additional_info
    )


def display_output(docx_fname):
    with open(docx_fname, "rb") as f:
        binary_file = f.read()
        st.download_button(
            label="Download Results",
            data=binary_file,
            file_name="results.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
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
