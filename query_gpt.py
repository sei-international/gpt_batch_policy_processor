from openai import OpenAI
import os

def new_openai_session(openai_apikey):
    os.environ["OPENAI_API_KEY"] = openai_apikey
    client = OpenAI()
    gpt_model = "gpt-4-turbo"
    max_num_chars = 400000
    return client, gpt_model, max_num_chars

def create_gpt_messages(query):
    return [
        {"role": "system", "content": "You extract requested pieces of information from a national climate policy document."},
        {"role": "user", "content": query}
    ]

def fetch_column_info(gpt_client, gpt_model, query, resp_fmt):
    response = gpt_client.chat.completions.create(
        model=gpt_model,
        messages=create_gpt_messages(query),
        temperature=0,
        response_format={ "type": resp_fmt}
    )
    return response.choices[0].message.content

def query_gpt_for_column(gpt_analyzer, variable_name, col_spec, context, relevant_texts, gpt_client, gpt_model):
    query_template = gpt_analyzer.main_query
    excerpts = '\n'.join(relevant_texts)
    main_query = f"{query_template.format(variable_name=variable_name, variable_description=col_spec, context=context)} \n\n"
    main_query = gpt_analyzer.optional_add_categorization(variable_name, main_query)
    output_prompt = gpt_analyzer.output_fmt_prompt(variable_name)
    prompt = f'From the following text excerpts, {main_query[0].lower()}{main_query[1:]}. {output_prompt} \n\n Text excerpts: """{excerpts}"""'
    resp_fmt = gpt_analyzer.resp_format_type()
    return fetch_column_info(gpt_client, gpt_model, prompt, resp_fmt)