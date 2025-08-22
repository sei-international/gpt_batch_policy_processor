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
    if os.environ.get("deployment_env"):
        if os.environ.get("deployment_env") == "azure":
            return os.environ.get(k)
    elif st.secrets["deployment_env"]:
        if st.secrets["deployment_env"] == "streamlit":
            return st.secrets[k]
    return st.secrets[k]
