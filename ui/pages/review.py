"""Review page: legible WhatsApp thread with subtle highlights (left) & compact extraction cards (right)."""
import html

import streamlit as st

from ui import api_client
from ui.api_client import ApiError
from ui.components.chat import render_chat
from ui.styles import inject_styles, page_header, pill, status_pill

inject_styles()

LABELS = {
    "client": "Client",
    "product_1": "Produit 1",
    "product_2": "Produit 2",
    "quantity_ordered": "Quantité commandée",
    "zone": "Zone de livraison",
    "payment_mode": "Mode de paiement",
    "paiement": "Mode de paiement",
    "delivered": "Livré",
    "refusal": "Refus",
    "refus": "Refus",
    "promo_code": "Code promo",
    "code_promo": "Code promo",
    "date_livraison": "Date de livraison",
}
STATUS = {
    "extracted": "Extrait",
    "needs_review": "À relire",
    "missing": "Manquant",
    "ambiguous": "Ambigu",
}
CONF_TONE = {"vert": "green", "orange": "amber", "rouge": "red"}


def _label(name: str) -> str:
    if name in LABELS:
        return LABELS[name]
    if name.startswith("produit_ambigu_"):
        return f"Produit ambigu #{name.split('_')[-1]}"
    if name.startswith("produit_"):
        return f"Produit #{name.split('_')[-1]}"
    if name.startswith("quantite_commandee_"):
        return f"Quantité commandée #{name.split('_')[-1]}"
    if name.startswith("quantite_livree_"):
        return f"Quantité livrée #{name.split('_')[-1]}"
    if name.startswith("variante_"):
        return f"Variante #{name.split('_')[-1]}"
    if name.startswith("prix_cite_"):
        return f"Prix cité #{name.split('_')[-1]}"
    if name.startswith("refus_"):
        return f"Refus #{name.split('_')[-1]}"
    return name


dossier_id = st.session_state.get("dossier_id")
if not dossier_id:
    page_header("Revue d'extraction", "Vérification et confirmation des champs extraits.")
    st.info("Aucun dossier ouvert. Importe un fil depuis **Chat & Import**.")
    st.stop()

user = st.session_state["user"]

try:
    dossier = api_client.get_dossier(dossier_id)
    messages = api_client.get_messages(dossier_id)
    fields = api_client.get_extractions(dossier_id)
    anomalies = api_client.get_anomalies(dossier_id)
except ApiError as e:
    page_header("Revue d'extraction", f"Dossier {dossier_id}")
    st.error(e.message)
    st.stop()

if not fields:
    page_header("Revue d'extraction", f"Dossier {dossier_id}")
    st.warning("Aucun champ extrait pour ce dossier.")
    st.stop()

required_fields = [f for f in fields if f.get("status") != "missing"]
done = sum(1 for f in required_fields if f.get("confirmed"))
total_req = max(len(required_fields), 1)
open_anoms = [a for a in anomalies if not a.get("resolved")]
model_ver = next((f.get("model_version") for f in fields if f.get("model_version")), "")

header_badges = (
    pill(dossier_id, "slate")
    + status_pill(dossier.get("doc_status", ""))
    + (pill(model_ver, "blue") if model_ver else "")
    + (pill(f"{len(open_anoms)} anomalie(s)", "red") if open_anoms else "")
)

page_header(
    "Revue d'extraction",
    "Vérifie les champs extraits et confirme avant validation.",
    right_html=header_badges,
)

if open_anoms:
    codes = ", ".join(str(a.get("code") or a.get("type") or a["id"]) for a in open_anoms)
    st.warning(f"{len(open_anoms)} anomalie(s) ouverte(s) (`{codes}`) — à traiter dans l'onglet **Anomalies**.")

p_col, btn_col = st.columns([3, 1.35])
with p_col:
    st.progress(done / total_req, text=f"{done} / {len(required_fields)} champ(s) confirmé(s)")
with btn_col:
    if done < len(required_fields) and dossier["doc_status"] not in ("VALIDEE", "EMISE"):
        if st.button("Confirmer tous les champs", type="primary", use_container_width=True):
            try:
                api_client.confirm_all_fields(dossier_id, user)
                st.rerun()
            except ApiError as e:
                st.error(f"{e.status} : {e.message}")

st.session_state.setdefault("selected_field", fields[0]["field"])
selected = next((f for f in fields if f["field"] == st.session_state["selected_field"]), fields[0])

