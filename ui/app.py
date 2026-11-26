"""Streamlit entry point: navigation, role selector, demo reset."""
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

st.set_page_config(page_title="Boutique X - Facturation", layout="wide")

HERE = Path(__file__).resolve().parent

PAGES = [
    ("pages/dashboard.py", "Tableau de bord", ":material/dashboard:"),
    ("pages/chat.py", "Chat", ":material/chat:"),
    ("pages/review.py", "Revue", ":material/fact_check:"),
    ("pages/anomalies.py", "Anomalies", ":material/warning:"),
    ("pages/draft.py", "Brouillon et validation", ":material/edit_document:"),
    ("pages/invoice.py", "Facture", ":material/receipt_long:"),
    ("pages/audit.py", "Audit", ":material/history:"),
]

st.session_state.setdefault("role", "vendeuse")
st.session_state.setdefault("dossier_id", None)

with st.sidebar:
    st.title("Boutique X")
    st.caption(f"Assistant IA de facturation · mode `{api_client.API_MODE}`")
    st.selectbox(
        "Rôle",
        options=list(USERS.keys()),
        format_func=lambda r: USERS[r],
        key="role",
    )
    st.session_state["user"] = {
        "vendeuse": "USR-VEND",
        "gerant": "USR-GER",
        "auditeur": "USR-AUD",
    }[st.session_state["role"]]
    st.caption(f"Connecté : {st.session_state['user']}")

    if st.session_state.get("dossier_id"):
        st.caption(f"Dossier actif : **{st.session_state['dossier_id']}**")

    st.divider()
    if st.button("Réinitialiser la démo", use_container_width=True):
        try:
            api_client.reset_demo()
            st.session_state["dossier_id"] = None
            st.toast("Démo réinitialisée")
            st.rerun()
        except ApiError as e:
            st.error(e.message)

pages = [
    st.Page(f, title=title, icon=icon)
    for f, title, icon in PAGES
    if (HERE / f).exists()
]

if not pages:
    st.info("Aucune page pour l'instant.")
    st.stop()

st.navigation(pages).run()
