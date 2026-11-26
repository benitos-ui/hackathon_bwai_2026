"""Schéma d'entités et labels BIO du service d'extraction NER (CDC §6.1, Guide §5.2 & §8.1).

Un seul label ``QUANTITE`` est prédit par le modèle : la distinction entre
``quantite_commandee`` et ``quantite_livree`` est résolue de manière déterministe
à partir du rôle de l'auteur du message (décision D3).
"""

ENTITES: list[str] = [
    "PRODUIT",
    "VARIANTE",
    "QUANTITE",
    "PRIX_CITE",
    "CODE_PROMO",
    "ZONE",
    "DATE_LIVRAISON",
    "PAIEMENT",
    "REFUS",
    "MOTIF_REFUS",
    "CLIENT",
]

LABELS: list[str] = ["O"] + [f"{p}-{e}" for e in ENTITES for p in ("B", "I")]
LABEL2ID: dict[str, int] = {label: idx for idx, label in enumerate(LABELS)}
ID2LABEL: dict[int, str] = {idx: label for label, idx in LABEL2ID.items()}