all_highlights = []
for f in fields:
    src_f = f.get("source") or {}
    if src_f.get("message_id") and src_f.get("start") is not None and src_f.get("end") is not None:
        cpct = round(float(f.get("confidence", 0.0)) * 100)
        all_highlights.append({
            "message_id": src_f["message_id"],
            "start": src_f["start"],
            "end": src_f["end"],
            "couleur": f.get("couleur") or "orange",
            "label": f"{_label(f['field'])} ({cpct} %)",
        })

left, right = st.columns([1.05, 1], gap="large")

with left:
    st.markdown(
        '<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.45rem;flex-wrap:wrap;gap:6px;">'
        '<strong style="font-size:0.98rem;color:#0F172A;">Conversation source</strong>'
        '<span>'
        + pill("≥ 90%", "green") + " "
        + pill("60–89%", "amber") + " "
        + pill("< 60%", "red")
        + '</span></div>',
        unsafe_allow_html=True,
    )
    src = selected.get("source") or {}
    has_source = bool(src.get("message_id"))
    active_hl = (
        {
            "message_id": src["message_id"],
            "start": src.get("start"),
            "end": src.get("end"),
            "couleur": selected.get("couleur") or "orange",
            "label": _label(selected["field"]),
        }
        if has_source
        else None
    )
    client_title = dossier.get("client_name") or "Conversation WhatsApp"
    render_chat(
        messages,
        highlight=active_hl,
        all_highlights=all_highlights,
        height=550,
        title=client_title,
        subtitle=f"Champ sélectionné : {_label(selected['field'])}",
    )
    if has_source and src.get("text"):
        st.caption(f"Source ({src['message_id']}) : « {src['text']} »")

with right:
    st.markdown(
        f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:0.45rem;">'
        f'<strong style="font-size:0.98rem;color:#0F172A;">Champs extraits</strong>'
        f'{pill(f"{len(fields)}", "slate")}</div>',
        unsafe_allow_html=True,
    )
    for f in fields:
        name = f["field"]
        confirmed = f.get("confirmed", False)
        value = f["value"] if f["value"] is not None else "(à renseigner)"
        couleur = f.get("couleur") if f.get("couleur") in ("vert", "orange", "rouge") else "orange"
        conf_pct = round(float(f.get("confidence", 0.0)) * 100)
        is_sel = name == st.session_state["selected_field"]
        tone = CONF_TONE.get(couleur, "slate")

        ref_html = (
            f' <span class="bx-pill bx-pill-slate mono">{html.escape(str(f["ref"]))}</span>'
            if f.get("ref")
            else ""
        )
        raw_line = (
            f'<div style="font-size:0.76rem;color:#64748B;margin-top:2px;">« {html.escape(str(f["raw_value"]))} »</div>'
            if f.get("raw_value") and str(f["raw_value"]) != str(value)
            else ""
        )
        conf_badge = pill(f"{conf_pct} %", tone)
        st_badge = pill("Confirmé", "green") if confirmed else pill(STATUS.get(f["status"], f["status"]), "slate")

        with st.container(border=True):
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;flex-wrap:wrap;">'
                f'<div><span style="font-weight:700;color:{"#1D4ED8" if is_sel else "#0F172A"};font-size:0.88rem;">'
                f'{html.escape(_label(name))}</span>{ref_html}'
                f'<div style="font-size:0.96rem;font-weight:600;color:#0F172A;margin-top:3px;">'
                f'{html.escape(str(value))}</div>{raw_line}</div>'
                f'<div style="text-align:right;">{conf_badge} {st_badge}</div></div>'
                f'<div class="bx-conf-track"><div class="bx-conf-fill bx-conf-{couleur}" style="width:{conf_pct}%;"></div></div>',
                unsafe_allow_html=True,
            )

            st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button(
                    "Source",
                    key=f"src_{name}",
                    disabled=not (f.get("source") or {}).get("message_id"),
                    use_container_width=True,
                ):
                    st.session_state["selected_field"] = name
                    st.rerun()
            with c2:
                if st.button(
                    "Confirmer",
                    key=f"ok_{name}",
                    disabled=confirmed,
                    type="primary" if not confirmed else "secondary",
                    use_container_width=True,
                ):
                    try:
                        api_client.confirm_field(dossier_id, name, user)
                        st.rerun()
                    except ApiError as e:
                        st.error(f"{e.status} : {e.message}")
            with c3:
                with st.popover("Corriger", use_container_width=True):
                    new = st.text_input("Nouvelle valeur", key=f"val_{name}")
                    if st.button("Enregistrer", key=f"save_{name}", type="primary", use_container_width=True):
                        if not new.strip():
                            st.warning("Saisis une valeur.")
                        else:
                            try:
                                api_client.confirm_field(dossier_id, name, user, new_value=new.strip())
                                st.rerun()
                            except ApiError as e:
                                st.error(f"{e.status} : {e.message}")
