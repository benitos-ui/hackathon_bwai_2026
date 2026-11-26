"""Refined High-Contrast Fintech Design System for Boutique X.

Clean, airy, high-legibility layout:
- Dark Obsidian Sidebar (#0F172A) with crisp contrast (no wildcard color leaks)
- Soft Alabaster Canvas (#F8FAFC) with crisp white cards (#FFFFFF) & legible dark ink (#0F172A)
- Minimal icons, zero visual clutter, tabular-nums monospace for FCFA & SHA-256

Strictly presentation-only: zero business calculations, zero permission decisions.
"""
import html

import streamlit as st

_CLEAN_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');

:root {
  --bx-bg: #F8FAFC;
  --bx-surface: #FFFFFF;
  --bx-border: #E2E8F0;
  --bx-border-strong: #CBD5E1;
  --bx-ink: #0F172A;
  --bx-ink-soft: #334155;
  --bx-muted: #64748B;
  --bx-accent: #1D4ED8;
  --bx-emerald: #047857;
  --bx-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
  --bx-shadow-hover: 0 8px 20px rgba(15, 23, 42, 0.07);
  --bx-radius: 12px;
  --bx-ease: cubic-bezier(0.2, 0, 0, 1);
}

/* Hide Streamlit default chrome */
#MainMenu, footer, [data-testid="stDeployButton"], [data-testid="stDecoration"] {
  visibility: hidden !important;
  display: none !important;
}

/* Global canvas & high-contrast typography */
html, body, .stApp {
  font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
  color: var(--bx-ink) !important;
  background-color: var(--bx-bg) !important;
}
[data-testid="stHeader"] {
  background: rgba(248, 250, 252, 0.9) !important;
  backdrop-filter: blur(8px);
}
.main .block-container {
  padding-top: 1.4rem !important;
  padding-bottom: 2.5rem !important;
  max-width: 1280px !important;
}

/* Force crisp legibility on all main-area Streamlit inputs, labels, radios & dropdowns */
.main p, .main label, .main .stMarkdown, .main .stRadio label, .main .stCheckbox label {
  color: #0F172A !important;
}
.main .stCaption, .main [data-testid="stCaptionContainer"] p {
  color: #475569 !important;
}
.main input, .main textarea, .main [data-baseweb="select"] > div {
  background-color: #FFFFFF !important;
  color: #0F172A !important;
  border-color: #CBD5E1 !important;
}
[data-baseweb="menu"], [data-baseweb="popover"] {
  background-color: #FFFFFF !important;
  color: #0F172A !important;
}
[data-baseweb="menu"] li, [data-baseweb="menu"] span, [data-baseweb="menu"] div {
  color: #0F172A !important;
}

/* ===== CLEAN DARK SIDEBAR (NO WILDCARD LEAK) ===== */
[data-testid="stSidebar"] {
  background: #0F172A !important;
  border-right: 1px solid #1E293B !important;
}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] span {
  color: #E2E8F0;
}
[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] {
  border-radius: 8px !important;
  margin: 2px 6px !important;
  padding: 0.48rem 0.8rem !important;
  color: #CBD5E1 !important;
  font-weight: 500 !important;
  font-size: 0.9rem !important;
  transition: background 0.18s var(--bx-ease) !important;
}
[data-testid="stSidebar"] [data-testid="stSidebarNavLink"] span {
  color: inherit !important;
}
[data-testid="stSidebar"] [data-testid="stSidebarNavLink"]:hover {
  background: rgba(255, 255, 255, 0.08) !important;
  color: #FFFFFF !important;
}
[data-testid="stSidebar"] [data-testid="stSidebarNavLink"][aria-current="page"] {
  background: rgba(212, 175, 55, 0.16) !important;
  border-left: 3px solid #D4AF37 !important;
  color: #FFFFFF !important;
  font-weight: 600 !important;
}
[data-testid="stSidebar"] [data-baseweb="select"] > div {
  background: #1E293B !important;
  border: 1px solid #334155 !important;
  border-radius: 8px !important;
}
[data-testid="stSidebar"] [data-baseweb="select"] span,
[data-testid="stSidebar"] [data-baseweb="select"] div {
  color: #F8FAFC !important;
}
[data-testid="stSidebar"] .stButton > button {
  background: #1E293B !important;
  color: #F8FAFC !important;
  border: 1px solid #334155 !important;
  border-radius: 8px !important;
  font-weight: 600 !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
  background: #334155 !important;
  border-color: #D4AF37 !important;
}
[data-testid="stSidebar"] hr {
  border-color: #1E293B !important;
}

