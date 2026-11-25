"""Point d'entrée officiel du parseur WhatsApp — Étape 2 ANALYSÉ (§2.2 & §6.3).

Signature appelée par le pipeline de Bénito :
    ``analyser(texte_brut=..., items_simulateur=None, telephone=None)``
    -> ``{"messages": [...], "empreinte": "sha256:...", "client": {...} | None,
          "medias_non_pris_en_charge": [...]}``
"""

import csv
import logging
from pathlib import Path
from typing import Optional, Union

import yaml

from ai.config import CHEMIN_CLIENTS
from .client import identifier_client
from .typologie import TYPES_MESSAGE, classifier_message
from .whatsapp import (
    FormatInvalide,
    detecter_media_non_pris_en_charge,
    empreinte_fil,
    messages_depuis_simulateur,
    messages_depuis_simulateur_detaille,
    parser_export,
    parser_export_detaille,
)

log = logging.getLogger("ai.parseur")

_ROLES_DEFAUT = Path(__file__).with_name("roles.yaml")


def _roles(path: Union[str, Path] = _ROLES_DEFAUT) -> dict[str, str]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _clients(path: Union[str, Path] = CHEMIN_CLIENTS) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        log.warning("Référentiel clients introuvable (%s) : liste vide utilisée", path)
        return []


def analyser(
    texte_brut: Optional[str] = None,
    items_simulateur: Optional[list[dict]] = None,
    telephone: Optional[str] = None,
    clients: Optional[list[dict]] = None,
    roles: Optional[dict[str, str]] = None,
) -> dict:
    """Exécute l'étape 2 ANALYSÉ : découpage, typologie, médias, empreinte et client.

    Fonction pure et déterministe (aucune écriture fichier ni base de données).
    Lève ``FormatInvalide`` si l'entrée est absente, vide ou mal formée.
    """
    if texte_brut is not None:
        messages, medias = parser_export_detaille(
            texte_brut, roles if roles is not None else _roles()
        )
    elif items_simulateur is not None:
        messages, medias = messages_depuis_simulateur_detaille(items_simulateur)
    else:
        raise FormatInvalide(
            "Aucune entrée fournie : fournir texte_brut ou items_simulateur."
        )

    if medias:
        log.info("Médias non pris en charge détectés : %d", len(medias))

    liste_clients = clients if clients is not None else _clients()
    client = identifier_client(messages, liste_clients, telephone)
    return {
        "messages": messages,
        "empreinte": empreinte_fil(messages),
        "client": client,
        "medias_non_pris_en_charge": medias,
    }


__all__ = [
    "analyser",
    "FormatInvalide",
    "TYPES_MESSAGE",
    "classifier_message",
    "detecter_media_non_pris_en_charge",
]
