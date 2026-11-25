"""Chat page: import a WhatsApp export (paste or .txt upload) and show the thread."""
from pathlib import Path

import streamlit as st

from ui import api_client
from ui.api_client import ApiError
from ui.components.chat import render_chat

# ui/pages/chat.py -> repo root is three levels up
SAMPLE = Path(__file__).resolve().parent.parent.parent / "data" / "scenarios" / "awa_dossou.txt"


def _decode(data: bytes) -> str:
    """WhatsApp exports are not always clean UTF-8."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _load_sample():
    st.session_state["paste"] = SAMPLE.read_text(encoding="utf-8-sig")


st.title("Chat")
st.caption("Colle un export WhatsApp ou téléverse le fichier .txt, puis crée le dossier.")

# Input 1: pasted text
st.text_area(
    "Texte de la conversation",
    key="paste",
    height=180,
    placeholder="25/11/2026 10:02 - Awa: Bonjour, je veux ...",
)

# Input 2: .txt upload (collapsed by default)
with st.expander("Ou téléverser un export .txt"):
    uploaded = st.file_uploader("Fichier d'export WhatsApp", type=["txt"], key="upload")

if uploaded is not None:
    raw = _decode(uploaded.getvalue())
    st.caption(f"Fichier utilisé : {uploaded.name} (le texte collé est ignoré)")
else:
    raw = st.session_state.get("paste", "")

col_a, col_b = st.columns([2, 1])
with col_a:
    create = st.button(
        "Créer le dossier depuis ce fil",
        type="primary",
        disabled=not raw.strip(),
        use_container_width=True,
    )
with col_b:
    if SAMPLE.exists():
        st.button("Charger le scénario d'Awa", on_click=_load_sample, use_container_width=True)

if create:
    try:
        res = api_client.import_conversation(raw, st.session_state["user"])
        st.session_state["dossier_id"] = res["dossier_id"]
        if res["duplicate"]:
            st.info("Ce fil a déjà été importé : le dossier existant est ouvert.")
        else:
            st.success("Dossier créé.")
    except ApiError as e:
        st.error(e.message)

dossier_id = st.session_state.get("dossier_id")
if dossier_id:
    try:
        dossier = api_client.get_dossier(dossier_id)
        st.markdown(f"Dossier **{dossier_id}** · statut **{dossier['doc_status']}**")
        render_chat(api_client.get_messages(dossier_id), height=420)
    except ApiError as e:
        st.error(e.message)