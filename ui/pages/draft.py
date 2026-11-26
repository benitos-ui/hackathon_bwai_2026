"""Draft page: invoice preview, PDF export, blockers checklist, validation by the manager."""
import streamlit as st

from ui import api_client
from ui.api_client import ApiError

DOC_LABELS = {
    "BROUILLON": "Brouillon",
    "A_REVOIR": "À revoir",
    "PRET_A_VALIDER": "Prêt à valider",
    "VALIDEE": "Validée",
    "EMISE": "Émise",
    "ANNULE": "Annulé",
}


def fcfa(n):
    return f"{int(n):,}".replace(",", " ") + " FCFA"


st.title("Brouillon et validation")

flash = st.session_state.pop("flash", None)
if flash:
    st.success(flash)

dossier_id = st.session_state.get("dossier_id")
if not dossier_id:
    st.info("Aucun dossier ouvert. Crée-en un depuis la page Chat.")
    st.stop()

user = st.session_state["user"]
role = st.session_state["role"]

try:
    dossier = api_client.get_dossier(dossier_id)
    invoice = api_client.get_invoice(dossier_id)
    anomalies = api_client.get_anomalies(dossier_id)
    fields = api_client.get_extractions(dossier_id)
except ApiError as e:
    st.error(e.message)
    st.stop()

status = dossier["doc_status"]
number = dossier["invoice_number"] or "À attribuer"

c1, c2, c3, c4 = st.columns(4)
c1.metric("Statut", DOC_LABELS.get(status, status))
c2.metric("N° de facture", number)
c3.metric("Initiateur", dossier["initiator"] or "Non défini")
c4.metric("Version", dossier.get("version", 1))

st.subheader("Lignes facturées")
st.caption("Facturation sur les quantités livrées et acceptées (prix officiels du catalogue).")
if invoice["lines"]:
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
else:
    st.info("Aucune ligne facturable pour le moment.")

t = invoice["totals"]
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

if api_client.API_MODE == "live" and invoice.get("calculation"):
    try:
        pdf_bytes = api_client.get_draft_pdf(dossier_id)
        st.download_button(
            "Télécharger le brouillon PDF",
            data=pdf_bytes,
            file_name=f"brouillon_{dossier_id}.pdf",
            mime="application/pdf",
        )
    except ApiError as e:
        st.caption(f"PDF indisponible : {e.message}")

st.subheader("Avant validation")
open_anoms = [x for x in anomalies if not x["resolved"]]
pending = [f for f in fields if not f.get("confirmed") and f.get("status") != "missing"]

if open_anoms:
    st.markdown(f":red[:material/cancel:] {len(open_anoms)} anomalie(s) ouverte(s), voir la page Anomalies")
else:
    st.markdown(":green[:material/check_circle:] Aucune anomalie ouverte")

if pending:
    st.markdown(f":red[:material/cancel:] {len(pending)} champ(s) requis non confirmé(s), voir la page Revue")
else:
    st.markdown(":green[:material/check_circle:] Tous les champs requis sont confirmés")

st.subheader("Validation")
st.caption(
    "Principe des quatre yeux : le gérant qui valide doit être différent de la personne "
    "qui a initié le dossier."
)
st.write(f"Connecté : **{user}** (`{role}`) · initiateur du dossier : **{dossier['initiator'] or 'Non défini'}**")

if status in ("VALIDEE", "EMISE"):
    st.success(f"Facture {number} validée et figée.")
else:
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        if st.button("Valider la facture", type="primary", use_container_width=True):
            try:
                api_client.validate_invoice(dossier_id, user, role, version=dossier.get("version"))
                st.session_state["flash"] = "Facture validée et figée."
                st.rerun()
            except ApiError as e:
                st.error(f"{e.status} : {e.message}")
    with col_v2:
        if api_client.API_MODE == "live":
            if st.button("Simuler 20 validations simultanées (E8)", use_container_width=True):
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
