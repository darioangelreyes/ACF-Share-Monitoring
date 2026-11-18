"""Genie Conversation API client — the native fallback for the Ask Genie page.

The primary Ask-Genie experience is an embedded iframe. When iframe embedding is
blocked (third-party cookies disabled, embedding policy off), this module drives
the same Genie Space through the Conversation API and renders results inline.

Auth matches the data layer: it acts **on behalf of the signed-in user** via the
forwarded ``X-Forwarded-Access-Token`` (forcing auth_type="pat" so the SDK
doesn't conflict with the app service principal's injected OAuth env vars), and
falls back to the SDK default (SP / local profile) when no user token is present.
The app service principal has no access to the Genie Space, so the user token is
required here.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from databricks.sdk import WorkspaceClient
from databricks.sdk.core import Config

import config


def _client() -> WorkspaceClient:
    # Not cached: the OBO token is per-user/per-session, so a shared client would
    # leak one user's identity to others.
    try:
        token = st.context.headers.get("X-Forwarded-Access-Token")
    except Exception:
        token = None
    if token:
        return WorkspaceClient(
            config=Config(host=config.HOST, token=token, auth_type="pat")
        )
    return WorkspaceClient()


def is_configured() -> bool:
    return bool(config.GENIE_SPACE_ID)


def ask(question: str, conversation_id: str | None = None, timeout_s: int = 120) -> dict:
    """Ask Genie a question and wait for the answer.

    Returns a dict with: ``text`` (Genie's narrative), ``sql`` (generated query,
    if any), ``dataframe`` (query result, if any), ``conversation_id`` and
    ``message_id`` so callers can thread follow-up questions.
    """
    w = _client()
    space_id = config.GENIE_SPACE_ID
    if not space_id:
        raise RuntimeError("ACF_GENIE_SPACE_ID is not configured.")

    if conversation_id:
        msg = w.genie.create_message_and_wait(space_id, conversation_id, question)
    else:
        msg = w.genie.start_conversation_and_wait(space_id, question)
        conversation_id = msg.conversation_id

    text_parts: list[str] = []
    dataframe: pd.DataFrame | None = None
    generated_sql: str | None = None

    for attachment in msg.attachments or []:
        if attachment.text and attachment.text.content:
            text_parts.append(attachment.text.content)
        if attachment.query:
            generated_sql = attachment.query.query
            if dataframe is None:
                # get_message_attachment_query_result is the only call that
                # returns the result rows (get_message_query_result comes back
                # empty). It needs a current SDK, which requirements.txt pins.
                result = w.genie.get_message_attachment_query_result(
                    space_id, conversation_id, msg.id, attachment.attachment_id
                )
                dataframe = _result_to_df(result)

    return {
        "text": "\n\n".join(text_parts).strip(),
        "sql": generated_sql,
        "dataframe": dataframe,
        "conversation_id": conversation_id,
        "message_id": msg.id,
    }


def _result_to_df(result) -> pd.DataFrame | None:
    """Convert a Genie statement-execution result into a DataFrame."""
    sr = getattr(result, "statement_response", None)
    if sr is None:
        return None
    schema = sr.manifest.schema if sr.manifest else None
    cols = [c.name for c in schema.columns] if schema and schema.columns else []
    data = sr.result.data_array if sr.result and sr.result.data_array else []
    return pd.DataFrame(data, columns=cols) if cols else None
