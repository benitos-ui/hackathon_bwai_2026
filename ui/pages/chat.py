"""Chat page: import a WhatsApp export (paste or .txt upload) and show the thread."""
from pathlib import Path

import streamlit as st

from ui import api_client
from ui.api_client import ApiError
from ui.components.chat import render_chat

ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE = ROOT / "data" / "scenarios" / "awa_dossou.txt"
if not SAMPLE.exists():
    SAMPLE = ROOT / "data" / "awa_dossou.txt"


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _load_sample():
    st.session_state["paste"] = SAMPLE.read_text(encoding="utf-8-sig")


st.title("Chat")
st.caption("Colle un export WhatsApp ou téléverse le fichier .txt, puis crée le dossier (rôle vendeuse).")

st.text_area(
    "Texte de la conversation",
    key="paste",
    height=180,
    placeholder="25/11/2026 10:02 - Awa: Bonjour, je veux ...",
)

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

with st.expander("Démonstration reprise après interruption (E12)"):
    st.caption("Simule une coupure du service après l'étape EXTRAIT, puis permet de reprendre sans doublon.")
    c_int, c_res = st.columns(2)
    with c_int:
        if st.button("Simuler interruption à EXTRAIT", disabled=not raw.strip(), use_container_width=True):
            try:
                res = api_client.simulate_interruption(raw, st.session_state["user"], "EXTRAIT")
                st.session_state["dossier_id"] = res["dossier_id"]
                st.warning(f"Traitement interrompu pour {res['dossier_id']} — étapes faites : {res.get('steps', [])}")
            except ApiError as e:
                st.error(e.message)
    with c_res:
        did = st.session_state.get("dossier_id")
        if st.button("Reprendre le traitement", disabled=not did, use_container_width=True):
            try:
                res = api_client.resume_dossier(did, st.session_state["user"])
                st.success(f"Reprise terminée sans doublon — étapes : {res.get('steps', [])}")
            except ApiError as e:
                st.error(e.message)

if create:
    try:
        res = api_client.import_conversation(raw, st.session_state["user"])
        st.session_state["dossier_id"] = res["dossier_id"]
        if res.get("duplicate"):
            st.info(f"Ce fil a déjà été importé : dossier existant **{res['dossier_id']}** ouvert.")
        else:
            st.success(f"Dossier **{res['dossier_id']}** créé (version {res.get('version', 1)}).")
    except ApiError as e:
        st.error(f"{e.status} : {e.message}")

dossier_id = st.session_state.get("dossier_id")
if dossier_id:
    try:
        dossier = api_client.get_dossier(dossier_id)
        st.markdown(
            f"Dossier **{dossier_id}** · statut **{dossier['doc_status']}** · "
            f"version **{dossier.get('version', 1)}** · étapes : `{', '.join(dossier.get('steps', []))}`"
        )
        render_chat(api_client.get_messages(dossier_id), height=420)
    except ApiError as e:
        st.error(e.message)
