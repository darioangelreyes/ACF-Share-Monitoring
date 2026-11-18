"""Remediation: recommended action, fix SQL, and an AI-drafted amendment / notice / memo for one finding."""

from __future__ import annotations

from datetime import date

import streamlit as st

from lib import ai, data, docs, remediation, retrieval, ui

ui.page_hero("Remediation",
             "Pick a finding: get the fix, the SQL for the share owner, and the paperwork as a Word document.", icon="build")

try:
    fnd = data.findings()
except Exception as exc:
    ui.data_error(exc, "remediation")
    st.stop()

actionable = fnd.reset_index(drop=True)
labels = [f"{r.severity} · {r.finding_type} · {r.share_name or ''}" + (f" · {r.column_name}" if r.column_name else "")
          for r in actionable.itertuples()]
pre = st.session_state.get("remediate_finding_id")
idx = int(actionable.index[actionable["finding_id"] == pre][0]) if pre in set(actionable["finding_id"]) else 0
choice = st.selectbox("Finding", range(len(labels)), index=idx, format_func=lambda i: labels[i])
f = actionable.iloc[choice].to_dict()
st.session_state["remediate_finding_id"] = f["finding_id"]
ft, share = f["finding_type"], f.get("share_name")

ag = data.agreement_for_share(share) if share else {}
cmp_df = data.column_comparison(share) if share else None
objs = data.share_objects(share) if share else None

with st.container(border=True):
    st.markdown(f"{ui.pill(f['severity'], ui.SEVERITY_COLORS.get(f['severity'], '#555'))} **{ft.replace('_', ' ').title()}**",
                unsafe_allow_html=True)
    st.write(f["detail"])
    st.markdown(f"**Recommended action:** {remediation.ACTIONS.get(ft, 'Review manually.')}")

# Findings on the same share are usually fixed together (e.g. three over-shared columns, one view).
siblings = fnd[(fnd["share_name"] == share) & (fnd["finding_id"] != f["finding_id"])] if share else fnd.iloc[0:0]
if not siblings.empty:
    st.caption("Other open findings on this share: " + "; ".join(f"{r.finding_type}" + (f" ({r.column_name})" if r.column_name else "")
                                                         for r in siblings.itertuples()))

# ---------------------------------------------------------------- SQL
sql = remediation.plan_sql(f, cmp_df, objs, ag, data.data_elements(ag["file_name"]) if ag else None,
                           data.source_columns()) if share and cmp_df is not None else ""
if sql:
    st.subheader("Fix the share")
    st.code(sql, language="sql")
    st.caption("Generated for a share owner to review and run. The app does not change shares.")

# ---------------------------------------------------------------- documents
st.subheader("Draft the paperwork")
options = remediation.DOC_OPTIONS.get(ft, ["MEMO"])
kind = st.radio("Document", options, format_func=lambda k: ai.DOC_KINDS[k], horizontal=True)

over_cols = cmp_df[cmp_df["status"].str.startswith("OVER")] if cmp_df is not None and not cmp_df.empty else None
facts = {
    "finding": {k: f.get(k) for k in ("finding_type", "severity", "share_name", "recipient_name", "agreement_number",
                                      "partner_agency", "source_table", "column_name", "identifier_level", "detail")},
    "all_findings_on_share": siblings[["finding_type", "column_name", "detail"]].to_dict("records") if not siblings.empty else [],
    "agreement": {k: str(ag.get(k)) for k in ("agreement_number", "document_type", "partner_agency", "partner_office",
                                              "partner_system_name", "purpose", "share_name", "recipient_name",
                                              "effective_date", "expiration_date")} if ag else None,
    "over_shared_columns": over_cols[["source_table", "column_name", "identifier_level"]].to_dict("records") if over_cols is not None else [],
    "planned_sql_fix": sql or None,
    "today": date.today().isoformat(),
    "acf_signatory": "Dana R. Whitfield, Chief Information Officer, ACF OCIO",
}

