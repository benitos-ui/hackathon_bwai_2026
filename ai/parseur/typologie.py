"""Classification déterministe de la typologie des messages WhatsApp (Addendum v1.1 §3.2).

Catégories officielles :
- ``COMMANDE`` : demande initiale d'achat
- ``CONFIRMATION`` : acceptation explicite de la commande ou de ses conditions
- ``MODIFICATION`` : changement de quantité, variante, produit ou adresse avant livraison
- ``ANNULATION`` : annulation totale ou partielle explicitement exprimée
- ``LIVRAISON`` : déclaration de livraison, refus, absence ou livraison partielle
- ``PAIEMENT`` : paiement annoncé ou confirmé
- ``RECLAMATION_RETOUR`` : problème après réception, demande de retour, échange ou remboursement
- ``INFORMATION`` : message ne modifiant pas directement le dossier

Socle linguistique (Addendum v1.1 §3.3 / D2) : français.
"""

import re

TYPES_MESSAGE: tuple[str, ...] = (
    "COMMANDE",
    "CONFIRMATION",
    "MODIFICATION",
    "ANNULATION",
    "LIVRAISON",
    "PAIEMENT",
    "RECLAMATION_RETOUR",
    "INFORMATION",
)

_RX_ANNULATION = re.compile(
    r"\b("
    r"j['’]?\s*annule|annule[rz]?|annulation|laisse[rz]?\s+tomber|"
    r"ne\s+livrez?\s+plus|plus\s+besoin|supprime[rz]?\s+(?:la\s+|ma\s+)?commande"
    r")\b",
    re.I,
)

_RX_LIVRAISON_LIVREUR = re.compile(
    r"\b("
    r"livr[ée]e?s?|refus[ée]e?s?|absent[e]?s?|manquant[e]?s?|"
    r"colis|remis[e]?|introuvable|[ée]chec|partielle?"
    r")\b",
    re.I,
)

_RX_LIVRAISON_GENERAL = re.compile(
    r"\b("
    r"livr[ée]e?s?|bien\s+re[çc]u[e]?s?|colis\s+re[çc]u|"
    r"refus[ée]e?s?|absent[e]?\s+[àa]\s+la\s+livraison|"
    r"livraison\s+(?:effectu[ée]e|faite|partielle|[ée]chou[ée]e)|"
    r"[ée]chec\s+(?:de\s+)?livraison|en\s+cours\s+de\s+livraison"
    r")\b",
    re.I,
)

_RX_RECLAMATION_RETOUR = re.compile(
    r"\b("
    r"r[ée]clamation|retour(?:ne[rz]?)?|renvoye[rz]?|[ée]change[rz]?|"
    r"rembourse[rz]?|remboursement|d[ée]fectueu\w*|ab[îi]m[ée]e?s?|"
    r"trou[ée]e?s?|d[ée]chir[ée]e?s?|cass[ée]e?s?|pas\s+conforme|"
    r"probl[èe]me\s+apr[èe]s|mauvais\s+article"
    r")\b",
    re.I,
)

_RX_MODIFICATION = re.compile(
    r"\b("
    r"finalement|non\s+plut[oô]t|plut[oô]t|change[rz]?|modifie[rz]?|"
    r"remplace[rz]?|mets?\s+(?:la\s+|en\s+)?taille|"
    r"passe[rz]?\s+[àa]\s+(?:la\s+)?taille|en\s+fait|au\s+lieu\s+de|"
    r"corrige[rz]?|nouvelle\s+adresse"
    r")\b",
    re.I,
)

_RX_COMMANDE = re.compile(
    r"\b("
    r"je\s+(?:veux|voudrais|prends|commande|souhaite)|j['’]?aimerais|"
    r"envoyez[\s-]?moi|mets[\s-]?moi|mettez[\s-]?moi|je\s+vais\s+prendre|"
    r"commande\s+de|ajoute[rz]?\s+(?:\d+|une?|deux|trois|quatre|cinq)"
    r")\b",
    re.I,
)

_RX_COMMANDE_IMPLICITE = re.compile(
    r"\b(?:\d{1,2}|une?|deux|trois|quatre|cinq|six|sept|huit|neuf|dix)\s+"
    r"(?:robes?|sacs?|s[ée]rums?|ensembles?|pagnes?|beurres?|karit[ée])\b",
    re.I,
)

_RX_PAIEMENT = re.compile(
    r"\b("
    r"pay[ée]e?s?|paiement|r[ée]gl[ée]e?s?|r[èe]glement|momo|mobile\s+money|"
    r"esp[èe]ces|cash|virement|transfert|mtn|moov|celtiis|vers[ée]e?|sold[ée]e?|acompte"
    r")\b",
    re.I,
)

_RX_CONFIRMATION = re.compile(
    r"\b("
    r"je\s+confirme|confirm[ée]e?|c['’]?est\s+not[ée]|c['’]?est\s+bon|"
    r"d['’]?accord|ok\s+pour|parfait|valid[ée]e?|oui|entendu|not[ée]"
    r")\b",
    re.I,
)


def classifier_message(texte: str, role: str = "client") -> str:
    """Classe un message dans l'une des 8 catégories officielles (Addendum §3.2).

    Fonction pure et déterministe basée sur le rôle et des indices lexicaux en français.
    """
    t = (texte or "").strip()
    if not t:
        return "INFORMATION"

    # Le livreur déclare en priorité un événement de livraison (livré, refus, absence, partiel)
    if role == "livreur":
        if _RX_LIVRAISON_LIVREUR.search(t):
            return "LIVRAISON"
        if _RX_PAIEMENT.search(t):
            return "PAIEMENT"

    if _RX_ANNULATION.search(t):
        return "ANNULATION"
    if _RX_RECLAMATION_RETOUR.search(t):
        return "RECLAMATION_RETOUR"
    if _RX_LIVRAISON_GENERAL.search(t):
        return "LIVRAISON"
    if _RX_MODIFICATION.search(t):
        return "MODIFICATION"
    if _RX_COMMANDE.search(t) or (role == "client" and _RX_COMMANDE_IMPLICITE.search(t)):
        return "COMMANDE"
    if _RX_PAIEMENT.search(t):
        return "PAIEMENT"
    if _RX_CONFIRMATION.search(t):
        return "CONFIRMATION"
    return "INFORMATION"
