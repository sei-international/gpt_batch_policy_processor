from openai import OpenAI
import os

def new_openai_session(openai_apikey):
    os.environ["OPENAI_API_KEY"] = openai_apikey
    client = OpenAI()
    gpt_model = "gpt-4o" #"o1-preview"
    max_num_chars = 100000
    return client, gpt_model, max_num_chars

def create_gpt_messages(query):
    system_command = "Use the provided collection of text excerpts delimited by triple quotes to respond to instructions delimited with XML tags. Be precise. Be accurate. Be exhaustive: do not cut off your response if the correct response requires more text. Be consistent with your responses to the same query."
    return [
        {"role": "system", "content": system_command},
        {"role": "user", "content": query}
    ]

def chat_gpt_query(gpt_client, gpt_model, resp_fmt, msgs):
    response = gpt_client.chat.completions.create(
        model=gpt_model,
        temperature=0,
        response_format={"type": resp_fmt},
        messages=msgs
    )
    return response.choices[0].message.content

def fetch_column_info(gpt_client, gpt_model, query, resp_fmt):
    msgs = create_gpt_messages(query)
    return chat_gpt_query(gpt_client, gpt_model, resp_fmt, msgs)
    """msgs.append({"role": "assistant", "content": init_response})
    follow_up_prompt = "<instructions>Based on the previous instructions, ensure that your response has included all correct answers and/or text excerpts. If your previous resposne is correct, return the same response. If there is more to add to your previous response, return the same format with the complete, correct response.</instructions>"
    msgs.append({"role": "user", "content": follow_up_prompt})
    follow_up_response = chat_gpt_query(gpt_client, gpt_model, resp_fmt, msgs)
    return follow_up_response"""

def query_gpt_for_column(gpt_analyzer, variable_name, col_spec, context, relevant_texts, gpt_client, gpt_model):
    query_template = gpt_analyzer.main_query
    excerpts = '\n'.join(relevant_texts)
    main_query = f"{query_template.format(variable_name=variable_name, variable_description=col_spec, context=context)} \n\n"
    main_query = gpt_analyzer.optional_add_categorization(variable_name, main_query)
    output_prompt = gpt_analyzer.output_fmt_prompt(variable_name)
    if len(output_prompt) > 1:
        output_prompt = " " + output_prompt
    prompt = f'<instructions>{main_query}.{output_prompt}</instructions> \n\n """{excerpts}"""'
    resp_fmt = gpt_analyzer.resp_format_type()
    return fetch_column_info(gpt_client, gpt_model, prompt, resp_fmt)