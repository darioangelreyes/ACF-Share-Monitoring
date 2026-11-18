# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# DBTITLE 1,How to configure
# MAGIC %md
# MAGIC # 00 — Configuration
# MAGIC Every other notebook starts with `%run ./00_config`.
# MAGIC
# MAGIC **Deployed with the bundle (normal path):** don't edit this notebook. Set the values as variables in `databricks.yml`
# MAGIC (per target). The bundle passes them to the job as parameters, and this notebook reads them below.
# MAGIC
# MAGIC **Running a notebook by hand (outside the job):** each value falls back to the default after the parameter name in
# MAGIC sections 1 and 2. Replace the `<FILL_IN: ...>` defaults, or add notebook widgets with the same names.
# MAGIC
# MAGIC 1. **Section 1 (required):** `catalog`, `schema`, `warehouse_id`, `vs_endpoint`. The notebooks stop with an error naming any value still unset.
# MAGIC 2. **Synthetic data switch:** `use_synthetic_data` = `true` (default) runs the demo on generated data; `false` runs on your real agreements and Delta Shares.
# MAGIC 3. **Section 2 (optional):** the defaults usually work.
# MAGIC 4. **Section 3 (derived):** don't edit. It builds the full names, finds this folder, and creates the schema and volume if they're missing.
# MAGIC
# MAGIC **Prerequisites in the target workspace**
# MAGIC * Unity Catalog with `USE CATALOG` + `CREATE SCHEMA` on `CATALOG` (or an existing `SCHEMA` you can create tables, views, volumes, functions and materialized views in).
# MAGIC * Serverless notebooks (environment version 3 or later) or DBR 18.2+, with the AI functions `ai_parse_document`, `ai_classify`, `ai_extract`, `ai_prep_search` and `ai_query` available in your region.
# MAGIC * A Vector Search endpoint, an embedding model serving endpoint (default `databricks-gte-large-en`) and a SQL warehouse.
# MAGIC * `SELECT` on system tables: `system.access.audit`, `system.access.table_lineage`, `system.access.column_lineage`, `system.lakeflow.jobs`, `system.lakeflow.job_run_timeline`, `system.information_schema.*`.
# MAGIC * For `USE_SYNTHETIC_DATA = False` only: `USE SHARE` / `USE RECIPIENT` (or ownership of the shares and recipients you monitor) on the metastore, and `SELECT` on the real source tables.
# MAGIC
# MAGIC With `USE_SYNTHETIC_DATA = True`, all data, agreements, people and shares are **synthetic**. See `README.md` for the full install checklist.

# COMMAND ----------

# DBTITLE 1,1. Required settings
# =====================================================================================
# 1. REQUIRED: set as bundle variables in databricks.yml (passed in as job parameters).
#    The second argument is only used when you run a notebook by hand outside the job.
# =====================================================================================
def _arg(name, default=""):
    """Job parameter / notebook widget `name`, or `default` when it is missing or empty."""
    try:
        value = dbutils.widgets.get(name).strip()
    except Exception:
        value = ""
    return value or default

CATALOG      = _arg("catalog",      "<FILL_IN: Unity Catalog catalog you can create a schema in>")
SCHEMA       = _arg("schema",       "<FILL_IN: schema for this project, e.g. acf_share_monitoring>")
WAREHOUSE_ID = _arg("warehouse_id", "<FILL_IN: SQL warehouse ID; used by the Genie space>")
VS_ENDPOINT  = _arg("vs_endpoint",  "<FILL_IN: name of an existing Vector Search endpoint>")

# COMMAND ----------

# DBTITLE 1,Synthetic data switch
# =====================================================================================
# SYNTHETIC DATA SWITCH: True = demo on generated data, False = your real data
# =====================================================================================
# True  (default) Demo mode. Generates everything the demo needs inside CATALOG.SCHEMA:
#                 11 synthetic agreement PDFs (01), nine synthetic ACF source tables (02),
#                 a synthetic Delta Share inventory (03) and synthetic recipient activity up to today (06).
#                 No real shares, recipients or source tables are read or changed.
# False           Real mode. 01 and 02 are skipped; 03 reads your real Delta Shares and recipients through the
#                 Delta Sharing API; 06 uses only real audit events. Before switching to False:
#                   1. Upload your signed agreement PDFs to AGREEMENTS_PATH (default /Volumes/<CATALOG>/<SCHEMA>/sample_mous/agreements).
#                   2. Set the bundle variables source_catalog / source_schema (where the shared ACF tables live) and share_name_prefix.
#                   3. Tag identifier columns on those tables: acf_identifier = 'direct' or 'indirect' (see README.md).
# To switch: set the bundle variable use_synthetic_data to true or false for the target in databricks.yml,
# run `databricks bundle deploy`, then run the job (01 and 02 skip themselves in real mode).
USE_SYNTHETIC_DATA = _arg("use_synthetic_data", "true").lower() in ("true", "1", "yes")

