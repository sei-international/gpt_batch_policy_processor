import os
import streamlit as st



def get_apikey_ids():
    return {
        get_secret("access_password"): "openai_apikey",
        get_secret("access_password_adis"): "openai_apikey_adis",
        get_secret("access_password_urbanadaptation"): "openai_apikey_adaptation",
        get_secret("access_password_bb"): "openai_apikey_bb",
        get_secret("access_password_leadit"): "openai_apikey_leadit",
    }

def get_secret(k):
    if os.environ.get("WEBSITE_SITE_NAME") or os.environ.get("WEBSITE_INSTANCE_ID"):
        return os.environ.get(k)
    elif os.environ.get("STREAMLIT_SERVER_HEADLESS") or os.environ.get("STREAMLIT_CLOUD"):
        return st.secrets[k]
    else:
        return st.secrets[k]
