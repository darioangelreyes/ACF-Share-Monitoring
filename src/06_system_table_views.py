# Databricks notebook source
# MAGIC %md
# MAGIC # 06 — Materialized views on system tables
# MAGIC | View | System tables | Question it answers |
# MAGIC |---|---|---|
# MAGIC | `mv_shared_columns` | `information_schema.columns`, `access.column_lineage`, `information_schema.column_tags` | Every column each recipient receives, traced to its source column and identifier level |
# MAGIC | `mv_source_refresh_activity` | `access.table_lineage`, `lakeflow.jobs`, `lakeflow.job_run_timeline` | How often each shared table is refreshed, by which job, and whether the job is scheduled |
# MAGIC | `mv_source_access_grants` | `information_schema.table/schema/catalog_privileges`, `column_tags` | Which internal users and groups can read the source tables and share objects |
# MAGIC | `mv_source_table_reads` | `access.table_lineage` | Who actually read those tables in the last 90 days, and through what |
# MAGIC | `mv_delta_sharing_activity` | `access.audit` (Delta Sharing events) | Which recipient queried which share, and when |
# MAGIC | `mv_agreement_permitted_columns` | extraction tables (notebook 04) | Columns each share is allowed to carry, with amendments applied |
# MAGIC
# MAGIC **Recipient activity:**
# MAGIC * With `USE_SYNTHETIC_DATA = True`, `share_access_events_synthetic` holds 60 days of synthetic recipient queries ending **today** (the day this notebook runs). Rerun the notebook to move the window forward.
# MAGIC * With `USE_SYNTHETIC_DATA = False`, that table is left empty, so only real audit events appear.
# MAGIC
# MAGIC The table has the same fields the audit log records for `deltaSharingQueryTable`, and it's unioned with the real audit events.
# MAGIC
# MAGIC The lineage, tag and privilege views look up source tables in `SOURCE_CATALOG.SOURCE_SCHEMA` (by default the project schema).

# COMMAND ----------

# MAGIC %run ./00_config

# COMMAND ----------

# DBTITLE 1,Synthetic recipient activity (demo mode only)
import random
from datetime import datetime, timedelta, date, timezone
# Synthetic recipient query events (shape of system.access.audit deltaSharingQueryTable): the 60 days up to today (UTC).
# Real mode (USE_SYNTHETIC_DATA = False): no events are generated; the table stays empty so only real audit events are used.
rng = random.Random(20261106); today = datetime.now(timezone.utc).date(); ev = []
grants = spark.sql(f"SELECT g.share_name, g.recipient_name, o.shared_as FROM {S}.share_grants g JOIN {S}.share_objects o USING (share_name)").collect() if USE_SYNTHETIC_DATA else []
RATE = {"acf_os_ocio_grants_adhoc": 6, "acf_cms_cmcs_tanf_medicaid": 3, "acf_nih_nichd_afcars": 2}
for g in grants:
    for back in range(60, -1, -1):
        d = today - timedelta(days=back)
        if d.weekday() >= 5 and rng.random() < 0.8: continue
        for _ in range(max(0, int(rng.gauss(RATE.get(g.share_name, 1.5), 1)))):
            t = datetime(d.year, d.month, d.day, rng.randint(11, 22), rng.randint(0, 59), rng.randint(0, 59))
            ev.append((t, d, "deltaSharingQueryTable", g.share_name, g.recipient_name, g.shared_as.split(".")[0], g.shared_as.split(".")[1], 200,
                       f"10.{rng.randint(10, 99)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}", "Delta-Sharing-Spark/1.4.1 Databricks-Runtime/18.x", "SYNTHETIC"))
spark.createDataFrame(ev, "event_time TIMESTAMP, event_date DATE, action_name STRING, share_name STRING, recipient_name STRING, schema_name STRING, "
                          "table_name STRING, status_code INT, source_ip_address STRING, user_agent STRING, event_source STRING") \
     .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{S}.share_access_events_synthetic")
spark.sql(f"COMMENT ON TABLE {S}.share_access_events_synthetic IS 'SYNTHETIC recipient query events for the demo shares, in the shape of system.access.audit deltaSharingQueryTable records. Replaced by real audit events once the shares are real.'")
print(len(ev), "synthetic recipient query events", f"({today - timedelta(days=60)} to {today})" if ev else "(real mode: none generated)")

# COMMAND ----------

def mv(name, comment, sql):
    spark.sql(f"CREATE OR REPLACE MATERIALIZED VIEW {S}.{name} COMMENT '{comment}' AS {sql}")
    print(f"{name:32s} {spark.table(f'{S}.{name}').count():>6,} rows")

