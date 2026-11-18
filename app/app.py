"""ACF Delta Share Compliance — Databricks Streamlit app entrypoint."""

from __future__ import annotations

import streamlit as st

import config
from lib import ui

st.set_page_config(page_title=config.APP_TITLE, page_icon=":material/share:", layout="wide",
                   initial_sidebar_state="expanded")

if config.MISSING_SETTINGS:
    st.error("This app is not configured yet. Set the matching bundle variables in databricks.yml and run `databricks bundle deploy`: "
             + ", ".join(f"`{name}`" for name in config.MISSING_SETTINGS))
    st.stop()

pages = [
    st.Page("views/home.py", title="Home", icon=":material/home:", default=True),
    st.Page("views/findings.py", title="Compliance findings", icon=":material/policy:"),
    st.Page("views/remediation.py", title="Remediation", icon=":material/build:"),
    st.Page("views/draft_agreement.py", title="Draft MOU / ISA", icon=":material/draft:"),
    st.Page("views/ask_genie.py", title="Ask Genie", icon=":material/forum:"),
]
nav = st.navigation(pages, position="sidebar")
ui.apply_chrome()
nav.run()
