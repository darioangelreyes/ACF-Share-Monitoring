# Databricks notebook source
# MAGIC %md
# MAGIC # 04 — Parse, classify and extract the agreements
# MAGIC 1. **`ai_parse_document`** (v2.0) reads every PDF in the agreements volume, including the scanned handwritten ones (OCR) → `parsed_agreements`.
# MAGIC 2. **`ai_classify`** (v2.0) types each document by content: MOU, Interconnection Security Agreement, or amendment.
# MAGIC 3. **`ai_extract`** (v2.1, **precision mode**, **confidence scores**, **citations**) pulls the agreement terms and two nested lists:
# MAGIC    the signatories and **Appendix C, Shared Data Elements** (the tables and columns the partner may receive).
# MAGIC
# MAGIC Output tables:
# MAGIC - `sharing_agreements`: one row per document.
# MAGIC - `agreement_data_elements`: one row per permitted column.
# MAGIC - `agreement_signatories`
# MAGIC - `agreement_field_confidence`: every extracted value with its confidence, the input to human review.
# MAGIC
# MAGIC The last cell scores the extraction against the generator's ground truth.

# COMMAND ----------

# MAGIC %run ./00_config

# COMMAND ----------

# MAGIC %run ./_agreements_spec

# COMMAND ----------

import json
spark.sql(f"""
CREATE OR REPLACE TABLE {S}.parsed_agreements
COMMENT 'Synthetic data-sharing agreements (PDF) parsed with ai_parse_document v2.0; scanned handwritten documents are OCRed. SYNTHETIC.'
AS
WITH f AS (SELECT path, content FROM read_files('{AGREEMENTS_PATH}/', format => 'binaryFile', pathGlobFilter => '*.pdf')),
p AS (SELECT path, ai_parse_document(content, map('version', '2.0')) AS parsed FROM f),
e AS (SELECT path, parsed, try_cast(parsed:document:elements AS ARRAY<VARIANT>) AS elements, try_cast(parsed:document:pages AS ARRAY<VARIANT>) AS pages FROM p)
SELECT regexp_extract(path, '([^/]+)\\\\.pdf$', 1) AS file_name, path AS source_path, size(pages) AS page_count,
       array_join(transform(elements, x -> x:content::string), '\\n') AS full_text, elements, parsed, current_timestamp() AS parsed_at
FROM e""")
display(spark.sql(f"SELECT file_name, page_count, length(full_text) AS chars FROM {S}.parsed_agreements ORDER BY 1"))
_parsed = spark.sql(f"SELECT count(*) FROM {S}.parsed_agreements WHERE length(full_text) > 500").first()[0]
if USE_SYNTHETIC_DATA:
    assert _parsed == 11, f"expected the 11 synthetic agreements, parsed {_parsed} (run 01_generate_agreements first)"
else:
    assert _parsed > 0, f"no agreement PDFs with text found in {AGREEMENTS_PATH}; upload your agreements there (see README.md)"

# COMMAND ----------

# MAGIC %md ## ai_classify + ai_extract

# COMMAND ----------

S_ = lambda d: {"type": "string", "description": d}
SCHEMA = {
 "agreement_number": S_("agreement number, e.g. ACF-NIH-2025-014 or ACF-NIH-2025-031-A1"),
 "acf_system_name": S_("name of the ACF system (System A)"),
 "partner_agency": S_("HHS operating division of the partner: NIH, CDC, FDA, CMS or OS"),
 "partner_office": S_("partner institute, center or office, e.g. NICHD, NCIPC, ASPE"),
 "partner_system_name": S_("name of the partner system (System B)"),
 "purpose": S_("purpose of the data exchange, one sentence"),
 "delta_share_name": S_("Delta Share name, lower case with underscores"),
 "recipient_name": S_("Delta Sharing recipient name, lower case with underscores"),
 "effective_date": S_("effective date, YYYY-MM-DD"),
 "expiration_date": S_("expiration date, YYYY-MM-DD"),
 "amends_agreement_number": S_("for an amendment: number of the agreement being amended; otherwise empty"),
 "signatories": {"type": "array", "description": "every person who signed the agreement", "items": {"type": "object", "properties": {
     "name": S_("signer name"), "title": S_("signer title"), "organization": S_("ACF or the partner agency"), "signature_date": S_("YYYY-MM-DD")}}},
 "shared_data_elements": {"type": "array", "description": "every row of the Shared Data Elements table (Appendix C, or the table in an amendment)",
     "items": {"type": "object", "properties": {"source_table": S_("source table name exactly as written, lower case with underscores"),
                                                 "column_name": S_("column name exactly as written, lower case with underscores"),
                                                 "sensitivity": S_("sensitivity as written")}}},
}
LABELS = {"MEMORANDUM_OF_UNDERSTANDING": "memorandum of understanding (MOU) for an interconnection within the same secure network",
          "INTERCONNECTION_SECURITY_AGREEMENT": "interconnection security agreement (ISA) for an interconnection between separate secure networks",
          "AMENDMENT": "an amendment that modifies an existing agreement",
          "OTHER": "anything else"}
