import logging
import streamlit as st

logger = logging.getLogger("aipolicy")

class SessionStateLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        if "live_log" not in st.session_state:
            st.session_state["live_log"] = []

    def emit(self, record):
        # Append each new line to session state; never touch Streamlit widgets here
        st.session_state["live_log"].append(self.format(record))

def init_logger():
    logger.handlers.clear()
    handler = SessionStateLogHandler()
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s : %(message)s"))  # just the message
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
