"""Word (.docx) rendering for agreements, amendments, notices and memos (python-docx, in memory).

Section structure follows the ACF TECH MOU template (NIST SP 800-47) used for the synthetic
agreements, including "Appendix C. Shared Data Elements" so a signed copy can be re-ingested by
the extraction pipeline unchanged.
"""

from __future__ import annotations

from datetime import date
from io import BytesIO

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
KIND_TITLE = {"MOU": "Memorandum of Understanding", "ISA": "Interconnection Security Agreement",
              "AMENDMENT": "Amendment to Agreement"}
SENSITIVITY = {"direct": "PII - direct identifier", "indirect": "Indirect identifier", "none": "Non-identifying"}
ACF_SYSTEM = {"name": "ACF Enterprise Data Platform (EDP)",
              "function": "Agency analytics lakehouse; publishes approved datasets to partner agencies through Delta Sharing",
              "location": "AWS us-east-1, Databricks workspace operated by ACF OCIO"}
DRAFT_MARK = "DRAFT - SYNTHETIC DEMONSTRATION DOCUMENT - generated with AI assistance; review before signature"
NAVY = RGBColor(0x1A, 0x44, 0x80)


def fmt(d) -> str:
    if not d:
        return "[date]"
    d = d if isinstance(d, date) else date.fromisoformat(str(d)[:10])
    return d.strftime("%B %d, %Y").replace(" 0", " ")


def _doc() -> Document:
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name, st.font.size = "Calibri", Pt(11)
    for sec in doc.sections:
        p = sec.header.paragraphs[0]
        p.text, p.alignment = DRAFT_MARK, WD_ALIGN_PARAGRAPH.CENTER
        p.runs[0].font.size, p.runs[0].font.color.rgb = Pt(8), RGBColor(0xC0, 0x39, 0x2B)
    return doc


def _title(doc, title: str, subtitles: list[str]):
    h = doc.add_heading(title, level=0)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for s in subtitles:
        p = doc.add_paragraph(s)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.runs[0].bold = True


def _h(doc, text: str):
    h = doc.add_heading(text, level=1)
    for r in h.runs:
        r.font.color.rgb = NAVY


def _fields(doc, rows: list[tuple[str, str]]):
    t = doc.add_table(rows=0, cols=2)
    t.style = "Light Grid Accent 1"
    for k, v in rows:
        c = t.add_row().cells
        c[0].text, c[1].text = k, str(v or "")
        c[0].paragraphs[0].runs[0].bold = True
    doc.add_paragraph()


def _table(doc, header: list[str], rows: list[list[str]]):
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Light Grid Accent 1"
    for i, h in enumerate(header):
        t.rows[0].cells[i].text = h
    for r in rows:
        cells = t.add_row().cells
        for i, v in enumerate(r):
            cells[i].text = str(v or "")
    doc.add_paragraph()


def _paras(doc, text: str):
    for chunk in (text or "").split("\n"):
        if chunk.strip():
            doc.add_paragraph(chunk.strip())


def _bullets(doc, items):
    for it in items or []:
        if str(it).strip():
            doc.add_paragraph(str(it).strip(), style="List Bullet")


def _signatures(doc, kind_title: str, partner_full: str, acf_signer: str, partner_signer: str):
    _h(doc, "Agreement Signatures")
    doc.add_paragraph(f"I agree with the terms of this {kind_title}.")
    for label, signer in (("APPROVED AND ACCEPTED FOR the Administration for Children and Families", acf_signer),
                          (f"APPROVED AND ACCEPTED FOR {partner_full}", partner_signer)):
        doc.add_paragraph(label).runs[0].bold = True
        doc.add_paragraph("Signature: ________________________________    Date: ______________")
        doc.add_paragraph(f"Name / Title: {signer or '[name, title]'}")
        doc.add_paragraph()


def _save(doc) -> BytesIO:
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


