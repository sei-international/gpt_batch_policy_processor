import json

class OutputFormatter():
    def __init__(self, additional_info):
        self.additional_info = additional_info
    def output_fmt_prompt(self, var_name, base_intruction):
        pass
    def optional_add_categorization(self, var_name, query):
        return query
    def get_results(self, policy_info):
        pass
    def format_gpt_response(self, resp):
        return json.loads(resp)["list_resp"]
    def get_output_headers(self):
        return ["Variable", "Response"]
    def resp_format_type(self):
        return "json_object"

class RawFormatter(OutputFormatter):
    def __init__(self, additional_info):
        super().__init__(additional_info)
    def output_fmt_prompt(self, var_name, base_intruction):
        return base_intruction
    def get_results(self, policy_info):
        resp_vals_fmt = {}
        for var_name, gpt_resp_vals in policy_info.items():
            resp_vals_fmt[var_name] = {
                self.get_output_headers()[1]: gpt_resp_vals
            }
        return resp_vals_fmt
    def format_gpt_response(self, resp):
        return resp
    def get_output_headers(self):              
        return ["Variable", self.optional_resp_col]
    def resp_format_type(self):
        return "text"

class StructuredFormatter(OutputFormatter):
    def __init__(self, additional_info):
        super().__init__(additional_info)
    def output_fmt_prompt(self, var_name, base_instruction):
        output_fmt_str = f"{base_instruction} in the following json format: "
        output_json_fmt = {
            "list_resp": [{self.optional_resp_col: "...", "page_number(s)": "...", "justification": "..."}],
        }
        return output_fmt_str + str(output_json_fmt).replace("]}", ", ...]}")
    def get_results(self, policy_info):
        all_quotes = {}
        for var_name, quotes_json in policy_info.items():
            quotes_for_var, justifications = [], []
            for quote_json in quotes_json:
                quotes_for_var.append(f"{quote_json[self.optional_resp_col]} (page {quote_json['page_number(s)']})")
                justifications.append(quote_json["justification"])
            all_quotes[var_name] = {self.get_output_headers()[1]: quotes_for_var, self.get_output_headers()[2]: justifications}
        return all_quotes
    def get_output_headers(self):               
        return ["Variable",  self.optional_resp_col, "Justification"]

class CustomFormatter(OutputFormatter):
    def __init__(self, additional_info):
        super().__init__(additional_info)
    def output_fmt_prompt(self, var_name, base_instruciton):
        #df = self.additional_info["output_detail"]
        #output_detail = df.loc[df["variable_name"] == var_name, "output_detail"].values[0]
        output_json_fmt = {k:"..." for k in self.get_output_headers() if k != "Variable name"}
        output_json_fmt_str = str(output_json_fmt).replace("]}", ", ...]}")
        return f"Return a json object formatted as {output_json_fmt_str} according to the following instructions: \n {self.additional_info['custom_output_fmt_instructions']} \n"
        #.replace("{output_detail}", output_detail)
    def get_results(self, policy_info):
        return policy_info
    def format_gpt_response(self, resp):
        return json.loads(resp)
    def resp_format_type(self):
        return "json_object"
    def get_output_headers(self):  
        return self.additional_info["custom_output_columns"]

def is_similar_quote(q1, q2):
    q1, q2 = q1.lower().strip(), q2.lower().strip()
    return q1 in q2 or q2 in q1 or q1 == q2 or q1 is q2

def get_results_with_sorted_quotes(policy_info, additional_info, output_headers, optional_resp_col, is_labelled):
    temp_quotes = []
    all_quotes = {}
    for var_name, quotes_json in policy_info.items():
        for quote_json in quotes_json:
            curr_quote = (
                f"{quote_json[optional_resp_col]} (page {quote_json['page_number(s)']})"
            )
            subcat_vals = None
            if is_labelled:
                subcats = additional_info.columns[1:]
                subcat_vals = [
                    quote_json[f"relevant_{subcat.replace(' ', '_').lower()}"]
                    for subcat in subcats
                ]
            found_similar = False
            for i, found_quote_val_list in enumerate(temp_quotes):
                existing_quote, var_names = (
                    found_quote_val_list[0],
                    found_quote_val_list[1],
                )
                if is_similar_quote(curr_quote, existing_quote):
                    add_labels_to_quote = [
                        existing_quote,
                        f"{var_names}, {var_name}",
                    ]
                    if subcat_vals:
                        for i, subcat_val in enumerate(subcat_vals):
                            add_labels_to_quote.append(
                                f"{found_quote_val_list[i+1]}, {subcat_val}"
                            )
                    temp_quotes[i] = add_labels_to_quote
                    found_similar = True
                    break
            if not found_similar:
                labels_for_quote = [curr_quote, var_name]
                if subcat_vals:
                    for subcat_val in subcat_vals:
                        labels_for_quote.append(subcat_val)
                temp_quotes.append(labels_for_quote)
    for quote_val_list in temp_quotes:
        quote, var_names = quote_val_list[0], quote_val_list[1]
        all_quotes[quote] = {output_headers[1]: var_names}
        if is_labelled:
            for i, var_name in enumerate(additional_info.columns[1:]):
                all_quotes[quote][var_name] = quote_val_list[i + 2]
    return all_quotes


