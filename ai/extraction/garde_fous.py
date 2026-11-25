"""Garde-fous anti-hallucination et seuils de revue humaine (§6.4, §7.8, D8 & D10).

Appliqués systématiquement APRÈS l'extraction (baseline ou modèle) :
1. Contrôle strict de présence dans le texte source : ``0 <= debut < fin <= len(texte)``
   et ``texte[debut:fin] == valeur``. Toute valeur absente est rejetée (``valeur=None``,
   ``statut='a_renseigner'``, ``couleur='rouge'``, ``rejet='absent_du_texte'``).
2. Seuils de confiance (lus dans ``data/regles.yaml``) :
   - ``confiance < seuils['rouge']`` -> champ vidé (``valeur=None``, ``statut='a_renseigner'``,
     ``couleur='rouge'``, ``rejet='confiance_basse'``) ;
   - ``confiance >= seuils['vert']`` -> ``statut='prerempli'``, ``couleur='vert'`` ;
   - entre les deux -> ``statut='prerempli'``, ``couleur='orange'``.
"""


def appliquer_garde_fous(
    champs: list[dict],
    messages: list[dict],
    seuils: dict[str, float],
) -> list[dict]:
    """Filtre et qualifie chaque champ brut sans jamais muter les entrées."""
    textes = {m["message_id"]: m["texte"] for m in messages}
    out: list[dict] = []

    for c in champs:
        mid = c.get("message_id")
        debut = c.get("debut")
        fin = c.get("fin")
        valeur = c.get("valeur")
        t = textes.get(mid, "") if mid is not None else ""

        present = (
            mid in textes
            and isinstance(debut, int)
            and isinstance(fin, int)
            and isinstance(valeur, str)
            and 0 <= debut < fin <= len(t)
            and t[debut:fin] == valeur
        )

        if not present:
            out.append({
                **c,
                "valeur": None,
                "message_id": None,
                "debut": None,
                "fin": None,
                "confiance": 0.0,
                "statut": "a_renseigner",
                "couleur": "rouge",
                "rejet": "absent_du_texte",
            })
        elif c["confiance"] < seuils["rouge"]:
            out.append({
                **c,
                "valeur": None,
                "statut": "a_renseigner",
                "couleur": "rouge",
                "rejet": "confiance_basse",
            })
        else:
            couleur = "vert" if c["confiance"] >= seuils["vert"] else "orange"
            out.append({**c, "statut": "prerempli", "couleur": couleur})

    return out
