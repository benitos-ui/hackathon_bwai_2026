"""Rapprochement flou et déterministe avec les référentiels (produits, zones, variantes, paiement).

Utilise ``rapidfuzz`` :
- ``fuzz.WRatio`` pour les produits (tolérant aux inversions/mots partiels, seuil 80) avec
  détection d'ambiguïté entre plusieurs articles proches (Addendum v1.1 §8 ``A_PRODUIT_AMBIGU`` / T12) ;
- correspondance exacte pour les alias courts de zones puis ``fuzz.ratio`` (seuil 85)
  pour les alias de 5 caractères et plus (évite les faux positifs sur les abréviations).
"""

import csv
import logging
import re
from pathlib import Path
from typing import Optional, Union

import yaml
from rapidfuzz import fuzz, process

from ai.config import CHEMIN_CATALOGUE
from .nombres import normaliser

log = logging.getLogger("ai.normalisation")

_ALIAS_DEFAUT = Path(__file__).with_name("alias.yaml")

# Noms canoniques de repli issus du CDC §3.3 (aucun prix stocké ici : l'IA ne calcule jamais)
_CATALOGUE_NOMS_DEFAUT: dict[str, dict[str, str]] = {
    "ART-001": {"reference": "ART-001", "nom": "Robe wax Ayoka"},
    "ART-002": {"reference": "ART-002", "nom": "Ensemble pagne Sènami"},
    "ART-003": {"reference": "ART-003", "nom": "Sac à main Lagune"},
    "ART-004": {"reference": "ART-004", "nom": "Sérum vitamine C 30 ml"},
    "ART-005": {"reference": "ART-005", "nom": "Beurre de karité 200 ml"},
}


def charger_alias(path: Union[str, Path] = _ALIAS_DEFAUT) -> dict:
    """Charge le fichier YAML d'alias produits/zones/variantes."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def charger_catalogue(path: Union[str, Path] = CHEMIN_CATALOGUE) -> dict[str, dict]:
    """Charge le catalogue CSV de Primel (``reference,nom,variantes,prix_ht``).

    En cas d'absence du fichier ``data/catalogue.csv`` (exécution isolée du module IA),
    journalise un avertissement et utilise les noms canoniques par défaut du CDC §3.3
    (sans aucun prix).
    """
    try:
        with open(path, encoding="utf-8") as f:
            return {r["reference"]: r for r in csv.DictReader(f)}
    except FileNotFoundError:
        log.warning(
            "Catalogue introuvable (%s) : noms canoniques par défaut utilisés (sans prix)",
            path,
        )
        return {k: dict(v) for k, v in _CATALOGUE_NOMS_DEFAUT.items()}


def match_produit(
    texte: str,
    alias: dict,
    seuil: int = 80,
    ecart_ambiguite: float = 5.0,
) -> Optional[dict]:
    """Rapproche une mention produit avec une référence du catalogue via ``WRatio``.

    Si plusieurs références distinctes dépassent ``seuil`` et se trouvent à moins de
    ``ecart_ambiguite`` points (sur 100) du meilleur score, aucune sélection automatique
    n'est effectuée : retourne ``{"ref": None, "score": ..., "ambigu": True, "candidats": [...]}``
    (Addendum v1.1 §8 ``A_PRODUIT_AMBIGU`` & Test T12).
    """
    t = normaliser(texte or "")
    if len(t) < 3:
        return None
    produits = alias.get("produits") or {}
    if not produits:
        return None

    meilleurs_par_ref: list[tuple[str, float]] = []
    for ref, al in produits.items():
        alias_norm = [normaliser(a) for a in (al or []) if normaliser(a)]
        if not alias_norm:
            continue
        score_max = max(float(fuzz.WRatio(t, a)) for a in alias_norm)
        if score_max >= seuil:
            meilleurs_par_ref.append((ref, score_max))

    if not meilleurs_par_ref:
        return None

    meilleurs_par_ref.sort(key=lambda item: (-item[1], item[0]))
    top_ref, top_score = meilleurs_par_ref[0]
    proches = [
        (ref, sc)
        for ref, sc in meilleurs_par_ref
        if (top_score - sc) <= ecart_ambiguite
    ]
    candidats = [{"ref": ref, "score": round(sc / 100, 4)} for ref, sc in proches]

    if len(proches) > 1:
        return {
            "ref": None,
            "score": round(top_score / 100, 4),
            "ambigu": True,
            "candidats": candidats,
        }

    return {
        "ref": top_ref,
        "score": round(top_score / 100, 4),
        "ambigu": False,
        "candidats": candidats,
    }


def match_zone(texte: str, alias: dict, seuil: int = 85) -> Optional[dict]:
    """Rapproche une mention de zone : exact sur tous les alias, puis ``fuzz.ratio`` (len ≥ 5)."""
    t = normaliser(texte or "")
    if not t:
        return None
    zones = alias.get("zones") or {}
    for nom, al in zones.items():
        if t in [normaliser(a) for a in al]:
            return {"zone": nom, "score": 1.0}
    plat = [
        (normaliser(a), nom)
        for nom, al in zones.items()
        for a in al
        if len(normaliser(a)) >= 5
    ]
    if not plat:
        return None
    best = process.extractOne(
        t, [a for a, _ in plat], scorer=fuzz.ratio, score_cutoff=seuil
    )
    return {"zone": plat[best[2]][1], "score": round(best[1] / 100, 4)} if best else None


def match_variante(texte: str, alias: dict) -> Optional[str]:
    """Normalise une variante/taille (ex. ``'taille L'``, ``'en M'``, ``'grande'`` -> ``'L'``/``'M'``)."""
    t = re.sub(r"\b(taille|en)\b", "", normaliser(texte or "")).strip()
    return (alias.get("variantes") or {}).get(t)


def normaliser_paiement(texte: str) -> Optional[str]:
    """Normalise un mode de paiement cité vers le vocabulaire canonique du contrat."""
    t = normaliser(texte or "")
    if "livraison" in t:
        return "a_la_livraison"
    if any(k in t for k in ("cash", "espece")):
        return "especes"
    if any(k in t for k in ("momo", "mobile money", "mtn", "moov", "celtiis")):
        return "mobile_money"
    return None
