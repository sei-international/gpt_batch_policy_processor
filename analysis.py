import json

class GPTAnalyzer:
    def __init__(self, pdfs, main_query, variable_specs, email, output_fmt, additional_info):
        self.pdfs = pdfs
        self.main_query = main_query
        self.variable_specs = variable_specs
        self.email = email
        self.output_fmt = output_fmt
        self.additional_info = additional_info
    
    def __str__(self):
        class_name = self.__class__.__name__
        return f"{class_name} -- PDFS: {self.pdfs}, Main Query: {self.main_query}, Variables: {self.variable_specs}, Email: {self.email}"

    def output_fmt_prompt(self, var_name):
        pass

    def format_gpt_response(self, resp):
        pass
    
    def get_chunk_size(self):
        return 200

    ## policy_info: {var_name: gpt response from above function}
    ## returns: {row_id: {"col_name": val, ...}}
    def get_results(self, policy_info):
        gpt_responses = {}
        hdr = self.get_output_headers()[1]
        for var_name, var_val in policy_info.items():
            if var_val.count('"')==2 and var_val[0]=='"' and var_val[-1]=='"':
                var_val = var_val[1:-1]
            if len(var_val) > len(var_name):
                if var_val[:len(var_name)] == var_name:
                    var_val = var_val.replace(f"{var_name}: ", "", 1) 
            gpt_responses[var_name] = {hdr: var_val}
        return gpt_responses

    def get_output_headers(self):
        return ["Variable Name", "GPT Response"]
    
    def get_num_excerpts(self, num_pages):
        if num_pages<100:
            return 40
        else:
            return 40 + int(num_pages / 5.0)
    
    def optional_add_categorization(self, v_name, query):
        return query

    def resp_format_type(self):
        return "json_object"

class DefaultAnalyzer(GPTAnalyzer):
    def __init__(self, pdfs, main_query, variable_specs, email, output_fmt, additional_info):
        super().__init__(pdfs, main_query, variable_specs, email, output_fmt, additional_info) 

    def output_fmt_prompt(self, var_name):
        output_fmt_str = "{'value': '...', 'relevant_page_numbers': '...'}"
        return f"Return your response in the following json format: \n {output_fmt_str}"
    
    def format_gpt_response(self, resp):
        return f"{json.loads(resp)['value']} [page(s) {resp['relevant_page_numbers']}]" 


class CustomOutputAnalyzer(GPTAnalyzer):
    def __init__(self, pdfs, main_query, variable_specs, email, output_fmt, additional_info):
        super().__init__(pdfs, main_query, variable_specs, email, output_fmt, additional_info) 

    def output_fmt_prompt(self, var_name):
        df = self.additional_info["output_detail"]
        output_detail = df.loc[df["variable_name"] == var_name, "output_detail"].values[0]
        return self.additional_info["custom_output_fmt"].replace("{output_detail}", output_detail)
    
    def format_gpt_response(self, resp):
        return resp

    def resp_format_type(self):
        return "text"


