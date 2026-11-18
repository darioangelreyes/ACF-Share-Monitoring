"""LLM drafting for agreements and remediation documents (foundation model, on behalf of the user).

Every function returns structured JSON-derived dicts so the pages can show editable fields
before anything is rendered to Word. Facts (columns, dates, names, share/recipient) are
always passed in by the app from Unity Catalog; the model writes narrative only.
"""

from __future__ import annotations

import json

import streamlit as st
from databricks.sdk import WorkspaceClient
from databricks.sdk.core import Config
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

import config

# Claude on Databricks is a reasoning model: long drafts can exceed the SDK's 60s default read timeout.
_HTTP_TIMEOUT_S = 300


def _client() -> WorkspaceClient:
    try:
        token = st.context.headers.get("X-Forwarded-Access-Token")
    except Exception:
        token = None
    if token:
        return WorkspaceClient(config=Config(host=config.HOST, token=token, auth_type="pat",
                                             http_timeout_seconds=_HTTP_TIMEOUT_S))
    return WorkspaceClient(config=Config(http_timeout_seconds=_HTTP_TIMEOUT_S))


def chat(system: str, user: str, max_tokens: int = 6000) -> str:
    """Query the chat endpoint (no temperature: Claude reasoning models reject it)."""
    resp = _client().serving_endpoints.query(
        name=config.LLM_ENDPOINT,
        messages=[ChatMessage(role=ChatMessageRole.SYSTEM, content=system),
                  ChatMessage(role=ChatMessageRole.USER, content=user)],
        max_tokens=max_tokens,
    )
    choices = resp.choices or []
    return _content_text(choices[0].message.content) if choices and choices[0].message else ""


def _content_text(content) -> str:
    """Keep only text blocks (reasoning models return [reasoning, text] blocks)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    parts = []
    for block in content if isinstance(content, list) else [content]:
        if isinstance(block, str):
            parts.append(block)
            continue
        btype = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
        if btype and btype != "text":
            continue
        t = block.get("text") if isinstance(block, dict) else getattr(block, "text", None)
        if t:
            parts.append(t)
    return "".join(parts).strip()


def _parse_json(raw: str) -> dict:
    if not raw:
        return {}
    s = raw.strip()
    try:
        return json.loads(s)
    except Exception:
        i, j = s.find("{"), s.rfind("}")
        if 0 <= i < j:
            try:
                return json.loads(s[i:j + 1])
            except Exception:
                return {}
    return {}


def _precedent_block(precedent: list[dict] | None) -> str:
    if not precedent:
        return ""
    joined = "\n\n".join(f"[{i + 1}] {p.get('agreement_number') or p.get('source')}: {(p.get('text') or '')[:1500]}"
                         for i, p in enumerate(precedent))
    return ("\n\nPRIOR ACF AGREEMENTS (mirror their tone, structure and obligations; do not copy partner-specific "
            "facts from them):\n" + joined)


_BASE_RULES = (
    "You draft documents for the Administration for Children and Families (ACF), Office of the Chief Information "
    "Officer, about Delta Sharing data exchanges with other HHS operating divisions. Follow NIST SP 800-47 and the "
    "Privacy Act. Use ONLY the facts in the request for names, dates, agreement numbers, share and recipient names, "
    "tables and columns; never invent new ones. Plain, formal federal prose. Return ONLY a JSON object, no fences."
)

# ---------------------------------------------------------------- new MOU / ISA
AGREEMENT_KEYS = {
    "purpose_statement": "1-2 sentence purpose of the data exchange",
    "system_b_function": "one sentence describing the partner system's function",
    "description_of_data": "1-2 sentences describing the data shared (reference Appendix C)",
    "minimum_necessary": "paragraph explaining why each selected column is needed and why the rest of the table is not",
    "identifier_justifications": [{"column": "table.column", "justification": "why this identifier is required, or 'NOT JUSTIFIED' if the purpose does not need it"}],
    "special_safeguards": ["additional security or privacy condition"],
    "review_flags": ["issue a privacy officer or ISSO should look at before signing"],
}


def draft_agreement(facts: dict, precedent: list[dict] | None = None) -> dict:
    system = (_BASE_RULES + "\n\nTask: write the narrative sections of a new ACF data-sharing agreement. JSON keys:\n"
              + json.dumps(AGREEMENT_KEYS, indent=2)
              + "\n\nFor every direct identifier in the column list, add an identifier_justifications entry. If the "
                "stated purpose can be met without a selected identifier, say NOT JUSTIFIED and add a review flag. "
                "Recommend de-identified alternatives (age instead of DOB, hashed instead of raw SSN) where they exist."
              + _precedent_block(precedent))
    data = _parse_json(chat(system, "Agreement facts:\n" + json.dumps(facts, indent=2, default=str), max_tokens=8000))
    if not data:
        raise RuntimeError("The model did not return a usable draft. Try again.")
    return data


# ---------------------------------------------------------------- remediation documents
DOC_KINDS = {
    "AMENDMENT": "Amendment to the agreement",
    "NOTICE": "Notice to the partner agency",
    "MEMO": "Internal remediation memo (ACF OCIO / Privacy Office)",
    "RENEWAL": "Renewal agreement cover memo",
}

_DOC_GUIDE = {
    "AMENDMENT": ("A formal amendment. 'change_summary' states exactly what changes in Appendix C, the recipient or the "
                  "dates. 'justification' explains why. 'conditions' lists obligations that come with the change."),
    "NOTICE": ("A letter from the ACF CIO to the partner's signatory. Explain what was found, what ACF did or will do, "
               "and what the partner must do (for over-sharing of identifiers: stop using, delete local copies and "
               "certify deletion within a deadline; for expiration: access ends unless renewed). Firm but collegial."),
    "MEMO": ("An internal memo to the ACF Privacy Officer and ISSO: finding, risk (cite Privacy Act / breach response "
             "obligations when direct identifiers were exposed), root cause hypotheses, remediation steps with owners, "
             "and whether a privacy incident report is required."),
    "RENEWAL": ("A cover memo proposing renewal of an expiring/expired agreement: current scope, usage evidence, "
                "recommended term, any scope reductions, and approval routing."),
}

DOC_KEYS = {
    "subject": "one-line subject",
    "sections": [{"heading": "section heading", "body": "paragraph text (use \\n for line breaks)"}],
    "action_items": [{"action": "what", "owner": "who (role)", "due": "relative due date"}],
    "change_summary": "AMENDMENT only: what Appendix C / recipient / dates change",
    "justification": "AMENDMENT only",
    "conditions": ["AMENDMENT only: condition"],
}


def draft_remediation_doc(doc_kind: str, facts: dict, precedent: list[dict] | None = None) -> dict:
    system = (_BASE_RULES + f"\n\nTask: draft a {DOC_KINDS[doc_kind]} for a Delta Share compliance finding. "
              + _DOC_GUIDE[doc_kind] + "\nJSON keys:\n" + json.dumps(DOC_KEYS, indent=2)
              + "\nOmit AMENDMENT-only keys for other document types. 3-6 sections."
              + _precedent_block(precedent))
    data = _parse_json(chat(system, "Finding and context:\n" + json.dumps(facts, indent=2, default=str), max_tokens=8000))
    if not data:
        raise RuntimeError("The model did not return a usable draft. Try again.")
    return data
