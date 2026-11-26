"""Configuration centralisée du Bloc IA (seuils de confiance, chemins, graine).

Les seuils de confiance sont lus dans le fichier YAML des règles géré par Primel
(``data/regles.yaml``, clé ``seuils_confiance``) conformément au §7.9 du cahier des charges.
En cas d'absence du fichier ou de la clé, des valeurs par défaut sûres sont appliquées.
"""

from pathlib import Path
from typing import Union

import yaml

# Graine globale pour la reproductibilité (E18)
SEED: int = 42

# Seuils de confiance par défaut (CDC §6.4, décision D5)
DEFAUT: dict[str, float] = {
    "vert": 0.90,   # >= 0.90 : prérempli, à confirmer par la vendeuse
    "rouge": 0.60,  # <  0.60 : champ laissé vide, statut 'a_renseigner'
}

# Chemins relatifs par défaut (conformes à l'arborescence officielle §7.13)
RACINE_PROJET: Path = Path(__file__).resolve().parent.parent
CHEMIN_REGLES: Path = Path("data/regles.yaml")
CHEMIN_CATALOGUE: Path = Path("data/catalogue.csv")
CHEMIN_CLIENTS: Path = Path("data/clients.csv")
CHEMIN_TEST_MANUEL: Path = Path("data/test_manuel.jsonl")
CHEMIN_ROLES: Path = Path("ai/parseur/roles.yaml")
CHEMIN_ALIAS: Path = Path("ai/normalisation/alias.yaml")
CHEMIN_MODELE: Path = Path("ai/modeles/ner-v1")
CHEMIN_DONNEES: Path = Path("ai/entrainement/donnees")


def charger_seuils(path: Union[str, Path] = CHEMIN_REGLES) -> dict[str, float]:
    """Charge les seuils de confiance depuis ``data/regles.yaml`` ou ``data/rules.yaml``.

    Fonction pure vis-à-vis de l'état applicatif : ne crée ni ne modifie aucun fichier.
    Retourne les valeurs par défaut si le fichier ou la clé est absent.
    """
    candidates = [Path(path)]
    if Path(path) == CHEMIN_REGLES:
        candidates.extend([
            RACINE_PROJET / CHEMIN_REGLES,
            Path("data/rules.yaml"),
            RACINE_PROJET / "data" / "rules.yaml",
        ])
    cfg = {}
    for candidate in candidates:
        try:
            with open(candidate, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            break
        except FileNotFoundError:
            continue
    seuils_yaml = cfg.get("seuils_confiance") or {}
    return {**DEFAUT, **seuils_yaml}