q = lambda o: json.dumps(o).replace("'", "''")
OPTS = ("map('version', '2.1', 'mode', 'precision', 'enableConfidenceScores', 'true', 'enableCitations', 'true', 'instructions', "
        "'Extract the terms of an HHS data-sharing agreement. Table and column names must be copied exactly as written, in lower case with underscores.')")
spark.sql(f"""
CREATE OR REPLACE TABLE {S}.agreements_ai
COMMENT 'Raw ai_classify v2.0 and ai_extract v2.1 output per agreement (values, confidence scores, citations).'
AS SELECT file_name, source_path,
       ai_classify(full_text, '{q(LABELS)}', map('version', '2.0', 'instructions', 'Classify an HHS data-sharing agreement by document type.')):response[0]::string AS document_type,
       parse_json(CAST(ai_extract(full_text, '{q(SCHEMA)}', {OPTS}) AS STRING)) AS extraction, current_timestamp() AS extracted_at
FROM {S}.parsed_agreements""")
display(spark.sql(f"SELECT file_name, document_type FROM {S}.agreements_ai ORDER BY 1"))

# COMMAND ----------

# MAGIC %md ## Typed tables

# COMMAND ----------

v = lambda k: f"nullif(trim(extraction:response:{k}:value::string), '')"
c = lambda k: f"extraction:response:{k}:confidence_score::double"
HEADER = [k for k, x in SCHEMA.items() if x["type"] != "array"]
spark.sql(f"""
CREATE OR REPLACE TABLE {S}.sharing_agreements (
  file_name STRING NOT NULL COMMENT 'PDF file name without extension.',
  agreement_number STRING COMMENT 'ai_extract: agreement number.',
  document_type STRING COMMENT 'ai_classify: MEMORANDUM_OF_UNDERSTANDING, INTERCONNECTION_SECURITY_AGREEMENT or AMENDMENT.',
  partner_agency STRING COMMENT 'ai_extract: HHS operating division of the partner (NIH, CDC, FDA, CMS, OS).',
  partner_office STRING COMMENT 'ai_extract: partner institute, center or office.',
  partner_system_name STRING COMMENT 'ai_extract: partner system (System B).',
  acf_system_name STRING COMMENT 'ai_extract: ACF system (System A).',
  purpose STRING COMMENT 'ai_extract: purpose of the data exchange.',
  share_name STRING COMMENT 'ai_extract: Delta Share named in the agreement.',
  recipient_name STRING COMMENT 'ai_extract: Delta Sharing recipient named in the agreement.',
  effective_date DATE COMMENT 'ai_extract: effective date.',
  expiration_date DATE COMMENT 'ai_extract: expiration date.',
  amends_agreement_number STRING COMMENT 'ai_extract: for amendments, the agreement being amended.',
  signatory_count INT COMMENT 'Number of signatories extracted.',
  fully_signed BOOLEAN COMMENT 'True when signatures for both ACF and the partner were extracted.',
  data_element_count INT COMMENT 'Rows extracted from the Shared Data Elements table.',
  min_confidence DOUBLE COMMENT 'Lowest ai_extract confidence across the header fields (0-1).',
  source_path STRING COMMENT 'Volume path of the PDF.',
  extraction VARIANT COMMENT 'Raw ai_extract v2.1 output (value, confidence_score, citation ids per field).',
  extracted_at TIMESTAMP COMMENT 'When extraction ran (UTC).',
  CONSTRAINT sharing_agreements_pk PRIMARY KEY (file_name))
COMMENT 'One row per data-sharing agreement or amendment, extracted from the PDFs with ai_classify and ai_extract. SYNTHETIC.'""")
spark.sql(f"""
INSERT INTO {S}.sharing_agreements
SELECT file_name, upper({v('agreement_number')}), document_type, upper({v('partner_agency')}), {v('partner_office')}, {v('partner_system_name')},
       {v('acf_system_name')}, {v('purpose')}, lower(regexp_replace({v('delta_share_name')}, '\\\\s', '')), lower(regexp_replace({v('recipient_name')}, '\\\\s', '')),
       try_to_date({v('effective_date')}), try_to_date({v('expiration_date')}), upper({v('amends_agreement_number')}),
       size(try_cast(extraction:response:signatories AS ARRAY<VARIANT>)),
       size(try_cast(extraction:response:signatories AS ARRAY<VARIANT>)) >= 2,
       size(try_cast(extraction:response:shared_data_elements AS ARRAY<VARIANT>)),
       least({', '.join(c(k) for k in HEADER if k != 'amends_agreement_number')}),
       source_path, extraction, extracted_at
FROM {S}.agreements_ai""")
norm = lambda x: f"regexp_replace(lower(trim({x})), '[^a-z0-9]+', '_')"
spark.sql(f"""
CREATE OR REPLACE TABLE {S}.agreement_data_elements
COMMENT 'Permitted data elements (table + column) from each agreement Shared Data Elements table, with ai_extract confidence. Names normalized to snake_case. SYNTHETIC.'
AS SELECT a.file_name, a.agreement_number, a.document_type, pos + 1 AS element_seq,
          {norm("e:source_table:value::string")} AS source_table, {norm("e:column_name:value::string")} AS column_name,
          e:sensitivity:value::string AS sensitivity,
          least(e:source_table:confidence_score::double, e:column_name:confidence_score::double) AS confidence,
          e:column_name:value::string AS column_name_as_extracted
   FROM {S}.sharing_agreements a LATERAL VIEW posexplode(try_cast(a.extraction:response:shared_data_elements AS ARRAY<VARIANT>)) x AS pos, e""")