# COMMAND ----------

# DBTITLE 1,2. Optional settings
# =====================================================================================
# 2. OPTIONAL: defaults usually work (same-named bundle variables override them)
# =====================================================================================
VOLUME             = _arg("volume", "sample_mous")                            # UC volume inside SCHEMA (created if missing)
AGREEMENTS_PATH    = _arg("agreements_path") or None   # agreement PDFs read by 04. Default: .../{VOLUME}/synthetic_data (synthetic) or .../{VOLUME}/agreements (real)
SOURCE_CATALOG     = _arg("source_catalog") or None    # real mode: catalog of the ACF tables your shares expose (default: CATALOG)
SOURCE_SCHEMA      = _arg("source_schema") or None     # real mode: schema of those tables (default: SCHEMA)
SHARE_NAME_PREFIX  = _arg("share_name_prefix", "acf_")                        # real mode: only Delta Shares whose name starts with this are monitored
EMBEDDING_MODEL    = _arg("embedding_model", "databricks-gte-large-en")       # embedding serving endpoint in your workspace (Serving)
ALERT_EMAIL        = ""                                                       # optional: who receives compliance alerts (not used by the notebooks yet)
GENIE_TITLE        = _arg("genie_title", "ACF Delta Share Compliance")        # Genie space title; 08 updates a visible space with this title, so make it unique
EXPIRING_SOON_DAYS = 90                                                       # agreements expiring within this window are flagged
CREATE_IF_MISSING  = True          # create SCHEMA and VOLUME if missing; set False if an admin pre-creates them
PROJECT_FOLDER     = None          # auto-detected from this notebook's folder; set a "/Workspace/..." path to override (used for the Genie space location)

# COMMAND ----------

# DBTITLE 1,3. Derived settings and checks
# =====================================================================================
# 3. DERIVED: do not edit
# =====================================================================================
import os
S = f"{CATALOG}.{SCHEMA}"
VS_INDEX = f"{S}.agreement_chunks_index"
if not PROJECT_FOLDER:
    _nb = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
    PROJECT_FOLDER = os.path.dirname(_nb if _nb.startswith("/Workspace") else "/Workspace" + _nb)
GENERATOR_PATH = f"{PROJECT_FOLDER}/generator"   # generator script, spec and fonts ship with the project
SHARE_SOURCE = "synthetic" if USE_SYNTHETIC_DATA else "api"   # 03 builds a synthetic share inventory, or reads the Delta Sharing API
AGREEMENTS_PATH = AGREEMENTS_PATH or f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}/" + ("synthetic_data" if USE_SYNTHETIC_DATA else "agreements")
SOURCE_CATALOG = SOURCE_CATALOG or CATALOG
SOURCE_SCHEMA = SOURCE_SCHEMA or SCHEMA

_unfilled = [k for k, v in {"CATALOG": CATALOG, "SCHEMA": SCHEMA, "WAREHOUSE_ID": WAREHOUSE_ID, "VS_ENDPOINT": VS_ENDPOINT}.items()
             if not v or str(v).startswith("<FILL_IN")]
if _unfilled:
    raise ValueError(f"00_config is not configured: set {', '.join(_unfilled)} (bundle variables in databricks.yml, or the defaults in section 1 when running by hand).")
if USE_SYNTHETIC_DATA and not os.path.exists(f"{GENERATOR_PATH}/generate_agreements.py"):
    print(f"WARNING: generator not found in {GENERATOR_PATH}. Keep the generator/ folder next to 00_config, or 01_generate_agreements will fail.")

if CREATE_IF_MISSING:
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{CATALOG}`.`{SCHEMA}`")
    spark.sql(f"CREATE VOLUME IF NOT EXISTS `{CATALOG}`.`{SCHEMA}`.`{VOLUME}`")
spark.sql(f"USE CATALOG `{CATALOG}`"); spark.sql(f"USE SCHEMA `{SCHEMA}`")
spark.conf.set("spark.sql.session.timeZone", "UTC")
print(f"ACF Delta Share Monitoring | {S} | mode: {'SYNTHETIC demo data' if USE_SYNTHETIC_DATA else 'REAL data'} | agreements: {AGREEMENTS_PATH} | sources: {SOURCE_CATALOG}.{SOURCE_SCHEMA}")