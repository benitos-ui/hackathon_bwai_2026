"""Parseur de conversations WhatsApp (.txt) et du simulateur de chat (Étape 2 ANALYSÉ).

Prend en charge :
- Les exports WhatsApp format iOS/crochets : ``[25/11/2026 10:02:11] Awa: msg``
- Les exports WhatsApp format Android/tiret : ``25/11/2026, 10:02 - Awa: msg``
- Les messages multi-lignes (lignes sans horodatage rattachées au message précédent)
- Le filtrage des notices système (chiffrement) et le signalement explicite des médias
  non pris en charge (vocaux, images, vidéos, pièces jointes — Addendum v1.1 §3.3 / D8)
- La classification déterministe de la typologie des messages (Addendum v1.1 §3.2)
- L'entrée structurée provenant du simulateur web de Femi
- Le calcul d'une empreinte logique SHA-256 déterministe du fil (exigence E1)
"""

import hashlib
import json
import re
from datetime import datetime
from typing import Optional

from .typologie import classifier_message

LIGNE = re.compile(
    r"^[\ufeff\u200e]*\[?(\d{1,2}/\d{1,2}/\d{2,4})[, ]+(\d{1,2}:\d{2})(?::\d{2})?\]?\s*-?\s*([^:]{1,40}?):\s(.*)$"
)

NOTICES_SYSTEME: tuple[str, ...] = (
    "messages et appels sont chiffrés",
    "messages and calls are end-to-end encrypted",
)

# Motifs WhatsApp de médias / pièces jointes non pris en charge (Addendum §3.3 / D8)
_MOTIFS_MEDIA: tuple[tuple[str, re.Pattern], ...] = (
    (
        "audio",
        re.compile(
            r"(audio\s+(?:omis|omitted|absent)|message\s+vocal|note\s+vocale|"
            r"\bptt-\d+|\.(?:opus|ogg|mp3|m4a|wav)\s*\((?:fichier\s+joint|file\s+attached)\))",
            re.I,
        ),
    ),
    (
        "image",
        re.compile(
            r"(image\s+(?:omitted|absente|omise)|photo\s+(?:absente|omise)|"
            r"\.(?:jpg|jpeg|png|webp|heic)\s*\((?:fichier\s+joint|file\s+attached)\))",
            re.I,
        ),
    ),
    (
        "video",
        re.compile(
            r"(vid[ée]o\s+(?:omitted|absente|omise)|"
            r"\.(?:mp4|mov|3gp)\s*\((?:fichier\s+joint|file\s+attached)\))",
            re.I,
        ),
    ),
    (
        "sticker",
        re.compile(r"(sticker\s+omitted|autocollant\s+omis|gif\s+omitted)", re.I),
    ),
    (
        "document",
        re.compile(
            r"(document\s+(?:omitted|omis|absent)|"
            r"\.(?:pdf|docx?|xlsx?|csv|zip)\s*\((?:fichier\s+joint|file\s+attached)\)|"
            r"\((?:fichier\s+joint|file\s+attached)\))",
            re.I,
        ),
    ),
    (
        "media",
        re.compile(r"(<\s*m[ée]dias?\s+omis\s*>|<\s*media\s+omitted\s*>)", re.I),
    ),
)

# Conservé pour compatibilité ascendante éventuelle
SYSTEME: tuple[str, ...] = NOTICES_SYSTEME + (
    "image omitted",
    "image absente",
    "<médias omis>",
    "<media omitted>",
    "vidéo absente",
    "audio omis",
    "sticker omitted",
)


class FormatInvalide(ValueError):
    """Fichier ou flux mal formé : refusé avec un message clair (E1).

    Bénito traduit cette exception en erreur HTTP 422 côté API.
    """


def detecter_media_non_pris_en_charge(texte: str) -> Optional[str]:
    """Détecte si un message correspond à un média ou une pièce jointe hors périmètre (§3.3).

    Retourne le type de média (``audio``, ``image``, ``video``, ``sticker``, ``document``,
    ``media``) ou ``None`` s'il s'agit d'un message texte exploitable.
    """
    t = (texte or "").strip()
    if not t:
        return None
    for type_media, rx in _MOTIFS_MEDIA:
        if rx.search(t):
            return type_media
    return None


def _horodatage(date_str: str, heure_str: str) -> str:
    """Convertit une date/heure WhatsApp (JJ/MM/AAAA ou JJ/MM/AA + HH:MM) en ISO-8601."""
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%y %H:%M"):
        try:
            return datetime.strptime(f"{date_str} {heure_str}", fmt).isoformat()
        except ValueError:
            continue
    raise FormatInvalide(f"Date illisible : {date_str} {heure_str}")