key = f"remdoc_{f['finding_id']}_{kind}"
if st.button("Draft with AI", icon=":material/auto_awesome:", type="primary"):
    with st.spinner("Finding similar agreement language and drafting…"):
        try:
            prec = retrieval.retrieve(f"{ai.DOC_KINDS[kind]} {ft.replace('_', ' ').lower()} {f.get('detail', '')}", k=4)
            st.session_state[key] = {"draft": ai.draft_remediation_doc(kind, facts, prec), "precedent": prec}
        except Exception as exc:
            st.error(f"Drafting failed: {exc}", icon=":material/error:")

state = st.session_state.get(key)
if state:
    d = state["draft"]
    subject = st.text_input("Subject", d.get("subject", ""), key=f"{key}_subj")
    if kind == "AMENDMENT":
        change = st.text_area("Change", d.get("change_summary", ""), height=120, key=f"{key}_chg")
        just = st.text_area("Justification", d.get("justification", ""), height=140, key=f"{key}_just")
        conds = st.text_area("Conditions (one per line)", "\n".join(d.get("conditions") or []), height=120, key=f"{key}_cond")
        amd_no = len(data.amendments_for(ag.get("agreement_number", ""))) + 1 if ag else 1
        add_cols = over_cols.rename(columns={"source_table": "table", "column_name": "column"}).to_dict("records") \
            if ft == "OVER_SHARING" and over_cols is not None and st.checkbox("Amendment ADDS the over-shared columns (instead of removing them from the share)") else []
        ctx = dict(agreement_number=f"{ag.get('agreement_number', 'ACF-XXX')}-A{amd_no}", amends=ag.get("agreement_number", ""),
                   amendment_no=amd_no, amends_kind=ag.get("document_type", "").replace("_", " ").title(),
                   office=ag.get("partner_office", ""), partner_full=data.PARTNERS.get(ag.get("partner_agency", ""), ""),
                   share=share, recipient=ag.get("recipient_name"), effective=date.today(), expires=ag.get("expiration_date"),
                   change_summary=change, justification=just, conditions=[c for c in conds.splitlines() if c.strip()],
                   add_elements=add_cols, acf_signer=facts["acf_signatory"])
        buf, fname = docs.render_amendment(ctx), f"{ctx['agreement_number']}_draft.docx"
    else:
        sections = []
        for i, s in enumerate(d.get("sections") or []):
            h = st.text_input(f"Section {i + 1} heading", s.get("heading", ""), key=f"{key}_h{i}")
            b = st.text_area(f"Section {i + 1}", s.get("body", ""), height=150, key=f"{key}_b{i}", label_visibility="collapsed")
            sections.append({"heading": h, "body": b})
        items = st.data_editor(d.get("action_items") or [], num_rows="dynamic", width="stretch", key=f"{key}_ai")
        partner_to = f"{ag.get('partner_office', '')}, {data.PARTNERS.get(ag.get('partner_agency', ''), '')}" if ag else f"{f.get('recipient_name')}"
        to = partner_to if kind == "NOTICE" else "ACF Privacy Officer; ACF ISSO" if kind == "MEMO" else "ACF Chief Information Officer"
        ctx = dict(title=ai.DOC_KINDS[kind], to=to,
                   **{"from": facts["acf_signatory"] if kind == "NOTICE" else "ACF Division of Data Governance"},
                   subject=subject, reference=f"{f.get('agreement_number') or 'No agreement'} / Delta Share {share}",
                   sections=sections, action_items=items)
        buf, fname = docs.render_letter(ctx), f"{kind.lower()}_{share or 'finding'}.docx"
    st.download_button("Download Word document", buf, file_name=fname, mime=docs.DOCX_MIME, icon=":material/download:",
                       type="primary")
    if state.get("precedent"):
        with st.expander("Agreement language used as precedent"):
            for p in state["precedent"]:
                st.markdown(f"**{p.get('agreement_number') or p.get('source')}**")
                st.caption((p.get("text") or "")[:600])
ui.synthetic_note()
