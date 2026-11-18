"""Shared design system for the ACF Delta Share Compliance app (adapted from the HHS OA app).

A single place for the look and feel: a federal, light-mode aesthetic built on
Public Sans (the U.S. government typeface) and Material Symbols icons, with depth
from layered shadows, subtle gradients, and translucency — kept clean and modern,
not quirky. Pages call ``apply_chrome()`` once at the top, then use ``page_hero``
and ``nav_card`` helpers.
"""

from __future__ import annotations

import streamlit as st

# Palette (USWDS-inspired federal navy) -------------------------------------
NAVY = "#1a4480"
NAVY_DARK = "#162e51"
INK = "#1b2b3a"
LINK = "#005ea2"
GOLD = "#ffbe2e"  # thin flag-accent rule

# Chart palette — federal, professional (not rainbow). Used per Storytelling
# with Data: sequential hue to encode magnitude, a small qualitative set only
# where bars are genuinely different categories, and a standout for the insight.
TEAL = "#2a9d8f"
AMBER = "#e9a800"
SLATE = "#5b8fb9"
PLUM = "#7b4f9d"
GREEN = "#4c956c"
RED = "#c0392b"    # standout for the "overpaying" extreme
MUTED = "#c3ccd9"  # gray for de-emphasised context
CHART_PALETTE = [NAVY, TEAL, AMBER, SLATE, PLUM, GREEN]
# Larger qualitative set for many-segment stacked charts (contractor mix, etc.).
# "Other" is rendered separately in MUTED gray so real segments stand out.
STACK_PALETTE = [
    NAVY, TEAL, AMBER, PLUM, GREEN, SLATE,
    "#c9453b", "#e07b39", "#3b6ea5", "#a23e8c",
]
# light → hue ranges for single-hue sequential (magnitude) encodings
_SEQ = {
    "navy": ["#dbe5f4", NAVY],
    "teal": ["#d9efeb", "#177e72"],
    "amber": ["#fbeeca", "#b07c08"],
    "slate": ["#e4ebf4", "#3a6ea5"],
}

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Public+Sans:ital,wght@0,300;0,400;0,500;0,600;0,700;0,800&display=swap');
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');

:root {{
  --oa-navy: {NAVY};
  --oa-navy-dark: {NAVY_DARK};
  --oa-ink: {INK};
  --oa-link: {LINK};
  --oa-border: #dce3ec;
  --oa-muted: #5a6b7b;
  --oa-shadow-sm: 0 1px 2px rgba(16,24,40,.06), 0 1px 3px rgba(16,24,40,.10);
  --oa-shadow-md: 0 4px 6px -2px rgba(16,24,40,.05), 0 12px 20px -4px rgba(16,24,40,.12);
  --oa-radius: 14px;
}}

