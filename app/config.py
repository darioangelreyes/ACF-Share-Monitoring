"""Central, env-driven configuration for the ACF Delta Share Compliance app.

Every value comes from an environment variable: the bundle sets them for the deployed
app (config.env in resources/acf_share_monitoring.app.yml), or your shell for local runs. There are no workspace-specific defaults; unset values
and unfilled "<FILL_IN: ...>" placeholders are listed in MISSING_SETTINGS and
shown as an error by app.py.
"""

from __future__ import annotations

import os


def _env(name: str, default: str = "") -> str:
    """Env var value; unset or an unfilled "<FILL_IN ...>" placeholder becomes the default."""
    value = os.getenv(name, "").strip()
    return default if not value or value.startswith("<FILL_IN") else value


def _host() -> str:
    """Workspace host as a clean https URL (Apps inject DATABRICKS_HOST without a scheme)."""
    host = _env("DATABRICKS_HOST").rstrip("/")
    return host if not host or host.startswith("http") else f"https://{host}"


HOST: str = _host()
ORG_ID: str = _env("DATABRICKS_WORKSPACE_ID") or _env("ACF_ORG_ID")
WAREHOUSE_ID: str = _env("ACF_WAREHOUSE_ID")
CATALOG: str = _env("ACF_CATALOG")
SCHEMA: str = _env("ACF_SCHEMA")

GENIE_SPACE_ID: str = _env("ACF_GENIE_SPACE_ID")          # optional: the Ask Genie page explains how to set it
LLM_ENDPOINT: str = _env("ACF_LLM_ENDPOINT")
VS_INDEX: str = _env("ACF_VS_INDEX", f"{CATALOG}.{SCHEMA}.agreement_chunks_index" if CATALOG and SCHEMA else "")

APP_TITLE: str = "ACF Delta Share Compliance"

# Required settings that are still unset (app.py stops with an error listing them).
MISSING_SETTINGS: list[str] = [name for name, value in {
    "DATABRICKS_HOST": HOST, "ACF_WAREHOUSE_ID": WAREHOUSE_ID, "ACF_CATALOG": CATALOG, "ACF_SCHEMA": SCHEMA,
    "ACF_LLM_ENDPOINT": LLM_ENDPOINT, "ACF_VS_INDEX": VS_INDEX}.items() if not value]


def fq(table: str) -> str:
    """Fully-qualified ``catalog.schema.table`` name."""
    return f"{CATALOG}.{SCHEMA}.{table}"
