# Licences des composants tiers — Partie Bloc IA (Hackathon BWAI 2026)

> Recensement des modèles et bibliothèques utilisés par le module `ai/`, `scripts/telecharger_modele.py` et `tests/ai/`.  
> Les versions exactes installées dans l'environnement de référence sont épinglées dans `requirements.txt` (exigence E18).

---

## 1. Modèles pré-entraînés (référencés pour le fine-tuning)

| Composant | Source / Identifiant | Rôle dans le Bloc IA | Licence |
|---|---|---|---|
| **DistilCamemBERT** | `cmarkea/distilcamembert-base` (Hugging Face Hub) | Modèle de base pour le fine-tuning NER Transformer (`ai/entrainement/train.py`, `ner-v1`) | **MIT** *(à reconfirmer sur la fiche Hugging Face lors du téléchargement des poids)* |

---

## 2. Bibliothèques Python directes du Bloc IA

| Bibliothèque | Version épinglée | Rôle dans le Bloc IA | Licence |
|---|---:|---|---|
| `transformers` | `5.20.2` | Tokenisation rapide, chargement, fine-tuning et inférence Transformer NER | **Apache-2.0** |
| `datasets` | `5.2.0` | Chargement et mapping des jeux d'entraînement / validation JSONL | **Apache-2.0** |
| `torch` | `2.14.1` | Backend PyTorch (inférence, entraînement, optimisation L-BFGS de température) | **BSD-3-Clause** *(distribution incluant composants Apache-2.0 / BSD-2-Clause / MIT / BSL-1.0)* |
| `accelerate` | `1.15.0` | Orchestration CPU/GPU pour `transformers.Trainer` | **Apache-2.0** |
| `seqeval` | `1.2.2` | Calcul du F1 strict sur séquences BIO (`train.py`, `crf_backup.py`) | **MIT** |
| `rapidfuzz` | `3.14.5` | Rapprochement flou rapide (`WRatio`, `ratio`) pour produits, zones et clients | **MIT** |
| `sklearn-crfsuite` | `0.5.0` | Plan de secours CPU : modèle NER CRF (`crf-v1`) | **MIT** |
| `python-crfsuite` | `0.9.12` | Moteur C++ sous-jacent de `sklearn-crfsuite` (CRFsuite) | **MIT** *(wrapper)* / **BSD-3-Clause** *(CRFsuite)* |
| `scikit-learn` | `1.7.2` | Utilitaires ML et métriques complémentaires | **BSD-3-Clause** |
| `scipy` | `1.15.3` | Optimisation scalaire convexe bornée (`minimize_scalar`) pour calibration CRF | **BSD-3-Clause** |
| `numpy` | `2.2.6` | Calcul numérique vectorisé (alignement, calibration, argmax) | **BSD-3-Clause** |
| `joblib` | `1.6.0` | Sérialisation locale des artefacts CRF (`crf_model.joblib`) | **BSD-3-Clause** |
| `PyYAML` | `6.0.4` | Lecture de `data/regles.yaml`, `ai/parseur/roles.yaml`, `ai/normalisation/alias.yaml` | **MIT** |
| `pytest` | `9.2.0` | Exécution de la suite de tests automatisés (`pytest tests/ai -q`) | **MIT** |

---

## 3. Dépendances transitives principales

| Bibliothèque | Version épinglée | Licence |
|---|---:|---|
| `huggingface_hub` | `2.4.0` | Apache-2.0 |
| `tokenizers` | `0.23.3` | Apache-2.0 |
| `safetensors` | `0.8.0` | Apache-2.0 |
| `pandas` | `2.3.3` | BSD-3-Clause |
| `pyarrow` | `25.0.1` | Apache-2.0 |
| `pydantic` | `2.14.4` | MIT |
| `regex` | `2026.9.29` | Apache-2.0 |
| `tqdm` | `4.70.1` | MPL-2.0 / MIT |

*Toutes les bibliothèques utilisées par le Bloc IA sont publiées sous licences open source permissives compatibles (MIT, BSD-3-Clause, Apache-2.0). Aucune dépendance propriétaire ni service payant externe n'est requis.*
