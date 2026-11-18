# Databricks notebook source
# MAGIC %md
# MAGIC # 07 — Share compliance findings
# MAGIC Compares what each share actually exposes (`mv_shared_columns`, `mv_delta_sharing_activity`, the share grants) with what the signed agreements
# MAGIC permit (`mv_agreement_permitted_columns`, `sharing_agreements`). Writes one row per issue to the materialized view `share_compliance_findings`.
# MAGIC
# MAGIC | Finding | Severity |
# MAGIC |---|---|
# MAGIC | `OVER_SHARING`: column shared but not permitted | CRITICAL for a direct identifier, HIGH for an indirect one, MEDIUM otherwise |
# MAGIC | `UNDER_SHARING`: column permitted but not shared | LOW |
# MAGIC | `EXPIRED_AGREEMENT`: share still granted after the agreement expired | CRITICAL |
# MAGIC | `ACCESS_AFTER_EXPIRATION`: recipient queried after expiration | CRITICAL |
# MAGIC | `EXPIRING_SOON`: agreement expires within `EXPIRING_SOON_DAYS` | MEDIUM |
# MAGIC | `RECIPIENT_MISMATCH`: share granted to a recipient the agreement does not name | HIGH |
# MAGIC | `NO_AGREEMENT`: share with no agreement on file | CRITICAL |
# MAGIC | `NOT_IMPLEMENTED`: signed, active agreement with no share yet | INFO |
# MAGIC | `UNSIGNED_AGREEMENT`: fewer than two signatures extracted | HIGH |
# MAGIC | `NEEDS_REVIEW`: an extracted agreement field below 0.8 confidence | REVIEW |
# MAGIC
# MAGIC `share_compliance_summary` rolls the findings up to one row per share. The last cell checks the findings against the generator's ground truth.

# COMMAND ----------

