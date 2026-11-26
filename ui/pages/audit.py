"""Audit page: append-only log of every action taken on the dossier + hash chain verification."""
import csv
import io

import streamlit as st

from ui import api_client
from ui.api_client import ApiError

ACTIONS = {
    "IMPORT": "Import du fil",
    "FIELD_CONFIRMED": "Champ confirmé",
    "FIELD_CORRECTED": "Champ corrigé",
    "ANOMALY_RESOLVED": "Anomalie résolue",
    "INVOICE_VALIDATED": "Facture validée",
    "VALIDER_FACTURE": "Facture validée",
    "INVOICE_EMITTED": "Facture émise (simulé)",
    "EMISSION_QUEUED_OFFLINE": "Émission en file hors-ligne",
    "PAYMENT_ADDED": "Règlement confirmé",
    "PAYMENT_REJECTED": "Règlement rejeté",
    "CREDIT_CREATED": "Avoir créé",
    "REFUND_ADDED": "Remboursement enregistré",
    "DOSSIER_CANCELLED": "Dossier annulé",
}

st.title("Audit")
st.caption("Journal des actions en ajout seul, chaîné par empreintes SHA-256.")

col_v, _ = st.columns([1, 2])
with col_v:
    if st.button("Vérifier l'intégrité de la chaîne d'audit", type="primary"):
        try:
            check = api_client.verify_audit()
            if check["valid"]:
                st.success(f"Chaîne d'audit intègre ({check['entries']} entrée(s) vérifiée(s)).")
            else:
                st.error(f"ALTÉRATION DÉTECTÉE à l'entrée #{check['broken_at']} !")
        except ApiError as e:
            st.error(e.message)

dossier_id = st.session_state.get("dossier_id")
scope = st.radio(
    "Périmètre",
    ["Dossier actif", "Tout le journal"],
    horizontal=True,
    index=0 if dossier_id else 1,
)

try:
    entries = api_client.get_audit(dossier_id if scope == "Dossier actif" else None)
except ApiError as e:
    st.error(e.message)
    st.stop()

if scope == "Dossier actif" and dossier_id:
    st.markdown(f"Dossier **{dossier_id}** · {len(entries)} entrée(s)")
else:
    st.markdown(f"Journal global · {len(entries)} entrée(s)")

if not entries:
    st.info("Aucune action enregistrée.")
    st.stop()

present = sorted({e["action"] for e in entries})
chosen = st.multiselect(
    "Filtrer par action",
    options=present,
    default=present,
    format_func=lambda a: ACTIONS.get(a, a),
)
shown = [e for e in entries if e["action"] in chosen]

st.dataframe(
    [
        {
            "N°": e["n"],
            "Horodatage": (e.get("timestamp") or "")[:19].replace("T", " "),
            "Action": ACTIONS.get(e["action"], e["action"]),
            "Utilisateur": e["user"],
            "Objet": e.get("object", ""),
            "Détail": e["detail"],
        }
        for e in shown
    ],
    hide_index=True,
    use_container_width=True,
)

buf = io.StringIO()
writer = csv.writer(buf)
writer.writerow(["n", "timestamp", "action", "user", "object", "detail"])
for e in shown:
    writer.writerow([e["n"], e.get("timestamp", ""), e["action"], e["user"], e.get("object", ""), e["detail"]])

st.download_button(
    "Exporter en CSV",
    data=buf.getvalue().encode("utf-8-sig"),
    file_name=f"audit_{dossier_id or 'global'}.csv",
    mime="text/csv",
)
