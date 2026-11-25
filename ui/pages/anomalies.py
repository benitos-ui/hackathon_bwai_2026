"""Anomalies page: order vs delivery context, resolve with a mandatory justification."""
import streamlit as st

from ui import api_client
from ui.api_client import ApiError

TYPES = {"commande_vs_livre": "Commande contre livré"}

st.title("Anomalies")

dossier_id = st.session_state.get("dossier_id")
if not dossier_id:
    st.info("Aucun dossier ouvert. Crée-en un depuis la page Chat.")
    st.stop()

user = st.session_state["user"]

try:
    dossier = api_client.get_dossier(dossier_id)
    anomalies = api_client.get_anomalies(dossier_id)
    delivery = api_client.get_delivery(dossier_id)
except ApiError as e:
    st.error(e.message)
    st.stop()

open_count = sum(1 for a in anomalies if not a["resolved"])
st.markdown(f"Dossier **{dossier_id}** · statut **{dossier['doc_status']}**")

# Context: what was ordered vs what was delivered
st.subheader("Commandé contre livré")
st.dataframe(
    [
        {
            "Article": d["label"],
            "Commandé": d["ordered"],
            "Livré": d["delivered"],
            "Accepté": d["accepted"],
            "Refusé": d["refused"],
            "Manquant": d["missing"],
            "Motif": d["reason"] or "-",
        }
        for d in delivery
    ],
    hide_index=True,
    use_container_width=True,
)

st.subheader("Anomalies")
if not anomalies:
    st.success("Aucune anomalie détectée.")
elif open_count == 0:
    st.success("Toutes les anomalies sont résolues.")
else:
    st.warning(f"{open_count} anomalie(s) bloquante(s) à résoudre avant la validation.")

for a in anomalies:
    aid = a["id"]
    with st.container(border=True):
        head, badge = st.columns([4, 1])
        with head:
            st.markdown(f"**{aid} · {TYPES.get(a['type'], a['type'])}**")
            st.write(a["message"])
        with badge:
            if a["resolved"]:
                st.markdown(":green[:material/check_circle: Résolue]")
            else:
                st.markdown(":red[:material/error: Ouverte]")

        if a["resolved"]:
            st.caption("Justification enregistrée :")
            st.write(a["resolution"])
        else:
            just = st.text_area(
                "Justification (obligatoire)",
                key=f"just_{aid}",
                height=90,
                placeholder="Ex : la cliente a refusé la robe L (taille trop petite), seule la robe M est facturée.",
            )
            if st.button("Lever l'anomalie", key=f"resolve_{aid}", type="primary"):
                try:
                    api_client.resolve_anomaly(dossier_id, aid, user, just)
                    st.rerun()
                except ApiError as e:
                    st.error(e.message)