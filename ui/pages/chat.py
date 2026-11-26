"""Chat page: import a WhatsApp export (paste, .txt upload, or preloaded scenario) and show the thread."""
from datetime import date, datetime
from pathlib import Path

import streamlit as st

from ui import api_client
from ui.api_client import ApiError
from ui.components.chat import render_chat
from ui.simulator import format_simulated_conversation

ROOT = Path(__file__).resolve().parent.parent.parent
SCENARIOS_DIR = ROOT / "data" / "scenarios"

SCENARIO_LABELS = {
    "awa_dossou.txt": "01 · Awa Dossou — Scénario court de référence (4 msg · refus taille L · 27 553 FCFA)",
    "02_koffi_bienvenue10_simple.txt": "02 · Koffi Adjovi — Première commande BIENVENUE10 (7 msg · Cotonou · sans anomalie)",
    "03_sika_modification_taille_et_quantite.txt": "03 · Sika Hounkpatin — Modification de taille & remise quantité (12 msg · Porto-Novo)",
    "04_client_inconnu_prix_inhabituel_et_media.txt": "04 · Nadège (client inconnu) — Prix cité erroné, audio/image & refus partiel (16 msg)",
    "05_awa_longue_negociation_livraison_partielle.txt": "05 · Awa Dossou — Longue négociation, correction qté & livraison partielle (22 msg)",
    "06_sika_tres_long_multi_commandes_et_reclamation.txt": "06 · Sika Hounkpatin — Fil très long multi-commandes sur 2 jours & réclamation (30 msg)",
}


def _available_scenarios() -> list[Path]:
    if not SCENARIOS_DIR.is_dir():
        return []
    files = sorted(SCENARIOS_DIR.glob("*.txt"))
    # Keep awa_dossou.txt first
    files.sort(key=lambda p: (0 if p.name == "awa_dossou.txt" else 1, p.name))
    return files


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _load_selected_scenario():
    chosen = st.session_state.get("scenario_choice")
    if chosen:
        p = SCENARIOS_DIR / chosen
        if p.is_file():
            st.session_state["paste"] = p.read_text(encoding="utf-8-sig")


st.title("Chat")
st.caption("Importe un export WhatsApp ou compose un fil simulé, puis crée le dossier.")

source_mode = st.radio(
    "Source de la conversation",
    ["Importer un export", "Simuler WhatsApp"],
    horizontal=True,
    key="chat_source_mode",
)
raw = ""
create = False

if source_mode == "Importer un export":
    scenarios = _available_scenarios()
    if scenarios:
        c_sel, c_btn, c_dl = st.columns([3, 1, 1])
        with c_sel:
            selected_name = st.selectbox(
                "Scénarios WhatsApp préchargés (du plus court au plus long)",
                options=[p.name for p in scenarios],
                format_func=lambda n: SCENARIO_LABELS.get(n, n),
                key="scenario_choice",
            )
        with c_btn:
            st.write("")
            st.write("")
            st.button("Charger ce scénario", on_click=_load_selected_scenario, use_container_width=True)
        with c_dl:
            st.write("")
            st.write("")
            chosen_path = SCENARIOS_DIR / selected_name
            st.download_button(
                "Télécharger .txt",
                data=chosen_path.read_bytes(),
                file_name=selected_name,
                mime="text/plain",
                use_container_width=True,
            )

    st.text_area(
        "Texte de la conversation",
        key="paste",
        height=200,
        placeholder="25/11/2026 10:02 - Awa: Bonjour, je veux ...",
    )

    with st.expander("Ou téléverser un export .txt"):
        uploaded = st.file_uploader("Fichier d'export WhatsApp", type=["txt"], key="upload")

    if uploaded is not None:
        raw = _decode(uploaded.getvalue())
        st.caption(f"Fichier utilisé : {uploaded.name} (le texte collé est ignoré)")
    else:
        raw = st.session_state.get("paste", "")

    create = st.button(
        "Créer le dossier depuis ce fil",
        type="primary",
        disabled=not raw.strip(),
        use_container_width=True,
    )