def element_rows(elements: list[dict]) -> list[list[str]]:
    return [[e["table"], e["column"], SENSITIVITY.get(e.get("identifier_level", "none"), "Non-identifying")] for e in elements]


def render_agreement(c: dict) -> BytesIO:
    """New MOU / ISA. ``c`` = facts + reviewed narrative (see views/draft_agreement.py)."""
    k, kt = c["kind"], KIND_TITLE[c["kind"]]
    doc = _doc()
    _title(doc, kt, ["ACF TECH", f"{k} Between {ACF_SYSTEM['name']} and {c['system_b']}"])
    _fields(doc, [("Agreement number", c["agreement_number"]), ("Version", "1.0 (draft)"), ("Date", fmt(c["effective"]))])
    _h(doc, "1. Supersession")
    doc.add_paragraph(c.get("supersession") or "None. This is the first agreement between the parties for this interconnection.")
    _h(doc, "2. Purpose and Scope")
    doc.add_paragraph(
        f"The purpose of this {kt} ({k}) is to establish a management agreement between the Administration for Children and "
        f"Families (ACF), Office of the Chief Information Officer, and the {c['office']}, {c['partner_full']}, hereafter referred "
        f"to as \"both parties\", regarding the development, management, operation, and security of a connection between their "
        f"respective systems, {ACF_SYSTEM['name']} and {c['system_b']}, hereafter referred to as \"the systems.\" Purpose of the "
        f"data exchange: {c['purpose_statement']}")
    doc.add_paragraph(
        "This agreement is based on NIST Special Publication 800-47, Security Guide for Interconnecting Information Technology "
        "Systems. " + ("An ISA is used because the interconnection is between separate, secure networks." if k == "ISA"
                       else "An MOU is used because the interconnection is within the same secure network."))
    _h(doc, "3. Authority")
    doc.add_paragraph("Federal Information Security Modernization Act of 2014; OMB Circular A-130; 18 U.S.C. 641; 18 U.S.C. 1905; "
                      "Privacy Act of 1974, 5 U.S.C. 552a; Health Insurance Portability and Accountability Act of 1996.")
    _h(doc, "4. Requirements")
    _fields(doc, [("System A name", ACF_SYSTEM["name"]), ("System A function", ACF_SYSTEM["function"]),
                  ("System A location", ACF_SYSTEM["location"]), ("System B name", c["system_b"]),
                  ("System B function", c["system_b_function"]),
                  ("System B location", f"{c['partner']} environment, Databricks Delta Sharing recipient '{c['recipient']}'"),
                  ("Description of data", c["description_of_data"])])
    _h(doc, "5. Data Exchange Method")
    _fields(doc, [("Delta Share name", c["share"]), ("Recipient", c["recipient"]), ("Effective date", fmt(c["effective"])),
                  ("Expiration date", fmt(c["expires"]))])
    doc.add_paragraph("ACF will share only the tables and columns listed in Appendix C. Any change to the shared data elements "
                      "requires a signed amendment before the change is made. The recipient will not re-share, link to direct "
                      "identifiers, or attempt to re-identify individuals.")
    _h(doc, "6. Security Responsibilities")
    doc.add_paragraph("Both parties agree to work together to ensure the joint security of the connected systems and the data they "
                      "store, process, and transmit, and to maintain the higher level of security commensurate with the risk of "
                      "loss, misuse, or disclosure of the information.")
    _bullets(doc, c.get("special_safeguards"))
    _h(doc, "7. Communications")
    doc.add_paragraph("Both parties will designate technical leads and notify each other immediately of security incidents, "
                      "disasters, and material changes to system configuration, and at least 30 calendar days before any new "
                      "interconnection.")
    _h(doc, "8. Timeline, Extensions, and Cancellations")
    doc.add_paragraph(f"This agreement is effective {fmt(c['effective'])} and expires {fmt(c['expires'])}, unless extended by a newly "
                      "signed agreement. Either party may terminate it in writing with 30 calendar days notice, or immediately in "
                      "the event of a security incident.")
    _h(doc, "Appendix A. Data Minimization")
    _paras(doc, c.get("minimum_necessary"))
    if c.get("identifier_justifications"):
        _table(doc, ["Identifier", "Justification"],
               [[j.get("column", ""), j.get("justification", "")] for j in c["identifier_justifications"]])
    _h(doc, "Appendix B. Responsible Parties")
    _fields(doc, [("ACF ISSO", c.get("acf_isso") or "[name, ACF OCIO]"), ("ACF Technical POC", c.get("acf_poc") or "[name]"),
                  (f"{c['partner']} ISSO", c.get("partner_isso") or "[name]"),
                  (f"{c['partner']} Technical POC", c.get("partner_poc") or "[name]")])
    _h(doc, "Appendix C. Shared Data Elements")
    doc.add_paragraph(f"Delta Share: {c['share']}    Recipient: {c['recipient']}")
    _table(doc, ["Source table", "Column", "Sensitivity"], element_rows(c["elements"]))
    _signatures(doc, kt, c["partner_full"], c.get("acf_signer"), c.get("partner_signer"))
    return _save(doc)