def parser_export_detaille(
    texte_brut: str, roles: dict[str, str]
) -> tuple[list[dict], list[dict]]:
    """Parse un export WhatsApp en ``(messages, medias_non_pris_en_charge)``.

    Les médias/pièces jointes (vocaux, images, vidéos, documents) ne sont pas ignorés
    silencieusement : ils sont signalés dans ``medias_non_pris_en_charge`` (§3.3).
    """
    if not isinstance(texte_brut, str) or not texte_brut.strip():
        raise FormatInvalide("Aucun message reconnu : fichier vide ou mal formé.")

    messages: list[dict] = []
    medias: list[dict] = []
    dernier_etait_ignore = False

    for ligne in texte_brut.splitlines():
        m = LIGNE.match(ligne)
        if m:
            date_str, heure_str, auteur, corps = m.groups()
            auteur = auteur.strip()
            corps_propre = corps.strip()
            corps_min = corps_propre.lower()
            horodatage = _horodatage(date_str, heure_str)
            role = roles.get(auteur, "client")

            if any(s in corps_min for s in NOTICES_SYSTEME):
                dernier_etait_ignore = True
                continue

            type_media = detecter_media_non_pris_en_charge(corps_propre)
            if type_media is not None:
                medias.append({
                    "horodatage": horodatage,
                    "auteur": auteur,
                    "role": role,
                    "type_media": type_media,
                    "texte_brut": corps_propre,
                    "motif": "media_non_pris_en_charge",
                })
                dernier_etait_ignore = True
                continue

            dernier_etait_ignore = False
            rang = len(messages)
            messages.append({
                "rang": rang,
                "message_id": f"m{rang + 1}",
                "horodatage": horodatage,
                "auteur": auteur,
                "role": role,
                "texte": corps_propre,
                "type_message": classifier_message(corps_propre, role),
            })
        elif messages and not dernier_etait_ignore and ligne.strip():
            # Suite multi-ligne rattachée au message précédent + recalcul de la typologie
            messages[-1]["texte"] += "\n" + ligne.strip()
            messages[-1]["type_message"] = classifier_message(
                messages[-1]["texte"], messages[-1]["role"]
            )

    if not messages:
        if medias:
            raise FormatInvalide(
                "Aucun message texte exploitable : uniquement des médias non pris en charge "
                "(audio, image, vidéo ou pièce jointe)."
            )
        raise FormatInvalide(
            "Aucun message reconnu : fichier mal formé ou format non supporté."
        )
    return messages, medias


def parser_export(texte_brut: str, roles: dict[str, str]) -> list[dict]:
    """Parse un export texte WhatsApp en une liste ordonnée de messages normalisés.

    ``roles`` associe un nom d'auteur à son rôle (ex. ``{"Boutique X": "vendeuse",
    "Livreur Marc": "livreur"}``) ; tout autre auteur reçoit le rôle ``"client"``.
    """
    messages, _ = parser_export_detaille(texte_brut, roles)
    return messages


def messages_depuis_simulateur_detaille(
    items: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Convertit les messages du simulateur en ``(messages, medias_non_pris_en_charge)``."""
    if not items or not isinstance(items, list):
        raise FormatInvalide("Conversation vide.")

    messages: list[dict] = []
    medias: list[dict] = []

    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise FormatInvalide(f"Message simulateur invalide à l'index {i}.")
        for cle in ("auteur", "role", "texte"):
            if cle not in item or not isinstance(item[cle], str):
                raise FormatInvalide(
                    f"Champ '{cle}' manquant ou invalide dans le message simulateur {i}."
                )
        auteur = item["auteur"].strip()
        role = item["role"].strip()
        texte = item["texte"].strip()
        horodatage = item.get("horodatage")

        type_media = detecter_media_non_pris_en_charge(texte)
        if type_media is not None:
            medias.append({
                "horodatage": horodatage,
                "auteur": auteur,
                "role": role,
                "type_media": type_media,
                "texte_brut": texte,
                "motif": "media_non_pris_en_charge",
            })
            continue

        rang = len(messages)
        messages.append({
            "rang": rang,
            "message_id": f"m{rang + 1}",
            "horodatage": horodatage,
            "auteur": auteur,
            "role": role,
            "texte": texte,
            "type_message": classifier_message(texte, role),
        })

    if not messages:
        if medias:
            raise FormatInvalide(
                "Aucun message texte exploitable : uniquement des médias non pris en charge."
            )
        raise FormatInvalide("Conversation vide.")
    return messages, medias


def messages_depuis_simulateur(items: list[dict]) -> list[dict]:
    """Convertit la liste de messages du simulateur en structure officielle de messages.

    Format attendu par élément :
    ``{"auteur": "Awa", "role": "client", "texte": "...", "horodatage": "2026-11-25T10:02:00"}``
    """
    messages, _ = messages_depuis_simulateur_detaille(items)
    return messages


def empreinte_fil(messages: list[dict]) -> str:
    """Calcule l'empreinte logique SHA-256 déterministe d'un fil de messages (E1).

    Un même fil importé deux fois (ou reçu via export puis simulateur) produit
    strictement la même empreinte.
    """
    canon = json.dumps(
        [(m["horodatage"], m["auteur"], m["texte"]) for m in messages],
        ensure_ascii=False,
        sort_keys=True,
    )
    return "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()
