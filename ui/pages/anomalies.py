"""Anomalies page: order vs delivery context, resolve blocking anomalies with justification."""
import html

import streamlit as st

from ui import api_client
from ui.api_client import ApiError
from ui.styles import inject_styles, page_header, pill, status_pill

inject_styles()

TYPES = {
    "commande_vs_livre": "Commande contre livré",
    "A_LIVRAISON": "Écart commande / livraison",
    "A_CLIENT_INCONNU": "Client inconnu",
    "A_PRODUIT_AMBIGU": "Produit ambigu ou inconnu",
    "A_QUANTITE": "Quantité incohérente",
    "A_VARIANTE": "Variante absente ou indisponible",
    "A_PRIX": "Écart de prix > 10 %",
    "A_PAIEMENT": "Incohérence de paiement",
    "A_DOUBLON": "Ligne en doublon",
    "A_CONVERSATION": "Multi-commandes / multi-clients",
    "A_MEDIA": "Média non pris en charge",
}

dossier_id = st.session_state.get("dossier_id")
if not dossier_id:
    page_header("Anomalies & Contrôles", "Résolution traçable des écarts détectés avant facturation.")
    st.info("Aucun dossier ouvert. Crée-en un depuis la page **Chat & Import**.")
    st.stop()

user = st.session_state["user"]

try:
    dossier = api_client.get_dossier(dossier_id)
    anomalies = api_client.get_anomalies(dossier_id)
    delivery = api_client.get_delivery(dossier_id)
except ApiError as e:
    page_header("Anomalies & Contrôles", f"Dossier {dossier_id}")
    st.error(e.message)
    st.stop()

open_count = sum(1 for a in anomalies if not a["resolved"])
resolved_count = len(anomalies) - open_count

badges = (
    pill(dossier_id, "slate")
    + status_pill(dossier.get("doc_status", ""))
    + (pill(f"{open_count} ouverte(s)", "red") if open_count else pill("0 ouverte", "green"))
    + pill(f"{resolved_count} résolue(s)", "slate")
)
page_header(
    "Anomalies & Contrôles métier",
    "Toute anomalie bloquante requiert une justification humaine horodatée dans l'audit.",
    right_html=badges,
)

with st.container(border=True):
    st.markdown("**Rapprochement commandé / livré / accepté**")
    if delivery:
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
    else:
        st.caption("Aucune ligne de livraison enregistrée.")

st.markdown("### Liste des anomalies")
if not anomalies:
    st.success("Aucune anomalie détectée sur ce dossier.")
elif open_count == 0:
    st.success("Toutes les anomalies sont résolues — le dossier peut poursuivre vers la validation.")
else:
    st.warning(f"{open_count} anomalie(s) bloquante(s) à résoudre avant la validation de la facture.")

for a in anomalies:
    aid = a["id"]
    atype = a.get("code") or a.get("type")
    state_badge = pill("✓ Résolue", "green") if a["resolved"] else pill("● Bloquante", "red")
    with st.container(border=True):
        st.markdown(
            f'<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">'
            f'<div><span class="mono" style="font-weight:700;color:#0F172A;margin-right:6px;">{html.escape(str(aid))}</span>'
            f'<strong style="font-size:0.96rem;color:#0F172A;">{html.escape(str(TYPES.get(atype, atype)))}</strong> '
            f'<span class="bx-pill bx-pill-slate mono">{html.escape(str(atype))}</span></div>'
            f'<div>{state_badge}</div></div>'
            f'<div style="margin-top:0.5rem;font-size:0.9rem;color:#334155;">{html.escape(str(a["message"]))}</div>',
            unsafe_allow_html=True,
        )

        if a["resolved"]:
            resolver = html.escape(str(a.get("resolved_by") or ""))
            st.markdown(
                f'<div style="margin-top:0.6rem;padding:0.65rem 0.85rem;background:#F0FDF4;border:1px solid #BBF7D0;'
                f'border-radius:8px;font-size:0.86rem;color:#166534;">'
                f'<strong>Justification enregistrée</strong> ({resolver}) : {html.escape(str(a["resolution"]))}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
            just = st.text_area(
                "Justification (obligatoire)",
                key=f"just_{aid}",
                height=85,
                placeholder="Ex : la cliente a refusé la robe L (taille trop petite), seule la robe M est facturée.",
            )
            if st.button("Lever l'anomalie", key=f"resolve_{aid}", type="primary"):
                try:
                    api_client.resolve_anomaly(dossier_id, aid, user, just)
                    st.rerun()
                except ApiError as e:
                    st.error(f"{e.status} : {e.message}")
