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
        self.organize_text_chunks_by_section = False
    def __str__(self):
        class_name = self.__class__.__name__
        return f"{class_name} -- PDFS: {self.pdfs} \n MAIN QUERY : {self.main_query} \n VARIABLE SPECIFICATIONS: {self.variable_specs}"
    def output_fmt_prompt(self, var_name):
        pass
    def format_gpt_response(self, resp):
        pass
    def get_chunk_size(self):
        pass
    def get_results(self, policy_info):
        pass
    def get_output_headers(self):
        pass
    def get_num_excerpts(self, num_pages):
        if num_pages < 100:
            return 40
        else:
            return 40 + int(num_pages / 5.0)
    def optional_add_categorization(self, v_name, query):
        return query
    def resp_format_type(self):
        return "json_object"   
    def get_gpt_model(self):
        return self.gpt_model


class QuoteAnalyzer(GPTAnalyzer):
    """
    Analyzer for extracting and formatting quotes from GPT responses.
    """

    def __init__(
        self, pdfs, main_query, variable_specs, email, output_fmt, additional_info, gpt_model
    ):
        self.label = "Quote extraction"
        super().__init__(
            pdfs, main_query, variable_specs, email, output_fmt, additional_info, gpt_model
        )
        self.formatter.optional_resp_col = "Quotes"
    def output_fmt_prompt(self, var_name):
        base_instruction = "Provide an exhaustive list of relevant quotes"
        return self.formatter.output_fmt_prompt(var_name, base_instruction)   
    def optional_add_categorization(self, var_name, query):
        return self.formatter.optional_add_categorization(var_name, query)
    def format_gpt_response(self, resp):
        return self.formatter.format_gpt_response(resp)   
    def get_results(self, policy_info):
        return self.formatter.get_results(policy_info)    
    def get_output_headers(self):
        return self.formatter.get_output_headers()
    def get_chunk_size(self):
        return 1000
    def get_num_excerpts(self, num_pages):
        if num_pages < 200:
            return 20 + num_pages
        else:
            return 220
    def resp_format_type(self):
        return self.formatter.resp_format_type()

class SummaryAnalyzer(GPTAnalyzer):
    def __init__(
        self, pdfs, main_query, variable_specs, email, output_fmt, additional_info, gpt_model
    ):
        self.label = "Targeted summaries"
        self.organize_text_chunks_by_section = True
        super().__init__(
            pdfs, main_query, variable_specs, email, output_fmt, additional_info, gpt_model
        )
        self.formatter.optional_resp_col = "Summary"
    def output_fmt_prompt(self, var_name):
        base_instruction = "Respond with a qualitative evaluation including a description of the relevant headings and page numbers"
        return self.formatter.output_fmt_prompt(var_name, base_instruction)
    def format_gpt_response(self, resp):
        return self.formatter.format_gpt_response(resp)
    def get_results(self, policy_info):
        return self.formatter.get_results(policy_info)
    def get_output_headers(self):
        return self.formatter.get_output_headers()
    def get_chunk_size(self):
        return 100
    def get_num_excerpts(self, num_pages):
        return 5 + num_pages
    def resp_format_type(self):
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
    task_type, output_fmt, pdfs, main_query, variable_specs, email, additional_info, gpt_model="gpt-4.1"
):
    """
    Returns an instance of the appropriate analyzer class based on the task type.
    """
    task_analyzer_class = get_task_types()[task_type]
    return task_analyzer_class(
        pdfs, main_query, variable_specs, email, output_fmt, additional_info, gpt_model
    )