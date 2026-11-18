"""Draft a new MOU / ISA: partner + exact columns -> AI narrative grounded in prior agreements -> Word."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from lib import ai, data, docs, retrieval, ui

ui.page_hero("Draft MOU / ISA",
             "Choose the partner and the exact columns to share. The draft follows the ACF TECH template, with Appendix C.",
             icon="draft")

try:
    recips, srccols, ags = data.recipients(), data.source_columns(), data.agreements()
except Exception as exc:
    ui.data_error(exc, "draft")
    st.stop()

# ---------------------------------------------------------------- 1. partner
st.subheader("1. Partner and exchange")
c1, c2, c3 = st.columns(3)
kind = c1.radio("Agreement type", ["MOU", "ISA"], horizontal=True,
                help="NIST SP 800-47: an MOU when both systems are on the same secure network, an ISA between separate networks.")
agency = c2.selectbox("Partner agency", list(data.PARTNERS))
known = recips[recips["agency"] == agency]
rec_opts = known["recipient_name"].tolist() + ["(new recipient)"]
recipient = c3.selectbox("Delta Sharing recipient", rec_opts)
if recipient == "(new recipient)":
    recipient = c3.text_input("New recipient name", f"{agency.lower()}_")
    office_default = ""
else:
    office_default = known.loc[known["recipient_name"] == recipient, "office"].iloc[0]

c1, c2 = st.columns(2)
office = c1.text_input("Partner office (full name)", office_default)
system_b = c2.text_input("Partner system (System B)", f"{office_default or agency} Analytics Environment")
purpose = st.text_area("Purpose of the data exchange", placeholder="e.g. Evaluate child care subsidy receipt and Medicaid/CHIP enrollment by state", height=80)

# ---------------------------------------------------------------- 2. data elements
st.subheader("2. Data elements (Appendix C)")
tables = st.multiselect("ACF source tables", data.SOURCE_TABLES)
elements: list[dict] = []
for t in tables:
    tc = srccols[srccols["table_name"] == t][["column_name", "data_type", "identifier_level"]].copy()
    tc.insert(0, "include", tc["identifier_level"] != "direct")
    st.markdown(f"**{t}**")
    ed = st.data_editor(tc, hide_index=True, width="stretch", key=f"cols_{t}", disabled=["column_name", "data_type", "identifier_level"],
                        column_config={"include": st.column_config.CheckboxColumn("Share"),
                                       "identifier_level": st.column_config.TextColumn("Identifier (UC tag)")})
    elements += [{"table": t, "column": r.column_name, "identifier_level": r.identifier_level} for r in ed[ed["include"]].itertuples()]

direct = [e for e in elements if e["identifier_level"] == "direct"]
if direct:
    st.warning("Direct identifiers selected: " + ", ".join(f"`{e['table']}.{e['column']}`" for e in direct)
               + ". Each one needs a minimum-necessary justification and Privacy Office review.", icon=":material/warning:")

# overlap with existing agreements for the same recipient / tables
overlap = ags[(ags["recipient_name"] == recipient) & (ags["document_type"] != "AMENDMENT")]
if not overlap.empty:
    st.info("Existing agreements with this recipient: " + ", ".join(
        f"{r.agreement_number} (share {r.share_name}, expires {r.expiration_date})" for r in overlap.itertuples())
        + ". Consider an amendment instead of a new agreement.", icon=":material/info:")

# ---------------------------------------------------------------- 3. terms
st.subheader("3. Terms and parties")
c1, c2, c3, c4 = st.columns(4)
effective = c1.date_input("Effective date", date.today())
years = c2.selectbox("Term", [1, 2, 3], index=2, format_func=lambda y: f"{y} year{'s' if y > 1 else ''}")
try:
    expires = effective.replace(year=effective.year + years) - timedelta(days=1)
except ValueError:  # Feb 29 effective date
    expires = effective.replace(year=effective.year + years, day=28)
c3.text_input("Expiration date", expires.isoformat(), disabled=True)
number = c4.text_input("Agreement number", data.next_agreement_number(agency, effective.year))
share_default = f"acf_{recipient}_{tables[0].split('_')[0] if tables else 'data'}".replace("__", "_")
share = st.text_input("Delta Share name", share_default)
c1, c2, c3, c4 = st.columns(4)
acf_isso = c1.text_input("ACF ISSO", "Lauren Mbeki, ACF OCIO")
acf_poc = c2.text_input("ACF technical POC", "Marcus Ellery")
partner_isso = c3.text_input(f"{agency} ISSO", "")
partner_poc = c4.text_input(f"{agency} technical POC / signatory", "")

# ---------------------------------------------------------------- 4. draft
st.subheader("4. Draft")
ready = bool(purpose.strip() and elements and recipient and office)
if not ready:
    st.caption("Fill in the purpose, partner office, recipient and at least one column to draft.")
facts = dict(kind=kind, agreement_number=number, partner=agency, partner_full=data.PARTNERS[agency], office=office,
             system_b=system_b, recipient=recipient, share=share, purpose=purpose, effective=effective.isoformat(),
             expires=expires.isoformat(), data_elements=elements)
if st.button("Draft with AI", icon=":material/auto_awesome:", type="primary", disabled=not ready):
    with st.spinner("Retrieving similar ACF agreements and drafting…"):
        try:
            prec = retrieval.retrieve(f"{purpose} {' '.join(tables)} {kind}", k=4)
            st.session_state["agreement_draft"] = {"facts": facts, "draft": ai.draft_agreement(facts, prec), "precedent": prec}
        except Exception as exc:
            st.error(f"Drafting failed: {exc}", icon=":material/error:")

state = st.session_state.get("agreement_draft")
if state:
    d = state["draft"]
    if state["facts"] != facts:
        st.caption(":material/sync_problem: Inputs changed since this draft. Facts below use your current inputs; redraft to refresh the narrative.")
    if d.get("review_flags"):
        with st.container(border=True):
            st.markdown("**Privacy / ISSO review flags**")
            for fl in d["review_flags"]:
                st.markdown(f"- {fl}")
    purpose_stmt = st.text_area("Purpose statement (Section 2)", d.get("purpose_statement", purpose), height=90)
    sysb_fn = st.text_input("System B function (Section 4)", d.get("system_b_function", ""))
    desc = st.text_area("Description of data (Section 4)", d.get("description_of_data", ""), height=80)
    minimum = st.text_area("Data minimization (Appendix A)", d.get("minimum_necessary", ""), height=160)
    just = st.data_editor(pd.DataFrame(d.get("identifier_justifications") or [], columns=["column", "justification"]),
                          num_rows="dynamic", width="stretch", hide_index=True, key="just_editor")
    safeguards = st.text_area("Additional safeguards (Section 6, one per line)", "\n".join(d.get("special_safeguards") or []), height=110)

    ctx = dict(facts, effective=effective, expires=expires, elements=elements, purpose_statement=purpose_stmt,
               system_b_function=sysb_fn, description_of_data=desc, minimum_necessary=minimum,
               identifier_justifications=just.to_dict("records"),
               special_safeguards=[s for s in safeguards.splitlines() if s.strip()],
               acf_isso=acf_isso, acf_poc=acf_poc, partner_isso=partner_isso, partner_poc=partner_poc,
               acf_signer="Dana R. Whitfield, Chief Information Officer, ACF OCIO", partner_signer=partner_poc)
    st.download_button("Download Word document", docs.render_agreement(ctx), file_name=f"{number}_{kind}_draft.docx",
                       mime=docs.DOCX_MIME, icon=":material/download:", type="primary")
    if state.get("precedent"):
        with st.expander("Prior agreement language used as precedent"):
            for p in state["precedent"]:
                st.markdown(f"**{p.get('agreement_number') or p.get('source')}** ({p.get('partner_agency') or ''})")
                st.caption((p.get("text") or "")[:600])
ui.synthetic_note()