.bx-sb-profile {
  background: #1E293B;
  border: 1px solid #334155;
  border-radius: 10px;
  padding: 0.7rem 0.85rem;
  margin: 0.45rem 0 0.65rem;
}
.bx-sb-row {
  display: flex; align-items: center; justify-content: space-between; gap: 6px;
}
.bx-sb-dossier {
  margin-top: 0.5rem; padding-top: 0.5rem;
  border-top: 1px solid #334155;
  display: flex; justify-content: space-between; align-items: center;
  font-size: 0.78rem; color: #CBD5E1;
}

/* ===== CLEAN WHITE CARDS ===== */
[data-testid="stVerticalBlockBorderWrapper"] {
  background: var(--bx-surface) !important;
  border: 1px solid var(--bx-border) !important;
  border-radius: var(--bx-radius) !important;
  box-shadow: var(--bx-shadow) !important;
  transition: border-color 0.2s var(--bx-ease), box-shadow 0.2s var(--bx-ease) !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:hover {
  border-color: var(--bx-border-strong) !important;
}

/* Buttons: crisp, high-contrast */
.main .stButton > button,
.main .stDownloadButton > button,
.main .stFormSubmitButton > button {
  border-radius: 8px !important;
  font-weight: 600 !important;
  font-size: 0.86rem !important;
  padding: 0.46rem 0.9rem !important;
  transition: all 0.18s var(--bx-ease) !important;
  border: 1px solid #CBD5E1 !important;
  background: #FFFFFF !important;
  color: #0F172A !important;
}
.main .stButton > button:hover,
.main .stDownloadButton > button:hover,
.main .stFormSubmitButton > button:hover {
  background: #F1F5F9 !important;
  border-color: #94A3B8 !important;
}
.main .stButton > button[kind="primary"],
.main .stDownloadButton > button[kind="primary"],
.main .stFormSubmitButton > button[kind="primary"] {
  background: #0F172A !important;
  color: #FFFFFF !important;
  border: 1px solid #0F172A !important;
}
.main .stButton > button[kind="primary"]:hover,
.main .stDownloadButton > button[kind="primary"]:hover,
.main .stFormSubmitButton > button[kind="primary"]:hover {
  background: #1E293B !important;
  border-color: #1E293B !important;
}
.main .stButton > button:disabled,
.main .stFormSubmitButton > button:disabled {
  opacity: 0.45 !important;
}

/* Dataframes & Monospace */
[data-testid="stDataFrame"] {
  border: 1px solid var(--bx-border);
  border-radius: 10px;
  overflow: hidden;
  background: #FFFFFF;
}
.tabular, .mono {
  font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace !important;
  font-variant-numeric: tabular-nums !important;
}

/* ===== COMPACT PAGE HEADER ===== */
.bx-page-header {
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 12px;
  padding: 1rem 1.3rem;
  margin-bottom: 1.15rem;
  background: #FFFFFF;
  border: 1px solid var(--bx-border);
  border-radius: var(--bx-radius);
  box-shadow: var(--bx-shadow);
}
.bx-title {
  font-size: 1.4rem; font-weight: 800; color: #0F172A;
  letter-spacing: -0.02em; line-height: 1.2; margin: 0;
}
.bx-subtitle { font-size: 0.86rem; color: #475569; margin-top: 0.2rem; }
.bx-header-right { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }

/* ===== HIGH-CONTRAST SEMANTIC PILLS ===== */
.bx-pill {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 0.2rem 0.62rem; border-radius: 999px;
  font-size: 0.74rem; font-weight: 600; line-height: 1.3; white-space: nowrap;
}
.bx-pill-green  { background: #DCFCE7; color: #14532D; border: 1px solid #BBF7D0; }
.bx-pill-amber  { background: #FEF3C7; color: #78350F; border: 1px solid #FDE68A; }
.bx-pill-red    { background: #FEE2E2; color: #7F1D1D; border: 1px solid #FECACA; }
.bx-pill-blue   { background: #DBEAFE; color: #1E3A8A; border: 1px solid #BFDBFE; }
.bx-pill-purple { background: #F3E8FF; color: #581C87; border: 1px solid #E9D5FF; }
.bx-pill-gold   { background: #FEF9C3; color: #713F12; border: 1px solid #FDE047; }
.bx-pill-slate  { background: #F1F5F9; color: #1E293B; border: 1px solid #E2E8F0; }
.bx-pill-dark   { background: #1E293B; color: #F8FAFC; border: 1px solid #334155; }

.bx-dot-green { width: 7px; height: 7px; border-radius: 50%; display: inline-block; background: #22C55E; }
.bx-dot-amber { width: 7px; height: 7px; border-radius: 50%; display: inline-block; background: #F59E0B; }
.bx-dot-red   { width: 7px; height: 7px; border-radius: 50%; display: inline-block; background: #EF4444; }

/* ===== CLEAN MINIMAL KPI GRID (NO BUSY SPARKLINES / BIG ICONS) ===== */
.bx-kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 1rem;
}
@media (max-width: 960px) {
  .bx-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
.bx-kpi-card {
  background: #FFFFFF;
  border: 1px solid var(--bx-border);
  border-top: 3px solid #CBD5E1;
  border-radius: var(--bx-radius);
  padding: 0.95rem 1.1rem;
  box-shadow: var(--bx-shadow);
  transition: transform 0.18s var(--bx-ease), box-shadow 0.18s var(--bx-ease);
}
.bx-kpi-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--bx-shadow-hover);
}
.bx-kpi-blue   { border-top-color: #2563EB; }
.bx-kpi-green  { border-top-color: #059669; }
.bx-kpi-amber  { border-top-color: #D97706; }
.bx-kpi-red    { border-top-color: #DC2626; }
.bx-kpi-purple { border-top-color: #7C3AED; }
.bx-kpi-gold   { border-top-color: #D4AF37; }
.bx-kpi-slate  { border-top-color: #64748B; }

.bx-kpi-label {
  font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.05em; color: #475569; margin-bottom: 0.35rem;
}
.bx-kpi-value {
  font-family: 'JetBrains Mono', monospace;
  font-size: 1.42rem; font-weight: 700; color: #0F172A;
  font-variant-numeric: tabular-nums; line-height: 1.2;
}
.bx-kpi-sub {
  font-size: 0.76rem; color: #64748B; margin-top: 0.3rem;
}

/* ===== SLIM CONFIDENCE GAUGE ===== */
.bx-conf-track {
  width: 100%; height: 4px; border-radius: 999px;
  background: #E2E8F0; overflow: hidden; margin-top: 7px;
}
.bx-conf-fill { height: 100%; border-radius: 999px; }
.bx-conf-vert   { background: #16A34A; }
.bx-conf-orange { background: #D97706; }
.bx-conf-rouge  { background: #DC2626; }

/* ===== CLEAN A4 INVOICE SHEET ===== */
.bx-a4-sheet {
  position: relative;
  background: #FFFFFF;
  border: 1px solid #CBD5E1;
  border-top: 4px solid #0F172A;
  border-radius: 12px;
  padding: 1.8rem 2rem;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.07);
  overflow: hidden;
  margin-bottom: 1.2rem;
}
.bx-a4-stamp {
  position: absolute;
  top: 22px; right: 24px;
  transform: rotate(-6deg);
  padding: 0.3rem 0.9rem;
  border-radius: 6px;
  font-size: 0.78rem; font-weight: 800; letter-spacing: 0.12em; text-transform: uppercase;
  border: 2px solid currentColor;
}
.bx-stamp-draft { color: #92400E; background: #FEF3C7; }
.bx-stamp-valid { color: #14532D; background: #DCFCE7; }
.bx-stamp-emise { color: #1E3A8A; background: #DBEAFE; }

.bx-a4-header {
  display: flex; justify-content: space-between; align-items: flex-start; gap: 16px;
  padding-bottom: 1rem; border-bottom: 1px solid #E2E8F0; margin-bottom: 1rem;
}
.bx-a4-meta { font-size: 0.8rem; color: #475569; margin-top: 4px; line-height: 1.45; }
.bx-a4-table {
  width: 100%; border-collapse: collapse; margin: 0.6rem 0 1.2rem; font-size: 0.88rem;
}
.bx-a4-table th {
  text-align: left; padding: 0.6rem 0.7rem;
  background: #F8FAFC; color: #334155;
  font-size: 0.72rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;
  border-bottom: 1.5px solid #CBD5E1;
}
.bx-a4-table td {
  padding: 0.65rem 0.7rem; border-bottom: 1px solid #E2E8F0; color: #0F172A;
}
.bx-a4-table th.num, .bx-a4-table td.num {
  text-align: right; font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums;
}
.bx-a4-totals {
  margin-left: auto; width: min(370px, 100%);
  background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 10px;
  padding: 0.8rem 1rem;
}
.bx-a4-trow {
  display: flex; justify-content: space-between; padding: 0.25rem 0;
  font-size: 0.86rem; color: #1E293B;
}
.bx-a4-trow .val { font-family: 'JetBrains Mono', monospace; font-variant-numeric: tabular-nums; }
.bx-a4-trow.grand {
  margin-top: 0.45rem; padding-top: 0.6rem;
  border-top: 2px solid #0F172A;
  font-size: 1.02rem; font-weight: 800; color: #0F172A;
}
.bx-a4-footer {
  margin-top: 1.15rem; padding-top: 0.75rem;
  border-top: 1px dashed #CBD5E1;
  font-size: 0.75rem; color: #475569;
  display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px;
}

/* ===== CLEAN VERTICAL AUDIT TIMELINE ===== */
.bx-timeline {
  position: relative;
  padding-left: 24px;
  margin: 0.75rem 0 1.2rem;
}
.bx-timeline::before {
  content: "";
  position: absolute;
  left: 7px; top: 8px; bottom: 8px;
  width: 2px;
  background: #CBD5E1;
}
.bx-tl-item {
  position: relative;
  background: #FFFFFF;
  border: 1px solid var(--bx-border);
  border-radius: 10px;
  padding: 0.8rem 1rem;
  margin-bottom: 10px;
  box-shadow: var(--bx-shadow);
}
.bx-tl-dot {
  position: absolute;
  left: -22px; top: 15px;
  width: 10px; height: 10px; border-radius: 50%;
  background: #2563EB;
  border: 2px solid #FFFFFF;
  box-shadow: 0 0 0 2px #BFDBFE;
}
.bx-tl-dot.green { background: #16A34A; box-shadow: 0 0 0 2px #BBF7D0; }
.bx-tl-dot.amber { background: #D97706; box-shadow: 0 0 0 2px #FDE68A; }
.bx-tl-dot.red   { background: #DC2626; box-shadow: 0 0 0 2px #FECACA; }
.bx-tl-top {
  display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;
}
.bx-tl-detail { font-size: 0.86rem; color: #1E293B; margin-top: 0.35rem; }
.bx-tl-hash {
  margin-top: 0.4rem; display: inline-block;
  font-family: 'JetBrains Mono', monospace; font-size: 0.72rem;
  color: #334155; background: #F8FAFC; border: 1px solid #E2E8F0;
  padding: 0.16rem 0.5rem; border-radius: 6px;
}

/* Login Header */
.bx-login-hero {
  text-align: center;
  padding: 0.9rem 0.5rem 0.6rem;
}
</style>
"""


def inject_styles() -> None:
    """Inject the clean high-contrast CSS into the current Streamlit page."""
    st.markdown(_CLEAN_CSS, unsafe_allow_html=True)


def logo_svg(variant: str = "light", size: str = "md") -> str:
    """Return bespoke inline SVG logo 'Boutique X — Atelier IA' (wax weave + BX gold/emerald)."""
    uid = f"bx_{variant}_{size}"
    word_fill = "#F8FAFC" if variant == "dark" else "#0F172A"
    sub_fill = "#94A3B8" if variant == "dark" else "#475569"
    width_map = {"sm": "195", "md": "225", "lg": "240"}
    w = width_map.get(size, "220")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 286 72" width="{w}" '
        f'style="max-width:100%;height:auto;display:inline-block;" role="img" aria-label="Boutique X">'
        f'<defs>'
        f'<linearGradient id="{uid}_g" x1="0%" y1="0%" x2="100%" y2="100%">'
        f'<stop offset="0%" stop-color="#D4AF37"/><stop offset="52%" stop-color="#F3E5AB"/>'
        f'<stop offset="100%" stop-color="#C59B27"/></linearGradient>'
        f'<linearGradient id="{uid}_e" x1="0%" y1="100%" x2="100%" y2="0%">'
        f'<stop offset="0%" stop-color="#059669"/><stop offset="100%" stop-color="#10B981"/></linearGradient>'
        f'<linearGradient id="{uid}_o" x1="0%" y1="0%" x2="100%" y2="100%">'
        f'<stop offset="0%" stop-color="#0F172A"/><stop offset="100%" stop-color="#1E293B"/></linearGradient>'
        f'</defs>'
        f'<rect x="4" y="4" width="64" height="64" rx="16" fill="url(#{uid}_o)" stroke="url(#{uid}_g)" stroke-width="1.9"/>'
        f'<path d="M36 10 L62 36 L36 62 L10 36 Z" stroke="url(#{uid}_g)" stroke-opacity="0.35" stroke-width="1.2" fill="none"/>'
        f'<path d="M36 15 L57 36 L36 57 L15 36 Z" stroke="url(#{uid}_e)" stroke-opacity="0.48" stroke-width="1" fill="none"/>'
        f'<circle cx="36" cy="11" r="2.1" fill="url(#{uid}_g)"/>'
        f'<circle cx="61" cy="36" r="2.1" fill="url(#{uid}_e)"/>'
        f'<circle cx="36" cy="61" r="2.1" fill="url(#{uid}_g)"/>'
        f'<circle cx="11" cy="36" r="2.1" fill="url(#{uid}_e)"/>'
        f'<path d="M21 24 H31.5 C35 24 37.2 25.9 37.2 28.8 C37.2 31 35.8 32.5 33.7 33.1 '
        f'C36.3 33.8 38 35.6 38 38.4 C38 41.9 35.4 44 31.3 44 H21 V24 Z '
        f'M25.4 31.8 H30.4 C32.1 31.8 33 30.9 33 29.5 C33 28.1 32.1 27.3 30.4 27.3 H25.4 V31.8 Z '
        f'M25.4 40.6 H30.8 C32.7 40.6 33.7 39.6 33.7 38 C33.7 36.4 32.6 35.4 30.8 35.4 H25.4 V40.6 Z" fill="url(#{uid}_g)"/>'
        f'<path d="M37.5 24 H42.5 L46.2 30.4 L49.9 24 H54.7 L48.8 33.8 L55.2 44 H50.1 L46.1 37.2 '
        f'L42.1 44 H37.1 L43.5 33.7 L37.5 24 Z" fill="url(#{uid}_e)"/>'
        f'<text x="82" y="34" fill="{word_fill}" font-family="Plus Jakarta Sans, Inter, sans-serif" '
        f'font-size="21" font-weight="800" letter-spacing="0.06em">BOUTIQUE X</text>'
        f'<rect x="82" y="42" width="26" height="2" rx="1" fill="url(#{uid}_g)"/>'
        f'<text x="114" y="47" fill="{sub_fill}" font-family="JetBrains Mono, monospace" '
        f'font-size="10.2" font-weight="600" letter-spacing="0.13em">ATELIER IA • COTONOU</text>'
        f'</svg>'
    )


def fcfa(n) -> str:
    return f"{int(n or 0):,}".replace(",", "\u00a0") + "\u00a0FCFA"


def pill(text: str, tone: str = "slate") -> str:
    safe = tone if tone in ("green", "amber", "red", "blue", "purple", "gold", "slate", "dark") else "slate"
    return f'<span class="bx-pill bx-pill-{safe}">{html.escape(str(text))}</span>'


_STATUS_MAP = {
    "BROUILLON": ("Brouillon", "slate"),
    "A_REVOIR": ("À revoir", "amber"),
    "PRET_A_VALIDER": ("Prêt à valider", "blue"),
    "VALIDEE": ("Validée", "green"),
    "EMISE": ("Émise", "green"),
    "ANNULE": ("Annulé", "red"),
    "NON_REGLEE": ("Non réglée", "slate"),
    "PARTIELLEMENT_REGLEE": ("Partiellement réglée", "amber"),
    "REGLEE": ("Réglée", "green"),
    "TROP_PERCU": ("Trop-perçu", "purple"),
    "REMBOURSEMENT_EN_COURS": ("Remboursement en cours", "amber"),
}


def status_pill(code: str) -> str:
    label, tone = _STATUS_MAP.get(str(code or "").upper(), (str(code or "-"), "slate"))
    return pill(label, tone)


def role_pill(role: str, *, dark: bool = False) -> str:
    mapping = {
        "vendeuse": ("Vendeuse", "blue"),
        "gerant": ("Gérant", "green"),
        "auditeur": ("Auditeur", "purple"),
    }
    label, tone = mapping.get(str(role or "").lower(), (str(role), "slate"))
    return pill(label, tone)


def page_header(
    title: str,
    subtitle: str = "",
    *,
    eyebrow: str = "",
    section: str = "",
    right_html: str = "",
    show_live_status: bool = False,
) -> None:
    """Render a clean, uncluttered page header."""
    sub_block = f'<div class="bx-subtitle">{html.escape(subtitle)}</div>' if subtitle else ""
    right_block = f'<div class="bx-header-right">{right_html}</div>' if right_html else ""
    st.markdown(
        '<div class="bx-page-header">'
        f'<div><h1 class="bx-title">{html.escape(title)}</h1>{sub_block}</div>'
        f'{right_block}</div>',
        unsafe_allow_html=True,
    )


def render_kpi_grid(cards: list[dict]) -> None:
    """Render a clean 4-column KPI grid with subtle colored top accent bar (zero icon clutter)."""
    items = []
    for c in cards:
        tone = c.get("tone", "slate")
        cls = f"bx-kpi-{tone}" if tone in ("blue", "green", "amber", "red", "purple", "gold", "slate") else "bx-kpi-slate"
        label = html.escape(str(c.get("label", "")))
        value = html.escape(str(c.get("value", "")))
        sub = html.escape(str(c.get("sub", "")))
        sub_html = f'<div class="bx-kpi-sub">{sub}</div>' if sub else ""
        items.append(
            f'<div class="bx-kpi-card {cls}">'
            f'<div class="bx-kpi-label">{label}</div>'
            f'<div class="bx-kpi-value">{value}</div>'
            f'{sub_html}</div>'
        )
    st.markdown('<div class="bx-kpi-grid">' + "".join(items) + "</div>", unsafe_allow_html=True)


def render_invoice_sheet(
    number: str,
    doc_status: str,
    lines: list[dict],
    totals: dict,
    *,
    dossier_id: str = "",
    client_name: str = "",
    initiator: str = "",
    content_hash: str = "",
) -> None:
    """Render a clean A4 invoice preview sheet with Boutique X SVG logo & diagonal stamp."""
    st_upper = str(doc_status or "BROUILLON").upper()
    if st_upper == "EMISE":
        stamp_cls, stamp_lbl = "bx-stamp-emise", "ÉMISE"
    elif st_upper == "VALIDEE":
        stamp_cls, stamp_lbl = "bx-stamp-valid", "VALIDÉE"
    else:
        stamp_cls, stamp_lbl = "bx-stamp-draft", "BROUILLON"

    rows_html = []
    if lines:
        for l in lines:
            rows_html.append(
                "<tr>"
                f"<td><strong>{html.escape(str(l.get('label', '')))}</strong></td>"
                f'<td class="num">{html.escape(str(l.get("qty", 0)))}</td>'
                f'<td class="num">{html.escape(fcfa(l.get("unit", 0)))}</td>'
                f'<td class="num"><strong>{html.escape(fcfa(l.get("amount", 0)))}</strong></td>'
                "</tr>"
            )
    else:
        rows_html.append(
            '<tr><td colspan="4" style="text-align:center;color:#64748B;padding:1.2rem;">'
            "Aucune ligne facturable pour le moment.</td></tr>"
        )

    tot_rows = [
        ("Sous-total articles HT", totals.get("subtotal", 0)),
        (totals.get("discount_label") or "Remise", -int(totals.get("discount", 0))),
        ("Base articles après remise", totals.get("base_after_discount", 0)),
        ("Frais de livraison HT", totals.get("delivery", 0)),
        ("Base HT totale", totals.get("base_ht", 0)),
        (f"TVA ({totals.get('vat_rate', 18)} %)", totals.get("vat", 0)),
    ]
    t_html = []
    for lbl, amt in tot_rows:
        amt_txt = ("\u2212\u00a0" + fcfa(-amt)) if amt < 0 else fcfa(amt)
        t_html.append(
            f'<div class="bx-a4-trow"><span>{html.escape(str(lbl))}</span>'
            f'<span class="val">{html.escape(amt_txt)}</span></div>'
        )
    t_html.append(
        '<div class="bx-a4-trow grand"><span>Total TTC</span>'
        f'<span class="val">{html.escape(fcfa(totals.get("total_ttc", 0)))}</span></div>'
    )

    meta_parts = []
    if dossier_id:
        meta_parts.append(f"Dossier : <span class='mono' style='color:#0F172A;font-weight:600;'>{html.escape(dossier_id)}</span>")
    if client_name:
        meta_parts.append(f"Client : <strong style='color:#0F172A;'>{html.escape(client_name)}</strong>")
    if initiator:
        meta_parts.append(f"Initiateur : <span class='mono'>{html.escape(initiator)}</span>")
    meta_line = " &nbsp;·&nbsp; ".join(meta_parts)

    hash_html = (
        f"<span class='mono' style='color:#14532D;font-weight:600;'>SHA-256 : {html.escape(str(content_hash)[:20])}…</span>"
        if content_hash
        else "<span>Numéro attribué à la validation gérant</span>"
    )

    sheet = (
        '<div class="bx-a4-sheet">'
        f'<div class="bx-a4-stamp {stamp_cls}">{stamp_lbl}</div>'
        '<div class="bx-a4-header">'
        f'<div>{logo_svg(variant="light", size="md")}'
        f'<div class="bx-a4-meta">{meta_line}</div></div>'
        '<div style="text-align:right;padding-right:125px;">'
        '<div style="font-size:0.7rem;color:#64748B;text-transform:uppercase;font-weight:700;">Document</div>'
        f'<div class="mono" style="font-size:1.05rem;font-weight:700;color:#0F172A;margin-top:2px;">{html.escape(str(number))}</div>'
        '</div></div>'
        '<table class="bx-a4-table"><thead><tr>'
        '<th>Désignation</th><th class="num">Qté livrée</th><th class="num">PU HT</th><th class="num">Montant HT</th>'
        f'</tr></thead><tbody>{"".join(rows_html)}</tbody></table>'
        f'<div class="bx-a4-totals">{"".join(t_html)}</div>'
        '<div class="bx-a4-footer">'
        '<span>Document pédagogique — données fictives — paiements simulés</span>'
        f'{hash_html}</div></div>'
    )
    st.markdown(sheet, unsafe_allow_html=True)


def render_audit_timeline(entries: list[dict], actions_map: dict[str, str]) -> None:
    """Render a clean vertical audit timeline with minimal dots & monospace SHA-256 chain."""
    action_tone = {
        "INVOICE_VALIDATED": "green",
        "VALIDER_FACTURE": "green",
        "INVOICE_EMITTED": "green",
        "PAYMENT_ADDED": "green",
        "ANOMALY_RESOLVED": "green",
        "FIELD_CORRECTED": "amber",
        "EMISSION_QUEUED_OFFLINE": "amber",
        "PAYMENT_REJECTED": "red",
        "DOSSIER_CANCELLED": "red",
        "CREDIT_CREATED": "amber",
    }
    pill_tone = {"green": "green", "amber": "amber", "red": "red"}

    items = []
    for e in entries:
        act = e.get("action", "")
        act_label = actions_map.get(act, act)
        dot_cls = action_tone.get(act, "")
        p_tone = pill_tone.get(dot_cls, "blue")
        ts = (e.get("timestamp") or "")[:19].replace("T", " ") or "Horodatage local"
        user = html.escape(str(e.get("user") or e.get("actor") or "-"))
        obj = html.escape(str(e.get("object") or ""))
        detail = html.escape(str(e.get("detail") or ""))
        h_cur = str(e.get("hash") or "")
        h_prev = str(e.get("previous_hash") or "")

        hash_block = ""
        if h_cur:
            prev_short = (h_prev[:10] + "…") if h_prev else "genesis"
            hash_block = (
                f'<div class="bx-tl-hash">SHA-256 : {html.escape(prev_short)} '
                f'&rarr; <strong>{html.escape(h_cur[:16])}…</strong></div>'
            )

        obj_pill = pill(obj, "slate") if obj else ""
        items.append(
            '<div class="bx-tl-item">'
            f'<div class="bx-tl-dot {dot_cls}"></div>'
            '<div class="bx-tl-top">'
            f'<div><span class="mono" style="color:#64748B;font-size:0.78rem;margin-right:6px;">#{e.get("n", "")}</span>'
            f'{pill(act_label, p_tone)} {obj_pill}</div>'
            f'<div style="font-size:0.78rem;color:#475569;">'
            f'<span class="mono" style="color:#0F172A;font-weight:600;">{user}</span>'
            f' &nbsp;·&nbsp; {html.escape(ts)}</div></div>'
            f'<div class="bx-tl-detail">{detail}</div>'
            f'{hash_block}</div>'
        )
    st.markdown('<div class="bx-timeline">' + "".join(items) + "</div>", unsafe_allow_html=True)
