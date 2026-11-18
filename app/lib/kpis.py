"""Home-page KPIs, computed from the compliance tables (nothing hard-coded).

Each KPI returns a value, a short subline that explains the number, and a hover tooltip
(Markdown) built from the same rows, listing exactly what was counted.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class Kpi:
    label: str
    value: int
    sub: str
    help: str


def _bullets(items: list[str], limit: int = 8) -> str:
    more = f"\n- …and {len(items) - limit} more" if len(items) > limit else ""
    return "\n".join(f"- {i}" for i in items[:limit]) + more


def compute(summary: pd.DataFrame, findings: pd.DataFrame, agreements: pd.DataFrame) -> list[Kpi]:
    base = agreements[agreements["document_type"] != "AMENDMENT"]
    amend = agreements[agreements["document_type"] == "AMENDMENT"]
    active = summary[summary["granted_to"].fillna("") != ""]
    no_agreement = sorted(findings.loc[findings["finding_type"] == "NO_AGREEMENT", "share_name"].dropna().unique())
    not_impl = findings[findings["finding_type"] == "NOT_IMPLEMENTED"]
    noncomp = summary[summary["compliance_status"] == "NON_COMPLIANT"]
    crit = findings[findings["severity"] == "CRITICAL"]
    direct = findings[(findings["finding_type"] == "OVER_SHARING") & (findings["identifier_level"] == "direct")]

    def plural(n: int, word: str) -> str:
        return f"{n} {word}{'' if n == 1 else 's'}"

    return [
        Kpi("Agreements", len(base),
            f"+ {plural(len(amend), 'amendment')}" + (f" · {len(not_impl)} not yet shared" if len(not_impl) else ""),
            "Signed MOUs and ISAs extracted from the PDFs in the agreements volume. Amendments change an existing "
            "agreement, so they are counted separately.\n\n"
            + (f"**Amendments:**\n{_bullets([f'{r.agreement_number} amends {r.amends_agreement_number}' for r in amend.itertuples()])}\n\n" if len(amend) else "")
            + (f"**Signed but no share yet:**\n{_bullets([f'{r.agreement_number} ({r.share_name})' for r in not_impl.itertuples()])}" if len(not_impl) else "")),
        Kpi("Active shares", len(active),
            f"{len(active) - len(no_agreement)} with an agreement · {len(no_agreement)} without",
            "Delta Shares currently granted to at least one recipient.\n\n"
            + (f"**Shares with no MOU or ISA on file:**\n{_bullets(no_agreement)}" if no_agreement else "Every active share has an agreement.")),
        Kpi("Non-compliant shares", len(noncomp), f"of {len(active)} active shares",
            "Shares with at least one CRITICAL or HIGH finding (over-sharing, expired agreement, wrong recipient, or no agreement).\n\n"
            + _bullets([f"{r.share_name}: {r.finding_types}" for r in noncomp.itertuples()])),
        Kpi("Critical findings", len(crit), f"across {plural(crit['share_name'].nunique(), 'share')}",
            "Findings that need action now: direct identifiers shared without permission, a share still granted (or "
            "queried) after its agreement expired, or a share with no agreement.\n\n"
            + _bullets([f"{t.replace('_', ' ').title()}: {n}" for t, n in crit["finding_type"].value_counts().items()])),
        Kpi("Over-shared PII columns", len(direct), f"in {plural(direct['share_name'].nunique(), 'share')}",
            "Direct identifiers: columns that identify a person on their own (name, date of birth, SSN, email, phone) that a share exposes "
            "but no agreement permits. Identifier level comes from the `acf_identifier` column tag in Unity Catalog.\n\n"
            + _bullets([f"`{r.source_table}.{r.column_name}` in {r.share_name}" for r in direct.itertuples()])),
    ]
