"""Invoice page: issued invoice with separate document and financial statuses, and balance."""
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
    """Format an integer amount like '27 553 FCFA'."""
    return f"{n:,}".replace(",", " ") + " FCFA"


st.title("Facture")

dossier_id = st.session_state.get("dossier_id")
if not dossier_id:
    st.info("Aucun dossier ouvert. Crée-en un depuis la page Chat.")
    st.stop()

try:
    dossier = api_client.get_dossier(dossier_id)
except ApiError as e:
    st.error(e.message)
    st.stop()

number = dossier["invoice_number"]
if not number:
    st.info("Cette facture n'a pas encore de numéro : elle est attribuée à la validation par le gérant.")
    st.write(f"Statut actuel du dossier : **{DOC_LABELS.get(dossier['doc_status'], dossier['doc_status'])}**")
    st.stop()

try:
    invoice = api_client.get_invoice(dossier_id)
    balance = api_client.get_balance(number)
except ApiError as e:
    st.error(e.message)
    st.stop()

# Header: number and the two independent statuses
c1, c2, c3 = st.columns(3)
c1.metric("N° de facture", number)
c2.metric("Statut documentaire", DOC_LABELS.get(dossier["doc_status"], dossier["doc_status"]))
c3.metric("Statut financier", FIN_LABELS.get(dossier["financial_status"], dossier["financial_status"]))

# Lines
st.subheader("Lignes")
st.dataframe(
    [
        {
            "Article": l["label"],
            "Qté": l["qty"],
            "Prix unitaire": fcfa(l["unit"]),
            "Montant": fcfa(l["amount"]),
        }
        for l in invoice["lines"]
    ],
    hide_index=True,
    use_container_width=True,
)

# Totals
t = invoice["totals"]
st.subheader("Totaux")
rows = [
    ("Sous-total", t["subtotal"]),
    (t["discount_label"], -t["discount"]),
    ("Base après remise", t["base_after_discount"]),
    ("Livraison", t["delivery"]),
    ("Base HT", t["base_ht"]),
    ("TVA", t["vat"]),
]
for label, amount in rows:
    a, b = st.columns([3, 1])
    a.write(label)
    b.write(("\u2212 " + fcfa(-amount)) if amount < 0 else fcfa(amount))
st.divider()
a, b = st.columns([3, 1])
a.markdown("**Total TTC**")
b.markdown(f"**{fcfa(t['total_ttc'])}**")

# Balance
st.subheader("Solde")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total TTC", fcfa(balance["total_ttc"]))
m2.metric("Avoirs", fcfa(balance["credits"]))
m3.metric("Payé", fcfa(balance["paid"]))
m4.metric("Reste à payer", fcfa(balance["balance"]))
st.caption("Les paiements et avoirs sont enregistrés côté API. L'interface affiche seulement le solde calculé.")