mv("mv_agreement_permitted_columns", "Columns each Delta Share may carry under its signed agreement, with amendments applied (from the ai_extract tables).", f"""
SELECT base.share_name, base.recipient_name, base.agreement_number AS base_agreement_number, e.agreement_number AS granted_by,
       e.document_type AS granted_by_type, e.source_table, e.column_name, e.sensitivity, e.confidence AS extraction_confidence
FROM {S}.sharing_agreements base
JOIN {S}.sharing_agreements doc ON doc.share_name = base.share_name AND (doc.file_name = base.file_name OR doc.amends_agreement_number = base.agreement_number OR doc.amends_agreement_number = base.file_name)
JOIN {S}.agreement_data_elements e ON e.file_name = doc.file_name
WHERE base.document_type <> 'AMENDMENT'""")

mv("mv_shared_columns", "Every column each recipient receives through a Delta Share, traced to its source column (column lineage) and identifier level (column tags).", f"""
WITH obj AS (SELECT o.*, split(o.object_name, '[.]') AS p, split(o.source_table, '[.]') AS s FROM {S}.share_objects o),
lin AS (SELECT DISTINCT target_table_name, target_column_name, source_table_name, source_column_name FROM system.access.column_lineage
        WHERE target_table_catalog = '{SOURCE_CATALOG}' AND target_table_schema = '{SOURCE_SCHEMA}' AND source_table_catalog = '{SOURCE_CATALOG}' AND source_table_schema = '{SOURCE_SCHEMA}'),
tags AS (SELECT table_name, column_name, tag_value FROM system.information_schema.column_tags
         WHERE catalog_name = '{SOURCE_CATALOG}' AND schema_name = '{SOURCE_SCHEMA}' AND tag_name = 'acf_identifier')
SELECT obj.share_name, g.recipient_name, obj.object_name, obj.data_object_type, obj.s[2] AS source_table, c.column_name AS shared_column,
       coalesce(lin.source_column_name, c.column_name) AS source_column, c.data_type, coalesce(t.tag_value, 'none') AS identifier_level,
       lin.source_column_name IS NOT NULL AS traced_by_lineage
FROM obj JOIN {S}.share_grants g USING (share_name)
JOIN system.information_schema.columns c ON c.table_catalog = obj.p[0] AND c.table_schema = obj.p[1] AND c.table_name = obj.p[2]
LEFT JOIN lin ON lin.target_table_name = obj.p[2] AND lin.target_column_name = c.column_name AND lin.source_table_name = obj.s[2]
LEFT JOIN tags t ON t.table_name = obj.s[2] AND t.column_name = coalesce(lin.source_column_name, c.column_name)""")

mv("mv_source_refresh_activity", "How often each shared source table is written (table lineage), by which job, and whether that job has a schedule (Lakeflow jobs).", f"""
WITH src AS (SELECT DISTINCT split(source_table, '[.]')[2] AS table_name FROM {S}.share_objects),
w AS (SELECT target_table_name AS table_name, entity_type, entity_id, created_by, event_time FROM system.access.table_lineage
      WHERE target_table_catalog = '{SOURCE_CATALOG}' AND target_table_schema = '{SOURCE_SCHEMA}' AND event_date >= current_date() - 90),
j AS (SELECT job_id, max_by(name, change_time) AS job_name, max_by(trigger_type, change_time) AS trigger_type,
             max_by(to_json(trigger), change_time) AS trigger_json FROM system.lakeflow.jobs GROUP BY job_id),
r AS (SELECT job_id, count(*) AS runs_90d, count_if(result_state = 'SUCCEEDED') AS successful_runs_90d, max(period_end_time) AS last_run_end
      FROM system.lakeflow.job_run_timeline WHERE period_start_time >= current_date() - 90 GROUP BY job_id)
SELECT src.table_name, count(w.event_time) AS writes_90d, count(DISTINCT to_date(w.event_time)) AS days_written_90d, max(w.event_time) AS last_write,
       min(w.event_time) AS first_write_90d, datediff(current_date(), to_date(max(w.event_time))) AS days_since_last_write,
       round((unix_timestamp(max(w.event_time)) - unix_timestamp(min(w.event_time))) / 3600 / greatest(count(DISTINCT to_date(w.event_time)) - 1, 1), 1) AS avg_hours_between_write_days,
       max_by(w.entity_type, w.event_time) AS last_writer_type, max_by(w.entity_id, w.event_time) AS last_writer_id, max_by(w.created_by, w.event_time) AS last_written_by,
       max_by(j.job_name, w.event_time) AS last_writer_job_name,
       coalesce(max_by(j.trigger_type, w.event_time), CASE WHEN max_by(w.entity_type, w.event_time) = 'JOB' THEN 'ONE_TIME_RUN' END) AS job_trigger_type,
       max_by(j.trigger_json, w.event_time) AS job_trigger, max_by(r.runs_90d, w.event_time) AS job_runs_90d, max_by(r.successful_runs_90d, w.event_time) AS job_successful_runs_90d
FROM src LEFT JOIN w USING (table_name) LEFT JOIN j ON w.entity_type = 'JOB' AND j.job_id = w.entity_id LEFT JOIN r ON w.entity_type = 'JOB' AND r.job_id = w.entity_id
GROUP BY src.table_name""")

