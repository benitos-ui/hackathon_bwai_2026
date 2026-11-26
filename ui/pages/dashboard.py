"""Dashboard page: Bento KPI grid with SVG sparklines & recent dossiers overview."""
import html

import streamlit as st

from ui import api_client
from ui.api_client import ApiError
from ui.styles import fcfa, inject_styles, page_header, pill, render_kpi_grid, status_pill

inject_styles()

try:
    dash = api_client.get_dashboard()
    dossiers = api_client.list_dossiers()
except ApiError as e:
    page_header("Tableau de bord", "Pilotage temps réel des dossiers, contrôles et factures.", section="Tableau de bord")
    st.error(e.message)
    st.stop()

audit_badge = (
    pill("Audit intègre", "green")
    if dash.get("audit_valid", True)
    else pill("Audit altéré", "red")
)
page_header(
    "Tableau de bord",
    "Vue d'ensemble des dossiers, factures et paiements.",
    right_html=audit_badge + pill(f"{dash.get('dossiers_total', 0)} dossier(s)", "blue"),
)

raw_by_status = dash.get("dossiers_by_status") or {}
by_status = {api_client._norm_code(k): v for k, v in raw_by_status.items()}
a_revoir = by_status.get("A_REVOIR", 0)
prets = by_status.get("PRET_A_VALIDER", 0)

render_kpi_grid([
    {
        "label": "Dossiers à revoir",
        "value": a_revoir,
        "sub": f"{dash.get('open_anomalies', 0)} anomalie(s) ouverte(s)",
        "icon_key": "alert",
        "tone": "amber" if (a_revoir or dash.get("open_anomalies", 0)) else "green",
        "badge": "Action requise" if a_revoir else "RAS",
    },
    {
        "label": "Prêts à valider",
        "value": prets,
        "sub": "Contrôle 4 yeux gérant",
        "icon_key": "check",
        "tone": "blue",
        "badge": "En attente" if prets else "À jour",
    },
    {
        "label": "Factures validées",
        "value": dash.get("invoices_count", 0),
        "sub": "Figées & numérotées",
        "icon_key": "doc",
        "tone": "green",
        "badge": "Immuables",
    },
    {
        "label": "Chiffre d'affaires TTC",
        "value": fcfa(dash.get("total_invoiced_ttc", 0)),
        "sub": "Calcul déterministe FCFA",
        "icon_key": "coin",
        "tone": "gold",
        "badge": "Simulé",
    },
])

render_kpi_grid([
    {
        "label": "Encaissé simulé",
        "value": fcfa(dash.get("total_paid", 0)),
        "sub": "Cumul règlements confirmés",
        "icon_key": "coin",
        "tone": "green",
    },
    {
        "label": "Avoirs validés",
        "value": fcfa(dash.get("total_credits", 0)),
        "sub": "Corrections post-émission",
        "icon_key": "sync",
        "tone": "purple",
    },
    {
        "label": "File hors-ligne",
        "value": dash.get("pending_outbox", 0),
        "sub": "Envois en attente de sync",
        "icon_key": "sync",
        "tone": "amber" if dash.get("pending_outbox", 0) else "slate",
    },
    {
        "label": "Intégrité audit",
        "value": "Intègre" if dash.get("audit_valid", True) else "Altérée",
        "sub": f"{dash.get('audit_entries', 0)} entrée(s) SHA-256",
        "icon_key": "shield",
        "tone": "green" if dash.get("audit_valid", True) else "red",
    },
])

st.markdown("### Dossiers récents")
if not dossiers:
    with st.container(border=True):
        st.info("Aucun dossier pour l'instant. Ouvre **Chat & Import** pour importer un fil WhatsApp (ex. Awa Dossou) ou composer une conversation simulée.")
else:
    for d in dossiers:
        did = d["dossier_id"]
        is_active = did == st.session_state.get("dossier_id")
        client_label = html.escape(str(d.get("client_name") or "Client inconnu"))
        inv_num = html.escape(str(d.get("invoice_number") or "À attribuer"))
        active_tag = pill("Actif", "gold") if is_active else ""

        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([2.4, 2.2, 2.1, 1])
            with col1:
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">'
                    f'<span class="mono" style="font-weight:700;font-size:0.95rem;color:#0F172A;">{html.escape(did)}</span>'
                    f'{active_tag}</div>'
                    f'<div style="font-size:0.84rem;color:#475569;margin-top:3px;">{client_label}</div>',
                    unsafe_allow_html=True,
                )
            with col2:
                st.markdown(
                    '<div style="font-size:0.72rem;color:#64748B;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px;">Statuts</div>'
                    f'{status_pill(d.get("doc_status", ""))} {status_pill(d.get("financial_status", ""))}',
                    unsafe_allow_html=True,
                )
            with col3:
                st.markdown(
                    f'<div style="font-size:0.72rem;color:#64748B;text-transform:uppercase;letter-spacing:0.05em;">'
                    f'Facture · <span class="mono" style="color:#0F172A;">{inv_num}</span></div>'
                    f'<div class="tabular" style="font-weight:700;font-size:1rem;color:#0F172A;margin-top:3px;">'
                    f'{html.escape(fcfa(d.get("total_ttc", 0)))}</div>',
                    unsafe_allow_html=True,
                )
            with col4:
                if st.button(
                    "Ouvrir",
                    key=f"open_{did}",
                    type="primary" if is_active else "secondary",
                    use_container_width=True,
                ):
                    st.session_state["dossier_id"] = did
                    st.toast(f"Dossier {did} sélectionné")
                    st.rerun()
