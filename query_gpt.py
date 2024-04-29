from openai import OpenAI
import json
import os

def new_openai_session(openai_apikey):
    os.environ["OPENAI_API_KEY"] = openai_apikey
    client = OpenAI()
    gpt_model = "gpt-4-1106-preview"
    max_num_chars = 400000
    return client, gpt_model, max_num_chars

def create_gpt_messages(query):
    return [
        {"role": "system", "content": "You extract requested pieces of information from a national climate policy document."},
        {"role": "user", "content": query}
    ]

def fetch_column_info(gpt_client, gpt_model, query):
    response = gpt_client.chat.completions.create(
        model=gpt_model,
        messages=create_gpt_messages(query),
        temperature=0,
        response_format={ "type": "json_object" }
    )
    return json.loads(response.choices[0].message.content)

def query_gpt_for_column(gpt_analyzer, variable_name, col_spec, context, relevant_texts, gpt_client, gpt_model):
    query_template = gpt_analyzer.main_query
    excerpts = '\n'.join(relevant_texts)
    main_query = f"{query_template.format(variable_name=variable_name, variable_description=col_spec, context=context)} \n\n"
    output_fmt_prompt = f"Return your response in the following json format: \n{gpt_analyzer.gpt_output_fmt()}"
    prompt = f"From the following text excerpts, {main_query[0].lower()}{main_query[1:]}. \n\n {output_fmt_prompt} \n\n Text excerpts: {excerpts}"
    return fetch_column_info(gpt_client, gpt_model, prompt)