import streamlit as st

def about_tab():
    text = """
## About the GPT-Batch Policy Processor (beta)

The **GPT-Batch Policy Processor (beta)** tool was developed to assist researchers, policymakers, and analysts in processing and analyzing policy documents at scale using advanced natural language processing techniques. It leverages large language models (LLMs) for automated insights extraction, text summarization, and topic modeling. This tool aims to help users streamline the process of working with large datasets of policy text to uncover key patterns, trends, and implications.

## Terms of Use

### Open Access to the Data Sets
The GPT-Batch Policy Processor (beta) tool is made available for public use with the intention of promoting transparency and fostering knowledge sharing in the field of environmental policy analysis.

**Date of release**: May 1st, 2024.

### Tool Attribution
The tool was created by the following contributors:

Babis, William / Munoz Cabre, Miquel / Dzebo, Adis / Martelo, Camilo / Salzano, Cora / Torres Morales, Eileen / Arsadita, Ferosa (2024): GPT-Batch Policy Processor (beta). Stockholm Environment Institute (SEI).

### Licensing and Copyright Information
The Stockholm Environment Institute (SEI) holds the copyright for the GPT-Batch Policy Processor (beta) tool. It is licensed under the [Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA)](https://creativecommons.org/licenses/by-nc-sa/4.0/).

### Usage Guidelines
By using the tool, you agree to the following terms:
- **Non-commercial use**: The tool is provided for non-commercial, academic, and research purposes only. Any commercial use or redistribution requires permission from the Stockholm Environment Institute.
- **Attribution**: You must provide appropriate credit to the authors and the Stockholm Environment Institute, as specified in the citation section.
- **ShareAlike**: Any derivative works created from this tool must be licensed under the same Creative Commons License (CC BY-NC-SA).

If you have any questions or need further information, feel free to reach out via email at [aipolicyreader@sei.org](mailto:aipolicyreader@sei.org) or consult the documentation provided with the tool.

## Acknowledgments
We would like to thank the Stockholm Environment Institute (SEI) for their support in the development of this tool. Their mission to promote environmental sustainability through evidence-based research has been a key inspiration for this project.
"""
    st.markdown(text)