# MAGIC %run ./00_config

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE MATERIALIZED VIEW {S}.share_compliance_findings
COMMENT 'One row per compliance issue between what ACF Delta Shares expose and what the signed agreements permit. Refreshed daily.'
AS
WITH ag AS (SELECT * FROM {S}.sharing_agreements WHERE document_type <> 'AMENDMENT'),
sh AS (SELECT DISTINCT share_name, recipient_name FROM {S}.share_grants),
perm AS (SELECT DISTINCT share_name, source_table, column_name FROM {S}.mv_agreement_permitted_columns),
shared AS (SELECT DISTINCT share_name, recipient_name, source_table, source_column, identifier_level FROM {S}.mv_shared_columns),
f AS (
  SELECT s.share_name, s.recipient_name, a.agreement_number, a.partner_agency, 'OVER_SHARING' AS finding_type,
         CASE s.identifier_level WHEN 'direct' THEN 'CRITICAL' WHEN 'indirect' THEN 'HIGH' ELSE 'MEDIUM' END AS severity,
         s.source_table, s.source_column AS column_name, s.identifier_level,
         concat('Column ', s.source_table, '.', s.source_column, ' is shared but not permitted by ', coalesce(a.agreement_number, 'any agreement'),
                CASE WHEN s.identifier_level = 'direct' THEN ' (direct identifier)' ELSE '' END) AS detail
  FROM shared s JOIN ag a ON a.share_name = s.share_name
  LEFT ANTI JOIN perm p ON p.share_name = s.share_name AND p.source_table = s.source_table AND p.column_name = s.source_column
  UNION ALL
  SELECT p.share_name, NULL, a.agreement_number, a.partner_agency, 'UNDER_SHARING', 'LOW', p.source_table, p.column_name, NULL,
         concat('Column ', p.source_table, '.', p.column_name, ' is permitted by ', a.agreement_number, ' but not in the share')
  FROM perm p JOIN ag a ON a.share_name = p.share_name
  WHERE p.share_name IN (SELECT share_name FROM sh)
    AND NOT EXISTS (SELECT 1 FROM shared s WHERE s.share_name = p.share_name AND s.source_table = p.source_table AND s.source_column = p.column_name)
  UNION ALL
  SELECT a.share_name, sh.recipient_name, a.agreement_number, a.partner_agency, 'EXPIRED_AGREEMENT', 'CRITICAL', NULL, NULL, NULL,
         concat(a.agreement_number, ' expired ', a.expiration_date, ' (', datediff(current_date(), a.expiration_date), ' days ago) but the share is still granted to ', sh.recipient_name)
  FROM ag a JOIN sh ON sh.share_name = a.share_name WHERE a.expiration_date < current_date()
  UNION ALL
  SELECT a.share_name, x.recipient_name, a.agreement_number, a.partner_agency, 'ACCESS_AFTER_EXPIRATION', 'CRITICAL', NULL, NULL, NULL,
         concat(x.recipient_name, ' queried the share ', count(*), ' times after ', a.agreement_number, ' expired on ', a.expiration_date, '; last query ', max(x.event_time))
  FROM ag a JOIN {S}.mv_delta_sharing_activity x ON x.share_name = a.share_name AND x.event_date > a.expiration_date
  GROUP BY a.share_name, x.recipient_name, a.agreement_number, a.partner_agency, a.expiration_date
  UNION ALL
  SELECT a.share_name, NULL, a.agreement_number, a.partner_agency, 'EXPIRING_SOON', 'MEDIUM', NULL, NULL, NULL,
         concat(a.agreement_number, ' expires ', a.expiration_date, ' (in ', datediff(a.expiration_date, current_date()), ' days); renew or plan to revoke the share')
  FROM ag a WHERE a.expiration_date BETWEEN current_date() AND current_date() + {EXPIRING_SOON_DAYS}
  UNION ALL
  SELECT a.share_name, sh.recipient_name, a.agreement_number, a.partner_agency, 'RECIPIENT_MISMATCH', 'HIGH', NULL, NULL, NULL,
         concat('Share is granted to ', sh.recipient_name, ' but ', a.agreement_number, ' names ', a.recipient_name)
  FROM ag a JOIN sh ON sh.share_name = a.share_name WHERE sh.recipient_name <> a.recipient_name
  UNION ALL
  SELECT sh.share_name, sh.recipient_name, NULL, NULL, 'NO_AGREEMENT', 'CRITICAL', NULL, NULL, NULL,
         concat('Share ', sh.share_name, ' is granted to ', sh.recipient_name, ' with no MOU or ISA on file')
  FROM sh WHERE sh.share_name NOT IN (SELECT share_name FROM ag WHERE share_name IS NOT NULL)
  UNION ALL
  SELECT a.share_name, a.recipient_name, a.agreement_number, a.partner_agency, 'NOT_IMPLEMENTED', 'INFO', NULL, NULL, NULL,
         concat(a.agreement_number, ' is signed and active but share ', a.share_name, ' does not exist')
  FROM ag a WHERE a.share_name NOT IN (SELECT share_name FROM sh) AND a.expiration_date >= current_date()
  UNION ALL
  SELECT a.share_name, NULL, a.agreement_number, a.partner_agency, 'UNSIGNED_AGREEMENT', 'HIGH', NULL, NULL, NULL,
         concat(a.agreement_number, ' has ', a.signatory_count, ' signature(s) extracted; both parties must sign')
  FROM {S}.sharing_agreements a WHERE a.signatory_count < 2
  UNION ALL
  SELECT a.share_name, NULL, a.agreement_number, a.partner_agency, 'NEEDS_REVIEW', 'REVIEW', NULL, c.field, NULL,
         concat('Extracted ', c.field, ' = "', coalesce(c.value, ''), '" in ', c.file_name, ' has confidence ', round(c.confidence, 2), '; confirm against the PDF')
  FROM {S}.agreement_field_confidence c JOIN {S}.sharing_agreements a USING (file_name)
  WHERE c.confidence < 0.8 AND c.value IS NOT NULL)
