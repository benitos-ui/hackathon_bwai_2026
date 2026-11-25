# Cartographie technique et pédagogique — Bloc IA

> Référentiel vivant du module `ai/` (Boutique X — Hackathon BWAI 2026). Mis à jour à chaque étape validée.

---

## 1. Arborescence et localisation des fichiers

| Chemin | Rôle et contenu | Statut |
|---|---|---|
| `requirements.txt` | Dépendances Python du Bloc IA épinglées par `pip freeze` (65 paquets, exigence E18) | Épinglé (Étape 7b) |
| `LICENSES.md` | Inventaire officiel des licences open source (modèle de base + bibliothèques directes et transitives du Bloc IA) | Créé (Étape 7b) |
| `ai/__init__.py` | Déclaration du package `ai` (bibliothèque pure, sans dépendance `app.*` ni `ui/`) | Créé (Étape 1) |
| `ai/config.py` | Graine globale (`SEED=42`), chemins par défaut et `charger_seuils()` depuis `data/regles.yaml` | Créé (Étape 1) |
| `ai/extraction/schema.py` | 11 entités métier (`ENTITES`) et 23 labels BIO (`LABELS`, `LABEL2ID`, `ID2LABEL`) | Créé (Étape 1) |
| `ai/entrainement/__init__.py` | Déclaration du sous-package `ai.entrainement` | Créé (Étape 1) |
| `ai/entrainement/markup.py` | Parseur `parse_markup()` (`[[texte|LABEL]]` → texte + spans Unicode) et `valider_spans()` | Créé (Étape 1) |
| `ai/parseur/__init__.py` | Point d'entrée `analyser()` (étape 2 ANALYSÉ : messages typés, médias non pris en charge, empreinte, client) et exports (`FormatInvalide`, `classifier_message`, `TYPES_MESSAGE`) | Mis à jour (Étape 4b) |
| `ai/parseur/typologie.py` | Classification déterministe des 8 types de messages (`COMMANDE`, `CONFIRMATION`, `MODIFICATION`, `ANNULATION`, `LIVRAISON`, `PAIEMENT`, `RECLAMATION_RETOUR`, `INFORMATION`, Addendum §3.2) | Créé (Étape 4b) |
| `ai/parseur/whatsapp.py` | `parser_export()`, `parser_export_detaille()`, `detecter_media_non_pris_en_charge()` (§3.3), `messages_depuis_simulateur()`, `empreinte_fil()` | Mis à jour (Étape 4b) |
| `ai/parseur/client.py` | `identifier_client()` : numéro de téléphone (8 derniers chiffres) puis `rapidfuzz.WRatio` sur le nom (seuil 85) | Créé (Étape 2) |
| `ai/parseur/roles.yaml` | Table YAML des auteurs connus (`vendeuse`, `livreur`) ; tout autre auteur est classé `client` | Créé (Étape 2) |
| `tests/ai/test_parseur.py` | Tests unitaires `pytest` du parseur, des empreintes, du simulateur et de l'identification client (E1) | Créé (Étape 2) |
| `ai/normalisation/__init__.py` | Exports officiels de l'étape 4 NORMALISÉ (`normaliser_dossier`, `normaliser_champs`, `assembler_lignes`, `en_contrat`) | Créé (Étape 3) |
| `ai/normalisation/nombres.py` | Normalisation Unicode/accents, conversion français→entier (`mots_vers_entier`), `parse_montant()` et `parse_quantite()` | Créé (Étape 3) |
| `ai/normalisation/alias.yaml` | Table YAML des alias produits (`ART-001`..`ART-005`), zones canoniques et variantes | Créé (Étape 3) |
| `ai/normalisation/rapprochement.py` | Chargeurs CSV/YAML et rapprochement `rapidfuzz` (`match_produit` avec détection `A_PRODUIT_AMBIGU`/T12, `match_zone`, `match_variante`, `normaliser_paiement`) | Mis à jour (Étape 4b) |
| `ai/normalisation/dossier.py` | Normalisation (`ref` + `valeur_brute`), séparation commandé/livré/refusé (T13), modifications T11, détection T12/T20 (`A_PRODUIT_AMBIGU`, `A_CONVERSATION`), assemblage et `en_contrat()` | Mis à jour (Étape 4b) |
| `tests/ai/test_nombres.py` | Suite `pytest` couvrant 61 formulations E3, valeurs indéchiffrables, exclusion des `REFUS` et format contrat Annexe A | Créé (Étape 3) |
| `ai/extraction/__init__.py` | Service unifié `extraire()`, `extraire_brut()`, `get_mode()` (étape 3 EXTRAIT) avec repli automatique sur la baseline et logs `ai.extraction` | Créé (Étape 4) |
| `ai/extraction/champ.py` | Fabrique `champ_brut()` au format plat officiel (§7.8) | Créé (Étape 4) |
| `ai/extraction/baseline.py` | Extracteur baseline déterministe par règles/regex (`baseline-1.0`, confiance fixe `0.75`, support quantité en modification T11) | Mis à jour (Étape 4b) |
| `ai/extraction/modele.py` | Inférence NER calibrée en cascade (`ner-v1` DistilCamemBERT → `crf-v1` CRF CPU), même signature `extraire_brut(messages)` (§7.8) | Créé (Étape 6b) |
| `ai/extraction/garde_fous.py` | `appliquer_garde_fous()` : contrôle de présence exacte dans le texte source + seuils `vert`/`orange`/`rouge` | Créé (Étape 4) |
| `ai/extraction/surlignage.py` | `surligner()` : génération sécurisée (échappement HTML) de `texte_html` en offsets Unicode (D9) | Créé (Étape 4) |
| `tests/ai/test_garde_fous.py` | 9 tests `pytest` : garde-fous anti-hallucination, seuils, repli automatique baseline (isolé via `monkeypatch`), surlignage HTML/Unicode | Mis à jour (Étape 6b) |
| `tests/ai/test_exemple_awa.py` | 2 tests `pytest` : scénario complet d'Awa (CDC §3.4) de bout en bout + déterminisme | Créé (Étape 4) |
| `tests/ai/test_addendum_v11.py` | 24 tests `pytest` : typologie §3.2, médias non pris en charge §3.3, modifications T11, ambiguïté produit T12, T13/§4 et multi-commandes T20 | Créé (Étape 4b) |
| `ai/entrainement/generateur.py` | Générateur synthétique pur et reproductible : 60 gabarits (12 familles × 5), bruit contrôlé, split disjoint par gabarit (`train`/`val`) | Mis à jour (Étape 6b) |
| `ai/entrainement/train.py` | Script Colab/Kaggle de fine-tuning `DistilCamemBERT` (`ner-v1`, `SEED=42`) + calibration par température (L-BFGS) sur `val.jsonl` | Créé (Étape 6a) |
| `ai/entrainement/crf_backup.py` | Plan B CPU (`sklearn-crfsuite`, `crf-v1`) + calibration des marginales sur `val.jsonl` (`F1_val=0.8869`, `T=1.0614`, `ECE=0.0138`) | Mis à jour (Étape 6b) |
| `ai/entrainement/evaluation.py` | Évaluation comparative Baseline vs Modèle : F1 strict/souple par entité, ECE, taux de revue (`vert`/`orange`/`rouge`), catégorisation des erreurs (`--corpus auto/test/val`) | Créé (Étape 7a) |
| `tests/ai/test_generateur.py` | 6 tests `pytest` : couverture ≥ 40 gabarits, déterminisme, split disjoint, 11 entités, offsets Unicode/émojis et messages sans entité | Créé (Étape 5) |
| `tests/ai/test_modele.py` | 6 tests `pytest` : inférence calibrée `crf-v1`, cas Awa en mode `modele`, déterminisme, cascade `ner-v1 -> crf-v1 -> baseline`, SHA-256 et Zip-Slip | Créé (Étape 6b) |
| `tests/ai/test_evaluation.py` | 5 tests `pytest` : chargement double format, F1 strict vs souple, ECE, 5 catégories d'erreurs, évaluation comparative | Créé (Étape 7a) |
| `ai/entrainement/donnees/` | Jeux synthétiques générés (`train.jsonl` : 4 817 msg, `val.jsonl` : 1 183 msg, `seed=42`) | Régénéré (Étape 6b) |
| `ai/modeles/` | Poids locaux hors Git (`ner-v1/` pour Transformer, `crf-v1/` entraîné localement — ignorés par `.gitignore`) | Actif (Étape 6b) |
| `tests/ai/` | Suite de tests automatisés `pytest` du Bloc IA (**128 tests verts**) | Actif (Étape 7a) |
| `scripts/telecharger_modele.py` | Téléchargement sécurisé des poids via `BWAI_MODELE_URL` ou CLI avec vérification SHA-256, suppression si corrompu et protection Zip-Slip (§7.11) | Créé (Étape 6b) |
| `docs/resultats_ia.json` | Benchmark comparatif interne (`baseline-1.0` vs `crf-v1` sur `val.jsonl`, marqué `est_score_final_publiable: false`) | Généré (Étape 7a) |
| `docs/fiche_ia.md` | Fiche IA complète pour le jury : architecture en cascade, données/split, résultats internes vs test manuel, analyse d'erreurs, seuils, limites et reproductibilité | Créé (Étape 7b) |
| `docs/journal_ia.md` | Journal chronologique complet des étapes 1 à 7b, justifications et résultats de tests | Finalisé (Étape 7b) |
| `docs/cartographie_ia.md` | Cartographie complète des fichiers, concepts IA et dépendances (ce fichier) | Finalisé (Étape 7b) |

