"""Streamlit entry point: navigation, role selector, demo reset."""
import sys
from pathlib import Path

# Make "import ui.xxx" work when launched with "streamlit run ui/app.py"
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from ui import api_client
from ui.mock_data import USERS

st.set_page_config(page_title="Boutique X - Facturation", layout="wide")

HERE = Path(__file__).resolve().parent

# (file, title, icon), in sidebar order
PAGES = [
    ("pages/chat.py", "Chat", ":material/chat:"),
    ("pages/review.py", "Revue", ":material/fact_check:"),
    ("pages/anomalies.py", "Anomalies", ":material/warning:"),
    ("pages/draft.py", "Brouillon et validation", ":material/edit_document:"),
    ("pages/invoice.py", "Facture", ":material/receipt_long:"),
    ("pages/audit.py", "Audit", ":material/history:"),
]

# Session defaults
st.session_state.setdefault("role", "vendeuse")
st.session_state.setdefault("dossier_id", None)

with st.sidebar:
    st.title("Boutique X")
    st.caption("Assistant de facturation")
    st.selectbox(
        "Rôle",
        options=list(USERS.keys()),
        format_func=lambda r: USERS[r],
        key="role",
    )
    # One fixed demo account per role, so initiator and validator differ
    st.session_state["user"] = {
        "vendeuse": "USR-VEND",
        "gerant": "USR-GER",
        "auditeur": "USR-AUD",
    }[st.session_state["role"]]
    st.caption(f"Connecté : {st.session_state['user']}")

    st.divider()
    if st.button("Réinitialiser la démo", use_container_width=True):
        api_client.reset_demo()
        st.session_state["dossier_id"] = None
        st.toast("Démo réinitialisée")
        st.rerun()

# Only register pages whose file already exists
pages = [
    st.Page(f, title=title, icon=icon)
    for f, title, icon in PAGES
    if (HERE / f).exists()
]

if not pages:
    st.info("Aucune page pour l'instant. Crée ui/pages/chat.py.")
    st.stop()

st.navigation(pages).run()