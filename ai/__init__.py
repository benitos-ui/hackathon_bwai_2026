"""Bloc IA — Assistant IA de facturation Boutique X (Hackathon BWAI 2026).

Bibliothèque pure et déterministe :
- ``ai.parseur`` : étape 2 ANALYSÉ (``analyser``, ``FormatInvalide``)
- ``ai.extraction`` : étape 3 EXTRAIT (``extraire``, ``extraire_brut``)
- ``ai.normalisation`` : étape 4 NORMALISÉ (``normaliser_dossier``)
- ``ai.entrainement`` : génération synthétique, entraînement, calibration, évaluation

Règle d'architecture (§7.2) : aucune dépendance vers ``app.*``, ``ui/``, FastAPI ou la base de données.
"""
