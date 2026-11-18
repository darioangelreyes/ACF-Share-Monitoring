# Databricks notebook source
# MAGIC %md
# MAGIC # 08 — Genie space: ACF Delta Share Compliance
# MAGIC Covers:
# MAGIC - the compliance findings
# MAGIC - the extracted agreements
# MAGIC - the share inventory
# MAGIC - the system-table views (shared columns, refresh cadence, internal access, reads, recipient activity)
# MAGIC - the `search_agreements` function, for questions about agreement text
# MAGIC
# MAGIC Every example SQL runs here first, so a broken query fails this notebook instead of teaching Genie a bad answer. Safe to re-run: it updates the space with the same title.

# COMMAND ----------

# MAGIC %run ./00_config

# COMMAND ----------

import json, uuid
from databricks.sdk import WorkspaceClient
w = WorkspaceClient()
# GENIE_TITLE comes from 00_config. A space you can see with the same title is updated in place, so keep titles unique per install.
def sid(t): return uuid.uuid5(uuid.NAMESPACE_URL, f"acf-ds-genie/{t}").hex
TABLES = [f"{S}.{t}" for t in [
  "share_compliance_findings", "share_compliance_summary", "sharing_agreements", "agreement_data_elements", "agreement_signatories",
  "agreement_field_confidence", "mv_agreement_permitted_columns", "mv_shared_columns", "mv_source_refresh_activity", "mv_source_access_grants",
  "mv_source_table_reads", "mv_delta_sharing_activity", "share_inventory", "share_objects", "share_grants", "share_recipients"]]
FUNCTIONS = [f"{S}.search_agreements"]
DATA_NOTE = ("All agreements, people, shares and records are synthetic. Do not describe results as real ACF operations." if USE_SYNTHETIC_DATA else
             "Agreements, shares, recipients and activity are real ACF data. Treat results as sensitive.")
INSTRUCTIONS = f"""
You answer questions from the ACF Office of the Chief Information Officer about whether ACF's Delta Shares with other HHS operating divisions (NIH, CDC, FDA, CMS, OS) match the signed data-sharing agreements (MOUs, Interconnection Security Agreements and amendments).
- {DATA_NOTE}
- Start compliance questions with share_compliance_findings (one row per issue: finding_type, severity, share_name, recipient_name, agreement_number, source_table, column_name, detail) or share_compliance_summary (one row per share: compliance_status, counts by severity).
- Finding types: OVER_SHARING (column shared but not permitted), UNDER_SHARING (permitted but not shared), EXPIRED_AGREEMENT, ACCESS_AFTER_EXPIRATION, EXPIRING_SOON, RECIPIENT_MISMATCH, NO_AGREEMENT, NOT_IMPLEMENTED, UNSIGNED_AGREEMENT, NEEDS_REVIEW (low-confidence AI extraction). Severity order: CRITICAL, HIGH, MEDIUM, LOW, INFO, REVIEW.
- Agreement terms come from PDFs via ai_parse_document, ai_classify and ai_extract: sharing_agreements (one row per document; document_type MEMORANDUM_OF_UNDERSTANDING, INTERCONNECTION_SECURITY_AGREEMENT or AMENDMENT), agreement_data_elements (permitted table + column per document), mv_agreement_permitted_columns (permitted columns per share with amendments applied). Join agreements to shares on share_name, not agreement_number.
- What is actually shared: mv_shared_columns (every column each recipient receives, its source column via column lineage, identifier_level direct / indirect / none from column tags), share_objects, share_grants, share_recipients.
- System-table views: mv_source_refresh_activity (how often each shared table is written, by which job, whether the job is scheduled), mv_source_access_grants (internal users, groups and service principals who can read the source tables), mv_source_table_reads (who read them in the last 90 days), mv_delta_sharing_activity (recipient queries per share; event_source AUDIT is real, SYNTHETIC is demo data).
- ROUTING: any question about what IS shared, allowed, permitted, exposed, over-shared, expired, granted or queried is a data question: answer it with SQL on share_compliance_findings / share_compliance_summary / mv_shared_columns / mv_agreement_permitted_columns, never with search_agreements. "Does the agreement allow column X" is answered from mv_agreement_permitted_columns.
- Use search_agreements('<question>') ONLY for the wording of an agreement that is not in a table: security responsibilities, notification and incident duties, termination and notice periods, authority, purpose narrative. Cite agreement_number.
- Never list individual people's names, SSNs, dates of birth or contact details from the ACF source tables; answer with counts. Column names are fine.
- When asked "what should we do", recommend revoking or narrowing the share, or amending the agreement, based on the finding type.
"""
SAMPLE_QUESTIONS = [
  "Which shares are out of compliance with their agreements?",
  "Are we sharing any direct identifiers that the agreement doesn't allow?",
  "Which agreements have expired but are still being queried?",
  "Is any share granted to a recipient the agreement doesn't name?",
  "Which shares have no agreement on file?",
  "Which agreements expire in the next 6 months?",
  "Who inside ACF can read tables that contain direct identifiers?",
  "How often are the shared tables refreshed, and are any on a schedule?",
  "Which recipients queried our shares most in the last 30 days?",
  "Which extracted agreement fields need human review?",
  "What does the CMS TANF agreement say about termination?",
  "Which columns does NIH NICHD receive, and which are identifiers?",
]
EXAMPLES = [
 ("Which shares are out of compliance?", f"""
SELECT share_name, partner_agency, agreement_number, compliance_status, critical, high, finding_types
FROM {S}.share_compliance_summary
WHERE compliance_status <> 'COMPLIANT'
ORDER BY critical DESC, high DESC"""),
 ("Are we sharing direct identifiers the agreement doesn't allow?", f"""
SELECT share_name, recipient_name, agreement_number, source_table, column_name, detail
FROM {S}.share_compliance_findings
WHERE finding_type = 'OVER_SHARING' AND identifier_level = 'direct'
ORDER BY share_name"""),
 ("Recipient queries after the agreement expired", f"""
SELECT a.share_name, a.agreement_number, a.expiration_date, x.recipient_name, count(*) AS queries_after_expiration, max(x.event_time) AS last_query
FROM {S}.sharing_agreements a JOIN {S}.mv_delta_sharing_activity x ON x.share_name = a.share_name AND x.event_date > a.expiration_date
WHERE a.document_type <> 'AMENDMENT'
GROUP BY ALL ORDER BY queries_after_expiration DESC"""),
 ("Which agreements expire soonest?", f"""
SELECT agreement_number, partner_agency, partner_office, share_name, expiration_date, datediff(expiration_date, current_date()) AS days_left
FROM {S}.sharing_agreements
WHERE document_type <> 'AMENDMENT' AND expiration_date >= current_date()
ORDER BY expiration_date"""),
 ("Who can read source tables that contain direct identifiers?", f"""
SELECT table_name, direct_identifier_columns, grantee, grantee_type, privileges, granted_on
FROM {S}.mv_source_access_grants
WHERE can_read AND direct_identifier_columns > 0 AND object_role = 'SOURCE_TABLE'
ORDER BY direct_identifier_columns DESC, table_name, grantee"""),
 ("How often are the shared tables refreshed?", f"""
SELECT table_name, writes_90d, days_written_90d, last_write, days_since_last_write, last_writer_type, last_writer_job_name, job_trigger_type
FROM {S}.mv_source_refresh_activity
ORDER BY days_since_last_write DESC"""),
 ("Recipient query volume in the last 30 days", f"""
SELECT recipient_name, share_name, count(*) AS queries, count(DISTINCT event_date) AS active_days, max(event_time) AS last_query
FROM {S}.mv_delta_sharing_activity
WHERE event_date >= current_date() - 30
GROUP BY ALL ORDER BY queries DESC"""),
 ("Columns a recipient receives, with identifier level", f"""
SELECT share_name, recipient_name, source_table, shared_column, source_column, identifier_level, traced_by_lineage
FROM {S}.mv_shared_columns
WHERE recipient_name = 'nih_nichd'
ORDER BY identifier_level, shared_column"""),
 ("Extracted fields that need human review", f"""
SELECT file_name, field, value, round(confidence, 2) AS confidence
FROM {S}.agreement_field_confidence
WHERE confidence < 0.8
ORDER BY confidence"""),
 ("What does an agreement say about termination?", f"""
SELECT agreement_number, partner_agency, round(score, 3) AS score, chunk_text
FROM {S}.search_agreements('termination of the agreement and notice period for CMS TANF data')"""),
]