def render_amendment(c: dict) -> BytesIO:
    """Amendment: change summary + (optionally) the Appendix C elements added / removed."""
    doc = _doc()
    _title(doc, KIND_TITLE["AMENDMENT"], ["ACF TECH", f"Amendment No. {c.get('amendment_no', 1)} to {c['amends']}"])
    _fields(doc, [("Agreement number", c["agreement_number"]), ("Version", "1.0 (draft)"), ("Date", fmt(c.get("effective")))])
    _h(doc, "1. Agreement Being Amended")
    doc.add_paragraph(f"This amendment modifies {c.get('amends_kind', 'the agreement')} {c['amends']} between the Administration "
                      f"for Children and Families (ACF) and the {c.get('office', '')}, {c.get('partner_full', '')}. All other "
                      "terms of the original agreement remain in effect.")
    _h(doc, "2. Change")
    _paras(doc, c.get("change_summary"))
    _fields(doc, [("Delta Share name", c.get("share")), ("Recipient", c.get("recipient")),
                  ("Amendment effective date", fmt(c.get("effective"))), ("Agreement expiration", fmt(c.get("expires")))])
    if c.get("add_elements"):
        doc.add_paragraph("Appendix C, Shared Data Elements, is amended to add the data elements below.")
        _table(doc, ["Source table", "Column", "Sensitivity"], element_rows(c["add_elements"]))
    if c.get("remove_elements"):
        doc.add_paragraph("Appendix C, Shared Data Elements, is amended to remove the data elements below.")
        _table(doc, ["Source table", "Column", "Sensitivity"], element_rows(c["remove_elements"]))
    _h(doc, "3. Justification")
    _paras(doc, c.get("justification"))
    if c.get("conditions"):
        _h(doc, "4. Conditions")
        _bullets(doc, c["conditions"])
    _signatures(doc, KIND_TITLE["AMENDMENT"], c.get("partner_full", "the partner agency"), c.get("acf_signer"), c.get("partner_signer"))
    return _save(doc)


def render_letter(c: dict) -> BytesIO:
    """Notice / memo / renewal cover memo: header block, sections, action-item table."""
    doc = _doc()
    _title(doc, c["title"], [])
    _fields(doc, [("To", c.get("to")), ("From", c.get("from")), ("Date", fmt(date.today())), ("Subject", c.get("subject")),
                  ("Reference", c.get("reference"))])
    for s in c.get("sections") or []:
        _h(doc, s.get("heading", ""))
        _paras(doc, s.get("body", ""))
    if c.get("action_items"):
        _h(doc, "Action items")
        _table(doc, ["Action", "Owner", "Due"], [[a.get("action"), a.get("owner"), a.get("due")] for a in c["action_items"]])
    return _save(doc)
