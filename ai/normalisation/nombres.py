"""Normalisation déterministe des textes, nombres en lettres, montants et quantités (E3).

Règle de sécurité : si une chaîne est indéchiffrable, les fonctions retournent
strictement ``None`` (l'IA ne devine jamais une valeur).
"""

import re
import unicodedata
from typing import Optional

UNITES: dict[str, int] = {
    "zero": 0,
    "un": 1,
    "une": 1,
    "deux": 2,
    "trois": 3,
    "quatre": 4,
    "cinq": 5,
    "six": 6,
    "sept": 7,
    "huit": 8,
    "neuf": 9,
    "dix": 10,
    "onze": 11,
    "douze": 12,
    "treize": 13,
    "quatorze": 14,
    "quinze": 15,
    "seize": 16,
    "vingt": 20,
    "trente": 30,
    "quarante": 40,
    "cinquante": 50,
    "soixante": 60,
}

_DEVISE_RE = re.compile(
    r"(?:(?<=\d)|\b)(?:francs?\s*cfa|f\s?cfa|fcfa|francs?|xof|f)\b"
)
_MONTANT_NUM_RE = re.compile(
    r"(\d{1,3}(?:[ .\u00a0\u202f]\d{3})+|\d+)\s*(k|mille)?"
)


def sans_accents(s: str) -> str:
    """Supprime les signes diacritiques Unicode (décomposition NFD)."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


def normaliser(s: str) -> str:
    """Met en minuscules, retire accents et ponctuation et normalise les espaces."""
    s = sans_accents(s.lower())
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def mots_vers_entier(txt: str) -> Optional[int]:
    """Convertit un nombre écrit en français en entier (ex. ``'vingt-deux mille cinq cents'`` -> ``22500``).

    Retourne ``None`` si la chaîne est vide ou contient un mot non reconnu.
    """
    if not isinstance(txt, str):
        return None
    nettoye = sans_accents(txt.lower().strip())
    toks = [t for t in re.split(r"[\s\-]+", nettoye) if t and t != "et"]
    if not toks:
        return None

    total = 0
    cur = 0
    prev: Optional[str] = None
    for t in toks:
        t = {"cents": "cent", "vingts": "vingt", "milles": "mille"}.get(t, t)
        if t == "vingt" and prev == "quatre":
            cur += 76  # quatre (4) + 76 = 80 (quatre-vingt)
        elif t in UNITES:
            cur += UNITES[t]
        elif t == "cent":
            cur = max(cur, 1) * 100
        elif t == "mille":
            total += max(cur, 1) * 1000
            cur = 0
        else:
            return None
        prev = t
    return total + cur


def parse_montant(s: str) -> Optional[int]:
    """Normalise un montant cité en entier FCFA (jamais utilisé pour le calcul final).

    Exemples supportés : ``'15.000'``, ``'15 000'``, ``'15000f'``, ``'15k'``,
    ``'15 mille'``, ``'quinze mille'``, ``'8.000 fcfa'``, ``'22000 XOF'``.
    Retourne ``None`` si le texte n'est pas interprétable.
    """
    if not isinstance(s, str) or not s.strip():
        return None
    t = _DEVISE_RE.sub("", sans_accents(s.lower())).strip()
    if not t:
        return None
    m = _MONTANT_NUM_RE.fullmatch(t)
    if m:
        n = int(re.sub(r"[ .\u00a0\u202f]", "", m.group(1)))
        return n * 1000 if m.group(2) else n
    return mots_vers_entier(t)


def parse_quantite(s: str) -> Optional[int]:
    """Normalise une quantité (chiffre, préfixe/suffixe ``x3``/``3x`` ou lettres) en entier.

    Retourne ``None`` si indéchiffrable.
    """
    if not isinstance(s, str) or not s.strip():
        return None
    nettoye = sans_accents(s.strip().lower())
    nettoye = re.sub(r"^x\s*(?=\d)|(?<=\d)\s*x$", "", nettoye).strip()
    if not nettoye:
        return None
    return int(nettoye) if nettoye.isdigit() else mots_vers_entier(nettoye)