---

## 2. Notions et concepts abordés

- **NER (Named Entity Recognition) & schéma BIO** : étiquetage de séquences où chaque token reçoit `O` (Outside), `B-<ENTITÉ>` (Beginning) ou `I-<ENTITÉ>` (Inside). Permet d'extraire des passages exacts du texte source sans génération libre, donc sans hallucination de valeurs.
- **Offsets Unicode (fin exclue)** : positions `[debut, fin[` en points de code Unicode Python (`str`), permettant de vérifier strictement que `texte[debut:fin] == valeur` et de surligner exactement le passage source (attention au décalage UTF-16 côté navigateur avec les émojis, décision D9).
- **Balisage inline `[[texte|LABEL]]`** : syntaxe légère lisible par un humain et analysable par expression régulière, unifiant la génération synthétique et l'annotation manuelle du jeu de test.
- **Configuration externalisée et seuils de confiance** : lecture des seuils (`vert ≥ 0,90`, `orange ∈ [0,60; 0,90[`, `rouge < 0,60`) depuis `data/regles.yaml` afin de séparer le code des paramètres métier et de faciliter la reproductibilité.
- **Pureté fonctionnelle et déterminisme** : une fonction pure renvoie toujours la même sortie pour une même entrée et n'altère aucun état externe (fichier, base). Indispensable pour la reprise après interruption (E12) et l'idempotence (E8).
- **Empreinte logique SHA-256 & idempotence (E1, E8)** : hachage cryptographique SHA-256 de la représentation JSON canonique `[(horodatage, auteur, texte), ...]` d'un fil. Garantit qu'un même fil importé deux fois (ou reçu via export `.txt` puis simulateur web) génère strictement la même empreinte logique et ne crée aucun doublon.
- **Rapprochement flou (`rapidfuzz.fuzz.WRatio`)** : score de similarité composite (0–100) combinant ratio de Levenshtein, correspondance partielle et indépendance à l'ordre des mots. Utilisé avec un seuil strict (`score_cutoff=85`) pour rapprocher un prénom/nom d'auteur (ex. `Awa` → `Awa Dossou`) lorsque le numéro de téléphone n'est pas disponible.
- **Validation stricte d'entrée (`FormatInvalide`)** : exception dédiée levée dès qu'un export est vide, mal formé ou sans message reconnu, traduite côté API (Bénito) en erreur HTTP 422 avec message explicite.
- **Distance de Levenshtein (`fuzz.ratio` vs `fuzz.WRatio`)** : `ratio` compare deux chaînes entières (adapté aux noms de zones ≥ 5 caractères pour tolérer une faute sans faux positif), tandis que `WRatio` combine plusieurs heuristiques partielles/ordonnées (adapté aux libellés produits libres face aux alias catalogue).
- **Normalisation déterministe sans hallucination (E3)** : toute chaîne numérique, montant, variante, zone ou produit non interprétable retourne `None`, ce qui bascule le champ en `a_renseigner` (`rouge`, `confiance = 0.0`) pour reprise humaine.
- **Séparation commandé / livré par rôle & isolation des refus** : le rôle de l'auteur (`livreur` vs `client`/`vendeuse`) affecte de manière déterministe `quantite_livree` ou `quantite_commandee` ; toute entité chevauchant un span `REFUS` est exclue des lignes et isolée dans `signaux.refus`.
- **Format plat vs contrat imbriqué (`en_contrat()`)** : les champs transitent à plat en interne/base (`message_id`, `debut`, `fin`) conformément au §7.8 et sont convertis en objet imbriqué `source: {message_id, debut, fin}` pour le JSON API (Annexe A, décision D1).
- **Baseline à règles vs modèle entraîné (§6.2)** : la baseline (`baseline-1.0`) repose sur des expressions régulières déterministes à confiance fixe (`0.75`). Elle garantit un fonctionnement immédiat hors-ligne et sert de mètre-étalon objectif pour démontrer la valeur ajoutée du modèle NER.
- **Garde-fous anti-hallucination (§7.8, E2)** : double filtre post-extraction imposant que chaque valeur existe mot pour mot dans le texte source aux indices `[debut:fin]` et dépasse le seuil `rouge` (`0.60`), faute de quoi le champ est vidé (`None`, `a_renseigner`).
- **Repli gracieux (Graceful Fallback)** : bascule automatique et tracée (`WARNING` sur `ai.extraction`) du mode `modele` vers `baseline` si les poids locaux sont absents, éliminant tout point de défaillance unique le jour de la démonstration.
- **Surlignage Unicode sécurisé (D9)** : application des balises `<mark>` en Python sur les indices Unicode avant échappement HTML (`html.escape`), évitant les décalages UTF-16 de JavaScript sur les émojis et toute faille XSS.
- **Typologie des messages & périmètre linguistique (Addendum §3.2–§3.3)** : classification déterministe en 8 catégories (`COMMANDE`, `CONFIRMATION`, `MODIFICATION`, `ANNULATION`, `LIVRAISON`, `PAIEMENT`, `RECLAMATION_RETOUR`, `INFORMATION`) sur le socle français (Fon / code-switching traité comme extension séparée) et signalement explicite des médias non pris en charge (`medias_non_pris_en_charge`).
- **Détection d'ambiguïtés métier (`A_PRODUIT_AMBIGU`, `A_CONVERSATION`, T11/T12/T20)** : refus de sélection automatique lorsque deux produits catalogue sont trop proches (≤ 5 points `WRatio`), mise à jour tracée des modifications ultérieures sans doublon silencieux, et signalement des fils multi-commandes/multi-clients via `signaux.ambiguite = True`.
- **Split disjoint par gabarit & data augmentation contrôlée (Guide §10.1)** : séparation `train`/`val` au niveau des gabarits (`tid % 5 == 0` → validation) pour éviter le sur-apprentissage syntaxique, combinée à un bruit orthographique contrôlé (fautes, accents, casse, formats numériques) appliqué avant `parse_markup()` afin de garantir des offsets Unicode exacts.
- **Calibration par mise à l'échelle de la température (Temperature Scaling)** : post-traitement probabiliste divisant les logits (ou log-probabilités marginales CRF) par un scalaire `T > 0` optimisé exclusivement sur la validation (`val.jsonl`) afin de minimiser la log-vraisemblance négative et l'ECE sans modifier les prédictions argmax.
- **CRF (Conditional Random Fields, `sklearn-crfsuite`)** : modèle probabiliste séquentiel linéaire léger sur CPU exploitant des traits lexicaux/contextuels (±2 tokens, bigrammes, sans accents, casse, chiffres) et des transitions BIO globales, offrant un plan de secours hors-ligne performant (`crf-v1`) et calibrable.
- **Vérification d'intégrité SHA-256 & protection Zip-Slip (§7.11)** : contrôle cryptographique de l'archive des poids avant extraction, suppression automatique en cas de divergence et validation stricte des chemins extraits pour prévenir toute traversée de répertoire.
- **Évaluation NER stricte vs souple, ECE & analyse d'erreurs (Guide §12)** : le F1 strict exige l'égalité exacte `(label, debut, fin)` tandis que le F1 souple tolère un chevauchement de même label (isolant les décalages de frontières) ; l'ECE (Expected Calibration Error) mesure l'écart moyen entre confiance affichée et précision empirique par tranche de probabilité.

