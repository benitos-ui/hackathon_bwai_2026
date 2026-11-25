"""Normalisation des champs, conversion au format contrat et assemblage des lignes (Étape 4).

Règles clés (CDC §3.4, §5.3, Guide §7.4 & Addendum v1.1 §3.2, §4, §8, §13) :
- Conservation simultanée de l'identifiant catalogue (``ref``) et de la mention originale
  (``valeur_brute``) sur chaque champ normalisé (Addendum §4).
- Séparation déterministe ``quantite_commandee`` / ``quantite_livree`` selon le rôle de l'auteur (D3),
  et suivi de ``quantite_refusee`` par ligne (Test T13).
- Les passages ``REFUS`` (et toute entité chevauchant un passage ``REFUS``) sont strictement
  exclus de l'assemblage des lignes et reportés dans ``signaux.refus``.
- Modifications ultérieures explicites de taille/quantité (Test T11) : mettent à jour la ligne
  existante avec trace dans ``signaux.corrections`` sans doublon silencieux ; en cas de doute
  (plusieurs produits ou variantes cibles), lève ``ambiguite = True``.
- Produits proches ambigus (``A_PRODUIT_AMBIGU``, Test T12) : aucune sélection automatique,
  champ passé en ``a_renseigner`` avec la liste des candidats et ``ambiguite = True``.
- Fils multi-commandes ou multi-clients (``A_CONVERSATION``, Test T20) : signalés via
  ``ambiguite = True`` et ``signaux.multi_commandes = True``.
- En cas d'échec de normalisation, la valeur devient ``None`` (statut ``a_renseigner``,
  couleur ``rouge``, confiance ``0.0``) : l'IA ne devine jamais.
"""

from datetime import datetime
import re
from typing import Optional

from ai.parseur.typologie import classifier_message
from .nombres import parse_montant, parse_quantite
from .rapprochement import (
    charger_alias,
    charger_catalogue,
    match_produit,
    match_variante,
    match_zone,
    normaliser_paiement,
)

CORRECTION = re.compile(
    r"\b(non\s+plut[oô]t|plut[oô]t|finalement|annule[rz]?|change[rz]?|modifie[rz]?|"
    r"remplace[rz]?|en\s+fait|au\s+lieu\s+de)\b",
    re.I,
)
_MULTI_COMMANDE_EXPLICITE = re.compile(
    r"\b("
    r"deuxi[èe]me\s+commande|2[èe]me\s+commande|autre\s+commande|"
    r"nouvelle\s+commande|commande\s+(?:n°|num[ée]ro|#)?\s*2|"
    r"commande\s+distincte|facture\s+s[ée]par[ée]e"
    r")\b",
    re.I,
)
_VARIANTE_REFUS_MAJ = re.compile(r"\b(XL|S|M|L)\b")
_VARIANTE_REFUS_TAILLE = re.compile(r"\btaille\s+(xl|s|m|l)\b", re.I)
_QTE_REFUS = re.compile(
    r"\b(\d{1,2}|une?|deux|trois|quatre|cinq|six|sept|huit|neuf|dix)\b",
    re.I,
)

SEUIL_HEURES_MULTI_COMMANDE: float = 24.0


def _rang_message(message_id: str, rangs: dict[str, int]) -> int:
    if message_id in rangs:
        return rangs[message_id]
    return int(message_id[1:])


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts or not isinstance(ts, str):
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _type_msg(msg: dict) -> str:
    return msg.get("type_message") or classifier_message(
        msg.get("texte", ""), msg.get("role", "client")
    )


def en_contrat(c: dict) -> dict:
    """Passe du champ plat (§7.8, table ``champs_extraits``) à la forme imbriquée (Annexe A)."""
    src = (
        None
        if c.get("message_id") is None
        else {"message_id": c["message_id"], "debut": c["debut"], "fin": c["fin"]}
    )
    sortie = {
        k: v for k, v in c.items() if k not in ("message_id", "debut", "fin", "rejet")
    }
    sortie["source"] = src
    return sortie


