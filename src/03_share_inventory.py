# Databricks notebook source
# MAGIC %md
# MAGIC # 03 — Shares: the objects being shared and the share inventory
# MAGIC For every Delta Share in `_agreements_spec`, this notebook creates the **real** object the share exposes:
# MAGIC - a view selecting exactly the columns the share carries (`shr_<share>__<table>`), or
# MAGIC - the source table itself, when the whole table is shared.
# MAGIC
# MAGIC It then records the share inventory in the same shape the Delta Sharing API returns:
# MAGIC
# MAGIC | Table | Holds |
# MAGIC |---|---|
# MAGIC | `share_inventory` | shares |
# MAGIC | `share_objects` | objects in each share |
# MAGIC | `share_recipients` | recipients |
# MAGIC | `share_grants` | recipient grants |
# MAGIC
# MAGIC **Synthetic vs real (`USE_SYNTHETIC_DATA` in `00_config`):**
# MAGIC - `True` (demo): the shares above are synthetic, because creating real shares and recipients needs `CREATE SHARE` / `CREATE RECIPIENT` on the metastore.
# MAGIC - `False` (real): no views are created; the same four tables are filled from the real Delta Sharing API instead (`w.shares`, `w.recipients`,
# MAGIC   share permissions), for shares whose name starts with `SHARE_NAME_PREFIX`. Downstream views don't change. Column metadata always comes from the real
# MAGIC `system.information_schema.columns`.

# COMMAND ----------

# MAGIC %run ./00_config

# COMMAND ----------

# MAGIC %run ./_agreements_spec

# COMMAND ----------

# DBTITLE 1,Build the share inventory
from datetime import date, timedelta
import pandas as pd
RECIPIENT_ORG = {"nih_nichd": ("NIH", "NICHD"), "nih_niehs": ("NIH", "NIEHS"), "cdc_ncipc": ("CDC", "NCIPC"), "cdc_ncird": ("CDC", "NCIRD"),
                 "cdc_nchs": ("CDC", "NCHS"), "fda_hfp": ("FDA", "Human Foods Program"), "cms_cmcs": ("CMS", "CMCS"), "cms_ccsq": ("CMS", "CCSQ"),
                 "os_aspe": ("OS", "ASPE"), "os_ocio": ("OS", "OCIO")}
shares, objects, grants = [], [], []
# Synthetic mode: shares come from _agreements_spec. Real mode: nothing here; the API block below fills the tables.
specs = ([a for a in AGREEMENTS if a["kind"] != "AMENDMENT" and a.get("shared")] + UNDOCUMENTED_SHARES) if USE_SYNTHETIC_DATA else []
for a in specs:
    created = date.fromisoformat(a.get("effective", "2026-05-18")) + timedelta(days=9)
    shares.append((a["share"], f"ACF share for {a['recipient']}", "acf-data-governance@acf.example.gov", created))
    for t, shared_cols in (a.get("shared") or a["tables"]).items():
        if sorted(shared_cols) == sorted(cols(t)):
            obj, typ = f"{S}.{t}", "TABLE"
        else:
            obj, typ = f"{S}.shr_{a['share']}__{t}", "VIEW"
            spark.sql(f"CREATE OR REPLACE VIEW {obj} COMMENT 'Object shared in Delta Share {a['share']} (columns exposed to the recipient). SYNTHETIC.' "
                      f"AS SELECT {', '.join(shared_cols)} FROM {S}.{t}")
        objects.append((a["share"], obj, typ, f"acf.{t}", f"{S}.{t}", created, "ACTIVE"))
    grants.append((a["share"], a.get("shared_recipient", a["recipient"]), "SELECT", created + timedelta(days=1)))
recipients = [(r, "DATABRICKS", org, office, f"aws:us-east-1:{abs(hash(r)) % 10**8:08d}-acf-demo", date(2024, 9, 1))
              for r, (org, office) in RECIPIENT_ORG.items()] if USE_SYNTHETIC_DATA else []

if SHARE_SOURCE == "api":   # real Delta Sharing metadata (needs USE SHARE / USE RECIPIENT)
    from databricks.sdk import WorkspaceClient
    w = WorkspaceClient(); shares, objects, grants, recipients = [], [], [], []
    for sh in w.shares.list():
        if not sh.name.startswith(SHARE_NAME_PREFIX): continue
        full = w.shares.get(sh.name, include_shared_data=True)
        shares.append((sh.name, sh.comment, sh.owner, date.fromtimestamp(sh.created_at / 1000)))
        for o in full.objects or []:
            objects.append((sh.name, o.name, o.data_object_type.value, o.shared_as or o.name, o.name, date.fromtimestamp(o.added_at / 1000), o.status.value if o.status else "ACTIVE"))
        for p in w.shares.share_permissions(sh.name).privilege_assignments or []:
            grants.append((sh.name, p.principal, ",".join(x.value for x in p.privileges), date.today()))
    for r in w.recipients.list():
        recipients.append((r.name, r.authentication_type.value, *(RECIPIENT_ORG.get(r.name, ("", ""))), r.data_recipient_global_metastore_id or "", date.fromtimestamp(r.created_at / 1000)))

def save(rows, name, schema, comment):
    spark.createDataFrame(rows, schema).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{S}.{name}")
    spark.sql(f"COMMENT ON TABLE {S}.{name} IS '{comment} Source: {SHARE_SOURCE}.'")
    print(f"{name:18s} {len(rows)} rows")
save(shares, "share_inventory", "share_name STRING, comment STRING, owner STRING, created_at DATE", "Delta Shares published by ACF (shape of the Delta Sharing shares API).")
save(objects, "share_objects", "share_name STRING, object_name STRING, data_object_type STRING, shared_as STRING, source_table STRING, added_at DATE, status STRING",
     "Objects in each Delta Share: the shared table or view, the name the recipient sees, and the ACF source table behind it.")
save(recipients, "share_recipients", "recipient_name STRING, authentication_type STRING, agency STRING, office STRING, sharing_identifier STRING, created_at DATE",
     "Delta Sharing recipients (partner HHS operating divisions and offices).")
save(grants, "share_grants", "share_name STRING, recipient_name STRING, privilege STRING, granted_at DATE", "Which recipient holds which privilege on which share.")

# ground truth, for the demo's reconciliation only (the compliance views never read it)
if USE_SYNTHETIC_DATA:
    gt = [(a.get("doc_id"), a.get("share"), a.get("scenario"), a.get("note")) for a in AGREEMENTS] + [(None, u["share"], u["scenario"], u["note"]) for u in UNDOCUMENTED_SHARES]
    save(gt, "_scenario_ground_truth", "doc_id STRING, share_name STRING, scenario STRING, note STRING", "GENERATOR ARTIFACT: the mismatch each share was built to show.")
else:
    spark.sql(f"DROP TABLE IF EXISTS {S}._scenario_ground_truth")
    if not shares: print(f"WARNING: no Delta Shares named {SHARE_NAME_PREFIX}* were found (check SHARE_NAME_PREFIX and USE SHARE privileges).")
display(spark.sql(f"SELECT o.share_name, g.recipient_name, o.data_object_type, o.object_name FROM {S}.share_objects o JOIN {S}.share_grants g USING (share_name) ORDER BY 1"))