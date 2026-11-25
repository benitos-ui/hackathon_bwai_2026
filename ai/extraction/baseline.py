"""Baseline déterministe à base de lexique et d'expressions régulières (Jalon H6).

Rôle (CDC §6.2 & §7.8) :
- Permet un parcours fonctionnel de bout en bout dès H6 sans attendre le modèle NER.
- Sert de référence objective pour mesurer l'apport réel du modèle entraîné.
- Sert de repli automatique si les poids du modèle ne sont pas disponibles.

La baseline attribue une confiance fixe (``0.75`` = ``orange``) car une méthode à règles
n'est pas calibrée en probabilité ; la vendeuse relit donc attentivement chaque valeur.
"""

import re

from .champ import champ_brut

VERSION: str = "baseline-1.0"
CONFIANCE_BASELINE: float = 0.75

NB = r"(?:\d{1,2}|une?|deux|trois|quatre|cinq|six|sept|huit|neuf|dix)"
OBJETS = r"(?:robes?|sacs?|s[ée]rums?|ensembles?|pagnes?|beurres?|cr[èe]mes?)"

REGLES: list[tuple[str, re.Pattern, int]] = [
    ("QUANTITE", re.compile(rf"\bx?({NB})\b(?=\s+{OBJETS})", re.I), 1),
    ("QUANTITE", re.compile(rf"\b({NB})\b(?=\s+en\s+(?:XL|S|M|L)\b)", re.I), 1),
    (
        "QUANTITE",
        re.compile(
            rf"\b(?:finalement|plut[oô]t|mets?|prends?|change[rz]?\s+(?:pour|en))\s+"
            rf"(?:en\s+)?({NB})\b(?!\s*(?:k|f\s?cfa|fcfa|francs?|xof|f|%|/|h)\b)",
            re.I,
        ),
        1,
    ),
    (
        "PRODUIT",
        re.compile(
            r"\b("
            r"robes?\s+(?:wax\s+)?ayoka|robes?\s+wax|robes?|"
            r"ensembles?\s+pagne(?:\s+s[èe]nami)?|ensembles?\s+s[èe]nami|"
            r"sacs?(?:\s+[àa]\s+main)?(?:\s+lagune)?|"
            r"s[ée]rums?(?:\s+(?:vitamine\s+c|vit\.?\s*c))?|"
            r"beurre\s+de\s+karit[ée]"
            r")\b",
            re.I,
        ),
        1,
    ),
    ("VARIANTE", re.compile(r"(?:taille\s+|\ben\s+|\b)(XL|S|M|L)\b(?!\w)"), 1),
    ("VARIANTE", re.compile(r"\btaille\s+(xl|s|m|l)\b", re.I), 1),
    (
        "PRIX_CITE",
        re.compile(
            r"\b(\d{1,3}(?:[ .\u00a0\u202f]\d{3})+|\d+)\s*(?:k|f\s?cfa|fcfa|francs?|xof|f)\b",
            re.I,
        ),
        0,
    ),
    ("CODE_PROMO", re.compile(r"\b([A-Z]{4,}\d{1,3})\b"), 1),
    (
        "ZONE",
        re.compile(r"\b(cotonou|abomey[\s-]?calavi|calavi|porto[\s-]?novo)\b", re.I),
        1,
    ),
    (
        "DATE_LIVRAISON",
        re.compile(
            r"\b(demain|aujourd'?hui|ce soir|lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|\d{1,2}/\d{1,2})\b",
            re.I,
        ),
        1,
    ),
    (
        "PAIEMENT",
        re.compile(
            r"\b(paiement\s+[àa]\s+la\s+livraison|cash|esp[èe]ces|momo|mobile\s+money|mtn|moov|celtiis)\b",
            re.I,
        ),
        1,
    ),
    (
        "MOTIF_REFUS",
        re.compile(
            r"\b(trop\s+(?:petite?|grande?|courte?|longue?|ch[èe]re?)|pas\s+la\s+bonne\s+taille|d[ée]fectueu\w+)\b",
            re.I,
        ),
        1,
    ),
    (
        "REFUS",
        re.compile(
            r"\b(refus[ée]e?\s+(?:la|le|les|l')?\s*\w+"
            r"(?:\s+(?:wax|ayoka|pagne|s[èe]nami|lagune))?"
            r"(?:\s+(?:XL|S|M|L))?)\b",
            re.I,
        ),
        1,
    ),
]


def spans(texte: str) -> list[dict]:
    """Détecte les passages d'entités dans un message unique (offsets Unicode, fin exclue)."""
    out: list[dict] = []
    for label, rx, groupe in REGLES:
        for m in rx.finditer(texte):
            debut, fin = m.start(groupe), m.end(groupe)
            if not any(
                s["label"] == label and s["debut"] < fin and s["fin"] > debut
                for s in out
            ):
                out.append({
                    "label": label,
                    "debut": debut,
                    "fin": fin,
                    "texte": texte[debut:fin],
                    "confiance": CONFIANCE_BASELINE,
                })
    return sorted(out, key=lambda s: (s["debut"], s["fin"], s["label"]))


def extraire_brut(messages: list[dict]) -> list[dict]:
    """Extrait les champs bruts (sans garde-fous) sur l'ensemble d'un fil de messages."""
    return [
        champ_brut(sp, msg, VERSION)
        for msg in messages
        for sp in spans(msg["texte"])
    ]
