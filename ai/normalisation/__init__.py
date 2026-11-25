"""Point d'entrée officiel du module de normalisation — Étape 4 NORMALISÉ (§2.2 & §7.4)."""

from .dossier import assembler_lignes, en_contrat, normaliser_champs, normaliser_dossier

__all__ = [
    "normaliser_dossier",
    "normaliser_champs",
    "assembler_lignes",
    "en_contrat",
]
