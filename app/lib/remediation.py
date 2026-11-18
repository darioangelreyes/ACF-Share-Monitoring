"""Deterministic remediation plans for compliance findings: recommended action, SQL, document options.

The SQL is generated for a share owner to review and run; the app never executes it (and the
demo metastore has no CREATE SHARE / CREATE RECIPIENT anyway). Delta Sharing has no column-level
filter on a shared table, so column fixes are made through a view that selects only the permitted
columns (views can be shared Databricks-to-Databricks).
"""

from __future__ import annotations

import pandas as pd

import config

ACTIONS = {
    "OVER_SHARING": "Remove the non-permitted columns from the share now, then either confirm the partner has deleted them "
                    "or, if the partner legitimately needs them, execute a signed amendment before re-adding them.",
    "UNDER_SHARING": "Confirm with the partner that the permitted column is still needed, then add it to the shared view. "
                     "No paperwork is needed: the agreement already permits it.",
    "EXPIRED_AGREEMENT": "Revoke the recipient's access until a renewal is signed. Notify the partner.",
    "ACCESS_AFTER_EXPIRATION": "Revoke access immediately and report the post-expiration queries to the Privacy Office.",
    "EXPIRING_SOON": "Start renewal now (or plan revocation) so access does not lapse or continue without an agreement.",
    "RECIPIENT_MISMATCH": "Move the grant to the recipient the agreement names, or amend the agreement to add the other office.",
    "NO_AGREEMENT": "Revoke the share grant until an MOU or ISA is executed. Investigate who created the share.",
    "NOT_IMPLEMENTED": "Create the share exactly as the agreement's Appendix C specifies, or record why it is not needed.",
    "UNSIGNED_AGREEMENT": "Obtain the missing signature before any data is shared under this agreement.",
    "NEEDS_REVIEW": "Open the PDF and confirm the low-confidence extracted value; correct the agreement record if needed.",
}

DOC_OPTIONS = {
    "OVER_SHARING": ["NOTICE", "MEMO", "AMENDMENT"],
    "UNDER_SHARING": ["NOTICE"],
    "EXPIRED_AGREEMENT": ["NOTICE", "RENEWAL", "MEMO"],
    "ACCESS_AFTER_EXPIRATION": ["MEMO", "NOTICE"],
    "EXPIRING_SOON": ["RENEWAL", "NOTICE"],
    "RECIPIENT_MISMATCH": ["AMENDMENT", "NOTICE", "MEMO"],
    "NO_AGREEMENT": ["MEMO", "NOTICE"],
    "NOT_IMPLEMENTED": ["MEMO"],
    "UNSIGNED_AGREEMENT": ["NOTICE", "MEMO"],
    "NEEDS_REVIEW": ["MEMO"],
}


def _view_name(share: str, table: str) -> str:
    return config.fq(f"shr_{share}__{table}")


def _view_sql(share: str, table: str, columns: list[str]) -> str:
    return (f"CREATE OR REPLACE VIEW {_view_name(share, table)}\n"
            f"  COMMENT 'Object shared in Delta Share {share}: columns permitted by the agreement only.'\n"
            f"AS SELECT {', '.join(columns)}\nFROM {config.fq(table)};")


def plan_sql(finding: dict, comparison: pd.DataFrame, objects: pd.DataFrame, agreement: dict,
             agreement_elements: pd.DataFrame | None = None, column_order: pd.DataFrame | None = None) -> str:
    """SQL to fix one finding (empty string when the fix is not a SQL change).

    ``agreement_elements`` (extracted Appendix C) is used when the share does not exist yet;
    ``column_order`` (source_columns) keeps view columns in table order.
    """
    def ordered(table: str, columns: list[str]) -> list[str]:
        if column_order is None or column_order.empty:
            return columns
        pos = dict(zip(column_order[column_order["table_name"] == table]["column_name"],
                       column_order[column_order["table_name"] == table]["ordinal_position"]))
        return sorted(columns, key=lambda c: pos.get(c, 999))

    ft, share = finding["finding_type"], finding["share_name"]
    granted = finding.get("recipient_name") or (objects["recipient_name"].dropna().iloc[0] if not objects.empty and objects["recipient_name"].notna().any() else None)
    out: list[str] = [f"-- {ft}: {finding.get('detail', '')}", "-- Review before running. Requires share owner privileges."]

    def tables_in_scope() -> list[str]:
        t = finding.get("source_table")
        return [t] if t else sorted(comparison["source_table"].dropna().unique())

    if ft in ("OVER_SHARING", "UNDER_SHARING"):
        for t in tables_in_scope():
            cmp_t = comparison[comparison["source_table"] == t]
            permitted = cmp_t[~cmp_t["status"].str.startswith("OVER")]["column_name"].tolist()
            if ft == "OVER_SHARING":
                keep = cmp_t[cmp_t["status"].str.startswith("OK")]["column_name"].tolist()
            else:
                keep = permitted
            obj = objects[objects["source_table"].str.endswith(f".{t}")]
            whole_table = (not obj.empty) and (obj.iloc[0]["data_object_type"] == "TABLE")
            out.append(f"\n-- {t}: share {len(keep)} column(s): permitted by the agreement"
                       + (" and already shared" if ft == "OVER_SHARING" else ""))
            out.append(_view_sql(share, t, ordered(t, keep)))
            if whole_table:
                out += ["-- The whole table is shared today: swap it for the view.",
                        f"ALTER SHARE {share} REMOVE TABLE {config.fq(t)};",
                        f"ALTER SHARE {share} ADD VIEW {_view_name(share, t)} AS acf.{t};"]
    elif ft in ("EXPIRED_AGREEMENT", "ACCESS_AFTER_EXPIRATION", "NO_AGREEMENT"):
        out.append(f"REVOKE SELECT ON SHARE {share} FROM RECIPIENT {granted or '<recipient>'};")
        if ft == "NO_AGREEMENT":
            out.append(f"-- After confirming nobody else depends on it:\n-- DROP SHARE {share};")
    elif ft == "RECIPIENT_MISMATCH":
        out += [f"REVOKE SELECT ON SHARE {share} FROM RECIPIENT {granted};",
                f"GRANT SELECT ON SHARE {share} TO RECIPIENT {agreement.get('recipient_name') or '<agreement recipient>'};"]
    elif ft == "NOT_IMPLEMENTED":
        out.append(f"CREATE SHARE IF NOT EXISTS {share} COMMENT 'Per agreement {finding.get('agreement_number')}';")
        el = agreement_elements if agreement_elements is not None and not agreement_elements.empty else comparison
        for t in sorted(el["source_table"].dropna().unique()):
            cols = el[el["source_table"] == t]["column_name"].dropna().tolist()
            out += [_view_sql(share, t, ordered(t, cols)), f"ALTER SHARE {share} ADD VIEW {_view_name(share, t)} AS acf.{t};"]
        out.append(f"GRANT SELECT ON SHARE {share} TO RECIPIENT {agreement.get('recipient_name') or '<recipient>'};")
    else:
        return ""
    return "\n".join(out)