mv("mv_source_access_grants", "Internal principals who can read the source tables and share objects, through table, schema or catalog privileges, with the identifiers each object holds.", f"""
WITH objs AS (SELECT DISTINCT split(source_table, '[.]')[2] AS table_name, 'SOURCE_TABLE' AS object_role FROM {S}.share_objects
              UNION SELECT DISTINCT split(object_name, '[.]')[2], 'SHARE_OBJECT' FROM {S}.share_objects WHERE data_object_type = 'VIEW'),
ids AS (SELECT table_name, count_if(tag_value = 'direct') AS direct_identifier_columns FROM system.information_schema.column_tags
        WHERE catalog_name = '{SOURCE_CATALOG}' AND schema_name = '{SOURCE_SCHEMA}' AND tag_name = 'acf_identifier' GROUP BY 1),
p AS (SELECT table_name, grantee, privilege_type, 'TABLE' AS granted_on FROM system.information_schema.table_privileges WHERE table_catalog = '{SOURCE_CATALOG}' AND table_schema = '{SOURCE_SCHEMA}'
      UNION ALL SELECT o.table_name, sp.grantee, sp.privilege_type, 'SCHEMA' FROM objs o CROSS JOIN system.information_schema.schema_privileges sp WHERE sp.catalog_name = '{SOURCE_CATALOG}' AND sp.schema_name = '{SOURCE_SCHEMA}'
      UNION ALL SELECT o.table_name, cp.grantee, cp.privilege_type, 'CATALOG' FROM objs o CROSS JOIN system.information_schema.catalog_privileges cp WHERE cp.catalog_name = '{SOURCE_CATALOG}')
SELECT o.table_name, o.object_role, coalesce(ids.direct_identifier_columns, 0) AS direct_identifier_columns, p.grantee,
       CASE WHEN p.grantee RLIKE '^[0-9a-f-]{{36}}$' THEN 'service principal' WHEN p.grantee LIKE '%@%' THEN 'user' ELSE 'group' END AS grantee_type,
       array_sort(collect_set(p.privilege_type)) AS privileges, array_sort(collect_set(p.granted_on)) AS granted_on,
       array_contains(collect_set(p.privilege_type), 'SELECT') OR array_contains(collect_set(p.privilege_type), 'ALL_PRIVILEGES') AS can_read
FROM objs o JOIN p USING (table_name) LEFT JOIN ids USING (table_name)
WHERE p.privilege_type IN ('SELECT', 'ALL_PRIVILEGES', 'MODIFY', 'MANAGE')
GROUP BY ALL""")

mv("mv_source_table_reads", "Who read the source tables and share objects in the last 90 days (table lineage), and through which entity (notebook, job, dashboard, query).", f"""
WITH objs AS (SELECT DISTINCT split(source_table, '[.]')[2] AS table_name FROM {S}.share_objects UNION SELECT DISTINCT split(object_name, '[.]')[2] FROM {S}.share_objects)
SELECT l.source_table_name AS table_name, l.created_by AS read_by, coalesce(l.entity_type, 'INTERACTIVE') AS entity_type, l.entity_id,
       count(*) AS read_events_90d, min(l.event_time) AS first_read, max(l.event_time) AS last_read
FROM system.access.table_lineage l JOIN objs ON objs.table_name = l.source_table_name
WHERE l.source_table_catalog = '{SOURCE_CATALOG}' AND l.source_table_schema = '{SOURCE_SCHEMA}' AND l.event_date >= current_date() - 90
GROUP BY ALL""")

mv("mv_delta_sharing_activity", "Recipient queries against ACF shares: real Delta Sharing audit events (system.access.audit) plus synthetic events while the demo shares are synthetic.", f"""
SELECT event_time, event_date, action_name, coalesce(request_params['share'], request_params['share_name']) AS share_name,
       request_params['recipient_name'] AS recipient_name, request_params['schema'] AS schema_name, request_params['name'] AS table_name,
       response.status_code AS status_code, source_ip_address, user_agent, 'AUDIT' AS event_source
FROM system.access.audit
WHERE service_name = 'unityCatalog' AND action_name IN ('deltaSharingQueryTable', 'deltaSharingQueriedTable') AND event_date >= current_date() - 90
  AND coalesce(request_params['share'], request_params['share_name']) IN (SELECT share_name FROM {S}.share_inventory)
UNION ALL
SELECT event_time, event_date, action_name, share_name, recipient_name, schema_name, table_name, status_code, source_ip_address, user_agent, event_source
FROM {S}.share_access_events_synthetic""")