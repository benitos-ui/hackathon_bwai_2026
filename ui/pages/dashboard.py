"""Dashboard page: overview of dossiers, invoices, anomalies, outbox, and audit integrity."""
import streamlit as st

from ui import api_client
from ui.api_client import ApiError

st.title("Tableau de bord")
st.caption("Vue d'ensemble temps réel fournie par l'API FastAPI.")


def fcfa(n):
    return f"{int(n):,}".replace(",", " ") + " FCFA"


try:
    dash = api_client.get_dashboard()
    dossiers = api_client.list_dossiers()
except ApiError as e:
    st.error(e.message)
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Dossiers", dash["dossiers_total"])
c2.metric("Anomalies ouvertes", dash["open_anomalies"])
c3.metric("Factures validées", dash["invoices_count"])
c4.metric("Total facturé TTC", fcfa(dash["total_invoiced_ttc"]))

c5, c6, c7, c8 = st.columns(4)
c5.metric("Encaissé (simulé)", fcfa(dash["total_paid"]))
c6.metric("Avoirs", fcfa(dash["total_credits"]))
c7.metric("File hors-ligne", dash["pending_outbox"])
c8.metric("Chaîne d'audit", "Intègre" if dash["audit_valid"] else "Altérée")

st.subheader("Dossiers")
if not dossiers:
    st.info("Aucun dossier pour l'instant. Va sur la page Chat pour importer un fil WhatsApp.")
else:
    for d in dossiers:
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
            col1.markdown(f"**{d['dossier_id']}** ({d.get('client_name') or 'Client inconnu'})")
            col2.write(f"Doc : **{d['doc_status']}** · Fin : **{d['financial_status']}**")
            col3.write(
                f"Facture : **{d['invoice_number'] or 'À attribuer'}** · "
                f"{fcfa(d.get('total_ttc', 0))}"
            )
            if col4.button("Ouvrir", key=f"open_{d['dossier_id']}", use_container_width=True):
                st.session_state["dossier_id"] = d["dossier_id"]
                st.toast(f"Dossier {d['dossier_id']} sélectionné")
                st.rerun()