SELECT sha2(concat_ws('|', finding_type, share_name, recipient_name, source_table, column_name, agreement_number), 256) AS finding_id,
       *, current_date() AS detected_on FROM f""")
spark.sql(f"""
CREATE OR REPLACE VIEW {S}.share_compliance_summary
COMMENT 'One row per Delta Share (or agreement without a share): compliance status and open findings by severity.'
AS
WITH keys AS (SELECT share_name FROM {S}.share_inventory UNION SELECT share_name FROM {S}.sharing_agreements WHERE document_type <> 'AMENDMENT')
SELECT k.share_name, max(a.agreement_number) AS agreement_number, max(a.partner_agency) AS partner_agency, max(a.partner_office) AS partner_office,
       max(a.expiration_date) AS expiration_date, concat_ws(', ', collect_set(g.recipient_name)) AS granted_to,
       count(DISTINCT f.finding_id) FILTER (WHERE f.severity = 'CRITICAL') AS critical, count(DISTINCT f.finding_id) FILTER (WHERE f.severity = 'HIGH') AS high,
       count(DISTINCT f.finding_id) FILTER (WHERE f.severity IN ('MEDIUM', 'LOW')) AS medium_low, count(DISTINCT f.finding_id) FILTER (WHERE f.severity = 'REVIEW') AS needs_review,
       concat_ws(', ', array_sort(collect_set(f.finding_type))) AS finding_types,
       CASE WHEN count(f.finding_id) FILTER (WHERE f.severity IN ('CRITICAL', 'HIGH')) > 0 THEN 'NON_COMPLIANT'
            WHEN count(f.finding_id) FILTER (WHERE f.severity IN ('MEDIUM', 'LOW', 'REVIEW')) > 0 THEN 'ATTENTION'
            WHEN count(f.finding_id) FILTER (WHERE f.finding_type = 'NOT_IMPLEMENTED') > 0 THEN 'NOT_IMPLEMENTED'
            ELSE 'COMPLIANT' END AS compliance_status
FROM keys k LEFT JOIN {S}.sharing_agreements a ON a.share_name = k.share_name AND a.document_type <> 'AMENDMENT'
LEFT JOIN {S}.share_grants g ON g.share_name = k.share_name LEFT JOIN {S}.share_compliance_findings f ON f.share_name = k.share_name
GROUP BY k.share_name""")
display(spark.sql(f"SELECT severity, finding_type, count(*) AS findings FROM {S}.share_compliance_findings GROUP BY ALL ORDER BY 1, 2"))
display(spark.sql(f"SELECT * FROM {S}.share_compliance_summary ORDER BY compliance_status, share_name"))

# COMMAND ----------

# MAGIC %md ## Did the checks catch every planted scenario?
# MAGIC Synthetic mode only: compares the findings with the mismatch each synthetic share was built to show. Skipped when `USE_SYNTHETIC_DATA = False`.

# COMMAND ----------

# DBTITLE 1,Reconcile findings with planted scenarios
if not USE_SYNTHETIC_DATA:   # no ground truth for real agreements and shares
    dbutils.notebook.exit("Findings written. Reconciliation skipped: USE_SYNTHETIC_DATA = False.")
EXPECT = {"OVER_SHARING": ["OVER_SHARING"], "UNDER_SHARING": ["UNDER_SHARING"], "EXPIRED_AGREEMENT": ["EXPIRED_AGREEMENT", "ACCESS_AFTER_EXPIRATION"],
          "RECIPIENT_MISMATCH": ["RECIPIENT_MISMATCH"], "NOT_IMPLEMENTED": ["NOT_IMPLEMENTED"], "NO_AGREEMENT": ["NO_AGREEMENT"],
          "COMPLIANT": [], "COMPLIANT_WITH_AMENDMENT": []}
found = {(r.share_name, r.finding_type) for r in spark.table(f"{S}.share_compliance_findings").collect() if r.severity != "REVIEW"}
rows = []
for r in spark.table(f"{S}._scenario_ground_truth").where("scenario <> 'AMENDMENT'").collect():
    got = sorted({t for s, t in found if s == r.share_name and t != "EXPIRING_SOON"})
    rows.append((r.share_name, r.scenario, ", ".join(EXPECT[r.scenario]) or "(none)", ", ".join(got) or "(none)", sorted(EXPECT[r.scenario]) == got))
res = spark.createDataFrame(rows, "share_name STRING, planted_scenario STRING, expected_findings STRING, detected_findings STRING, matches BOOLEAN")
display(res)
res.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{S}._compliance_reconciliation")
assert all(r[4] for r in rows), "a planted scenario was not detected as expected"