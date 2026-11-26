"""Draft page: A4 invoice preview, PDF export, blockers checklist, 4-eyes validation."""
import html

import streamlit as st

from ui import api_client
from ui.api_client import ApiError
from ui.export_doc import render_pdf_bytes, render_word_bytes
from ui.styles import (
    fcfa,
    inject_styles,
    page_header,
    pill,
    render_invoice_sheet,
    render_kpi_grid,
    role_pill,
    status_pill,
)

inject_styles()

DOC_LABELS = {
    "BROUILLON": "Brouillon",
    "A_REVOIR": "À revoir",
    "PRET_A_VALIDER": "Prêt à valider",
    "VALIDEE": "Validée",
    "EMISE": "Émise",
    "ANNULE": "Annulé",
}

flash = st.session_state.pop("flash", None)
if flash:
    st.success(flash)

dossier_id = st.session_state.get("dossier_id")
if not dossier_id:
    page_header("Brouillon & Validation", "Aperçu A4 de la facture et validation selon le principe des 4 yeux.")
    st.info("Aucun dossier ouvert. Crée-en un depuis la page **Chat & Import**.")
    st.stop()

user = st.session_state["user"]
role = st.session_state["role"]

try:
    dossier = api_client.get_dossier(dossier_id)
    invoice = api_client.get_invoice(dossier_id)
    anomalies = api_client.get_anomalies(dossier_id)
    fields = api_client.get_extractions(dossier_id)
except ApiError as e:
    page_header("Brouillon & Validation", f"Dossier {dossier_id}")
    st.error(e.message)
    st.stop()

status = dossier["doc_status"]
number = dossier["invoice_number"] or "À attribuer"

page_header(
    "Brouillon & Validation",
    "Aperçu de la facture et validation gérant (principe des 4 yeux).",
    right_html=pill(dossier_id, "slate") + status_pill(status) + pill(f"v{dossier.get('version', 1)}", "slate"),
)

render_kpi_grid([
    {"label": "Statut documentaire", "value": DOC_LABELS.get(status, status), "sub": "Cycle de vie dossier", "icon_key": "doc", "tone": "blue"},
    {"label": "N° de facture", "value": number, "sub": "Attribué à la validation", "icon_key": "shield", "tone": "slate"},
    {"label": "Initiateur", "value": dossier.get("initiator") or "Non défini", "sub": "Séparation des rôles", "icon_key": "user", "tone": "purple"},
    {"label": "Total TTC calculé", "value": fcfa(invoice["totals"].get("total_ttc", 0)), "sub": "Moteur déterministe FCFA", "icon_key": "coin", "tone": "gold"},
])

# A4 Invoice Sheet Preview
render_invoice_sheet(
    number=number,
    doc_status=status,
    lines=invoice.get("lines", []),
    totals=invoice.get("totals", {}),
    dossier_id=dossier_id,
    client_name=dossier.get("client_name") or "",
    initiator=dossier.get("initiator") or "",
)

pdf_bytes = None
if api_client.API_MODE == "live" and invoice.get("calculation"):
    try:
        pdf_bytes = api_client.get_draft_pdf(dossier_id)
    except ApiError:
        pdf_bytes = None
if pdf_bytes is None:
    pdf_bytes = render_pdf_bytes(
        number=number,
        doc_status=status,
        lines=invoice.get("lines", []),
        totals=invoice.get("totals", {}),
        dossier_id=dossier_id,
        client_name=dossier.get("client_name") or "",
        initiator=dossier.get("initiator") or "",
    )

word_bytes = render_word_bytes(
    number=number,
    doc_status=status,
    lines=invoice.get("lines", []),
    totals=invoice.get("totals", {}),
    dossier_id=dossier_id,
    client_name=dossier.get("client_name") or "",
    initiator=dossier.get("initiator") or "",
)

dl1, dl2, _ = st.columns([1.2, 1.2, 1.6])
with dl1:
    st.download_button(
        "Télécharger le brouillon (PDF)",
        data=pdf_bytes,
        file_name=f"brouillon_{dossier_id}.pdf",
        mime="application/pdf",
        type="primary",
        use_container_width=True,
    )
with dl2:
    st.download_button(
        "Télécharger le brouillon (Word .doc)",
        data=word_bytes,
        file_name=f"brouillon_{dossier_id}.doc",
        mime="application/msword",
        use_container_width=True,
    )

open_anoms = [x for x in anomalies if not x["resolved"]]
pending = [f for f in fields if not f.get("confirmed") and f.get("status") != "missing"]

col_chk, col_val = st.columns([1, 1.2], gap="large")

with col_chk:
    with st.container(border=True):
        st.markdown("**Contrôles avant validation**")
        anom_html = (
            pill(f"✗ {len(open_anoms)} anomalie(s) ouverte(s)", "red")
            + " <span style='font-size:0.84rem;color:#64748B;'>Voir l'onglet Anomalies</span>"
            if open_anoms
            else pill("✓ Aucune anomalie ouverte", "green")
        )
        field_html = (
            pill(f"✗ {len(pending)} champ(s) non confirmé(s)", "red")
            + " <span style='font-size:0.84rem;color:#64748B;'>Voir l'onglet Revue IA</span>"
            if pending
            else pill("✓ Tous les champs requis confirmés", "green")
        )
        st.markdown(
            f'<div style="display:flex;flex-direction:column;gap:10px;margin-top:8px;">'
            f'<div>{anom_html}</div><div>{field_html}</div></div>',
            unsafe_allow_html=True,
        )

with col_val:
    with st.container(border=True):
        st.markdown("**Validation gérant (principe des 4 yeux)**")
        st.markdown(
            f'<div style="font-size:0.84rem;color:#475569;margin-bottom:0.75rem;">'
            f'Connecté : <span class="mono" style="font-weight:600;color:#0F172A;">{html.escape(user)}</span> '
            f'{role_pill(role)} &nbsp;·&nbsp; Initiateur : '
            f'<span class="mono" style="font-weight:600;color:#0F172A;">{html.escape(str(dossier.get("initiator") or "Non défini"))}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if status in ("VALIDEE", "EMISE"):
            st.success(f"Facture **{number}** validée, figée et protégée contre toute modification.")
        else:
            b1, b2 = st.columns(2)
            with b1:
                if st.button("Valider la facture", type="primary", use_container_width=True):
                    try:
                        api_client.validate_invoice(dossier_id, user, role, version=dossier.get("version"))
                        st.session_state["flash"] = "Facture validée et figée."
                        st.rerun()
                    except ApiError as e:
                        st.error(f"{e.status} : {e.message}")
            with b2:
                if api_client.API_MODE == "live":
                    if st.button("Simuler 20 validations (E8)", use_container_width=True):
                        try:
                            res = api_client.simulate_concurrency(dossier_id, user, role, n_requests=20)
                            st.info(
                                f"20 requêtes simultanées -> **{res['invoices_in_db']} facture** en base, "
                                f"numéro(s) : `{res['unique_numbers']}`"
                            )
                            if res["invoices_in_db"] == 1:
                                st.rerun()
                        except ApiError as e:
                            st.error(f"{e.status} : {e.message}")