# COMMAND ----------

for t in TABLES: spark.sql(f"DESCRIBE TABLE {t}").collect()
for f in FUNCTIONS: spark.sql(f"DESCRIBE FUNCTION {f}").collect()
for q, sql in EXAMPLES:
    n = spark.sql(sql).count(); print(f"{n:>5} rows  {q}")
    # Synthetic data is built so every example returns rows. Real data may legitimately return none (e.g. no expired agreements).
    if USE_SYNTHETIC_DATA: assert n > 0, q
    elif n == 0: print("      (no rows in your data; the example still runs, so it is kept)")

# COMMAND ----------

lines = lambda s: [l + "\n" for l in s.strip().split("\n")]
space = {
  "version": 2,
  "config": {"sample_questions": sorted([{"id": sid("q/" + q), "question": [q]} for q in SAMPLE_QUESTIONS], key=lambda x: x["id"])},
  "data_sources": {"tables": sorted([{"identifier": t} for t in TABLES], key=lambda x: x["identifier"])},
  "instructions": {
    "text_instructions": [{"id": sid("instructions"), "content": lines(INSTRUCTIONS)}],
    "sql_functions": sorted([{"id": sid("fn/" + f), "identifier": f} for f in FUNCTIONS], key=lambda x: x["id"]),
    "example_question_sqls": sorted([{"id": sid("sql/" + q), "question": [q], "sql": lines(s)} for q, s in EXAMPLES], key=lambda x: x["id"])},
}
body = {"title": GENIE_TITLE, "warehouse_id": WAREHOUSE_ID, "serialized_space": json.dumps(space),
        "description": "Ask whether ACF Delta Shares with NIH, CDC, FDA, CMS and OS match the signed MOUs and ISAs: over-sharing, expired agreements, wrong recipients, refresh cadence, internal access and recipient activity." + (" Synthetic demo data." if USE_SYNTHETIC_DATA else "")}
existing = [s for s in w.api_client.do("GET", "/api/2.0/genie/spaces").get("spaces", []) if s.get("title") == GENIE_TITLE]
if existing:
    space_id = existing[0]["space_id"]; w.api_client.do("PATCH", f"/api/2.0/genie/spaces/{space_id}", body=body); print("updated", space_id)
else:
    space_id = w.api_client.do("POST", "/api/2.0/genie/spaces", body=dict(body, parent_path=PROJECT_FOLDER))["space_id"]; print("created", space_id)
print(f"{w.config.host.rstrip('/')}/genie/rooms/{space_id}")
dbutils.notebook.exit(space_id)