else:
    st.info("Conversation simulée localement : aucun message n'est envoyé à WhatsApp ou à Meta.")
    st.session_state.setdefault("simulated_messages", [])

    simulated_messages = st.session_state["simulated_messages"]
    if simulated_messages:
        chat_title = next(
            (
                message["author"]
                for message in simulated_messages
                if message["author"].lower() not in {"vendeuse", "livreur"}
            ),
            "Client",
        )
    else:
        chat_title = "Nouvelle conversation"

    render_chat(
        [{"id": f"sim-{index}", **message} for index, message in enumerate(simulated_messages, start=1)],
        height=380,
        title=chat_title,
        subtitle="simulation locale",
    )

    with st.form("simulator_add_message", clear_on_submit=True):
        speaker = st.selectbox("Envoyer en tant que", ["Client", "Vendeuse", "Livreur"])
        author = st.text_input("Nom du client", value="Awa") if speaker == "Client" else speaker
        message_text = st.text_area("Message", placeholder="Écris le contenu du message...")
        c_date, c_time = st.columns(2)
        with c_date:
            sent_date = st.date_input("Date", value=date.today())
        with c_time:
            sent_time = st.time_input(
                "Heure",
                value=datetime.now().time().replace(second=0, microsecond=0),
            )
        add_message = st.form_submit_button("Envoyer dans la conversation")

    if add_message:
        if not author.strip() or not message_text.strip():
            st.warning("Le nom de l'intervenant et le message sont obligatoires.")
        else:
            st.session_state["simulated_messages"].append({
                "time": f"{sent_date:%d/%m/%Y} {sent_time:%H:%M}",
                "author": author.strip(),
                "text": message_text.strip(),
            })
            st.rerun()

    create = st.button(
        "Créer le dossier depuis la conversation simulée",
        type="primary",
        disabled=not simulated_messages,
        use_container_width=True,
    )
    if simulated_messages and st.button("Vider le fil simulé"):
        st.session_state["simulated_messages"] = []
        st.rerun()
    if simulated_messages:
        raw = format_simulated_conversation(simulated_messages)

with st.expander("Démonstration reprise après interruption (E12)"):
    st.caption("Simule une coupure du service après l'étape EXTRAIT, puis permet de reprendre sans doublon.")
    c_int, c_res = st.columns(2)
    with c_int:
        if st.button("Simuler interruption à EXTRAIT", disabled=not raw.strip(), use_container_width=True):
            try:
                res = api_client.simulate_interruption(raw, st.session_state["user"], "EXTRAIT")
                st.session_state["dossier_id"] = res["dossier_id"]
                st.warning(f"Traitement interrompu pour {res['dossier_id']} — étapes faites : {res.get('steps', [])}")
            except ApiError as e:
                st.error(e.message)
    with c_res:
        did = st.session_state.get("dossier_id")
        if st.button("Reprendre le traitement", disabled=not did, use_container_width=True):
            try:
                res = api_client.resume_dossier(did, st.session_state["user"])
                st.success(f"Reprise terminée sans doublon — étapes : {res.get('steps', [])}")
            except ApiError as e:
                st.error(e.message)

if create:
    try:
        res = api_client.import_conversation(raw, st.session_state["user"])
        st.session_state["dossier_id"] = res["dossier_id"]
        if res.get("duplicate"):
            st.info(f"Ce fil a déjà été importé : dossier existant **{res['dossier_id']}** ouvert.")
        else:
            st.success(f"Dossier **{res['dossier_id']}** créé (version {res.get('version', 1)}).")
    except ApiError as e:
        st.error(f"{e.status} : {e.message}")

dossier_id = st.session_state.get("dossier_id")
if dossier_id:
    try:
        dossier = api_client.get_dossier(dossier_id)
        st.markdown(
            f"Dossier **{dossier_id}** · statut **{dossier['doc_status']}** · "
            f"version **{dossier.get('version', 1)}** · étapes : `{', '.join(dossier.get('steps', []))}`"
        )
        render_chat(
            api_client.get_messages(dossier_id),
            height=420,
            title="Conversation WhatsApp",
            subtitle="Fil importé · analyse en cours ou terminée",
        )
    except ApiError as e:
        st.error(e.message)
