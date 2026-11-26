"""Invoice page: frozen A4 invoice, PDF export, simulated emission (offline queue), payments, credits."""
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
    status_pill,
)

inject_styles()

DOC_LABELS = {
    "BROUILLON": "Brouillon",
    "A_REVOIR": "À revoir",
    "PRET_A_VALIDER": "Prêt à valider",
    "VALIDEE": "Validée",
    "EMISE": "Émise",
}
FIN_LABELS = {
    "NON_REGLEE": "Non réglée",
    "PARTIELLEMENT_REGLEE": "Partiellement réglée",
    "REGLEE": "Réglée",
    "TROP_PERCU": "Trop-perçu",
    "REMBOURSEMENT_EN_COURS": "Remboursement en cours",
}

dossier_id = st.session_state.get("dossier_id")
if not dossier_id:
    page_header("Facture & Règlements", "Document figé, émission simulée, règlements et avoirs.")
    st.info("Aucun dossier ouvert. Crée-en un depuis la page **Chat & Import**.")
    st.stop()

user = st.session_state["user"]
role = st.session_state["role"]

try:
    dossier = api_client.get_dossier(dossier_id)
except ApiError as e:
    page_header("Facture & Règlements", f"Dossier {dossier_id}")
    st.error(e.message)
    st.stop()

number = dossier["invoice_number"]
invoice_id = dossier.get("invoice_id") or number
if not number:
    page_header(
        "Facture & Règlements",
        f"Dossier {dossier_id}",
        right_html=status_pill(dossier.get("doc_status", "")),
    )
    st.info("Cette facture n'a pas encore de numéro définitif : il est attribué lors de la validation par le gérant.")
    st.stop()

try:
    detail = api_client.get_invoice_detail(invoice_id)
    balance = api_client.get_balance(invoice_id)
except ApiError as e:
    page_header("Facture & Règlements", f"Facture {number}")
    st.error(e.message)
    st.stop()

page_header(
    f"Facture {number}",
    "Facture définitive figée (immuable) · toute correction postérieure passe par un avoir.",
    right_html=status_pill(dossier.get("doc_status", "")) + status_pill(balance.get("financial_status", "")),
)

# Frozen A4 Invoice Sheet
render_invoice_sheet(
    number=number,
    doc_status=dossier.get("doc_status", "VALIDEE"),
    lines=detail.get("lines", []),
    totals=detail.get("totals", {}),
    dossier_id=dossier_id,
    client_name=dossier.get("client_name") or "",
    initiator=dossier.get("initiator") or "",
    content_hash=detail.get("content_hash") or "",
)

pdf_bytes = None
if api_client.API_MODE == "live" and detail.get("calculation"):
    try:
        pdf_bytes = api_client.get_invoice_pdf(invoice_id)
    except ApiError:
        pdf_bytes = None
if pdf_bytes is None:
    pdf_bytes = render_pdf_bytes(
        number=number,
        doc_status=dossier.get("doc_status", "VALIDEE"),
        lines=detail.get("lines", []),
        totals=detail.get("totals", {}),
        dossier_id=dossier_id,
        client_name=dossier.get("client_name") or "",
        initiator=dossier.get("initiator") or "",
        content_hash=detail.get("content_hash") or "",
    )

word_bytes = render_word_bytes(
    number=number,
    doc_status=dossier.get("doc_status", "VALIDEE"),
    lines=detail.get("lines", []),
    totals=detail.get("totals", {}),
    dossier_id=dossier_id,
    client_name=dossier.get("client_name") or "",
    initiator=dossier.get("initiator") or "",
    content_hash=detail.get("content_hash") or "",
)

col_dl1, col_dl2, col_hash = st.columns([1.2, 1.2, 1.8])
with col_dl1:
    st.download_button(
        f"Télécharger en PDF ({number})",
        data=pdf_bytes,
        file_name=f"{number}.pdf",
        mime="application/pdf",
        type="primary",
        use_container_width=True,
    )
with col_dl2:
    st.download_button(
        f"Télécharger en Word (.doc)",
        data=word_bytes,
        file_name=f"{number}.doc",
        mime="application/msword",
        use_container_width=True,
    )
