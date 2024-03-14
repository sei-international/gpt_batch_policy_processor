from openai import OpenAI
import os

def new_openai_session():
    os.environ["OPENAI_API_KEY"] = "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"
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

def query_gpt_for_column(main_query, col_nm, col_spec, relevant_texts, gpt_client, gpt_model):
    excerpts = '\n'.join(relevant_texts)
    prompt = main_query.format(excerpts=excerpts, column_name=col_nm, column_description=col_spec)
    return fetch_column_info(gpt_client, gpt_model, prompt)