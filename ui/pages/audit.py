"""Audit page: vertical SHA-256 hash-chained timeline + integrity verification & CSV export."""
import csv
import io

import streamlit as st

from ui import api_client
from ui.api_client import ApiError
from ui.styles import inject_styles, page_header, pill, render_audit_timeline

inject_styles()

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

dossier_id = st.session_state.get("dossier_id")

page_header(
    "Journal d'audit",
    "Historique en ajout seul, chaîné par empreintes SHA-256.",
    right_html=pill(f"Dossier : {dossier_id}", "blue") if dossier_id else pill("Vue globale", "slate"),
)

with st.container(border=True):
    col_v, col_scope = st.columns([1.3, 1.7])
    with col_v:
        if st.button("Vérifier l'intégrité de la chaîne d'audit", type="primary", use_container_width=True):
            try:
                check = api_client.verify_audit()
                if check["valid"]:
                    st.success(f"Chaîne d'audit intègre ({check['entries']} entrée(s) vérifiée(s)).")
                else:
                    st.error(f"ALTÉRATION DÉTECTÉE à l'entrée #{check['broken_at']} !")
            except ApiError as e:
                st.error(e.message)
    with col_scope:
        scope = st.radio(
            "Périmètre du journal",
            ["Dossier actif", "Tout le journal"],
            horizontal=True,
            index=0 if dossier_id else 1,
        )

try:
    entries = api_client.get_audit(dossier_id if scope == "Dossier actif" else None)
except ApiError as e:
    st.error(e.message)
    st.stop()

if not entries:
    st.info("Aucune action enregistrée dans ce périmètre.")
    st.stop()

present = sorted({e["action"] for e in entries})
f_col, dl_col = st.columns([3.2, 1])
with f_col:
    chosen = st.multiselect(
        "Filtrer par type d'événement",
        options=present,
        default=present,
        format_func=lambda a: ACTIONS.get(a, a),
    )
shown = [e for e in entries if e["action"] in chosen]

buf = io.StringIO()
writer = csv.writer(buf)
writer.writerow(["n", "timestamp", "action", "user", "object", "detail", "hash"])
for e in shown:
    writer.writerow([
        e["n"],
        e.get("timestamp", ""),
        e["action"],
        e["user"],
        e.get("object", ""),
        e["detail"],
        e.get("hash", ""),
    ])

with dl_col:
    st.write("")
    st.write("")
    st.download_button(
        "Exporter CSV",
        data=buf.getvalue().encode("utf-8-sig"),
        file_name=f"audit_{dossier_id or 'global'}.csv",
        mime="text/csv",
        use_container_width=True,
    )

scope_label = f"Dossier {dossier_id}" if (scope == "Dossier actif" and dossier_id) else "Journal global"
st.markdown(
    f'<div style="display:flex;align-items:center;gap:8px;margin:0.4rem 0 0.25rem;">'
    f'<strong style="color:#0F172A;">Timeline des événements</strong>'
    f'{pill(scope_label, "slate")} {pill(f"{len(shown)} entrée(s)", "blue")}</div>',
    unsafe_allow_html=True,
)

# Vertical Enterprise Timeline with monospace SHA-256 hashes
render_audit_timeline(shown, ACTIONS)

with st.expander("Vue tabulaire brute"):
    st.dataframe(
        [
            {
                "N°": e["n"],
                "Horodatage": (e.get("timestamp") or "")[:19].replace("T", " "),
                "Action": ACTIONS.get(e["action"], e["action"]),
                "Utilisateur": e["user"],
                "Objet": e.get("object", ""),
                "Détail": e["detail"],
                "Empreinte SHA-256": (e.get("hash") or "")[:16],
            }
            for e in shown
        ],
        hide_index=True,
        use_container_width=True,
    )
