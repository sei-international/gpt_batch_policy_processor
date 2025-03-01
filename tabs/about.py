import streamlit as st

def about_tab():
    text = """
## Terms of use
**Open access to the data sets** \n
The GPT-Batch Policy Processor (beta) tool has been published on May 1st, 2024.
\n
**The GPT-Batch Policy Processor (beta) tool** \n
Babis, William / Munoz Cabre, Miquel / Dzebo, Adis / Martelo, Camilo / Salzano, Cora / Torres Morales, Eileen / Arsadita, Ferosa (2024): GPT-Batch Policy Processor (beta). Stockholm Environment Institute (SEI).
\n
**Referring to GPT-Batch Policy Processor (beta) tool analysis** \n
 The Stockholm Environment Institute (SEI) hold the copyright of the GPT-Batch Policy Processor (beta) tool. It is 
 licensed under Creative Commons and you are free to copy and redistribute material derived from the  GPT-Batch Policy 
 Processor (beta) tool by following the guideline of the Creative Commons License. [CC BY-NC-NA](https://creativecommons.org/licenses/by-nc-sa/4.0/) (Attribution, NonCommercial, ShareAlike).
"""
    st.markdown(text)