def normaliser_champs(
    champs: list[dict],
    messages: list[dict],
    alias: dict,
    catalogue: dict[str, dict],
) -> list[dict]:
    """Normalise chaque champ brut extrait en valeur typée + référence catalogue.

    Fonction pure : ne mute pas les dictionnaires d'entrée.
    Conserve toujours ``valeur_brute`` et, pour les produits, ``ref`` (Addendum §4).
    """
    roles = {m["message_id"]: m["role"] for m in messages}
    out: list[dict] = []

    for n, c in enumerate(champs, 1):
        n_c = {**c, "id": f"c{n}", "ref": None, "valeur_brute": c["valeur"]}
        if c["valeur"] is None:
            out.append(n_c)
            continue

        nom, brut = c["nom"], c["valeur"]
        valeur = None

        if nom == "quantite":
            role = roles.get(c["message_id"], "client")
            n_c["nom"] = "quantite_livree" if role == "livreur" else "quantite_commandee"
            valeur = parse_quantite(brut)
        elif nom == "prix_cite":
            valeur = parse_montant(brut)
        elif nom == "variante":
            valeur = match_variante(brut, alias)
        elif nom == "produit":
            m = match_produit(brut, alias)
            if m and m.get("ambigu"):
                # Addendum §8 A_PRODUIT_AMBIGU / T12 : aucune sélection automatique risquée
                candidats = [
                    {
                        "ref": cand["ref"],
                        "nom": catalogue[cand["ref"]]["nom"]
                        if cand["ref"] in catalogue
                        else cand["ref"],
                        "score": cand["score"],
                    }
                    for cand in m.get("candidats", [])
                ]
                n_c["ambiguite_produit"] = True
                n_c["candidats_produits"] = candidats
                valeur = None
            elif m and m["ref"] in catalogue:
                n_c["ref"] = m["ref"]
                valeur = catalogue[m["ref"]]["nom"]
                conf = round(min(c["confiance"], m["score"]), 4)
                n_c["confiance"] = conf
                if n_c.get("couleur") == "vert" and conf < 0.90:
                    n_c["couleur"] = "orange"
        elif nom == "zone":
            m = match_zone(brut, alias)
            if m:
                valeur = m["zone"]
                conf = round(min(c["confiance"], m["score"]), 4)
                n_c["confiance"] = conf
                if n_c.get("couleur") == "vert" and conf < 0.90:
                    n_c["couleur"] = "orange"
        elif nom == "paiement":
            valeur = normaliser_paiement(brut)
        elif nom == "code_promo":
            valeur = brut.strip().upper() if isinstance(brut, str) and brut.strip() else None
        else:
            valeur = brut  # date_livraison, refus, motif_refus, client

        if valeur is None:
            # Normalisation impossible ou produit ambigu : on ne devine jamais
            n_c.update(
                valeur=None,
                ref=None,
                statut="a_renseigner",
                couleur="rouge",
                confiance=0.0,
            )
        else:
            n_c["valeur"] = valeur
        out.append(n_c)

    return out


def _chevauche_refus(c: dict, refus: list[dict]) -> bool:
    """Retourne True si le span ``c`` se trouve dans ou chevauche un passage ``REFUS``."""
    return any(
        r["message_id"] == c["message_id"]
        and r["debut"] < c["fin"]
        and c["debut"] < r["fin"]
        for r in refus
    )


def _ajouter_champ_id(ligne_dict: dict, champ_id: str) -> None:
    if champ_id not in ligne_dict["champs_ids"]:
        ligne_dict["champs_ids"].append(champ_id)


def _ajouter_mention_brute(ligne_dict: dict, valeur_brute: Optional[str]) -> None:
    if valeur_brute and valeur_brute not in ligne_dict["mentions_brutes"]:
        ligne_dict["mentions_brutes"].append(valeur_brute)


