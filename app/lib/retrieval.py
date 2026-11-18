"""Precedent retrieval over the agreement corpus (vector index agreement_chunks_index).

Acts on behalf of the signed-in user. Falls back to the SQL table function
``search_agreements`` (same chunks, ai_query embeddings) if the vector index call fails.
"""

from __future__ import annotations

import streamlit as st
from databricks.sdk import WorkspaceClient
from databricks.sdk.core import Config

import config
from lib import db


def _client() -> WorkspaceClient:
    try:
        token = st.context.headers.get("X-Forwarded-Access-Token")
    except Exception:
        token = None
    if token:
        return WorkspaceClient(config=Config(host=config.HOST, token=token, auth_type="pat"))
    return WorkspaceClient()


def retrieve(query: str, k: int = 5) -> list[dict]:
    """Top-k agreement passages for ``query``: [{text, source, agreement_number, partner_agency, score}]."""
    if not query.strip():
        return []
    try:
        cols = ["chunk_to_retrieve", "file_name", "agreement_number", "partner_agency"]
        resp = _client().vector_search_indexes.query_index(
            index_name=config.VS_INDEX, columns=cols, query_text=query, num_results=k)
        names = [c.name for c in resp.manifest.columns] if resp.manifest and resp.manifest.columns else []
        rows = (resp.result.data_array if resp.result and resp.result.data_array else []) or []
        out = [dict(zip(names, r)) for r in rows]
        return [{"text": (r.get("chunk_to_retrieve") or "").strip(), "source": r.get("file_name"),
                 "agreement_number": r.get("agreement_number"), "partner_agency": r.get("partner_agency"),
                 "score": r.get("score")} for r in out if r.get("chunk_to_retrieve")]
    except Exception:
        df = db.query_df(f"SELECT * FROM {config.fq('search_agreements')}(:q)", {"q": query})
        return [{"text": r.chunk_text, "source": r.file_name, "agreement_number": r.agreement_number,
                 "partner_agency": r.partner_agency, "score": r.score} for r in df.itertuples()]