spark.sql(f"""
CREATE OR REPLACE TABLE {S}.agreement_signatories
COMMENT 'Signatories extracted from each agreement. SYNTHETIC.'
AS SELECT a.file_name, a.agreement_number, pos + 1 AS seq, s:name:value::string AS name, s:title:value::string AS title,
          s:organization:value::string AS organization, try_to_date(s:signature_date:value::string) AS signature_date,
          least(s:name:confidence_score::double, s:signature_date:confidence_score::double) AS confidence
   FROM {S}.sharing_agreements a LATERAL VIEW posexplode(try_cast(a.extraction:response:signatories AS ARRAY<VARIANT>)) x AS pos, s""")
stack = ", ".join(f"'{k}', {v(k)}, {c(k)}" for k in HEADER)
spark.sql(f"""
CREATE OR REPLACE TABLE {S}.agreement_field_confidence
COMMENT 'Every extracted header field with its ai_extract confidence score (0-1), for human review of low-confidence values. SYNTHETIC.'
AS SELECT file_name, field, value, confidence FROM {S}.agreements_ai LATERAL VIEW stack({len(HEADER)}, {stack}) s AS field, value, confidence""")
display(spark.sql(f"""SELECT file_name, agreement_number, document_type, partner_agency, share_name, recipient_name, effective_date, expiration_date,
                             amends_agreement_number, signatory_count, data_element_count, round(min_confidence, 2) AS min_conf FROM {S}.sharing_agreements ORDER BY 1"""))

# COMMAND ----------

# MAGIC %md ## Score the extraction against the generator's ground truth
# MAGIC Synthetic mode only. In real mode this step is skipped; use `agreement_field_confidence` to review low-confidence fields.

# COMMAND ----------

if not USE_SYNTHETIC_DATA:   # scoring needs the generator's ground truth, which only exists for synthetic agreements
    dbutils.notebook.exit("Extraction done. Scoring skipped: USE_SYNTHETIC_DATA = False (review agreement_field_confidence instead).")
truth = []
for a in AGREEMENTS:
    for t, cs in a["tables"].items():
        for col in cs: truth.append((a["doc_id"], t, col))
spark.createDataFrame(truth, "doc_id STRING, source_table STRING, column_name STRING").write.mode("overwrite").saveAsTable(f"{S}._agreement_elements_truth")
spark.sql(f"COMMENT ON TABLE {S}._agreement_elements_truth IS 'GENERATOR ARTIFACT: data elements printed in each agreement (for scoring extraction only).'")
TYPE = {"MOU": "MEMORANDUM_OF_UNDERSTANDING", "ISA": "INTERCONNECTION_SECURITY_AGREEMENT", "AMENDMENT": "AMENDMENT"}
hdr = [(a["doc_id"], TYPE[a["kind"]], a["share"], a["recipient"], a["effective"], a["expires"], a["style"]) for a in AGREEMENTS]
spark.createDataFrame(hdr, "doc_id STRING, kind STRING, share STRING, recipient STRING, effective STRING, expires STRING, style STRING").createOrReplaceTempView("hdr_truth")
score = spark.sql(f"""
WITH e AS (SELECT file_name, source_table, column_name FROM {S}.agreement_data_elements),
t AS (SELECT doc_id AS file_name, source_table, column_name FROM {S}._agreement_elements_truth),
el AS (SELECT coalesce(e.file_name, t.file_name) AS file_name, count_if(e.column_name IS NOT NULL AND t.column_name IS NOT NULL) AS matched,
              count_if(t.column_name IS NULL) AS extra, count_if(e.column_name IS NULL) AS missed
       FROM e FULL OUTER JOIN t ON e.file_name = t.file_name AND e.source_table = t.source_table AND e.column_name = t.column_name GROUP BY 1)
SELECT h.style, a.file_name, a.document_type = h.kind AS type_ok, a.share_name = h.share AS share_ok, a.recipient_name = h.recipient AS recipient_ok,
       a.effective_date = to_date(h.effective) AS effective_ok, a.expiration_date = to_date(h.expires) AS expires_ok,
       el.matched, el.extra, el.missed, round(a.min_confidence, 2) AS min_conf
FROM {S}.sharing_agreements a JOIN hdr_truth h ON h.doc_id = a.file_name LEFT JOIN el USING (file_name) ORDER BY h.style, a.file_name""")
display(score)
score.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{S}._extraction_scorecard")