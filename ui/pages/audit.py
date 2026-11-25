"""Audit page: append-only log of every action taken on the dossier."""
import csv
import io

import streamlit as st

from ui import api_client
from ui.api_client import ApiError

# Readable labels; unknown actions fall back to the raw code
ACTIONS = {
    "IMPORT": "Import du fil",
    "FIELD_CONFIRMED": "Champ confirmé",
    "FIELD_CORRECTED": "Champ corrigé",
    "ANOMALY_RESOLVED": "Anomalie résolue",
    "INVOICE_VALIDATED": "Facture validée",
}

st.title("Audit")
st.caption("Journal des actions, en lecture seule. Chaque décision humaine y est tracée.")

dossier_id = st.session_state.get("dossier_id")
if not dossier_id:
    st.info("Aucun dossier ouvert. Crée-en un depuis la page Chat.")
    st.stop()

try:
    entries = api_client.get_audit(dossier_id)
except ApiError as e:
    st.error(e.message)
    st.stop()

st.markdown(f"Dossier **{dossier_id}** · {len(entries)} entrée(s)")

if not entries:
    st.info("Aucune action enregistrée pour ce dossier.")
    st.stop()

# Filter by action type
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
            "Action": ACTIONS.get(e["action"], e["action"]),
            "Utilisateur": e["user"],
            "Détail": e["detail"],
        }
        for e in shown
    ],
    hide_index=True,
    use_container_width=True,
)

# CSV export of the filtered log
buf = io.StringIO()
writer = csv.writer(buf)
writer.writerow(["n", "action", "user", "detail"])
for e in shown:
    writer.writerow([e["n"], e["action"], e["user"], e["detail"]])

st.download_button(
    "Exporter en CSV",
    data=buf.getvalue().encode("utf-8-sig"),
    file_name=f"audit_{dossier_id}.csv",
    mime="text/csv",
)