def _detecter_multi_commandes(messages: list[dict]) -> list[str]:
    """Détecte les indices de plusieurs commandes ou clients dans un même fil (T20)."""
    motifs: list[str] = []
    if not messages:
        return motifs

    # 1. Plusieurs auteurs clients distincts dans le même fil
    auteurs_clients = sorted(
        {
            m["auteur"].strip()
            for m in messages
            if m.get("role") == "client" and isinstance(m.get("auteur"), str) and m["auteur"].strip()
        }
    )
    if len(auteurs_clients) > 1:
        motifs.append(
            f"A_CONVERSATION — plusieurs clients détectés dans le même fil : {', '.join(auteurs_clients)}"
        )

    msgs_ordonnes = sorted(messages, key=lambda m: m.get("rang", 0))
    livraison_vue = False
    derniere_commande_ts: Optional[datetime] = None
    derniere_commande_mid: Optional[str] = None
    commande_apres_livraison_signalee = False
    ecart_temporel_signale = False

    for m in msgs_ordonnes:
        mid = m.get("message_id", "?")
        role = m.get("role", "client")
        texte = m.get("texte", "")
        t_msg = _type_msg(m)

        # 2. Marqueur explicite de deuxième/autre commande distincte
        if _MULTI_COMMANDE_EXPLICITE.search(texte):
            motifs.append(
                f"{mid}: A_CONVERSATION — mention explicite d'une seconde commande dans le même fil"
            )

        if t_msg == "LIVRAISON" or role == "livreur":
            livraison_vue = True
            continue

        if role == "client" and t_msg == "COMMANDE":
            # 3. Nouvelle commande après une livraison dans le même fil
            if livraison_vue and not commande_apres_livraison_signalee:
                motifs.append(
                    f"{mid}: A_CONVERSATION — nouvelle commande détectée après une livraison dans le même fil"
                )
                commande_apres_livraison_signalee = True

            # 4. Deux commandes distinctes espacées d'au moins 24 heures
            ts = _parse_iso(m.get("horodatage"))
            if (
                ts is not None
                and derniere_commande_ts is not None
                and not ecart_temporel_signale
            ):
                ecart_h = (ts - derniere_commande_ts).total_seconds() / 3600.0
                if ecart_h >= SEUIL_HEURES_MULTI_COMMANDE:
                    motifs.append(
                        f"{mid}: A_CONVERSATION — deux commandes espacées de {int(ecart_h)}h "
                        f"({derniere_commande_mid} et {mid}) dans le même fil"
                    )
                    ecart_temporel_signale = True
            if ts is not None:
                derniere_commande_ts = ts
                derniere_commande_mid = mid

    return motifs