with col_hash:
    if detail.get("content_hash"):
        st.caption(f"Empreinte SHA-256 figée : `{detail['content_hash']}`")

render_kpi_grid([
    {"label": "Total TTC", "value": fcfa(balance["total_ttc"]), "sub": "Montant facturé figé", "icon_key": "doc", "tone": "gold"},
    {"label": "Avoirs validés", "value": fcfa(balance["credits"]), "sub": "Déduits du net dû", "icon_key": "sync", "tone": "purple"},
    {"label": "Payé confirmé", "value": fcfa(balance["paid"]), "sub": "Règlements simulés", "icon_key": "check", "tone": "green"},
    {
        "label": "Reste à payer",
        "value": fcfa(balance["balance"]),
        "sub": FIN_LABELS.get(balance["financial_status"], balance["financial_status"]),
        "icon_key": "coin",
        "tone": "green" if int(balance["balance"]) == 0 else "amber",
    },
])

col_em, col_pay, col_crd = st.columns(3, gap="medium")

with col_em:
    with st.container(border=True):
        st.markdown("**Émission simulée**")
        channel = st.selectbox("Canal", ["whatsapp", "sms", "email"], key="emit_channel")
        offline = st.checkbox("Mode hors-ligne simulé (E13)", key="emit_offline")
        if st.button("Émettre (simulation)", use_container_width=True):
            try:
                res = api_client.emit_invoice(invoice_id, channel, user, offline=offline)
                st.success(f"Statut file d'envoi : {res['status']} ({channel})")
                st.rerun()
            except ApiError as e:
                st.error(f"{e.status} : {e.message}")
        if st.button("Synchroniser la file hors-ligne", use_container_width=True):
            try:
                res = api_client.sync_outbox(user)
                st.info(f"{res['synced_count']} envoi(s) synchronisé(s) sans doublon.")
                st.rerun()
            except ApiError as e:
                st.error(f"{e.status} : {e.message}")

with col_pay:
    with st.container(border=True):
        st.markdown("**Règlement simulé**")
        default_amt = max(int(balance["balance"]), 0)
        pay_amt = st.number_input("Montant (FCFA)", min_value=0, value=default_amt, step=500, key="pay_amt")
        pay_mode = st.selectbox("Mode", ["espèces", "mobile_money"], key="pay_mode")
        pay_ref = st.text_input("Référence (marquée FICTIF)", value="MOMO-001", key="pay_ref")
        pay_status = st.selectbox("Statut", ["confirme", "rejete"], key="pay_status")
        if st.button("Enregistrer le règlement", type="primary", use_container_width=True):
            try:
                api_client.add_payment(invoice_id, pay_amt, pay_mode, pay_ref, user, status=pay_status)
                st.success("Règlement enregistré.")
                st.rerun()
            except ApiError as e:
                st.error(f"{e.status} : {e.message}")

with col_crd:
    with st.container(border=True):
        st.markdown("**Avoir lié (gérant)**")
        crd_amt = st.number_input("Montant avoir (FCFA)", min_value=0, value=0, step=500, key="crd_amt")
        crd_reason = st.text_input("Motif de l'avoir", placeholder="Retour article défectueux", key="crd_reason")
        if st.button("Créer un avoir", use_container_width=True):
            try:
                api_client.add_credit(invoice_id, crd_amt, crd_reason, user, role)
                st.success("Avoir créé (facture originale intacte).")
                st.rerun()
            except ApiError as e:
                st.error(f"{e.status} : {e.message}")

if detail.get("payments"):
    st.markdown("### Historique des règlements")
    st.dataframe(
        [
            {
                "ID": p["id"],
                "Montant": fcfa(p["amount"]),
                "Mode": p["mode"],
                "Référence": p["reference"],
                "Statut": p["status"],
                "Saisi par": p["entered_by"],
            }
            for p in detail["payments"]
        ],
        hide_index=True,
        use_container_width=True,
    )

if detail.get("credits"):
    st.markdown("### Avoirs liés")
    st.dataframe(
        [
            {
                "Numéro": c.get("number") or c["id"],
                "Montant": fcfa(c["amount"]),
                "Motif": c["reason"],
                "Créé par": c["created_by"],
            }
            for c in detail["credits"]
        ],
        hide_index=True,
        use_container_width=True,
    )
