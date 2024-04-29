class GPTAnalyzer:
    def __init__(self, pdfs, main_query, variable_specs, email, output_fmt):
        self.pdfs = pdfs
        self.main_query = main_query
        self.variable_specs = variable_specs
        self.email = email
        self.output_fmt = output_fmt
    
    def __str__(self):
        class_name = self.__class__.__name__
        return f"{class_name} -- PDFS: {self.pdfs}, Main Query: {self.main_query}, Variables: {self.variable_specs}, Email: {self.email}"

    def gpt_output_fmt(self):
        pass

    def format_gpt_response(self, resp):
        pass

    def output_results(self, policy_info):
        var_names = list(policy_info.keys())
        gpt_row = []
        for var_name, var_val in policy_info.items():
            if var_val.count('"')==2 and var_val[0]=='"' and var_val[-1]=='"':
                var_val = var_val[1:-1]
            if len(var_val) > len(var_name):
                if var_val[:len(var_name)] == var_name:
                    var_val = var_val.replace(f"{var_name}: ", "", 1) 
            gpt_row.append(var_val)
        return var_names, gpt_row

    def get_output_headers(self):
        return ["Variable Name", "GPT Response"]

class DefaultAnalyzer(GPTAnalyzer):
    def __init__(self, pdfs, main_query, variable_specs, email, output_fmt):
        super().__init__(pdfs, main_query, variable_specs, email, output_fmt) 

    def gpt_output_fmt(self):
        return "{'value': '...', 'relevant_page_numbers': '...'}"

    def format_gpt_response(self, resp):
        return f"{resp['value']} [page(s) {resp['relevant_page_numbers']}]" 

class QuoteAnalyzer(GPTAnalyzer):
    def __init__(self, pdfs, main_query, variable_specs, email, output_fmt):
        super().__init__(pdfs, main_query, variable_specs, email, output_fmt) 

    def gpt_output_fmt(self):
        if self.output_fmt:
            return "{'list_of_quotes': [{'quote': '...', 'page_number': '...', 'explanation': '...'}, ...]}"
        else:
            return "{'value': '...',  'relevant_page_numbers': '...'}"
    
    def format_gpt_response(self, resp):
        if self.output_fmt:
            return resp["list_of_quotes"]
        else:
            return resp['value']

    def output_results(self, policy_info):
        def is_similar_quote(q1, q2):
            q1, q2 = q1.lower().strip(), q2.lower().strip()
            return q1 in q2 or q2 in q1 or q1==q2 or q1 is q2
        temp_quotes = []
        all_quotes = {}
        for var_name, quotes_json in policy_info.items():
            for quote_json in quotes_json:
                curr_quote = f"{quote_json['quote']} [page {quote_json['page_number']}]"
                found_similar = False
                for i, (existing_quote, names) in enumerate(temp_quotes):
                    if is_similar_quote(curr_quote, existing_quote):
                        temp_quotes[i] = (existing_quote, f"{names}, {var_name}")
                        found_similar = True
                        break
                if not found_similar:
                    temp_quotes.append((curr_quote, var_name))
        for quote, names in temp_quotes:
            all_quotes[quote] = names    
        return list(all_quotes.keys()), list(all_quotes.values())  
    
    def get_output_headers(self):
        return ["Quote", "Related Variables"]


def get_task_types():
    return {
        "Targeted inquiries": DefaultAnalyzer, 
        "Quote extraction": QuoteAnalyzer
    }

def get_analyzer(task_type, output_fmt, pdfs, main_query, variable_specs, email):
    task_analyzer_class = get_task_types()[task_type]
    return task_analyzer_class(pdfs, main_query, variable_specs, email, output_fmt)
