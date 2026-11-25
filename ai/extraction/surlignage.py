"""Génération optionnelle de HTML surligné pour l'interface web de Femi (décision D9).

Résout le risque de décalage d'offsets UTF-16 côté JavaScript en présence d'émojis :
les offsets ``debut``/``fin`` sont appliqués côté Python (caractères Unicode) et le texte
est intégralement échappé contre toute injection HTML/XSS.
"""

import html


def surligner(texte: str, champs: list[dict]) -> str:
    """Produit ``texte_html`` avec balises ``<mark data-champ='...' class='conf-...'>``."""
    pts = sorted(
        [
            c
            for c in champs
            if isinstance(c.get("debut"), int) and isinstance(c.get("fin"), int)
        ],
        key=lambda c: (c["debut"], c["fin"]),
    )
    out = ""
    pos = 0
    for c in pts:
        debut, fin = c["debut"], c["fin"]
        if debut < pos or fin > len(texte) or debut >= fin:
            continue
        out += html.escape(texte[pos:debut])
        cid = html.escape(str(c.get("id", "")), quote=True)
        couleur = html.escape(str(c.get("couleur", "orange")), quote=True)
        out += (
            f"<mark data-champ='{cid}' class='conf-{couleur}'>"
            f"{html.escape(texte[debut:fin])}</mark>"
        )
        pos = fin
    return out + html.escape(texte[pos:])
