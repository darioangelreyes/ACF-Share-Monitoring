"""Reads over the acf_deltashare_demo schema (compliance MVs, agreements, share inventory).

All SQL goes through ``lib.db`` (Statement Execution API, on behalf of the signed-in
user). The only exception is the agreement PDF download, which uses the app service
principal (it needs READ VOLUME on the agreements volume, granted as an app resource).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st
from databricks.sdk import WorkspaceClient

import config
from lib import db

# The ACF source tables published through Delta Sharing (see _agreements_spec).
SOURCE_TABLES = (
    "foster_care_afcars", "child_maltreatment_reports", "head_start_enrollment", "head_start_centers",
    "tanf_recipients", "tanf_caseload_monthly", "ccdf_children_served", "child_support_collections", "grant_awards",
)
PARTNERS = {
    "NIH": "National Institutes of Health (NIH)",
    "CDC": "Centers for Disease Control and Prevention (CDC)",
    "FDA": "U.S. Food and Drug Administration (FDA)",
    "CMS": "Centers for Medicare & Medicaid Services (CMS)",
    "OS": "HHS Office of the Secretary (OS)",
}
SEVERITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "REVIEW", "INFO"]


def summary() -> pd.DataFrame:
    return db.query_df(f"SELECT * FROM {config.fq('share_compliance_summary')} ORDER BY share_name")


def findings() -> pd.DataFrame:
    df = db.query_df(
        f"""SELECT finding_id, severity, finding_type, share_name, recipient_name, agreement_number, partner_agency,
                   source_table, column_name, identifier_level, detail, detected_on
            FROM {config.fq('share_compliance_findings')}"""
    )
    if not df.empty:
        df["_sev"] = df["severity"].map({s: i for i, s in enumerate(SEVERITY_ORDER)}).fillna(99)
        df = df.sort_values(["_sev", "share_name", "finding_type", "column_name"]).drop(columns="_sev").reset_index(drop=True)
    return df


def agreements() -> pd.DataFrame:
    return db.query_df(
        f"""SELECT file_name, agreement_number, document_type, partner_agency, partner_office, partner_system_name,
                   acf_system_name, purpose, share_name, recipient_name, effective_date, expiration_date,
                   amends_agreement_number, signatory_count, fully_signed, data_element_count,
                   round(min_confidence, 2) AS min_confidence, source_path
            FROM {config.fq('sharing_agreements')} ORDER BY agreement_number"""
    )


def agreement_for_share(share_name: str) -> dict:
    ag = agreements()
    hit = ag[(ag["share_name"] == share_name) & (ag["document_type"] != "AMENDMENT")]
    return hit.iloc[0].to_dict() if not hit.empty else {}


def amendments_for(agreement_number: str) -> pd.DataFrame:
    ag = agreements()
    return ag[ag["amends_agreement_number"] == agreement_number]


def column_comparison(share_name: str) -> pd.DataFrame:
    """Permitted (agreements incl. amendments) vs actually shared columns for one share."""
    return db.query_df(
        f"""WITH p AS (SELECT DISTINCT source_table, column_name, granted_by, granted_by_type, sensitivity
                       FROM {config.fq('mv_agreement_permitted_columns')} WHERE share_name = :s),
                 s AS (SELECT DISTINCT source_table, source_column AS column_name, identifier_level, object_name, data_object_type
                       FROM {config.fq('mv_shared_columns')} WHERE share_name = :s)
            SELECT coalesce(s.source_table, p.source_table) AS source_table, coalesce(s.column_name, p.column_name) AS column_name,
                   CASE WHEN s.column_name IS NOT NULL AND p.column_name IS NOT NULL THEN 'OK: shared and permitted'
                        WHEN s.column_name IS NOT NULL THEN 'OVER-SHARED: not in agreement'
                        ELSE 'UNDER-SHARED: permitted, not shared' END AS status,
                   s.identifier_level, p.sensitivity AS agreement_sensitivity, p.granted_by, p.granted_by_type,
                   s.object_name AS shared_object, s.data_object_type
            FROM s FULL OUTER JOIN p ON s.source_table = p.source_table AND s.column_name = p.column_name
            ORDER BY status DESC, source_table, column_name""",
        {"s": share_name},
    )


def share_objects(share_name: str) -> pd.DataFrame:
    return db.query_df(
        f"""SELECT o.share_name, o.object_name, o.data_object_type, o.source_table, g.recipient_name
            FROM {config.fq('share_objects')} o LEFT JOIN {config.fq('share_grants')} g USING (share_name)
            WHERE o.share_name = :s""",
        {"s": share_name},
    )


def data_elements(file_name: str) -> pd.DataFrame:
    return db.query_df(
        f"""SELECT element_seq AS seq, source_table, column_name, column_name_as_extracted, sensitivity,
                   round(confidence, 2) AS confidence
            FROM {config.fq('agreement_data_elements')} WHERE file_name = :f ORDER BY element_seq""",
        {"f": file_name},
    )


def signatories(file_name: str) -> pd.DataFrame:
    return db.query_df(
        f"""SELECT name, title, organization, signature_date, round(confidence, 2) AS confidence
            FROM {config.fq('agreement_signatories')} WHERE file_name = :f ORDER BY seq""",
        {"f": file_name},
    )


def recipients() -> pd.DataFrame:
    return db.query_df(f"SELECT recipient_name, agency, office FROM {config.fq('share_recipients')} ORDER BY agency, recipient_name")


@st.cache_data(ttl=600, show_spinner=False)
def source_columns() -> pd.DataFrame:
    """Columns of the ACF source tables with their acf_identifier tag (direct / indirect / none)."""
    names = ", ".join(f"'{t}'" for t in SOURCE_TABLES)
    return db.query_df(
        f"""SELECT c.table_name, c.column_name, c.data_type, coalesce(t.tag_value, 'none') AS identifier_level, c.ordinal_position
            FROM {config.CATALOG}.information_schema.columns c
            LEFT JOIN {config.CATALOG}.information_schema.column_tags t
              ON t.schema_name = c.table_schema AND t.table_name = c.table_name AND t.column_name = c.column_name
             AND t.tag_name = 'acf_identifier'
            WHERE c.table_schema = '{config.SCHEMA}' AND c.table_name IN ({names})
            ORDER BY c.table_name, c.ordinal_position"""
    )


def next_agreement_number(agency: str, year: int) -> str:
    ag = agreements()
    prefix = f"ACF-{agency}-{year}-"
    nums = [int(n[len(prefix):len(prefix) + 3]) for n in ag["agreement_number"].dropna()
            if n.startswith(prefix) and n[len(prefix):len(prefix) + 3].isdigit()]
    return f"{prefix}{(max(nums) + 1) if nums else 1:03d}"


@st.cache_data(ttl=3600, show_spinner="Loading the agreement PDF…")
def pdf_bytes(source_path: str) -> bytes:
    """Download an agreement PDF from the UC volume (app service principal / local profile)."""
    path = source_path.removeprefix("dbfs:")
    resp = WorkspaceClient().files.download(path)
    return resp.contents.read()


@st.cache_data(ttl=3600, show_spinner=False)
def pdf_pages(source_path: str, scale: float = 1.4) -> list:
    """Render each PDF page to a PIL image (works for typed and scanned/handwritten PDFs)."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(pdf_bytes(source_path))
    return [pdf[i].render(scale=scale).to_pil() for i in range(len(pdf))]