class QuoteAnalyzer(GPTAnalyzer):
    def __init__(self, pdfs, main_query, variable_specs, email, output_fmt, additional_info):
        super().__init__(pdfs, main_query, variable_specs, email, output_fmt, additional_info) 

    def output_fmt_prompt(self, var_name):
        if self.output_fmt == "quotes_gpt_resp":
            return "Provide an exhaustive list of relevant quotes."
        else:
            output_json_fmt = {'list_of_quotes': [{'quote': '...', 'page_number': '...'}]}
            if self.output_fmt == "quotes_sorted_and_labelled":
                for col in self.additional_info.columns[1:]:
                    label = f"relevant_{col.lower().replace(' ', '_')}"
                    output_json_fmt["list_of_quotes"][0][label] = "..."
            output_fmt_str = str(output_json_fmt).replace("]}", ", ...}]")
            return f"Return your response in the following json format: \n {output_fmt_str}"
    
    def optional_add_categorization(self, var_name, query):
        if self.output_fmt=="quotes_sorted_and_labelled":
            row = self.additional_info[self.additional_info['variable_name'] == var_name].iloc[0]
            subcat_label1 = self.additional_info.columns[1]
            query += f"For each relevant quote, select which {subcat_label1} it addresses from the following list ({row[subcat_label1]})"
            if len(self.additional_info.columns) > 2:
                if self.additional_info.columns[2]:
                    subcat_label2 = self.additional_info.columns[1]
                    query += f" and which {subcat_label2} it addresses from the following list ({row[subcat_label1]})"
            query += "."
        return query

    ## Returns either an unstructured string or a json object list
    def format_gpt_response(self, resp):
        if self.output_fmt == "quotes_gpt_resp":
            print("RESP", resp)
            return resp
        else:  
            return json.loads(resp)["list_of_quotes"]

    ## policy_info: {var_name: gpt response from above function}
    ## returns: {row_id: {"col_name": val, ...}}
    def get_results(self, policy_info):
        if self.output_fmt == "quotes_gpt_resp":
            quotes = {}
            for var_name, relevant_quotes_gpt_resp in policy_info.items():
                quotes[var_name] = {self.get_output_headers()[1]: relevant_quotes_gpt_resp}
            return quotes
        elif self.output_fmt == "quotes_structured":
            all_quotes = {}
            for var_name, quotes_json in policy_info.items():
                quotes_for_var = ""
                ctr = 1
                for quote_json in quotes_json:
                    quotes_for_var += f"{str(ctr)}. {quote_json['quote']} [page {quote_json['page_number']}]. \n"
                    ctr+=1
                all_quotes[var_name] = {self.get_output_headers()[1]: quotes_for_var}
            return all_quotes
        else:
            def is_similar_quote(q1, q2):
                q1, q2 = q1.lower().strip(), q2.lower().strip()
                return q1 in q2 or q2 in q1 or q1==q2 or q1 is q2
            temp_quotes = []
            all_quotes = {}
            for var_name, quotes_json in policy_info.items():
                for quote_json in quotes_json:
                    curr_quote = f"{quote_json['quote']} [page {quote_json['page_number']}]"
                    subcat_vals = None
                    if self.output_fmt=="quotes_sorted_and_labelled":        
                        subcats = self.additional_info.columns[1:]            
                        subcat_vals = [quote_json[f"relevant_{subcat.replace(' ', '_').lower()}"] for subcat in subcats]
                    found_similar = False
                    for i, found_quote_val_list in enumerate(temp_quotes):
                        existing_quote, var_names = found_quote_val_list[0], found_quote_val_list[1]
                        if is_similar_quote(curr_quote, existing_quote):
                            add_labels_to_quote = [existing_quote, f"{var_names}, {var_name}"]
                            if subcat_vals:
                                for i, subcat_val in enumerate(subcat_vals):
                                    add_labels_to_quote.append(f"{found_quote_val_list[i+1]}, {subcat_val}")
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
                all_quotes[quote] = {self.get_output_headers()[1]: var_names}
                if self.output_fmt=="quotes_sorted_and_labelled": 
                    for i, col_name in enumerate(self.additional_info.columns[1:]):
                        all_quotes[quote][col_name] = quote_val_list[i+2]
            return all_quotes
        
    def get_output_headers(self):
        if self.output_fmt == "quotes_gpt_resp":
            return ["Variable", "Relevant Quotes"]
        else:
            headers = ["Quote", "Relevant Variables"]
            if self.output_fmt == "quotes_sorted_and_labelled":
                for subcat_header in self.additional_info.columns[1:]:
                    headers.append(subcat_header)
            return headers
    
    def get_chunk_size(self):
        return 200
        
    def get_num_excerpts(self, num_pages):
        return 40 + int(float(num_pages) / (5.0))
    
    def resp_format_type(self):
        return "text" if self.output_fmt == "quotes_gpt_resp" else "json_object"

class SummaryAnalyzer(GPTAnalyzer):
    def __init__(self, pdfs, main_query, variable_specs, email, output_fmt, additional_info):
        super().__init__(pdfs, main_query, variable_specs, email, output_fmt, additional_info) 
    
    def output_fmt_prompt(self, var_name):
        return ""
    
    def format_gpt_response(self, resp):
        print("FMT", resp)
        return resp
    
    def get_results(self, policy_info):
        resp = {}
        for var_name, r in policy_info.items():
            resp[var_name] = {self.get_output_headers()[1]: r}
        print("POLICY INFO", policy_info)
        print("RESP", resp)            
        return resp
    
    def get_output_headers(self):
        return ["Variable", "Summary"]
    
    def get_chunk_size(self):
        return 500
        
    def get_num_excerpts(self, num_pages):
        return 40 + int(float(num_pages) / (5.0))
    
    def resp_format_type(self):
        return "text"

def get_task_types():
    return {
        "Quote extraction": QuoteAnalyzer,
        "Custom output format": CustomOutputAnalyzer,
        "Targeted summaries": SummaryAnalyzer,
        "Targeted inquiries": DefaultAnalyzer
    }

def get_analyzer(task_type, output_fmt, pdfs, main_query, variable_specs, email, additional_info):
    task_analyzer_class = get_task_types()[task_type]
    return task_analyzer_class(pdfs, main_query, variable_specs, email, output_fmt, additional_info)