def assembler_lignes(
    champs: list[dict],
    messages: list[dict],
    alias: dict,
) -> dict:
    """Assemble les champs normalisés en lignes de commande/livraison, zone, paiement et signaux.

    En cas d'ambiguïté, de produit proche ambigu (T12), de fil multi-commandes (T20) ou
    de contradiction sans indice explicite de correction, ``signaux.ambiguite`` passe à ``True``
    (jamais de devinette silencieuse).
    """
    roles = {m["message_id"]: m["role"] for m in messages}
    textes = {m["message_id"]: m["texte"] for m in messages}
    types_msg = {m["message_id"]: _type_msg(m) for m in messages}
    rangs = {m["message_id"]: m.get("rang", i) for i, m in enumerate(messages)}

    utiles = [
        c
        for c in champs
        if c["valeur"] is not None
        and c.get("message_id") is not None
        and c.get("debut") is not None
        and c.get("fin") is not None
    ]
    produits_ambigus_champs = [
        c for c in champs if c.get("ambiguite_produit") and c.get("message_id") is not None
    ]
    refus = [c for c in utiles if c["nom"] == "refus"]

    lignes: dict[str, dict] = {}
    motifs: list[str] = []
    corrections: list[dict] = []
    sig_refus: list[dict] = []
    produits_ambigus: list[dict] = []
    zones: list[dict] = []
    paiements: list[dict] = []

    # Détection T12 : produits proches ambigus
    for c in produits_ambigus_champs:
        candidats = c.get("candidats_produits", [])
        refs_txt = ", ".join(cand["ref"] for cand in candidats)
        motifs.append(
            f"{c['message_id']}: A_PRODUIT_AMBIGU — mention '{c.get('valeur_brute')}' "
            f"correspond à plusieurs produits proches ({refs_txt})"
        )
        produits_ambigus.append({
            "champ_id": c["id"],
            "message_id": c["message_id"],
            "valeur_brute": c.get("valeur_brute"),
            "candidats": candidats,
        })

    # Détection T20 : plusieurs commandes ou clients dans le même fil
    motifs_multi = _detecter_multi_commandes(messages)
    motifs.extend(motifs_multi)

    def obtenir_ligne(ref: str, nom: str) -> dict:
        return lignes.setdefault(
            ref,
            {
                "ref": ref,
                "produit": nom,
                "mentions_brutes": [],
                "quantite_commandee": None,
                "quantite_livree": None,
                "quantite_refusee": 0,
                "variantes": {"commandees": [], "livrees": []},
                "repartition_commandee": [],
                "repartition_livree": [],
                "prix_cite": None,
                "champs_ids": [],
            },
        )

    mids_a_parcourir = sorted(
        {c["message_id"] for c in utiles} | {c["message_id"] for c in produits_ambigus_champs},
        key=lambda x: _rang_message(x, rangs),
    )

    for mid in mids_a_parcourir:
        role = roles.get(mid, "client")
        suffixe = "livree" if role == "livreur" else "commandee"
        cle_variantes = "livrees" if role == "livreur" else "commandees"
        texte_msg = textes.get(mid, "")
        est_modification = role != "livreur" and (
            bool(CORRECTION.search(texte_msg)) or types_msg.get(mid) == "MODIFICATION"
        )

        # État existant AVANT ce message (évite qu'un mot de correction dans m1 n'écrase m1)
        refs_avant_msg = set(lignes.keys())
        variantes_avant_msg = {
            ref: list(l["variantes"][cle_variantes]) for ref, l in lignes.items()
        }
        variante_modifiee_dans_msg: set[str] = set()

        pending: Optional[dict] = None
        last: Optional[dict] = None

        champs_msg = sorted(
            [x for x in utiles if x["message_id"] == mid]
            + [x for x in produits_ambigus_champs if x["message_id"] == mid],
            key=lambda x: (x["debut"], x["fin"]),
        )

        for c in champs_msg:
            if c.get("ambiguite_produit"):
                # Ne pas créer de ligne sur un produit ambigu ; consommer l'éventuelle quantité liée
                pending = None
                last = None
                continue

            if c["nom"] in ("refus", "motif_refus") or _chevauche_refus(c, refus):
                # Les passages REFUS n'entrent jamais dans les lignes
                continue

            if c["nom"].startswith("quantite"):
                if pending is not None:
                    motifs.append(f"{mid}: deux quantités de suite")
                pending = c
            elif c["nom"] == "produit" and c.get("ref"):
                last = obtenir_ligne(c["ref"], c["valeur"])
                _ajouter_champ_id(last, c["id"])
                _ajouter_mention_brute(last, c.get("valeur_brute"))
                if pending is not None:
                    cle_qte = f"quantite_{suffixe}"
                    ancienne = last[cle_qte]
                    nouvelle = pending["valeur"]
                    est_correction = bool(CORRECTION.search(texte_msg)) or types_msg.get(mid) == "MODIFICATION"
                    if ancienne is not None and ancienne != nouvelle:
                        if est_correction:
                            corrections.append({
                                "type": "quantite",
                                "ref": c["ref"],
                                "ancienne": ancienne,
                                "nouvelle": nouvelle,
                                "message_id": mid,
                            })
                        else:
                            motifs.append(f"{mid}: valeur contradictoire pour {c['ref']}")
                    if ancienne is None or est_correction:
                        last[cle_qte] = nouvelle
                        _ajouter_champ_id(last, pending["id"])
                    pending = None
            elif c["nom"] == "variante":
                cible = last
                # T11 : modification de taille sans répéter le produit (« finalement mets la taille L »)
                if cible is None and est_modification:
                    if len(lignes) == 1:
                        cible = next(iter(lignes.values()))
                    elif len(lignes) > 1:
                        motifs.append(
                            f"{mid}: modification de variante ambiguë "
                            "(plusieurs produits dans le dossier)"
                        )
                        pending = None
                        continue

                if cible is None:
                    motifs.append(f"{mid}: variante sans produit")
                    continue

                ref_cible = cible["ref"]
                vars_avant = variantes_avant_msg.get(ref_cible, [])
                if (
                    est_modification
                    and ref_cible in refs_avant_msg
                    and ref_cible not in variante_modifiee_dans_msg
                ):
                    if len(vars_avant) == 1:
                        ancienne_var = vars_avant[0]
                        nouvelle_var = c["valeur"]
                        if ancienne_var != nouvelle_var:
                            cible["variantes"][cle_variantes] = [nouvelle_var]
                            rep = cible[f"repartition_{suffixe}"]
                            if len(rep) == 1 and rep[0]["variante"] == ancienne_var:
                                rep[0]["variante"] = nouvelle_var
                            corrections.append({
                                "type": "variante",
                                "ref": ref_cible,
                                "ancienne": ancienne_var,
                                "nouvelle": nouvelle_var,
                                "message_id": mid,
                            })
                        _ajouter_champ_id(cible, c["id"])
                        variante_modifiee_dans_msg.add(ref_cible)
                        pending = None
                        continue
                    elif len(vars_avant) > 1:
                        motifs.append(
                            f"{mid}: modification de variante ambiguë pour {ref_cible} "
                            f"(plusieurs variantes existantes : {vars_avant})"
                        )
                        pending = None
                        continue

                cible["variantes"][cle_variantes].append(c["valeur"])
                _ajouter_champ_id(cible, c["id"])
                if pending is not None:
                    cible[f"repartition_{suffixe}"].append({
                        "variante": c["valeur"],
                        "quantite": pending["valeur"],
                    })
                    _ajouter_champ_id(cible, pending["id"])
                    pending = None
            elif c["nom"] == "prix_cite" and last is not None:
                last["prix_cite"] = c["valeur"]
                _ajouter_champ_id(last, c["id"])
            elif c["nom"] == "zone":
                zones.append(c)
            elif c["nom"] == "paiement":
                paiements.append(c)

        if pending is not None:
            # T11 : modification de quantité sans répéter le produit (« non plutôt 3 »)
            if est_modification and len(lignes) == 1:
                cible = next(iter(lignes.values()))
                cle_qte = f"quantite_{suffixe}"
                ancienne = cible[cle_qte]
                nouvelle = pending["valeur"]
                if ancienne is not None and ancienne != nouvelle:
                    corrections.append({
                        "type": "quantite",
                        "ref": cible["ref"],
                        "ancienne": ancienne,
                        "nouvelle": nouvelle,
                        "message_id": mid,
                    })
                cible[cle_qte] = nouvelle
                rep = cible[f"repartition_{suffixe}"]
                if len(rep) == 1:
                    rep[0]["quantite"] = nouvelle
                _ajouter_champ_id(cible, pending["id"])
            elif est_modification and len(lignes) > 1:
                motifs.append(
                    f"{mid}: modification de quantité ambiguë "
                    "(plusieurs produits dans le dossier)"
                )
            else:
                motifs.append(f"{mid}: quantité sans produit")

    # Vérification de cohérence entre quantité totale et répartition par variante
    for l in lignes.values():
        for suf in ("commandee", "livree"):
            rep = l[f"repartition_{suf}"]
            qte = l[f"quantite_{suf}"]
            if rep and qte is not None and sum(r["quantite"] for r in rep) != qte:
                motifs.append(f"{l['ref']}: répartition des variantes incohérente ({suf})")

    # Construction de signaux.refus (produit + variante + motif du même message) + quantite_refusee (T13)
    for r in refus:
        m_prod = match_produit(r["valeur"], alias)
        ref_refus = (
            m_prod["ref"]
            if m_prod and not m_prod.get("ambigu") and m_prod.get("ref")
            else None
        )
        m_var = _VARIANTE_REFUS_MAJ.search(r["valeur"]) or _VARIANTE_REFUS_TAILLE.search(
            r["valeur"]
        )
        motif = next(
            (
                x["valeur"]
                for x in utiles
                if x["nom"] == "motif_refus" and x["message_id"] == r["message_id"]
            ),
            None,
        )
        sig_refus.append({
            "ref": ref_refus,
            "variante": m_var.group(1).upper() if m_var else None,
            "motif": (
                "taille"
                if motif and re.search(r"taille|petit|grand", motif, re.I)
                else motif
            ),
            "message_id": r["message_id"],
        })
        if ref_refus and ref_refus in lignes:
            m_q = _QTE_REFUS.search(r["valeur"])
            q_ref = parse_quantite(m_q.group(1)) if m_q else None
            lignes[ref_refus]["quantite_refusee"] += q_ref if q_ref and q_ref > 0 else 1

    def unique(cs: list[dict], nom: str) -> Optional[dict]:
        valeurs = {c["valeur"] for c in cs}
        if len(valeurs) > 1:
            motifs.append(f"{nom} contradictoire : {sorted(valeurs)}")
        return {"valeur": cs[-1]["valeur"], "champ_id": cs[-1]["id"]} if cs else None

    return {
        "lignes": list(lignes.values()),
        "zone": unique(zones, "zone"),
        "paiement": unique(paiements, "paiement"),
        "signaux": {
            "ambiguite": bool(motifs),
            "motifs_ambiguite": motifs,
            "corrections": corrections,
            "refus": sig_refus,
            "produits_ambigus": produits_ambigus,
            "multi_commandes": bool(motifs_multi),
        },
    }


def normaliser_dossier(
    messages: list[dict],
    champs: list[dict],
    client: Optional[dict],
    alias: Optional[dict] = None,
    catalogue: Optional[dict[str, dict]] = None,
) -> dict:
    """Point d'entrée officiel de l'étape 4 NORMALISÉ (§2.2 & §7.4).

    Signature appelée par Bénito :
        ``normaliser_dossier(messages, champs, client)``
        -> ``{"client", "champs", "lignes", "zone", "paiement", "signaux"}``
    """
    alias_res = alias if alias is not None else charger_alias()
    catalogue_res = catalogue if catalogue is not None else charger_catalogue()
    normalises = normaliser_champs(champs, messages, alias_res, catalogue_res)
    assemblage = assembler_lignes(normalises, messages, alias_res)
    return {
        "client": client,
        "champs": [en_contrat(c) for c in normalises],
        **assemblage,
    }