/* Base typography */
html, body, .stApp, [class*="st-"], button, input, textarea, select {{
  font-family: 'Public Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}}
/* Re-assert the Material icon font — the broad rule above otherwise clobbers
   Streamlit's icon glyphs and they render as literal text (e.g. "arrow_forward",
   "history"). Tag-agnostic and matches every IconMaterial testid variant
   (buttons, page links, expanders, alerts, selectbox, etc.). */
[data-testid*="IconMaterial"], [data-testid="stExpanderIcon"],
[data-testid="stAlertDynamicIcon"], [class*="material-symbols"],
.material-symbols-rounded, .material-symbols-outlined {{
  font-family: 'Material Symbols Rounded' !important;
  font-weight: normal !important; font-style: normal !important;
  -webkit-font-feature-settings: 'liga' !important; font-feature-settings: 'liga' !important;
}}
.stApp {{
  background:
    radial-gradient(1200px 600px at 100% -10%, rgba(36,145,255,.06), transparent 60%),
    radial-gradient(900px 500px at -10% 0%, rgba(26,68,128,.05), transparent 55%),
    #f5f7fa;
}}
h1, h2, h3, h4 {{ color: var(--oa-ink); letter-spacing: -0.01em; font-weight: 700; }}
.main .block-container {{ padding-top: 1.2rem; max-width: 1320px; }}

/* Material Symbols helper for custom HTML */
.ms {{
  font-family: 'Material Symbols Rounded';
  font-weight: normal; font-style: normal; line-height: 1;
  vertical-align: middle; -webkit-font-feature-settings: 'liga';
  font-variation-settings: 'FILL' 0, 'wght' 500, 'GRAD' 0, 'opsz' 24;
}}

/* ---- Federal full-width masthead (fixed, spans the whole viewport) ---- */
.oa-masthead {{
  position: fixed; top: 0; left: 0; right: 0; width: 100%;
  z-index: 1000000;
  display: flex; align-items: center; gap: .7rem;
  height: 64px; padding: 0 1.4rem;
  background: linear-gradient(90deg, var(--oa-navy-dark) 0%, var(--oa-navy) 55%, #21539c 100%);
  color: #eaf1fb; box-shadow: var(--oa-shadow-md);
  border-bottom: 3px solid {GOLD};
}}
.oa-masthead::before {{
  content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 6px;
  background: linear-gradient(180deg, {GOLD}, #d9302c);
}}
.oa-masthead .seal {{
  width: 38px; height: 38px; border-radius: 9px; display: grid; place-items: center;
  background: rgba(255,255,255,.10); border: 1px solid rgba(255,255,255,.18);
}}
.oa-masthead .seal .ms {{ font-size: 22px; color: #fff; }}
.oa-masthead .org {{ font-weight: 700; font-size: .98rem; letter-spacing: .02em; }}
.oa-masthead .sub {{ font-weight: 400; font-size: .8rem; color: #bcd0ec; }}

/* Push the app below the fixed masthead */
[data-testid="stSidebar"] {{ top: 64px !important; height: calc(100vh - 64px) !important; }}
[data-testid="stMain"] .block-container,
section.main .block-container {{ padding-top: 5rem !important; }}
header[data-testid="stHeader"] {{ height: 0 !important; background: transparent !important; }}

/* When the sidebar is collapsed, the "expand" control lives in the header,
   which sits BEHIND the fixed masthead — so it's hidden and the sidebar can't be
   reopened. Pull it out to a fixed spot just below the masthead, above it in
   stacking order, so it stays clickable. */
[data-testid="stExpandSidebarButton"] {{
  position: fixed !important;
  top: 74px !important;
  left: 10px !important;
  z-index: 1000002 !important;
  background: #ffffff !important;
  border: 1px solid var(--oa-border) !important;
  border-radius: 9px !important;
  box-shadow: var(--oa-shadow-sm) !important;
}}
[data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"] {{
  color: var(--oa-navy) !important;
}}

/* ---- Page hero ---- */
.oa-hero {{
  display: flex; align-items: center; gap: 1rem;
  background: linear-gradient(135deg, #ffffff 0%, #f3f7fc 100%);
  border: 1px solid var(--oa-border); border-radius: var(--oa-radius);
  padding: 1.15rem 1.4rem; margin-bottom: 1.25rem;
  box-shadow: var(--oa-shadow-sm);
}}
.oa-hero .icon {{
  flex: 0 0 auto; width: 52px; height: 52px; border-radius: 12px;
  display: grid; place-items: center;
  background: linear-gradient(135deg, var(--oa-navy), #2a64b8);
  box-shadow: 0 6px 14px rgba(26,68,128,.35);
}}
.oa-hero .icon .ms {{ font-size: 28px; color: #fff; font-variation-settings: 'FILL' 1, 'wght' 500; }}
.oa-hero h1 {{ margin: 0; font-size: 1.55rem; }}
.oa-hero p {{ margin: .15rem 0 0; color: var(--oa-muted); font-size: .95rem; }}

/* ---- Cards (bordered containers) ---- */
[data-testid="stVerticalBlockBorderWrapper"] {{
  background: rgba(255,255,255,.85); backdrop-filter: blur(6px);
  border: 1px solid var(--oa-border) !important; border-radius: var(--oa-radius) !important;
  box-shadow: var(--oa-shadow-sm); transition: box-shadow .18s ease, transform .18s ease;
}}
[data-testid="stVerticalBlockBorderWrapper"]:hover {{
  box-shadow: var(--oa-shadow-md); transform: translateY(-2px);
}}

/* Nav card content */
.oa-card-head {{ display:flex; align-items:center; gap:.6rem; margin-bottom:.35rem; }}
.oa-card-head .ms {{
  font-size: 24px; color: var(--oa-navy);
  background: #eaf1fb; padding: 8px; border-radius: 10px;
}}
.oa-card-head .t {{ font-weight: 700; font-size: 1.08rem; color: var(--oa-ink); }}
/* Uniform description height keeps the three home nav cards — and their action
   buttons — aligned regardless of copy length. */
.oa-card-desc {{ color: var(--oa-muted); font-size: .92rem; min-height: 6.5em; }}

/* ---- Metrics as cards ---- */
[data-testid="stMetric"] {{
  background: #fff; border: 1px solid var(--oa-border); border-radius: 12px;
  padding: .85rem 1rem; box-shadow: var(--oa-shadow-sm);
  border-left: 4px solid var(--oa-navy);
}}
[data-testid="stMetricValue"] {{ color: var(--oa-navy-dark); font-weight: 700; }}
[data-testid="stMetricLabel"] {{ color: var(--oa-muted); }}

/* ---- Buttons / page links ---- */
.stButton > button, .stDownloadButton > button {{
  border-radius: 10px; font-weight: 600; border: 1px solid var(--oa-border);
  box-shadow: var(--oa-shadow-sm); transition: all .15s ease;
}}
.stButton > button[kind="primary"], .stDownloadButton > button {{
  background: linear-gradient(135deg, var(--oa-navy), #21539c);
  border: none; color: #fff;
}}
.stButton > button[kind="primary"]:hover, .stDownloadButton > button:hover {{
  box-shadow: 0 8px 18px rgba(26,68,128,.35); transform: translateY(-1px);
}}
[data-testid="stPageLink"] a {{
  border: 1px solid var(--oa-border); border-radius: 10px; padding: .45rem .7rem;
  background: #fff; box-shadow: var(--oa-shadow-sm); font-weight: 600;
  color: var(--oa-navy) !important; transition: all .15s ease;
}}
[data-testid="stPageLink"] a:hover {{ background: #f3f7fc; transform: translateY(-1px); }}

/* ---- Sidebar: deep navy, federal ---- */
[data-testid="stSidebar"] {{
  background: linear-gradient(180deg, var(--oa-navy-dark) 0%, var(--oa-navy) 100%);
  border-right: 1px solid rgba(255,255,255,.06);
}}
[data-testid="stSidebar"] * {{ color: #dfe8f5; }}
[data-testid="stSidebarNav"] {{ padding-top: .4rem; }}
[data-testid="stSidebarNav"] a {{
  border-radius: 9px; margin: 2px 8px; padding: .35rem .55rem;
}}
[data-testid="stSidebarNav"] a:hover {{ background: rgba(255,255,255,.08); }}
[data-testid="stSidebarNav"] a[aria-current="page"] {{
  background: rgba(255,255,255,.14); border-left: 3px solid {GOLD};
}}
[data-testid="stSidebarNav"] span {{ color: #eaf1fb !important; font-weight: 600; }}

/* ---- Inputs ---- */
[data-baseweb="input"], [data-baseweb="select"], .stTextArea textarea {{
  border-radius: 10px !important;
}}
.stTextInput input, .stTextArea textarea, [data-baseweb="select"] > div {{
  background: #fff !important; border-color: var(--oa-border) !important;
}}

/* ---- Tabs / radio segmented ---- */
[data-testid="stTabs"] button[aria-selected="true"] {{ color: var(--oa-navy); font-weight: 700; }}

/* Tighten the default header bar */
header[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stDecoration"] {{ background: linear-gradient(90deg, var(--oa-navy), {GOLD}); }}

/* Dataframes */
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {{
  border: 1px solid var(--oa-border); border-radius: 12px; box-shadow: var(--oa-shadow-sm);
}}

/* ---- Conceptual data-flow diagram (home page) ---- */
.oa-flow {{
  display: flex; align-items: stretch; gap: 0; flex-wrap: nowrap;
  margin: .35rem 0 .2rem;
}}
.oa-flow .stage {{
  flex: 1 1 0; min-width: 0;
  background: linear-gradient(160deg, #ffffff 0%, #f3f7fc 100%);
  border: 1px solid var(--oa-border); border-radius: 12px;
  padding: .95rem 1.05rem; box-shadow: var(--oa-shadow-sm);
}}
.oa-flow .stage .cap {{
  display: flex; align-items: center; gap: .45rem;
  font-size: .72rem; font-weight: 700; letter-spacing: .06em;
  text-transform: uppercase; color: var(--oa-navy); margin-bottom: .1rem;
}}
.oa-flow .stage .cap .ms {{ font-size: 18px; color: var(--oa-navy); }}
.oa-flow .stage .lead {{
  font-size: .82rem; color: var(--oa-muted); margin: .1rem 0 .6rem;
}}
.oa-flow .item {{
  display: flex; align-items: flex-start; gap: .5rem;
  padding: .4rem .55rem; margin-bottom: .35rem;
  background: #fff; border: 1px solid var(--oa-border); border-radius: 9px;
}}
.oa-flow .item:last-child {{ margin-bottom: 0; }}
.oa-flow .item .ms {{ font-size: 18px; color: var(--oa-navy); margin-top: 1px; }}
.oa-flow .item .txt {{ line-height: 1.2; }}
.oa-flow .item .t {{ font-weight: 600; font-size: .86rem; color: var(--oa-ink); }}
.oa-flow .item .m {{ font-size: .74rem; color: var(--oa-muted); }}
.oa-flow .item .badge {{
  margin-left: auto; align-self: center; flex: 0 0 auto;
  font-size: .68rem; font-weight: 700; color: #9a6a00;
  background: #fbeeca; border-radius: 999px; padding: .05rem .45rem;
}}
.oa-flow .arrow {{
  flex: 0 0 34px; display: grid; place-items: center; color: var(--oa-navy);
}}
.oa-flow .arrow .ms {{ font-size: 26px; opacity: .55; }}
.oa-flow-note {{
  display: flex; align-items: center; gap: .5rem; flex-wrap: wrap;
  margin-top: .7rem; padding: .55rem .8rem;
  background: #eef4fb; border: 1px solid #d6e3f2; border-radius: 10px;
  font-size: .8rem; color: var(--oa-ink);
}}
.oa-flow-note .ms {{ font-size: 18px; color: var(--oa-navy); }}
.oa-flow-note .syn {{
  font-size: .68rem; font-weight: 700; color: #9a6a00;
  background: #fbeeca; border-radius: 999px; padding: .05rem .45rem;
}}
@media (max-width: 900px) {{
  .oa-flow {{ flex-wrap: wrap; }}
  .oa-flow .arrow {{ flex-basis: 100%; transform: rotate(90deg); height: 26px; }}
}}
</style>
"""


def apply_chrome() -> None:
    """Inject the global stylesheet and render the federal top banner."""
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown(
        """
<div class="oa-masthead">
  <span class="seal"><span class="ms">share</span></span>
  <div>
    <div class="org">U.S. DEPARTMENT OF HEALTH &amp; HUMAN SERVICES</div>
    <div class="sub">Administration for Children &amp; Families &middot; Delta Share Agreement Compliance</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def page_hero(title: str, subtitle: str, icon: str) -> None:
    """A page header band with a Material icon, title, and subtitle."""
    st.markdown(
        f"""
<div class="oa-hero">
  <div class="icon"><span class="ms">{icon}</span></div>
  <div>
    <h1>{title}</h1>
    <p>{subtitle}</p>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def data_error(exc: Exception, key: str) -> None:
    """Friendly, recoverable error when a warehouse query fails.

    Distinguishes a stale/unconsented sign-in token (needs a page reload) from a
    transient warehouse hiccup (worth a retry).
    """
    import re

    from lib import db

    msg = str(exc)
    if db.is_auth_error(exc) and "scope" in msg.lower():
        # Missing OAuth scope: a reload re-mints the token with the SAME consented
        # scopes, so it won't help — the user must RE-AUTHORIZE the app.
        m = re.search(r"required scopes?:\s*([\w\-.,\s]+)", msg, re.I)
        needed = f"**{m.group(1).strip()}**" if m else "an additional"
        st.error(
            f"This feature needs the {needed} permission, which your current "
            "sign-in hasn't granted. A plain reload won't add it — you need to "
            "**re-authorize the app**: open it in a new incognito/private window "
            "(or fully sign out of Databricks and back in), approve the "
            "authorization prompt, then return. See the admin about a persistent "
            "fix if this keeps happening.",
            icon=":material/lock_reset:",
        )
    elif db.is_auth_error(exc):
        st.error(
            "Your sign-in session has expired. **Reload this page** "
            "(Cmd/Ctrl + Shift + R) to renew it, then try again.",
            icon=":material/lock_reset:",
        )
    else:
        st.error(
            "Couldn't load data from the SQL warehouse. Serverless warehouses "
            "pause when idle, so it may be starting up — wait a few seconds and "
            "retry.",
            icon=":material/cloud_off:",
        )
        if st.button("Retry", icon=":material/refresh:", key=f"retry_{key}"):
            st.cache_data.clear()
            st.rerun()
    with st.expander("Technical details"):
        st.code(str(exc))


def nav_card(icon: str, title: str, description: str, page: str, link_label: str) -> None:
    """A clean navigation card for the home page (uniform height via .oa-card-desc)."""
    with st.container(border=True):
        st.markdown(
            f"""
<div class="oa-card-head">
  <span class="ms">{icon}</span><span class="t">{title}</span>
</div>
<div class="oa-card-desc">{description}</div>
""",
            unsafe_allow_html=True,
        )
        st.page_link(page, label=link_label, icon=":material/arrow_forward:")


SEVERITY_COLORS = {"CRITICAL": "#c0392b", "HIGH": "#e07b39", "MEDIUM": "#e9a800", "LOW": "#5b8fb9",
                   "INFO": "#7b8a9a", "REVIEW": "#7b4f9d"}
STATUS_COLORS = {"NON_COMPLIANT": "#c0392b", "ATTENTION": "#e9a800", "NOT_IMPLEMENTED": "#7b8a9a", "COMPLIANT": "#4c956c"}


def pill(text: str, color: str) -> str:
    """Small colored badge (HTML) for severities / statuses."""
    return (f'<span style="display:inline-block;padding:.08rem .55rem;border-radius:999px;'
            f'background:{color}1f;color:{color};font-weight:700;font-size:.74rem;'
            f'border:1px solid {color}55">{text}</span>')


def synthetic_note() -> None:
    st.caption(":material/science: All agreements, partners, people, and data in this demo are **synthetic**.")


# ---------------------------------------------------------------- "How it works" diagram
_FLOW_CSS = """
<style>
.hw-flow { display:flex; align-items:stretch; gap:0; margin:.4rem 0 0; }
.hw-stage { flex:1 1 0; min-width:0; background:linear-gradient(160deg,#fff 0%,#f3f7fc 100%);
  border:1px solid var(--oa-border); border-radius:12px; padding:.85rem .9rem; box-shadow:var(--oa-shadow-sm); }
.hw-cap { display:flex; align-items:center; gap:.4rem; font-size:.72rem; font-weight:700; letter-spacing:.06em;
  text-transform:uppercase; color:var(--oa-navy); }
.hw-cap .num { display:grid; place-items:center; width:20px; height:20px; border-radius:50%;
  background:var(--oa-navy); color:#fff; font-size:.68rem; letter-spacing:0; }
.hw-lead { font-size:.8rem; color:var(--oa-muted); margin:.15rem 0 .55rem; }
.hw-lane { font-size:.66rem; font-weight:700; text-transform:uppercase; letter-spacing:.05em; color:#8a97a6;
  margin:.45rem 0 .25rem; }
.hw-item { display:flex; gap:.5rem; align-items:flex-start; background:#fff; border:1px solid var(--oa-border);
  border-radius:9px; padding:.42rem .55rem; margin-bottom:.35rem; }
.hw-item .ms { font-size:19px; color:var(--oa-navy); margin-top:1px; }
.hw-item .t { font-weight:600; font-size:.84rem; color:var(--oa-ink); line-height:1.2; }
.hw-item .m { font-size:.72rem; color:var(--oa-muted); line-height:1.25; }
.hw-chip { display:inline-block; margin-top:.2rem; font-size:.64rem; font-weight:700; color:#b3290f;
  background:#ffece6; border:1px solid #ffc9b8; border-radius:999px; padding:.02rem .45rem; }
.hw-chip.gw { color:#5b2a86; background:#f1e8fa; border-color:#d9c2ef; }
.hw-gw { display:flex; align-items:center; gap:.9rem; flex-wrap:wrap; margin-top:.6rem; padding:.55rem .9rem;
  background:#f6f0fc; border:1px solid #d9c2ef; border-radius:12px; color:#3d1f5c; }
.hw-gw .ttl { display:flex; align-items:center; gap:.4rem; font-weight:700; font-size:.86rem; }
.hw-gw .ttl .ms { font-size:20px; color:#7b4f9d; }
.hw-gw .g { display:flex; align-items:center; gap:.3rem; font-size:.76rem; }
.hw-gw .g .ms { font-size:16px; color:#7b4f9d; }
.hw-badge { display:inline-block; margin-left:.3rem; font-size:.62rem; font-weight:700; color:#9a6a00;
  background:#fbeeca; border-radius:999px; padding:.02rem .4rem; vertical-align:middle; }
.hw-arrow { flex:0 0 52px; display:flex; flex-direction:column; align-items:center; justify-content:center;
  color:var(--oa-navy); }
.hw-arrow .ms { font-size:26px; opacity:.6; }
.hw-arrow .lbl { font-size:.6rem; color:var(--oa-muted); text-align:center; line-height:1.1; margin-top:.1rem; }
.hw-gov { display:flex; align-items:center; gap:.9rem; flex-wrap:wrap; margin-top:.6rem; padding:.55rem .9rem;
  background:#fff3ef; border:1px solid #ffc9b8; border-radius:12px; color:#7a1d0a; }
.hw-gov .ttl { display:flex; align-items:center; gap:.4rem; font-weight:700; font-size:.86rem; }
.hw-gov .ttl .ms { font-size:20px; color:#b3290f; }
.hw-gov .g { display:flex; align-items:center; gap:.3rem; font-size:.76rem; }
.hw-gov .g .ms { font-size:16px; color:#b3290f; }
@media (max-width: 1000px) { .hw-flow { flex-wrap:wrap; } .hw-arrow { flex-basis:100%; transform:rotate(90deg); height:30px; } }
</style>
"""


def _hw_item(icon: str, title: str, feature: str, meta: str = "", badge: str = "", gateway: bool = False) -> str:
    b = f'<span class="hw-badge">{badge}</span>' if badge else ""

    m = f'<div class="m">{meta}</div>' if meta else ""
    return (f'<div class="hw-item"><span class="ms">{icon}</span><div><div class="t">{title}{b}</div>{m}'
            f'<span class="hw-chip{" gw" if gateway else ""}">{feature}</span></div></div>')


def _hw_stage(num: int, cap: str, lead: str, body: str) -> str:
    return (f'<div class="hw-stage"><div class="hw-cap"><span class="num">{num}</span>{cap}</div>'
            f'<div class="hw-lead">{lead}</div>{body}</div>')


def _hw_arrow(label: str) -> str:
    return f'<div class="hw-arrow"><span class="ms">arrow_forward</span><span class="lbl">{label}</span></div>'


def how_it_works_diagram() -> None:
    """Data flow from agreements + shares to findings and action, labeled with the Databricks feature behind each step."""
    s1 = _hw_stage(1, "Ingest", "Two sides of every exchange land in one governed place.",
        '<div class="hw-lane">What was agreed</div>'
        + _hw_item("picture_as_pdf", "MOU / ISA / amendment PDFs", "Unity Catalog Volume", "Typed and scanned, handwritten")
        + '<div class="hw-lane">What is shared</div>'
        + _hw_item("table_chart", "ACF source tables", "Unity Catalog tables + column tags", "PII tagged direct / indirect")
        + _hw_item("share", "Shares, recipients, grants", "Delta Sharing")
        + _hw_item("monitoring", "Columns, lineage, audit logs", "System tables"))
    s2 = _hw_stage(2, "Understand", "AI reads the documents; SQL reads the shares.",
        _hw_item("document_scanner", "Parse every page, incl. handwriting", "ai_parse_document", gateway=True)
        + _hw_item("category", "MOU, ISA or amendment?", "ai_classify", gateway=True)
        + _hw_item("data_object", "Parties, dates, share, Appendix C columns", "ai_extract", "With per-field confidence", gateway=True)
        + _hw_item("travel_explore", "Searchable agreement language", "ai_prep_search + Vector Search", gateway=True))
    s3 = _hw_stage(3, "Compare", "Permitted vs actually shared, refreshed on a schedule.",
        _hw_item("rule", "Permitted columns (incl. amendments)", "Materialized views")
        + _hw_item("view_column", "Shared columns traced to source", "Materialized views + lineage")
        + _hw_item("gpp_maybe", "Compliance findings", "Materialized view",
                   "Over / under-sharing, expired, wrong recipient, no agreement, needs review")
        + _hw_item("schedule", "Daily refresh", "Lakeflow Jobs"))
    s4 = _hw_stage(4, "Act", "Find, fix and document every issue.",
        _hw_item("apps", "Compliance app", "Databricks Apps", "Review findings, generate fixes, draft agreements")
        + _hw_item("auto_awesome", "Drafts MOUs, amendments, notices", "Foundation Model API (Claude)", gateway=True)
        + _hw_item("forum", "Plain-language questions", "AI/BI Genie")
        + _hw_item("notifications_active", "Email on new critical findings", "Databricks SQL Alerts"))
    gw = ('<div class="hw-gw"><span class="ttl"><span class="ms">shield_lock</span>Unity AI Gateway governs every model call'
          '</span><span class="g">AI Functions + LLMs</span>'
          '<span class="g"><span class="ms">key</span>Endpoint permissions</span>'
          '<span class="g"><span class="ms">speed</span>Rate limits</span>'
          '<span class="g"><span class="ms">health_and_safety</span>Guardrails</span>'
          '<span class="g"><span class="ms">receipt_long</span>Usage + payload logs</span></div>')
    gov = ('<div class="hw-gov"><span class="ttl"><span class="ms">verified_user</span>Unity Catalog governs every step</span>'
           '<span class="g"><span class="ms">sell</span>Column tags</span>'
           '<span class="g"><span class="ms">lock_person</span>Per-user access (app runs as you)</span>'
           '<span class="g"><span class="ms">account_tree</span>Lineage</span>'
           '<span class="g"><span class="ms">history</span>Audit logs</span>'
           '<span class="g"><span class="ms">bolt</span>Serverless SQL warehouse</span></div>')
    st.markdown(_FLOW_CSS + '<div class="hw-flow">' + s1 + _hw_arrow("files + metadata") + s2
                + _hw_arrow("tables") + s3 + _hw_arrow("findings") + s4 + '</div>' + gw + gov,
                unsafe_allow_html=True)