class sortedFormatter(OutputFormatter):
    def __init__(self, additional_info):
        super().__init__(additional_info)
    def output_fmt_prompt(self, var_name, base_instruction):
        output_json_fmt = {
            "list_resp": [{self.optional_resp_col: "...", "page_number(s)": "..."}]
        }
        output_fmt_str = str(output_json_fmt).replace("]}", ", ...]}")
        return f"Return your response in the following json format: \n {output_fmt_str}"   
    def get_results(self, policy_info):
        return get_results_with_sorted_quotes(policy_info, self.additional_info, self.get_output_headers(), self.optional_resp_col, False)
    def get_output_headers(self):               
        return [self.optional_resp_col, "Relevant Variables"]

class sortedAndLabelledFormatter(OutputFormatter):
    def __init__(self, additional_info):
        super().__init__(additional_info)
    def output_fmt_prompt(self, var_name, base_instruction):
        output_json_fmt = {
            "list_resp": [{self.optional_resp_col: "...", "page_number(s)": "..."}]
        }
        for col in self.additional_info.columns[1:]:
            label = f"relevant_{col.lower().replace(' ', '_')}"
            output_json_fmt["list_resp"][0][label] = "..."
        output_fmt_str = str(output_json_fmt).replace("]}", ", ...]}")
        return f"Return your response in the following json format: \n {output_fmt_str}"    
    def optional_add_categorization(self, var_name, query):
        row = self.additional_info[
            self.additional_info["variable_name"] == var_name
        ].iloc[0]
        subcat_label1 = self.additional_info.columns[1]
        query += f"For each relevant quote, select which {subcat_label1} it addresses from the following list ({row[subcat_label1]})"
        if len(self.additional_info.columns) > 2:
            if self.additional_info.columns[2]:
                subcat_label2 = self.additional_info.columns[1]
                query += f" and which {subcat_label2} it addresses from the following list ({row[subcat_label1]})"
        query += "."
        return query
    def get_results(self, policy_info):      
        return get_results_with_sorted_quotes(policy_info, self.additional_info, self.get_output_headers(), self.optional_resp_col, True)
    def get_output_headers(self):               
        headers = [self.optional_resp_col, "Relevant Variables"]
        for subcat_header in self.additional_info.columns[1:]:
            headers.append(subcat_header)
        return headers

def get_formatter_types(task_type=None):
    formatters = {
        "quotes_structured": {
            "label": "Return list of text excerpts per variable", 
            "class": StructuredFormatter
        },
        "quotes_gpt_resp": {
            "label": "Return raw GPT responses for each variable",
            "class": RawFormatter
        },
        "quotes_sorted": {
            "label": "Sort by quotes; each quote will be one row", 
            "class": sortedFormatter
        },
        "quotes_sorted_and_labelled": {
            "label": "Sort by quotes labelled with variable_name and subcategories", 
            "class": sortedAndLabelledFormatter
        },
        "custom_output_fmt":  {
            "label": "Custom output format", 
            "class": CustomFormatter
        }
    }
    formatters_for_each_task_type = {
         "Quote extraction": ["quotes_gpt_resp", "quotes_structured", "quotes_sorted", "quotes_sorted_and_labelled", "custom_output_fmt"],  
         "Targeted summaries": ["quotes_gpt_resp", "custom_output_fmt"]
    }
    if task_type==None:
        return formatters
    else:
        relevant_formatter_keys = formatters_for_each_task_type[task_type]
        relevant_formatters = {}
        for k in relevant_formatter_keys:
            relevant_formatters[k] = formatters[k]
        return relevant_formatters

def get_formatter_type_with_labels(task_type):
    formatters = get_formatter_types(task_type)
    return {formatters[f]["label"]:f for f in formatters}

def get_formatter(task_type, output_fmt, additional_info):
    formatter_type = get_formatter_types(task_type)[output_fmt]["class"]
    return formatter_type(additional_info)
