"""Unity Catalog reads via the Databricks SQL **Statement Execution API**.

We use the Statement Execution REST API (through the Databricks SDK) rather than
the Thrift `databricks-sql-connector`. Inside the Databricks Apps runtime the
Thrift/cloud-fetch transport proved unreliable ("Error during request to
server"); the Statement Execution API talks plain HTTPS to the workspace control
plane, returns clean error messages, and accepts the on-behalf-of-user bearer
token directly.

Auth, in priority order:
1. **On-behalf-of-user (OBO):** the signed-in user's ``X-Forwarded-Access-Token``
   (so Unity Catalog enforces per-user grants).
2. **SDK default:** the app service principal when deployed, or your CLI/profile
   when running locally.
"""

from __future__ import annotations

import time

import pandas as pd
import streamlit as st
from databricks.sdk import WorkspaceClient
from databricks.sdk.core import Config
from databricks.sdk.service.sql import StatementParameterListItem, StatementState

import config

# Column type names (ColumnInfoTypeName) that should become numeric in pandas.
_NUMERIC_TYPES = {"BYTE", "SHORT", "INT", "LONG", "FLOAT", "DOUBLE", "DECIMAL"}
_MAX_ATTEMPTS = 4

# Substrings that mark an auth/session error (stale or unconsented OBO token) —
# these are NOT transient, so retrying is pointless; the user must reload.
_AUTH_HINTS = (
    "invalid scope", "required scopes", "403", "forbidden", "unauthenticated",
    "permission_denied", "permission denied", "unable to parse response",
)


def is_auth_error(exc: Exception) -> bool:
    return any(h in str(exc).lower() for h in _AUTH_HINTS)


def _user_token() -> str | None:
    """The signed-in user's forwarded access token, if running in an App."""
    try:
        return st.context.headers.get("X-Forwarded-Access-Token")
    except Exception:
        return None


def _client() -> WorkspaceClient:
    token = _user_token()
    if token:  # OBO — act as the signed-in user
        # Force PAT-only auth: the Apps runtime also injects the app service
        # principal's OAuth env vars (DATABRICKS_CLIENT_ID/SECRET), and the SDK
        # refuses to start when it detects two auth methods at once. auth_type
        # ="pat" makes it send only the user's bearer token.
        return WorkspaceClient(
            config=Config(host=config.HOST, token=token, auth_type="pat")
        )
    return WorkspaceClient()  # SP (deployed) or local profile


def _to_df(resp) -> pd.DataFrame:
    """Build a typed DataFrame from a Statement Execution response."""
    schema = resp.manifest.schema if resp.manifest else None
    cols = list(schema.columns) if schema and schema.columns else []
    names = [c.name for c in cols]
    data = (resp.result.data_array if resp.result and resp.result.data_array else []) or []
    df = pd.DataFrame(data, columns=names)
    for c in cols:  # the API returns everything as strings; coerce numerics
        tn = getattr(c.type_name, "value", str(c.type_name)) if c.type_name else ""
        if tn in _NUMERIC_TYPES and c.name in df.columns:
            df[c.name] = pd.to_numeric(df[c.name], errors="coerce")
    return df


def _execute(query: str, params) -> pd.DataFrame:
    """Run a statement and return a DataFrame, with retry + polling.

    Retries ride out transient hiccups and serverless cold starts; polling waits
    for statements that don't finish within the inline wait window.
    """
    plist = (
        [StatementParameterListItem(name=k, value=(None if v is None else str(v)))
         for k, v in params.items()]
        if params else None
    )
    last_err: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            w = _client()
            resp = w.statement_execution.execute_statement(
                warehouse_id=config.WAREHOUSE_ID, statement=query,
                parameters=plist, wait_timeout="30s",
            )
            sid = resp.statement_id
            while resp.status and resp.status.state in (
                StatementState.PENDING, StatementState.RUNNING
            ):
                time.sleep(1.5)
                resp = w.statement_execution.get_statement(sid)
            state = resp.status.state if resp.status else None
            if state != StatementState.SUCCEEDED:
                err = resp.status.error if resp.status else None
                raise RuntimeError(
                    f"Statement {state}: {err.message if err else 'unknown error'}"
                )
            return _to_df(resp)
        except Exception as exc:
            last_err = exc
            # Auth/session errors won't fix themselves — fail fast so the UI can
            # tell the user to reload rather than stalling on retries.
            if is_auth_error(exc) or attempt == _MAX_ATTEMPTS - 1:
                break
            time.sleep(3 * (attempt + 1))  # 3s, 6s, 9s
    raise last_err  # type: ignore[misc]


@st.cache_data(ttl=300, show_spinner="Querying the warehouse…")
def query_df(query: str, params: dict | None = None) -> pd.DataFrame:
    """Run a read query and return a DataFrame. Cached for 5 minutes."""
    return _execute(query, params)


@st.cache_data(ttl=600, show_spinner=False)
def distinct_values(table: str, column: str, limit: int = 500) -> list:
    """Distinct, non-null values for a column — used to populate filters."""
    df = query_df(
        f"SELECT DISTINCT {column} AS v FROM {config.fq(table)} "
        f"WHERE {column} IS NOT NULL ORDER BY v LIMIT {int(limit)}"
    )
    return df["v"].tolist() if not df.empty else []
