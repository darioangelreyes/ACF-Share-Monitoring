"""Compliance findings: shares vs agreements, with drill-down to the agreement PDF and Appendix C."""

from __future__ import annotations

import streamlit as st

from lib import data, ui

ui.page_hero("Compliance findings",
             "What each Delta Share actually exposes, compared with what its signed agreement permits.", icon="policy")

try:
    fnd = data.findings()
except Exception as exc:
    ui.data_error(exc, "findings")
    st.stop()

# ---------------------------------------------------------------- findings with filters
f1, f2, f3, f4 = st.columns(4)
sev = f1.multiselect("Severity", [s for s in data.SEVERITY_ORDER if s in set(fnd["severity"])])
typ = f2.multiselect("Finding type", sorted(fnd["finding_type"].unique()))
agency = f3.multiselect("Partner agency", sorted(fnd["partner_agency"].dropna().unique()))
share = f4.multiselect("Share", sorted(fnd["share_name"].dropna().unique()))
view = fnd
for col, sel in (("severity", sev), ("finding_type", typ), ("partner_agency", agency), ("share_name", share)):
    if sel:
        view = view[view[col].isin(sel)]
view = view.reset_index(drop=True)

TC = st.column_config.TextColumn
# Fixed pixel widths (wider than the page) so the grid scrolls horizontally and Detail shows in full.
event = st.dataframe(
    view[["severity", "finding_type", "share_name", "recipient_name", "agreement_number", "source_table", "column_name",
          "identifier_level", "detail"]],
    hide_index=True, width="stretch", height=min(38 + 35 * len(view), 600), on_select="rerun",
    selection_mode="single-row", key="findings_table",
    column_config={"severity": TC("Severity", width=90, pinned=True), "finding_type": TC("Type", width=200, pinned=True),
                   "share_name": TC("Share", width=230, pinned=True), "recipient_name": TC("Recipient", width=100),
                   "agreement_number": TC("Agreement", width=140), "source_table": TC("Table", width=190),
                   "column_name": TC("Column", width=190), "identifier_level": TC("Identifier", width=85),
                   "detail": TC("Detail", width=1150)},
)
st.caption(f"{len(view)} of {len(fnd)} findings. Scroll right for the full Detail, or select a row to see it below with the share, the agreement and the PDF.")

rows = event.selection.rows if event and event.selection else []
if not rows:
    st.stop()
f = view.iloc[rows[0]].to_dict()

# ---------------------------------------------------------------- drill-down
st.divider()
head, btn = st.columns([4, 1])
head.markdown(f"### {ui.pill(f['severity'], ui.SEVERITY_COLORS.get(f['severity'], '#555'))} {f['finding_type'].replace('_', ' ').title()}"
              f" &middot; `{f['share_name']}`", unsafe_allow_html=True)
head.write(f["detail"])
if btn.button("Remediate", icon=":material/build:", type="primary", width="stretch"):
    st.session_state["remediate_finding_id"] = f["finding_id"]
    st.switch_page("views/remediation.py")

ag = data.agreement_for_share(f["share_name"]) if f.get("share_name") else {}
left, right = st.columns([3, 2], gap="large")
with left:
    if f.get("share_name"):
        st.markdown("**Columns: shared vs permitted**")
        cmp_df = data.column_comparison(f["share_name"])
        if cmp_df.empty:
            st.info("No column-level data for this share.")
        else:
            def _style(row):
                s = row["status"]
                color = "#fdecea" if s.startswith("OVER") else "#fff6dc" if s.startswith("UNDER") else ""
                return [f"background-color: {color}"] * len(row)
            st.dataframe(cmp_df.style.apply(_style, axis=1), hide_index=True, width="stretch",
                         column_config={"granted_by": "Permitted by", "granted_by_type": "Doc type",
                                        "agreement_sensitivity": "Sensitivity (agreement)",
                                        "identifier_level": "Identifier (UC tag)"})
            st.caption("Identifier level comes from the `acf_identifier` Unity Catalog column tag; permitted columns include amendments.")
    if ag:
        st.markdown("**Agreement record (extracted)**")
        st.dataframe(
            [{"Field": k, "Value": str(ag.get(k))} for k in (
                "agreement_number", "document_type", "partner_agency", "partner_office", "partner_system_name", "purpose",
                "share_name", "recipient_name", "effective_date", "expiration_date", "fully_signed", "data_element_count",
                "min_confidence")],
            hide_index=True, width="stretch")
        amd = data.amendments_for(ag["agreement_number"])
        if not amd.empty:
            st.caption("Amendments: " + ", ".join(amd["agreement_number"]))

with right:
    docs = [ag] + data.amendments_for(ag["agreement_number"]).to_dict("records") if ag else []
    if not docs:
        st.info("No agreement on file for this share.", icon=":material/description:")
    else:
        pick = st.selectbox("Document", [d["agreement_number"] for d in docs]) if len(docs) > 1 else docs[0]["agreement_number"]
        doc = next(d for d in docs if d["agreement_number"] == pick)
        tab_pdf, tab_el, tab_sig = st.tabs(["PDF", "Appendix C (extracted)", "Signatures"])
        with tab_pdf:
            try:
                pages = data.pdf_pages(doc["source_path"])
                page = st.number_input("Page", 1, len(pages), 1) if len(pages) > 1 else 1
                st.image(pages[page - 1], width="stretch")
                st.download_button("Download PDF", data.pdf_bytes(doc["source_path"]), file_name=f"{doc['file_name']}.pdf",
                                   mime="application/pdf", icon=":material/download:")
            except Exception as exc:
                st.warning(f"Couldn't load the PDF: {exc}")
        with tab_el:
            st.dataframe(data.data_elements(doc["file_name"]), hide_index=True, width="stretch")
        with tab_sig:
            st.dataframe(data.signatories(doc["file_name"]), hide_index=True, width="stretch")
ui.synthetic_note()
