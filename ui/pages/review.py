"""Review page: thread with source highlighting (left), fields to confirm (right)."""
import streamlit as st

from ui import api_client
from ui.api_client import ApiError
from ui.components.chat import render_chat

LABELS = {
    "client": "Client",
    "product_1": "Produit 1",
    "quantity_ordered": "Quantité commandée",
    "product_2": "Produit 2",
    "zone": "Zone de livraison",
    "payment_mode": "Mode de paiement",
    "delivered": "Livré",
    "refusal": "Refus",
    "promo_code": "Code promo",
}
STATUS = {
    "extracted": "Extrait",
    "needs_review": "À relire",
    "missing": "Manquant",
    "ambiguous": "Ambigu",
}
ORIGIN = {"conversation": "Conversation", "referentiel": "Référentiel", "systeme": "Système"}
COLORS = {"vert": "green", "orange": "orange", "rouge": "red"}

st.title("Revue")

dossier_id = st.session_state.get("dossier_id")
if not dossier_id:
    st.info("Aucun dossier ouvert. Crée-en un depuis la page Chat.")
    st.stop()

user = st.session_state["user"]

try:
    dossier = api_client.get_dossier(dossier_id)
    messages = api_client.get_messages(dossier_id)
    fields = api_client.get_extractions(dossier_id)
except ApiError as e:
    st.error(e.message)
    st.stop()

done = sum(1 for f in fields if f.get("confirmed"))
st.markdown(f"Dossier **{dossier_id}** · statut **{dossier['doc_status']}**")
st.progress(done / len(fields), text=f"{done} champ(s) confirmé(s) sur {len(fields)}")

st.session_state.setdefault("selected_field", fields[0]["field"])
selected = next((f for f in fields if f["field"] == st.session_state["selected_field"]), fields[0])

left, right = st.columns([1, 1], gap="large")

with left:
    st.subheader("Conversation")
    src = selected["source"]
    has_source = bool(src.get("message_id"))
    render_chat(messages, highlight=src if has_source else None, height=520)
    if has_source:
        st.caption(f"Source de « {LABELS.get(selected['field'], selected['field'])} » : "
                   f"message {src['message_id']}")
    else:
        st.caption(f"Aucune source pour « {LABELS.get(selected['field'], selected['field'])} ».")

with right:
    st.subheader("Champs extraits")
    for f in fields:
        name = f["field"]
        confirmed = f.get("confirmed", False)
        value = f["value"] if f["value"] is not None else "(vide)"
        color = COLORS.get(f.get("couleur"), "gray")
        is_sel = name == st.session_state["selected_field"]

        with st.container(border=True):
            top, badge = st.columns([3, 2])
            with top:
                st.markdown(("**" if not is_sel else "**:blue[") + LABELS.get(name, name)
                            + ("**" if not is_sel else "]**"))
                st.markdown(f"{value}")
            with badge:
                st.markdown(f":{color}[**{round(f['confidence'] * 100)} %**] · "
                            f"{STATUS.get(f['status'], f['status'])}")
                st.caption(f"{ORIGIN.get(f['origin'], f['origin'])} · {f['model_version']}")
                if confirmed:
                    st.markdown(":green[:material/check_circle: Confirmé]")

            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("Voir la source", key=f"src_{name}",
                             disabled=not f["source"].get("message_id"),
                             use_container_width=True):
                    st.session_state["selected_field"] = name
                    st.rerun()
            with c2:
                if st.button("Confirmer", key=f"ok_{name}", disabled=confirmed,
                             use_container_width=True):
                    try:
                        api_client.confirm_field(dossier_id, name, user)
                        st.rerun()
                    except ApiError as e:
                        st.error(e.message)
            with c3:
                with st.popover("Corriger", use_container_width=True):
                    new = st.text_input("Nouvelle valeur", key=f"val_{name}")
                    if st.button("Enregistrer", key=f"save_{name}"):
                        if not new.strip():
                            st.warning("Saisis une valeur.")
                        else:
                            try:
                                api_client.confirm_field(dossier_id, name, user,
                                                         new_value=new.strip())
                                st.rerun()
                            except ApiError as e:
                                st.error(e.message)