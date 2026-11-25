"""Service d'extraction unifié — Étape 3 EXTRAIT (interface officielle §7.8).

Signature appelée par le pipeline de Bénito :
    ``extraire(messages, mode=None)`` -> ``list[champ]`` plat
    (``nom, valeur, message_id, debut, fin, confiance, version_modele, statut, couleur``)

Deux implémentations strictement interchangeables :
- ``ai/extraction/baseline.py`` : règles et expressions régulières (toujours disponible) ;
- ``ai/extraction/modele.py``   : modèle NER entraîné (DistilCamemBERT ou CRF, Étape 6).

En cas d'indisponibilité du modèle, le service bascule automatiquement sur la baseline
et journalise le repli (Logger ``ai.extraction``, exigence E17).
"""

import logging
import time
from typing import Optional

from ai.config import charger_seuils
from . import baseline
from .garde_fous import appliquer_garde_fous

log = logging.getLogger("ai.extraction")


def _modele_disponible():
    """Importe ``modele.py`` paresseusement et retourne le module s'il est disponible."""
    try:
        from . import modele  # type: ignore[attr-defined]
    except ImportError:
        return None
    return modele if modele.disponible() else None


def _impl(mode: Optional[str]):
    if mode == "baseline":
        return baseline, "baseline"
    if mode in (None, "modele"):
        mod = _modele_disponible()
        if mod is not None:
            return mod, "modele"
        if mode == "modele":
            log.warning("Modèle indisponible : repli automatique sur la baseline")
    return baseline, "baseline"


def get_mode(mode: Optional[str] = None) -> str:
    """Retourne le mode effectivement résolu (``'modele'`` ou ``'baseline'``)."""
    _, utilise = _impl(mode)
    return utilise


def extraire_brut(messages: list[dict], mode: Optional[str] = None) -> list[dict]:
    """Extrait les passages bruts sans garde-fous (utilisé par ``evaluation.py`` pour le F1)."""
    impl, _ = _impl(mode)
    return impl.extraire_brut(messages)


def extraire(
    messages: list[dict],
    mode: Optional[str] = None,
    seuils: Optional[dict[str, float]] = None,
) -> list[dict]:
    """Exécute l'étape 3 EXTRAIT avec garde-fous anti-hallucination et seuils de confiance."""
    t0 = time.time()
    impl, utilise = _impl(mode)
    brut = impl.extraire_brut(messages)
    seuils_actifs = seuils if seuils is not None else charger_seuils()
    champs = appliquer_garde_fous(brut, messages, seuils_actifs)
    duree_ms = int((time.time() - t0) * 1000)
    log.info(
        "extraction mode=%s messages=%d champs=%d rouges=%d duree_ms=%d",
        utilise,
        len(messages),
        len(champs),
        sum(c["couleur"] == "rouge" for c in champs),
        duree_ms,
    )
    return champs


__all__ = ["extraire", "extraire_brut", "get_mode"]
