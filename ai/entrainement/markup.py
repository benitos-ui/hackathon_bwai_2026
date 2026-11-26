"""Parseur du format d'annotation inline ``[[texte|LABEL]]`` (Guide §8.2 & §10.2).

Utilisé de façon identique par :
- le générateur de conversations synthétiques (``generateur.py``) ;
- le jeu de test manuel rédigé par les 4 membres (``data/test_manuel.jsonl``).

Les offsets ``debut`` et ``fin`` (fin exclue) sont exprimés en caractères Unicode
relatifs au texte débalisé (décision D9).
"""

import re

from ai.extraction.schema import ENTITES

MARK = re.compile(r"\[\[(.+?)\|([A-Z_]+)\]\]")


def parse_markup(s: str) -> tuple[str, list[dict]]:
    """Extrait le texte brut et les spans annotés depuis une chaîne balisée.

    Exemple :
        ``'je veux [[2|QUANTITE]] robes'``
        -> ``('je veux 2 robes', [{'label': 'QUANTITE', 'debut': 8, 'fin': 9, 'texte': '2'}])``
    """
    texte, spans, last = "", [], 0
    for m in MARK.finditer(s):
        texte += s[last:m.start()]
        debut = len(texte)
        contenu = m.group(1)
        texte += contenu
        spans.append({
            "label": m.group(2),
            "debut": debut,
            "fin": len(texte),
            "texte": contenu,
        })
        last = m.end()
    return texte + s[last:], spans


def valider_spans(texte: str, spans: list[dict]) -> list[str]:
    """Vérifie la cohérence d'une liste de spans (offsets, contenu, labels connus).

    Retourne une liste d'erreurs (vide si tout est valide).
    """
    erreurs: list[str] = []
    entites_valides = set(ENTITES)
    for i, sp in enumerate(spans):
        label = sp.get("label")
        debut = sp.get("debut")
        fin = sp.get("fin")
        contenu = sp.get("texte")
        if label not in entites_valides:
            erreurs.append(f"span[{i}]: label inconnu '{label}'")
        if not (isinstance(debut, int) and isinstance(fin, int) and 0 <= debut < fin <= len(texte)):
            erreurs.append(f"span[{i}]: offsets invalides ({debut}, {fin}) pour longueur {len(texte)}")
        elif texte[debut:fin] != contenu:
            erreurs.append(
                f"span[{i}]: texte attendu '{contenu}' != extrait '{texte[debut:fin]}'"
            )
    return erreurs