---

## 3. Outils et bibliothèques du Bloc IA

> Licences à reporter dans `LICENSES.md` et `docs/fiche_ia.md` (vérification officielle à chaque ajout).

| Bibliothèque | Rôle dans le Bloc IA | Licence |
|---|---|---|
| `transformers` | Chargement, fine-tuning et inférence du modèle NER (`DistilCamemBERT`) | Apache-2.0 |
| `datasets` | Structuration et mapping des jeux d'entraînement / validation pour Hugging Face Trainer | Apache-2.0 |
| `torch` | Backend PyTorch (entraînement, inférence CPU, optimisation L-BFGS de la température) | BSD-3-Clause |
| `accelerate` | Orchestration matériel CPU/GPU utilisée par `transformers.Trainer` | Apache-2.0 |
| `seqeval` | Calcul du F1 strict sur séquences BIO pendant l'entraînement | MIT |
| `rapidfuzz` | Rapprochement flou rapide (produits, zones, noms clients) par distance de Levenshtein / `WRatio` | MIT |
| `sklearn-crfsuite` | Plan de secours CPU : modèle CRF (Conditional Random Fields) pour l'étiquetage NER | MIT |
| `scikit-learn` | Utilitaires ML et métriques complémentaires | BSD-3-Clause |
| `pyyaml` | Lecture des fichiers de configuration (`data/regles.yaml`, `roles.yaml`, `alias.yaml`) | MIT |
| `pytest` | Exécution de la suite de tests automatisés (`pytest tests/ai -q`) | MIT |
