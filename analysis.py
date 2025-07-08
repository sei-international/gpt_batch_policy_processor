"""
This module contains classes and functions for analyzing GPT responses from PDFs.
It includes various analyzers for different types of tasks such as quote extraction,
custom output formatting, targeted summaries, and targeted inquiries.
"""

import json
from formatter import get_formatter


class GPTAnalyzer:
    """
    Base class for analyzing GPT responses from PDFs.
    """

    def __init__(
        self, pdfs, main_query, variable_specs, email, output_fmt, additional_info, gpt_model
    ):
        """
        Initializes the GPTAnalyzer with the given parameters.
        """
        self.pdfs = pdfs
        self.main_query = main_query
        self.variable_specs = variable_specs
        self.email = email
        self.formatter = get_formatter(self.label, output_fmt, additional_info)
        self.additional_info = additional_info
        self.gpt_model = gpt_model

    def __str__(self):
        """
        Returns a string representation of the GPTAnalyzer.
        """
        class_name = self.__class__.__name__
        return f"{class_name} -- PDFS: {self.pdfs}, Main Query: {self.main_query}, Variables: {self.variable_specs}, Email: {self.email}"

    def output_fmt_prompt(self, var_name):
        return self.formatter.output_fmt_prompt(var_name)

    def format_gpt_response(self, resp):
        """
        Formats the GPT response.
        """
        pass

    def get_chunk_size(self):
        """
        Returns the chunk size for processing PDFs.
        """
        return 200

    def get_results(self, policy_info):
        """
        Processes the policy information and returns the results.
        """
        gpt_responses = {}
        hdr = self.formatter.get_output_headers()[1]
        for var_name, var_val in policy_info.items():
            if var_val.count('"') == 2 and var_val[0] == '"' and var_val[-1] == '"':
                var_val = var_val[1:-1]
            if len(var_val) > len(var_name):
                if var_val[: len(var_name)] == var_name:
                    var_val = var_val.replace(f"{var_name}: ", "", 1)
            gpt_responses[var_name] = {hdr: var_val}
        return gpt_responses

    def get_output_headers(self):
        """
        Returns the output headers for the results.
        """
        return ["Variable Name", "GPT Response"]

    def get_num_excerpts(self, num_pages):
        """
        Returns the number of excerpts to process based on the number of pages.
        """
        if num_pages < 100:
            return 40
        else:
            return 40 + int(num_pages / 5.0)

    def optional_add_categorization(self, v_name, query):
        """
        Optionally adds categorization to the query.
        """
        return query

    def resp_format_type(self):
        """
        Returns the response format type.
        """
        return "json_object"
    
    def get_gpt_model(self):
        """
        Returns the gpt model selected by the user (or default is "o4-mini").
        """
        return self.gpt_model

## TODO: delete
class DefaultAnalyzer(GPTAnalyzer):
    """
    Analyzer for handling default GPT responses.
    """

    def __init__(
        self, pdfs, main_query, variable_specs, email, output_fmt, additional_info, gpt_model
    ):
        """
        Initializes the DefaultAnalyzer with the given parameters.
        """
        self.label = "Default"
        super().__init__(
            pdfs, main_query, variable_specs, email, output_fmt, additional_info, gpt_model
        )


    def output_fmt_prompt(self, var_name):
        """
        Returns the output format prompt for the given variable name.
        """
        output_fmt_str = "{'value': '...', 'relevant_page_numbers': '...'}"
        return f"Return your response in the following json format: \n {output_fmt_str}"

    def format_gpt_response(self, resp):
        """
        Formats the GPT response.
        """
        return f"{json.loads(resp)['value']} [page(s) {resp['relevant_page_numbers']}]"


class QuoteAnalyzer(GPTAnalyzer):
    """
    Analyzer for extracting and formatting quotes from GPT responses.
    """

    def __init__(
        self, pdfs, main_query, variable_specs, email, output_fmt, additional_info, gpt_model
    ):
        """
        Initializes the QuoteAnalyzer with the given parameters.
        """
        self.label = "Quote extraction"
        super().__init__(
            pdfs, main_query, variable_specs, email, output_fmt, additional_info, gpt_model
        )

    def optional_add_categorization(self, var_name, query):
        """
        Optionally adds categorization to the query.
        """
        return self.formatter.optional_add_categorization(var_name, query)

    def format_gpt_response(self, resp):
        return self.formatter.format_gpt_response(resp)
    def get_results(self, policy_info):
        """
        Processes the policy information and returns the results.
        """
        return self.formatter.get_results(policy_info)
    
    def get_output_headers(self):
        """
        Returns the output headers for the results.
        """
        return self.formatter.get_output_headers()

    def get_chunk_size(self):
        """
        Returns the chunk size for processing PDFs.
        """
        return 200

    def get_num_excerpts(self, num_pages):
        """
        Returns the number of excerpts to process based on the number of pages.
        """
        if num_pages < 200:
            return 20 + num_pages
        else:
            return 220

    def resp_format_type(self):
        return self.formatter.resp_format_type()

class SummaryAnalyzer(GPTAnalyzer):
    """
    Analyzer for generating summaries from GPT responses.
    """

    def __init__(
        self, pdfs, main_query, variable_specs, email, output_fmt, additional_info, gpt_model
    ):
        """
        Initializes the SummaryAnalyzer with the given parameters.
        """
        self.label = "Targeted summaries"
        super().__init__(
            pdfs, main_query, variable_specs, email, output_fmt, additional_info, gpt_model
        )

    def output_fmt_prompt(self, var_name):
        """
        Returns the output format prompt for the given variable name.
        """
        return ""

    def format_gpt_response(self, resp):
        """
        Formats the GPT response.
        """
        return resp

    def get_results(self, policy_info):
        """
        Processes the policy information and returns the results.
        """
        resp = {}
        for var_name, r in policy_info.items():
            resp[var_name] = {self.formatter.get_output_headers()[1]: r}
        return resp

    def get_output_headers(self):
        """
        Returns the output headers for the results.
        """
        return ["Variable", "Summary"]

    def get_chunk_size(self):
        """
        Returns the chunk size for processing PDFs.
        """
        return 500

    def get_num_excerpts(self, num_pages):
        """
        Returns the number of excerpts to process based on the number of pages.
        """
        return 5 + num_pages

    def resp_format_type(self):
        """
        Returns the response format type.
        """
        return "text"


def get_task_types():
    """
    Returns a dictionary mapping task types to their corresponding analyzer classes.
    """
    return {
        "Quote extraction": QuoteAnalyzer,
        "Targeted summaries": SummaryAnalyzer,
        #"Targeted inquiries": DefaultAnalyzer,
    }


def get_analyzer(
    task_type, output_fmt, pdfs, main_query, variable_specs, email, additional_info, gpt_model="o4-mini"
):
    """
    Returns an instance of the appropriate analyzer class based on the task type.
    """
    task_analyzer_class = get_task_types()[task_type]
    return task_analyzer_class(
        pdfs, main_query, variable_specs, email, output_fmt, additional_info, gpt_model
    )
