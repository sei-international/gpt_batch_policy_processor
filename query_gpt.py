from openai import OpenAI
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
        temperature=0
    )
    return response.choices[0].message.content

def query_gpt_for_column(main_query, col_nm, col_spec, context, relevant_texts, gpt_client, gpt_model):
    excerpts = '\n'.join(relevant_texts)
    prompt = f"{main_query.format(variable_name=col_nm, variable_description=col_spec, context=context)} \n\n Text excerpts: {excerpts}"
    prompt = f"From the following text, {prompt[0].lower()}{prompt[1:]}"
    return fetch_column_info(gpt_client, gpt_model, prompt)