"""Streamlit entry point: clean login screen, readable dark sidebar, navigation, demo reset."""
import sys
from pathlib import Path

# Make "import ui.xxx" work when launched with "streamlit run ui/app.py"
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from ui import api_client
from ui.api_client import ApiError
from ui.mock_data import USERS
from ui.styles import inject_styles, logo_svg, pill, role_pill

st.set_page_config(
    page_title="Boutique X • Facturation",
    page_icon="BX",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_styles()

HERE = Path(__file__).resolve().parent

PAGES = [
    ("pages/dashboard.py", "Tableau de bord", ":material/dashboard:"),
    ("pages/chat.py", "Chat & Import", ":material/chat:"),
    ("pages/review.py", "Revue", ":material/fact_check:"),
    ("pages/anomalies.py", "Anomalies", ":material/warning:"),
    ("pages/draft.py", "Brouillon & Validation", ":material/edit_document:"),
    ("pages/invoice.py", "Facture & Règlements", ":material/receipt_long:"),
    ("pages/audit.py", "Journal d'audit", ":material/history:"),
]

ROLE_TO_USER = {
    "vendeuse": "USR-VEND",
    "gerant": "USR-GER",
    "auditeur": "USR-AUD",
}

st.session_state.setdefault("authenticated", False)
st.session_state.setdefault("role", "vendeuse")
st.session_state.setdefault("user", ROLE_TO_USER["vendeuse"])
st.session_state.setdefault("dossier_id", None)
st.session_state.setdefault("login_identifier", "USR-VEND")


def _render_login_screen() -> None:
    """Clean, high-contrast centered login card with Boutique X logo and role buttons."""
    _, center, _ = st.columns([1, 1.25, 1])
    with center:
        st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown(
                '<div class="bx-login-hero">'
                f'<div style="margin-bottom:0.65rem;">{logo_svg(variant="light", size="lg")}</div>'
                '<div style="font-size:0.86rem;color:#475569;margin-bottom:0.5rem;">'
                'Facturation WhatsApp assistée · Environnement local</div>'
                '</div>',
                unsafe_allow_html=True,
            )

            selected_id = st.session_state.get("login_identifier", "USR-VEND")
            c1, c2, c3 = st.columns(3)
            if c1.button(
                "Vendeuse",
                key="quick_USR-VEND",
                type="primary" if selected_id == "USR-VEND" else "secondary",
                use_container_width=True,
            ):
                st.session_state["login_identifier"] = "USR-VEND"
                st.rerun()
            if c2.button(
                "Gérant",
                key="quick_USR-GER",
                type="primary" if selected_id == "USR-GER" else "secondary",
                use_container_width=True,
            ):
                st.session_state["login_identifier"] = "USR-GER"
                st.rerun()
            if c3.button(
                "Auditeur",
                key="quick_USR-AUD",
                type="primary" if selected_id == "USR-AUD" else "secondary",
                use_container_width=True,
            ):
                st.session_state["login_identifier"] = "USR-AUD"
                st.rerun()

            st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
            with st.form("enterprise_login_form", border=False):
                identifier = st.text_input(
                    "Identifiant",
                    key="login_identifier",
                    placeholder="USR-VEND, USR-GER ou USR-AUD",
                )
                password = st.text_input(
                    "Mot de passe",
                    type="password",
                    placeholder="Mot de passe de démonstration",
                )
                submitted = st.form_submit_button(
                    "Se connecter",
                    type="primary",
                    use_container_width=True,
                )

            if submitted:
                try:
                    auth = api_client.login(identifier.strip(), password)
                    st.session_state["authenticated"] = True
                    st.session_state["role"] = auth["role"]
                    st.session_state["user"] = auth["identifier"]
                    st.toast(f"Connecté : {auth['name']}")
                    st.rerun()
                except ApiError as exc:
                    st.error(f"Connexion refusée ({exc.status}) : {exc.message}")


if not st.session_state["authenticated"]:
    _render_login_screen()
    st.stop()

# ---- Clean Dark Sidebar ----
with st.sidebar:
    st.markdown(
        f'<div style="padding:0.2rem 0.1rem 0.5rem;">{logo_svg(variant="dark", size="sm")}</div>',
        unsafe_allow_html=True,
    )

    api_live = api_client.check_api_health()
    if api_client.API_MODE == "mock":
        sys_pill = '<span class="bx-pill bx-pill-dark"><span class="bx-dot-amber"></span>Mode hors-ligne</span>'
    elif api_live:
        sys_pill = '<span class="bx-pill bx-pill-dark"><span class="bx-dot-green"></span>API connectée</span>'
    else:
        sys_pill = '<span class="bx-pill bx-pill-dark"><span class="bx-dot-red"></span>API indisponible</span>'

    st.markdown(f'<div style="margin-bottom:0.55rem;">{sys_pill}</div>', unsafe_allow_html=True)

    st.selectbox(
        "Rôle actif",
        options=list(USERS.keys()),
        format_func=lambda r: USERS[r],
        key="role",
    )
    st.session_state["user"] = ROLE_TO_USER[st.session_state["role"]]

    dossier_active = st.session_state.get("dossier_id")
    dossier_row = (
        f'<div class="bx-sb-dossier"><span>Dossier</span>'
        f'<span class="mono" style="color:#FDE047;font-weight:700;">{dossier_active}</span></div>'
        if dossier_active
        else '<div class="bx-sb-dossier"><span>Dossier</span><span>Aucun</span></div>'
    )
    st.markdown(
        '<div class="bx-sb-profile">'
        '<div class="bx-sb-row">'
        f'<span class="mono" style="font-size:0.82rem;font-weight:700;color:#FFFFFF;">{st.session_state["user"]}</span>'
        f'{role_pill(st.session_state["role"], dark=True)}</div>'
        f'{dossier_row}</div>',
        unsafe_allow_html=True,
    )

    st.divider()
    c_rst, c_out = st.columns(2)
    with c_rst:
        if st.button("Réinitialiser", use_container_width=True, help="Réinitialiser la démo"):
            try:
                api_client.reset_demo()
                st.session_state["dossier_id"] = None
                st.toast("Démo réinitialisée")
                st.rerun()
            except ApiError as e:
                st.error(e.message)
    with c_out:
        if st.button("Déconnexion", use_container_width=True):
            st.session_state["authenticated"] = False
            st.rerun()

pages = [
    st.Page(f, title=title, icon=icon)
    for f, title, icon in PAGES
    if (HERE / f).exists()
]

if not pages:
    st.info("Aucune page pour l'instant.")
    st.stop()

st.navigation(pages).run()
