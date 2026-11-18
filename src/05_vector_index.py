# Databricks notebook source
# MAGIC %md
# MAGIC # 05 — Chunk the agreements with ai_prep_search and build the vector index
# MAGIC 1. **`ai_prep_search`** (Beta) takes the `ai_parse_document` output already in `parsed_agreements` and returns search-ready chunks.
# MAGIC    Each chunk has a `chunk_to_embed` (text enriched with document context, which is what gets embedded) and a `chunk_to_retrieve`
# MAGIC    (the raw text returned to the user). No hand-written chunking.
# MAGIC 2. `agreement_chunks` (Change Data Feed on) feeds a **Delta Sync vector index** with Databricks-managed embeddings.
# MAGIC 3. **`search_agreements(question)`**: a SQL table function Genie can call. It ranks the same chunks with the same embedding
# MAGIC    model, using cosine similarity in SQL, because `vector_search()` inside a function isn't reachable from Genie. The index serves agents and apps.

# COMMAND ----------

# MAGIC %run ./00_config

# COMMAND ----------

# DBTITLE 1,Chunk agreements with ai_prep_search
spark.sql(f"""
CREATE OR REPLACE TABLE {S}.agreement_chunks (
  chunk_id STRING NOT NULL COMMENT 'file_name + ai_prep_search chunk id.',
  file_name STRING COMMENT 'Agreement PDF file name.',
  agreement_number STRING COMMENT 'Agreement number (from ai_extract).',
  document_type STRING COMMENT 'ai_classify document type.',
  partner_agency STRING COMMENT 'Partner HHS operating division.',
  share_name STRING COMMENT 'Delta Share named in the agreement.',
  chunk_position INT COMMENT 'Position of the chunk in the document.',
  chunk_to_embed STRING COMMENT 'ai_prep_search text to embed (chunk enriched with document context).',
  chunk_to_retrieve STRING COMMENT 'ai_prep_search raw chunk text to show the user.',
  CONSTRAINT agreement_chunks_pk PRIMARY KEY (chunk_id))
COMMENT 'Search-ready chunks of every agreement, produced by ai_prep_search over the ai_parse_document output. Source of the vector index. SYNTHETIC.'
TBLPROPERTIES (delta.enableChangeDataFeed = true)""")
spark.sql(f"""
INSERT INTO {S}.agreement_chunks
WITH prep AS (SELECT p.file_name, ai_prep_search(p.parsed) AS r FROM {S}.parsed_agreements p)
SELECT concat(prep.file_name, '-', ch.value:chunk_id::string), prep.file_name, a.agreement_number, a.document_type, a.partner_agency, a.share_name,
       ch.value:chunk_position::int, ch.value:chunk_to_embed::string, ch.value:chunk_to_retrieve::string
FROM prep, LATERAL variant_explode(prep.r:document.contents) AS ch
JOIN {S}.sharing_agreements a USING (file_name)""")
display(spark.sql(f"SELECT file_name, count(*) AS chunks, round(avg(length(chunk_to_embed))) AS avg_chars FROM {S}.agreement_chunks GROUP BY 1 ORDER BY 1"))
_docs = spark.table(f"{S}.agreement_chunks").select("file_name").distinct().count()
assert _docs == (11 if USE_SYNTHETIC_DATA else spark.table(f"{S}.sharing_agreements").count()), f"only {_docs} agreements were chunked"

# COMMAND ----------

# MAGIC %md ## Delta Sync index

# COMMAND ----------

import time
from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import NotFound
w = WorkspaceClient()
spec = {"name": VS_INDEX, "endpoint_name": VS_ENDPOINT, "primary_key": "chunk_id", "index_type": "DELTA_SYNC",
        "delta_sync_index_spec": {"source_table": f"{S}.agreement_chunks", "pipeline_type": "TRIGGERED",
                                  "embedding_source_columns": [{"name": "chunk_to_embed", "embedding_model_endpoint_name": EMBEDDING_MODEL}],
                                  "columns_to_sync": ["chunk_id", "file_name", "agreement_number", "document_type", "partner_agency", "share_name",
                                                      "chunk_position", "chunk_to_retrieve"]}}
try:
    w.api_client.do("GET", f"/api/2.0/vector-search/indexes/{VS_INDEX}")
    w.api_client.do("POST", f"/api/2.0/vector-search/indexes/{VS_INDEX}/sync"); print("index exists; sync triggered")
except NotFound:
    w.api_client.do("POST", "/api/2.0/vector-search/indexes", body=spec); print("index created")
n = spark.table(f"{S}.agreement_chunks").count()
for _ in range(80):
    st = w.api_client.do("GET", f"/api/2.0/vector-search/indexes/{VS_INDEX}").get("status", {})
    if st.get("ready") and st.get("indexed_row_count", 0) >= n: break
    time.sleep(30)
print({k: st.get(k) for k in ("ready", "indexed_row_count", "message")})
assert st.get("ready") and st.get("indexed_row_count", 0) >= n, "index did not finish syncing"
display(spark.sql(f"""SELECT file_name, round(search_score, 3) AS score, left(chunk_to_retrieve, 160) AS preview
                      FROM vector_search(index => '{VS_INDEX}', query_text => 'notification required before changing the shared data elements', num_results => 3)"""))

# COMMAND ----------

# MAGIC %md ## Genie-safe search function (same embeddings, cosine similarity in SQL)

# COMMAND ----------

spark.sql(f"""CREATE OR REPLACE TABLE {S}.agreement_chunk_embeddings
COMMENT 'Agreement chunks with {EMBEDDING_MODEL} embeddings (ai_query) for SQL semantic search from Genie. SYNTHETIC.'
AS SELECT chunk_id, file_name, agreement_number, document_type, partner_agency, share_name, chunk_position, chunk_to_retrieve,
          ai_query('{EMBEDDING_MODEL}', chunk_to_embed) AS embedding FROM {S}.agreement_chunks""")
spark.sql(f"""CREATE OR REPLACE FUNCTION {S}.search_agreements(
  question STRING COMMENT 'Natural-language question about the terms of ACF data-sharing agreements (MOUs, ISAs, amendments)')
RETURNS TABLE (agreement_number STRING, file_name STRING, partner_agency STRING, share_name STRING, chunk_text STRING, score DOUBLE)
COMMENT 'Semantic search over the WORDING of ACF data-sharing agreements: security responsibilities, notification and incident duties, termination and notice periods, authority, purpose narrative. Not for questions about which columns are shared or permitted (use the compliance tables). Returns the 5 most relevant passages. SYNTHETIC documents.'
RETURN
  WITH q AS (SELECT ai_query('{EMBEDDING_MODEL}', question) AS v)
  SELECT c.agreement_number, c.file_name, c.partner_agency, c.share_name, c.chunk_to_retrieve AS chunk_text,
         aggregate(zip_with(c.embedding, q.v, (a, b) -> a * b), 0D, (acc, x) -> acc + x) /
         (sqrt(aggregate(transform(c.embedding, x -> x * x), 0D, (acc, x) -> acc + x)) * sqrt(aggregate(transform(q.v, x -> x * x), 0D, (acc, x) -> acc + x))) AS score
  FROM {S}.agreement_chunk_embeddings c CROSS JOIN q ORDER BY score DESC LIMIT 5""")
display(spark.sql(f"SELECT agreement_number, round(score, 3) AS score, left(chunk_text, 160) AS preview FROM {S}.search_agreements('What must ACF do before changing the shared data elements?')"))