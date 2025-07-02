from openai import OpenAI
import os
from log_config import logger

def new_openai_session(openai_apikey):
    try:
        os.environ["OPENAI_API_KEY"] = openai_apikey
        client = OpenAI()
        max_num_chars = 25000
        return client, max_num_chars

    except Exception as e:
        logger.exception(f"Failed to initialize OpenAI session: {e}")
        raise


def create_gpt_messages(query, run_on_full_text):
    try:
        text_label = "collection of text excerpts"
        if run_on_full_text:
            text_label = "document"
        system_command = (
            "Use the provided "
            + text_label
            + " delimited by triple quotes to respond to instructions delimited with XML tags. "
            "Be precise…"
        )
        msgs = [
            {"role": "system", "content": system_command},
            {"role": "user", "content": query},
        ]
        return msgs

    except Exception as e:
        logger.exception(f"Error building GPT message payload: {e}")
        raise

def chat_gpt_query(gpt_client, gpt_model, resp_fmt, msgs):
    print(gpt_model)
    try: 
        if gpt_model == "gpt-4.1":
            response = gpt_client.chat.completions.create(
                model=gpt_model,
                temperature=0,
                response_format={"type": resp_fmt},
                messages=msgs,
            )
        else:
            response = gpt_client.chat.completions.create(
                model=gpt_model,
                response_format={"type": resp_fmt},
                messages=msgs,
            )
        return response.choices[0].message.content
    except Exception as e:
        logger.exception(f"GPT query failed: {e}")
        raise



def fetch_variable_info(gpt_client, gpt_model, query, resp_fmt, run_on_full_text):
    try:
        msgs = create_gpt_messages(query, run_on_full_text)
        return chat_gpt_query(gpt_client, gpt_model, resp_fmt, msgs)
        """msgs.append({"role": "assistant", "content": init_response})
        follow_up_prompt = "<instructions>Based on the previous instructions, ensure that your response has included all correct answers and/or text excerpts. If your previous resposne is correct, return the same response. If there is more to add to your previous response, return the same format with the complete, correct response.</instructions>"
        msgs.append({"role": "user", "content": follow_up_prompt})
        follow_up_response = chat_gpt_query(gpt_client, gpt_model, resp_fmt, msgs)
        return follow_up_response"""
    except Exception as e:
        logger.exception(f"Failed to fetch variable info: {e}")
        raise


def query_gpt_for_variable_specification(
    gpt_analyzer,
    variable_name,
    var_spec,
    context,
    relevant_texts,
    run_on_full_text,
    gpt_client,
    gpt_model="o4-mini",
):
    try:
        query_template = gpt_analyzer.main_query
        excerpts = "\n".join(relevant_texts)
        main_query = f"{query_template.format(variable_name=variable_name, variable_description=var_spec, context=context)} \n\n"
        main_query = gpt_analyzer.optional_add_categorization(variable_name, main_query)
        output_prompt = gpt_analyzer.output_fmt_prompt(variable_name)
        if len(output_prompt) > 1:
            output_prompt = " " + output_prompt
        prompt = f'<instructions>{main_query}.{output_prompt}</instructions> \n\n """{excerpts}"""'
        resp_fmt = gpt_analyzer.resp_format_type()
        return fetch_variable_info(
            gpt_client, gpt_model, prompt, resp_fmt, run_on_full_text
        )
    except Exception as e:
        logger.exception(f"Error querying variable “{variable_name}”: {e}")
        raise