"""Invoice page: frozen invoice, PDF export, simulated emission (with offline queue), payments, credits, balance."""
import streamlit as st

from ui import api_client
from ui.api_client import ApiError

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


def fcfa(n):
    return f"{int(n):,}".replace(",", " ") + " FCFA"


st.title("Facture")

dossier_id = st.session_state.get("dossier_id")
if not dossier_id:
    st.info("Aucun dossier ouvert. Crée-en un depuis la page Chat.")
    st.stop()

user = st.session_state["user"]
role = st.session_state["role"]

try:
    dossier = api_client.get_dossier(dossier_id)
except ApiError as e:
    st.error(e.message)
    st.stop()

number = dossier["invoice_number"]
invoice_id = dossier.get("invoice_id") or number
if not number:
    st.info("Cette facture n'a pas encore de numéro : elle est attribuée à la validation par le gérant.")
    st.write(f"Statut actuel du dossier : **{DOC_LABELS.get(dossier['doc_status'], dossier['doc_status'])}**")
    st.stop()

try:
    detail = api_client.get_invoice_detail(invoice_id)
    balance = api_client.get_balance(invoice_id)
except ApiError as e:
    st.error(e.message)
    st.stop()

c1, c2, c3 = st.columns(3)
c1.metric("N° de facture", number)
c2.metric("Statut documentaire", DOC_LABELS.get(dossier["doc_status"], dossier["doc_status"]))
c3.metric("Statut financier", FIN_LABELS.get(balance["financial_status"], balance["financial_status"]))

if detail.get("content_hash"):
    st.caption(f"Empreinte SHA-256 figée : `{detail['content_hash']}`")

if api_client.API_MODE == "live" and detail.get("calculation"):
    try:
        pdf_bytes = api_client.get_invoice_pdf(invoice_id)
        st.download_button(
            f"Télécharger la facture PDF ({number})",
            data=pdf_bytes,
            file_name=f"{number}.pdf",
            mime="application/pdf",
        )
    except ApiError as e:
        st.caption(f"PDF indisponible : {e.message}")

st.subheader("Lignes")
st.dataframe(
    [
        {
            "Article": l["label"],
            "Qté": l["qty"],
            "Prix unitaire": fcfa(l["unit"]),
            "Montant": fcfa(l["amount"]),
        }
        for l in detail["lines"]
    ],
    hide_index=True,
    use_container_width=True,
)

t = detail["totals"]
st.subheader("Totaux")
rows = [
    ("Sous-total", t["subtotal"]),
    (t["discount_label"], -t["discount"]),
    ("Base après remise", t["base_after_discount"]),
    ("Livraison", t["delivery"]),
    ("Base HT", t["base_ht"]),
    (f"TVA ({t.get('vat_rate', 18)} %)", t["vat"]),
]
for label, amount in rows:
    a, b = st.columns([3, 1])
    a.write(label)
    b.write(("\u2212 " + fcfa(-amount)) if amount < 0 else fcfa(amount))
st.divider()
a, b = st.columns([3, 1])
a.markdown("**Total TTC**")
b.markdown(f"**{fcfa(t['total_ttc'])}**")

st.subheader("Solde")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total TTC", fcfa(balance["total_ttc"]))
m2.metric("Avoirs", fcfa(balance["credits"]))
m3.metric("Payé (confirmé)", fcfa(balance["paid"]))
m4.metric("Reste à payer", fcfa(balance["balance"]))

st.divider()
col_em, col_pay, col_crd = st.columns(3)

with col_em:
    st.subheader("Émission simulée")
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
    st.subheader("Règlement simulé")
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
    st.subheader("Avoir lié (gérant)")
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
    st.subheader("Historique des règlements")
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
    st.subheader("Avoirs liés")
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
