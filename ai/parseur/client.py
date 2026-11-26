"""Identification du client à l'étape ANALYSÉ (décision D6, Guide §6.2).

Ordre de priorité déterministe :
1. Numéro de téléphone (fourni par le simulateur ou présent comme nom d'auteur dans l'export),
   comparé sur les 8 derniers chiffres pour s'affranchir des variantes d'indicatif (+229 / 00229 / local).
2. Rapprochement flou sur le nom d'auteur client via ``rapidfuzz.fuzz.WRatio`` (seuil ≥ 85).
3. Sinon ``None`` (client inconnu : Primel lève l'anomalie correspondante à l'étape CONTRÔLÉ).
"""

import re
from typing import Optional

from rapidfuzz import fuzz, process


def _chiffres(s: Optional[str]) -> str:
    """Extrait uniquement les chiffres d'une chaîne."""
    return re.sub(r"\D", "", s or "")


def _client_id(c: dict) -> str:
    return c.get("identifiant") or c.get("id") or ""


def _client_nom(c: dict) -> str:
    return c.get("nom") or c.get("name") or ""


def _client_tel(c: dict) -> Optional[str]:
    return c.get("telephone") or c.get("phone")


def identifier_client(
    messages: list[dict],
    clients: list[dict],
    telephone: Optional[str] = None,
) -> Optional[dict]:
    """Identifie le client à partir du fil de messages et du référentiel ``clients``.

    Accepte les colonnes françaises (``identifiant,nom,telephone``) ou anglaises
    (``id,name,phone``) issues de ``data/clients.csv``.
    Retourne ``{"id", "nom", "confiance", "methode"}`` ou ``None`` si introuvable.
    """
    if not clients:
        return None

    candidats = [telephone] + [
        m["auteur"] for m in messages if m.get("role") == "client"
    ]
    for cand in candidats:
        tel = _chiffres(cand)
        if len(tel) >= 8:
            suffixe = tel[-8:]
            for c in clients:
                tel_ref = _chiffres(_client_tel(c))
                if len(tel_ref) >= 8 and tel_ref.endswith(suffixe):
                    return {
                        "id": _client_id(c),
                        "nom": _client_nom(c),
                        "confiance": 0.96,
                        "methode": "telephone",
                    }

    # On ignore les auteurs qui sont uniquement des numéros pour éviter tout faux match sur le nom
    noms = [
        m["auteur"]
        for m in messages
        if m.get("role") == "client" and len(_chiffres(m.get("auteur"))) < 8
    ]
    if noms:
        best = process.extractOne(
            noms[0].lower(),
            [_client_nom(c).lower() for c in clients],
            scorer=fuzz.WRatio,
            score_cutoff=85,
        )
        if best:
            c = clients[best[2]]
            return {
                "id": _client_id(c),
                "nom": _client_nom(c),
                "confiance": round(best[1] / 100, 2),
                "methode": "nom",
            }

    return None
