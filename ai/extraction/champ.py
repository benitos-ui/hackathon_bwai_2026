"""Construction d'un champ brut extrait au format plat officiel (§7.8)."""


def champ_brut(sp: dict, msg: dict, version: str) -> dict:
    """Convertit un span détecté sur un message en champ plat de la table ``champs_extraits``.

    Format retourné (§7.8) :
        ``{nom, valeur, message_id, debut, fin, confiance, version_modele}``
    """
    return {
        "nom": sp["label"].lower(),
        "valeur": sp["texte"],
        "message_id": msg["message_id"],
        "debut": sp["debut"],
        "fin": sp["fin"],
        "confiance": sp["confiance"],
        "version_modele": version,
    }
