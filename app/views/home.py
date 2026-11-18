"""Home: compliance posture at a glance and navigation."""

from __future__ import annotations

import streamlit as st

from lib import data, kpis, ui

ui.page_hero(
    "ACF Delta Share Compliance",
    "Check that every Delta Share matches its signed MOU or ISA, fix what doesn't, and draft new agreements.",
    icon="share",
)

try:
    summ, fnd = data.summary(), data.findings()
except Exception as exc:
    ui.data_error(exc, "home")
    st.stop()

for col, k in zip(st.columns(5), kpis.compute(summ, fnd, data.agreements())):
    col.metric(k.label, k.value, delta=k.sub, delta_color="off", delta_arrow="off", help=k.help)

st.write("")
cols = st.columns(2, gap="large")
with cols[0]:
    ui.nav_card("policy", "Compliance findings",
                "Every share compared column by column with its agreement and amendments. Open the source PDF and the "
                "extracted Appendix C next to what is actually shared.", "views/findings.py", "Open findings")
with cols[1]:
    ui.nav_card("build", "Remediation",
                "For any finding: the recommended action, the SQL to fix the share, and an AI-drafted amendment, partner "
                "notice, or internal memo as a Word document.", "views/remediation.py", "Open remediation")
st.write("")
cols = st.columns(2, gap="large")
with cols[0]:
    ui.nav_card("draft", "Draft MOU / ISA",
                "Pick a partner and the exact columns to share. Get a NIST SP 800-47 agreement with Appendix C, data "
                "minimization justifications, and a privacy review, grounded in prior ACF agreements.",
                "views/draft_agreement.py", "Start a draft")
with cols[1]:
    ui.nav_card("forum", "Ask Genie",
                "Plain-language questions over shares, agreements, findings, and system tables: \"Which shares expose "
                "direct identifiers that no agreement permits?\"", "views/ask_genie.py", "Ask Genie")

st.write("")
st.subheader("How it works")
ui.how_it_works_diagram()
st.write("")
ui.synthetic_note()
