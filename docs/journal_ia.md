# Journal d'exécution — Bloc IA (Jean-Arthur)

> Projet : **Assistant IA de facturation — Boutique X (Hackathon BWAI 2026)**
> Principe directeur : **« L'IA extrait, les règles calculent, l'humain décide. »**
> Ce journal trace chronologiquement chaque étape implémentée, les choix techniques justifiés (base directe de `docs/fiche_ia.md` et du rapport final) ainsi que les vérifications exécutées.

---

## Étape 1 — Socle, configuration, schéma NER et balisage d'annotation

### Réalisations
- Initialisation de l'arborescence officielle du Bloc IA conforme au Cahier des charges (§7.13) :
  - `ai/` (`parseur/`, `normalisation/`, `extraction/`, `entrainement/`, `entrainement/donnees/`, `modeles/`)
  - `tests/ai/`, `scripts/`, `docs/`
- Création de `requirements.txt` listant les 10 dépendances IA (épinglage prévu via `pip freeze` une fois l'environnement stabilisé, exigence E18).
- Création de `ai/config.py` : centralisation des chemins par défaut, de la graine globale (`SEED = 42`) et de la fonction `charger_seuils(path="data/regles.yaml")`.
- Création de `ai/extraction/schema.py` : définition des 11 entités métier (`ENTITES`) et des 23 étiquettes BIO (`LABELS`, `LABEL2ID`, `ID2LABEL`).
- Création de `ai/entrainement/markup.py` : parseur `parse_markup()` pour la syntaxe `[[texte|LABEL]]` et validateur pur `valider_spans()`.

### Justifications techniques
1. **Séparation stricte en bibliothèque pure (§7.2)** : `ai/` n'importe jamais `app.*`, FastAPI ni SQLite. Chaque module est testable isolément, déterministe et sans effet de bord, condition nécessaire à la reprise après interruption (§7.4, E12) et à l'idempotence (E8).
2. **Externalisation des seuils dans `data/regles.yaml` (§7.9, D5)** : `charger_seuils()` lit la clé `seuils_confiance` du fichier géré par Primel avec un repli sûr (`{"vert": 0.90, "rouge": 0.60}`) en cas d'absence du fichier ou de la clé. Aucune constante métier n'est figée sans possibilité de surcharge externe (exigence jury).
3. **Un seul label `QUANTITE` dans `schema.py` (D3)** : plutôt que de demander au modèle NER de distinguer `quantite_commandee` et `quantite_livree` (source de confusion fréquente sur des textes courts), la séparation sera opérée de manière **déterministe** à l'étape NORMALISÉ à partir du rôle de l'auteur (`livreur` vs `client`/`vendeuse`).
4. **Label `VARIANTE` unifié (D2)** : couvre à la fois les tailles (S, M, L, XL) et les teintes/variantes du catalogue (§6.1), évitant une multiplication inutile de classes rares.
5. **Format d'annotation unique `[[texte|LABEL]]` et offsets Unicode (D9)** : la même fonction `parse_markup()` sert au générateur synthétique et au jeu de test manuel (`data/test_manuel.jsonl`), garantissant la cohérence des offsets (`debut`, `fin` exclus, en indices de caractères Unicode Python).

### Vérifications et tests
- Vérification de l'arborescence et contrôle fonctionnel direct (import + assertions sur `charger_seuils`, `LABELS`, `parse_markup`, `valider_spans`) : **OK**.
- Note environnement : Python 3.10.11 détecté ; environnement virtuel dédié `.venv` créé et peuplé à l'Étape 2.

---

## Étape 2 — Parseur WhatsApp, simulateur et identification client (Jalons H1–H3)

### Réalisations
- Création de l'environnement virtuel dédié `.venv/` et installation complète de `requirements.txt` (via `--use-pep517` pour la compilation du wheel `seqeval 1.2.2`).
- Mise à jour de `.gitignore` pour exclure `.venv/`, `BWAI2026_Bloc_IA_Jean-Arthur_v2.md`, `cahier_des_charges_BWAI_2026-1.pdf` ainsi que les poids de modèles (`ai/modeles/*/*.bin`, `*.safetensors`, `ai/modeles/*.zip`).
- Création de `ai/parseur/roles.yaml` : table externe des rôles connus (`vendeuse`, `livreur`).
- Création de `ai/parseur/whatsapp.py` : `parser_export()`, `messages_depuis_simulateur()`, `empreinte_fil()` et exception `FormatInvalide`.
- Création de `ai/parseur/client.py` : `identifier_client()` (téléphone puis rapprochement flou sur le nom).
- Création de `ai/parseur/__init__.py` : point d'entrée officiel `analyser(texte_brut=None, items_simulateur=None, telephone=None, clients=None, roles=None)`.
- Création de `tests/ai/test_parseur.py` : 12 tests couvrant les formats iOS/Android, suites multi-lignes, messages système, simulateur, empreinte commune, identification client par téléphone/nom/inconnu, erreurs `FormatInvalide` et déterminisme.

### Justifications techniques
1. **Uniformisation des deux formats WhatsApp (iOS/Android) et horodatage à la minute** : la regex `LIGNE` tolère les crochets, les secondes optionnelles, la marque LTR `\u200e` et le BOM UTF-8 `\ufeff` (fréquent sur Windows). L'horodatage est normalisé en ISO-8601 à la minute (`%d/%m/%Y %H:%M`) afin que `empreinte_fil()` produise une empreinte logique identique entre un export texte et le simulateur de chat (E1).
2. **Double identifiant `rang` (0, 1, 2…) et `message_id` (`m1`, `m2`…) (D7)** : aligne directement la structure des messages sur la clé `(conversation, rang)` de la table SQLite `messages` (Bénito) et sur les références `m1`, `m2` du contrat JSON (Annexe A).
3. **Priorité au numéro sur les 8 derniers chiffres puis `rapidfuzz.fuzz.WRatio` (seuil 85) (D6)** : la comparaison sur les 8 derniers chiffres tolère les écarts de formatage (`+229`, `00229`, espaces, tirets). En l'absence de numéro correspondant, `WRatio` (insensible aux préfixes/suffixes partiels, contrairement à `ratio` strict) retrouve « Awa » dans « Awa Dossou », tout en excluant les auteurs purement numériques pour éviter tout faux positif. En cas d'échec, retour strict `None` (jamais de devinette : Primel lève « client inconnu »).
4. **Repli sûr si `data/clients.csv` n'est pas encore présent** : `_clients()` journalise un avertissement et renvoie `[]` plutôt que de planter, ce qui maintient le module testable seul indépendamment de l'avancement de `data/` (Primel).

### Vérifications et tests
- Commande : `.\.venv\Scripts\python.exe -m pytest tests/ai -q`
- Résultat : **`12 passed in 0.77s`** (100 % vert).
- Vérification `git status -sb` : `.venv/`, `BWAI2026_Bloc_IA_Jean-Arthur_v2.md` et `cahier_des_charges_BWAI_2026-1.pdf` sont bien ignorés.

---

## Étape 3 — Normalisation, rapprochement et assemblage des lignes (Jalons H1–H3)

### Réalisations
- Création de `ai/normalisation/nombres.py` : `sans_accents()`, `normaliser()`, `mots_vers_entier()`, `parse_montant()` et `parse_quantite()`.
- Création de `ai/normalisation/alias.yaml` : table YAML d'alias produits (`ART-001`..`ART-005`), zones (`Cotonou`, `Abomey-Calavi`, `Porto-Novo`) et variantes (`S`, `M`, `L`, `XL`, `Unique`).
- Création de `ai/normalisation/rapprochement.py` : `charger_alias()`, `charger_catalogue()`, `match_produit()`, `match_zone()`, `match_variante()`, `normaliser_paiement()`.
- Création de `ai/normalisation/dossier.py` : `en_contrat()`, `normaliser_champs()`, `assembler_lignes()` et `normaliser_dossier()`.
- Création de `ai/normalisation/__init__.py` : exports officiels de l'étape 4 NORMALISÉ.
- Création de `tests/ai/test_nombres.py` : **61 formulations positives** (19 montants, 14 quantités, 9 alias de zones, 9 produits approchants, 6 variantes, 4 paiements — exigence E3 ≥ 30 largement couverte), tests d'échec sûr (`None`), test d'exclusion stricte des `REFUS` et tests du format contrat Annexe A (`en_contrat()`).

### Justifications techniques
1. **Regex de devise collée aux chiffres (`15000f`, `8000fcfa`) et sécurité sur le `x` multiplicateur** : dans `parse_montant()`, l'ancrage `(?:(?<=\d)|\b)` devant la devise permet de normaliser `15000f` (où `\b` échoue entre `0` et `f`). Dans `parse_quantite()`, le préfixe/suffixe `x` n'est retiré que s'il jouxte un chiffre (`x3`, `3x`), afin de ne jamais tronquer les mots français se terminant par `x` (`deux`, `six`, `dix`, `quatre-vingt-dix`).
2. **`WRatio` (seuil 80) pour les produits vs exact + `ratio` (seuil 85) pour les zones** : les noms de produits comportent souvent des mots partiels ou inversés (« pagne senami », « rbe wax »), où `WRatio` excelle (avec garde `len >= 3` contre le bruit court). Pour les zones, les alias courts (`pn`, `abc`, `ctn`) exigent une correspondance exacte et les alias ≥ 5 caractères utilisent `fuzz.ratio` pour tolérer une faute de frappe (`calavie`, `cotonu`) sans déclencher de faux positif sur une sous-chaîne arbitraire.
3. **Séparation déterministe `quantite_commandee` / `quantite_livree` par rôle (D3)** : si `role == "livreur"`, le champ `quantite` devient `quantite_livree`, sinon `quantite_commandee`. Les deux compteurs coexistent sur la même ligne afin que Primel puisse détecter « commandé ≠ livré » sans que l'IA ne tranche ni ne calcule de montant.
4. **Exclusion stricte des passages `REFUS` de l'assemblage des lignes** : tout champ `refus` ou `motif_refus`, ainsi que tout champ `produit`/`variante`/`quantite` chevauchant un span `refus` dans le même message (`_chevauche_refus`), est écarté des lignes et remonté uniquement dans `signaux.refus`. Ainsi « refusé la robe L » ne pollue jamais `variantes.livrees`.
5. **Repli sûr sur échec de normalisation et propagation de confiance** : une valeur non normalisable passe systématiquement à `valeur=None, statut="a_renseigner", couleur="rouge", confiance=0.0`. Pour un produit ou une zone rapprochés du référentiel, la confiance devient `min(confiance_extraction, score_rapprochement)` avec mise à jour cohérente de `couleur` si elle descend sous `0.90`.
6. **Autonomie du module IA vis-à-vis de `data/catalogue.csv`** : si `data/catalogue.csv` (Primel) n'est pas présent sur disque lors des tests isolés, `charger_catalogue()` journalise un avertissement et utilise uniquement les 5 noms canoniques du CDC §3.3 (sans aucun prix, l'IA ne manipulant jamais les prix catalogue).

### Vérifications et tests
- Commande : `.\.venv\Scripts\python.exe -m pytest tests/ai -q`
- Résultat : **`76 passed in 0.50s`** (12 tests parseur + 64 tests normalisation/assemblage, 100 % verts).

---

## Étape 4 — Extraction Baseline, Garde-fous, Surlignage et Cas Awa (Jalon H6)

### Réalisations
- Création de `ai/extraction/champ.py` : fabrique `champ_brut()` au format plat officiel (§7.8 : `nom, valeur, message_id, debut, fin, confiance, version_modele`).
- Création de `ai/extraction/baseline.py` : extracteur déterministe par règles/regex (`VERSION = "baseline-1.0"`, confiance fixe `0.75` = `orange`, fonctions `spans()` et `extraire_brut()`).
- Création de `ai/extraction/garde_fous.py` : `appliquer_garde_fous()` vérifiant strictement la présence dans le texte source (`texte[debut:fin] == valeur`) et appliquant les seuils de confiance (`vert`, `orange`, `rouge` → `valeur=None`, `statut='a_renseigner'`).
- Création de `ai/extraction/surlignage.py` : `surligner()` générant un `texte_html` échappé contre XSS avec balises `<mark data-champ='...' class='conf-...'>` en offsets Unicode (D9).
- Création de `ai/extraction/__init__.py` : service unifié `extraire()`, `extraire_brut()`, `get_mode()` avec repli automatique journalisé (`ai.extraction`) sur la baseline lorsque le modèle NER est absent ou indisponible.
- Création de `tests/ai/test_garde_fous.py` (9 tests) et `tests/ai/test_exemple_awa.py` (2 tests : parcours complet Awa CDC §3.4 + déterminisme de bout en bout).

### Justifications techniques
1. **Confiance fixe `0.75` (`orange`) sur la baseline** : les expressions régulières ne produisent pas de probabilités calibrées ; forcer `0.75` place tous les champs préremplis en `orange` (confirmation attentive par la vendeuse) et fournit un contraste mesurable face au modèle NER calibré (critère jury « Qualité de l'automatisation »).
2. **Correction des regex `PRODUIT` et `REFUS` de la baseline** : placer `\s+` à l'intérieur des groupes optionnels (`s[ée]rums?(?:\s+(?:vitamine\s+c|vit\.?\s*c))?`, `sacs?(?:\s+[àa]\s+main)?(?:\s+lagune)?`) évite la capture d'un espace final dans `"1 sérum livrés"` et assure la détection en fin de phrase (`"et 1 sérum"`). L'extension de `REFUS` couvre les variantes `XL` et les noms de produits composés.
3. **Garde-fous post-extraction obligatoires (§7.8, E2, D10)** : toute valeur non retrouvée exactement aux offsets `[debut:fin]` dans le message source (hallucination, offset hors limites ou `message_id` inexistant) est rejetée (`valeur=None`, `source=None`, `confiance=0.0`, `statut='a_renseigner'`, `couleur='rouge'`, `rejet='absent_du_texte'`). Tout champ sous `seuils['rouge']` est vidé (`rejet='confiance_basse'`).
4. **Repli automatique transparent sur la baseline (§6.2 & §7.8)** : `_modele_disponible()` charge `ai.extraction.modele` paresseusement ; si le module ou les poids manquent, `extraire(..., mode="modele")` bascule sans crash sur `baseline-1.0` en émettant un `WARNING` sur le logger `ai.extraction` (E17).
5. **Validation complète sur le cas d'Awa (CDC §3.4)** : le pipeline `analyser -> extraire(mode="baseline") -> normaliser_dossier` produit exactement `ART-001` (`quantite_commandee=2`, `quantite_livree=1`, `variantes.commandees=["M", "L"]`, `variantes.livrees=["M"]`, `L` absente des livrées), `ART-004` (`1/1`), `zone="Abomey-Calavi"`, `signaux.refus=[{ref: "ART-001", variante: "L", motif: "taille"}]` et des sorties 100 % déterministes.

### Vérifications et tests
- Commande : `.\.venv\Scripts\python.exe -m pytest tests/ai -q`
- Résultat : **`87 passed in 0.37s`** (12 parseur + 64 normalisation + 9 garde-fous/repli/surlignage + 2 bout-en-bout Awa).
- **Jalon H6 atteint** : les trois fonctions officielles (`analyser`, `extraire`, `normaliser_dossier`) sont livrables à Bénito dès maintenant avec la baseline.

---

## Étape 4b — Alignement Addendum v1.1 (Typologie, Médias, T11, T12, T13, T20)

### Réalisations
- Mise à jour de `.gitignore` pour exclure `addendum_cahier_des_charges_BWAI_2026_v1-1.pdf`.
- Création de `ai/parseur/typologie.py` : définition des 8 catégories officielles (`TYPES_MESSAGE` : `COMMANDE`, `CONFIRMATION`, `MODIFICATION`, `ANNULATION`, `LIVRAISON`, `PAIEMENT`, `RECLAMATION_RETOUR`, `INFORMATION`) et de la fonction déterministe `classifier_message(texte, role)` (Addendum §3.2).
- Mise à jour de `ai/parseur/whatsapp.py` et `ai/parseur/__init__.py` :
  - Ajout de `type_message` sur chaque message renvoyé par `analyser()`.
  - Détection explicite des médias et pièces jointes hors périmètre (`detecter_media_non_pris_en_charge()` : `audio`, `image`, `video`, `sticker`, `document`, `media`), signalés dans `analyser()["medias_non_pris_en_charge"]` plutôt qu'ignorés silencieusement (Addendum §3.3 / D8).
  - Rétrocompatibilité totale des signatures (`analyser`, `parser_export`, `messages_depuis_simulateur`, `empreinte_fil`).
- Mise à jour de `ai/normalisation/rapprochement.py` : détection d'ambiguïté entre produits proches dans `match_produit()` (`ecart_ambiguite = 5.0` points `WRatio` entre références distinctes → `ambigu=True, ref=None, candidats=[...]`, Addendum §8 `A_PRODUIT_AMBIGU` / T12).
- Mise à jour de `ai/normalisation/dossier.py` et `ai/extraction/baseline.py` :
  - **T11 (modifications ultérieures)** : mise à jour en place de la taille ou de la quantité sur la ligne unique existante avec trace dans `signaux.corrections` sans doublon silencieux ; levée explicite de `ambiguite = True` si plusieurs produits ou plusieurs variantes préexistantes rendent la cible ambiguë.
  - **T12 (`A_PRODUIT_AMBIGU`)** : aucune sélection automatique sur produit ambigu ; champ basculé en `a_renseigner`/`rouge` en conservant `valeur_brute` et `candidats_produits`, plus signalement dans `signaux.produits_ambigus` et `signaux.motifs_ambiguite`.
  - **T13 & §4 (traçabilité)** : suivi de `quantite_refusee` et `mentions_brutes` par ligne, et conservation systématique de `ref` et `valeur_brute` sur les champs normalisés.
  - **T20 (`A_CONVERSATION`)** : détection déterministe multi-clients / multi-commandes (≥ 2 auteurs clients, nouvelle commande après livraison, marqueur explicite de seconde commande, ou deux commandes espacées de ≥ 24 h) avec `signaux.ambiguite = True` et `signaux.multi_commandes = True`.
- Création de `tests/ai/test_addendum_v11.py` : 24 tests dédiés couvrant les 8 catégories de typologie, les médias non pris en charge (export + simulateur + fichier uniquement média), T11 (univoque et ambigu), T12, T13/§4 et les 4 cas de T20.

### Justifications techniques
1. **Périmètre linguistique explicite (Addendum §3.3 / D2)** : la typologie et les règles de normalisation ciblent le socle français ; le Fon / code-switching reste documenté comme extension séparée à évaluer avec un jeu de test dédié, sans jamais être présenté comme acquis.
2. **Séparation stricte entre notices système et médias non pris en charge (§3.3 / D8)** : les bannières de chiffrement restent filtrées, tandis que les vocaux, images, vidéos et pièces jointes sont retirés du texte fiable mais remontés dans `medias_non_pris_en_charge` (type, auteur, horodatage, texte brut) afin que Bénito/Femi puissent alerter la vendeuse.
3. **Modification ciblée uniquement sur l'état antérieur au message (T11)** : la comparaison de `refs_avant_msg` et `variantes_avant_msg` empêche un mot de modification dans un message initial d'écraser une seconde variante du même message, tout en résolvant proprement « finalement mets la taille L » sur un message ultérieur.
4. **Refus de deviner sur produits proches ou fils mélangés (T12 / T20)** : aligné sur le principe directeur (« L'IA extrait, les règles calculent, l'humain décide »), toute proximité ≤ 5 points `WRatio` entre deux références ou tout indice de multi-commandes bloque l'automatisation silencieuse via `signaux.ambiguite = True` (passage en `À_REVOIR`).

### Vérifications et tests
- Commande : `.\.venv\Scripts\python.exe -m pytest tests/ai -q`
- Résultat : **`111 passed in 1.52s`** (87 tests existants sans régression + 24 nouveaux tests Addendum v1.1).
- Vérification `git status -sb` : `addendum_cahier_des_charges_BWAI_2026_v1-1.pdf` est bien ignoré par `.gitignore`.

---

## Étape 5 — Données synthétiques et split disjoint par gabarit (Jalon H8)

### Réalisations
- Création de `ai/entrainement/generateur.py` :
  - **60 gabarits variés** sur le socle linguistique français, structurés en **12 familles × 5 gabarits** (`commande_simple`, `multi_produits`, `variantes_separees`, `zone_paiement`, `prix_cite`, `code_promo`, `correction`, `court_familier`, `livraison`, `refus_motif`, `date_livraison`, `sans_entite`).
  - **Split strictement disjoint par gabarit** (`tid % 5 == 0` → `val.jsonl`, 12 gabarits soit 20 % ; les 48 autres → `train.jsonl`, 80 %), garantissant que toutes les 12 familles et les 11 entités NER (`ENTITES`) sont présentes à la fois en entraînement et en validation sans fuite de gabarit.
  - **Bruit orthographique contrôlé** (`typo()`) : suppression contrôlée (sur mots ≥ 6 caractères), doublement, inversion de lettres adjacentes, retrait d'accents (25 %), variations de casse (30 %), formats numériques variés et émojis multi-octets, appliqué avant le balisage et vérifié par `valider_spans()` sur chaque exemple.
  - **Fonction pure et reproductible** : `generer(n=6000, seed=42)` sans effet de bord ; écriture isolée dans `main()` (CLI `python -m ai.entrainement.generateur`).
- Création de `tests/ai/test_generateur.py` : 6 tests vérifiant le nombre de gabarits (≥ 40) et l'unicité des `tid`, le déterminisme à graine identique, la stricte disjonction `train`/`val` par gabarit, la présence des 12 familles et des 11 entités dans chaque split, l'exactitude des offsets Unicode (y compris avec émojis) et la présence de messages sans entité.
- Génération des jeux synthétiques avec `seed=42` :
  - `ai/entrainement/donnees/train.jsonl` : **4 814 messages** (48 gabarits, ~1,54 Mo).
  - `ai/entrainement/donnees/val.jsonl` : **1 186 messages** (12 gabarits, ~0,45 Mo).

### Justifications techniques
1. **Split par gabarit plutôt qu'aléatoire (Guide §10.1)** : découper aléatoirement des phrases issues des mêmes gabarits gonfle artificiellement le F1 de validation par mémorisation syntaxique. La partition `tid % 5 == 0` (1 gabarit sur 5 par famille) force le modèle à généraliser sur des formulations inédites tout en couvrant 100 % des familles et des 11 classes NER en validation.
2. **Protection contre la corruption d'offsets Unicode (D9)** : le bruit `typo()` est appliqué exclusivement aux valeurs de slots avant l'appel à `parse_markup()`, jamais après, et `valider_spans()` rejette toute anomalie d'indice ou de label à la génération.
3. **Messages sans entité (`sans_entite`) et données 100 % fictives (§12)** : l'inclusion d'une famille dédiée à 0 entité réduit les faux positifs sur les formules de politesse/confirmation, et tous les prénoms, montants et codes générés sont strictement fictifs.

### Vérifications et tests
- Commande génération : `.\.venv\Scripts\python.exe -m ai.entrainement.generateur`
- Sortie : `Généré : ai\entrainement\donnees\train.jsonl (4814 messages) | ai\entrainement\donnees\val.jsonl (1186 messages) | 60 gabarits`
- Commande tests : `.\.venv\Scripts\python.exe -m pytest tests/ai -q`
- Résultat : **`117 passed in 1.27s`** (111 existants + 6 nouveaux tests générateur, 100 % verts).
- **Jalon H8 (données synthétiques reproductibles) atteint.**

---

## Étape 6a — Scripts d'entraînement (`train.py`) et Plan B CPU (`crf_backup.py`)

### Réalisations
- Mise à jour de `.gitignore` pour exclure les dossiers de poids/artefacts locaux (`ai/modeles/ner-v1/`, `ai/modeles/crf-v1/`, `*.joblib`, `*.pkl`) tout en permettant de versionner l'empreinte `ai/modeles/ner-v1.sha256`.
- Création de `ai/entrainement/train.py` :
  - Script de fine-tuning NER `cmarkea/distilcamembert-base` prêt pour Colab/Kaggle (`SEED = 42`, tokenizer rapide obligatoire pour `offset_mapping`, gestion automatique de `eval_strategy` vs `evaluation_strategy` selon la version de `transformers`).
  - Calibration par mise à l'échelle de la température (`calibrer_temperature()`, L-BFGS avec paramétrisation `T = exp(log_T)` garantissant `T > 0`) ajustée **exclusivement** sur `val.jsonl` et sauvegardée dans `ai/modeles/ner-v1/calibration.json` (`version = "ner-v1"`).
  - Aucun téléchargement ni effet de bord à l'import du module.
- Création de `ai/entrainement/crf_backup.py` :
  - Plan de secours CPU déterministe basé sur `sklearn-crfsuite` (L-BFGS, fenêtre contextuelle ±2, formes sans accents, bigrammes, indicateurs de tailles/nombres/devises/émojis) produisant `version_modele = "crf-v1"`.
  - Calibration des probabilités marginales par température sur `val.jsonl` (optimisation convexe 1D bornée sur la log-vraisemblance négative) avec mesure d'ECE avant/après calibration.
  - Exécution locale immédiate sur `train.jsonl` (4 814 messages) / `val.jsonl` (1 186 messages) → artefacts générés dans `ai/modeles/crf-v1/` (`crf_model.joblib`, ~228 Ko, + `calibration.json`).

### Justifications techniques
1. **Plan B CPU exécutable immédiatement sans dépendre d'un GPU (CDC §6.2 & Guide §11.2)** : disposer dès maintenant d'un modèle statistique entraîné et calibré (`crf-v1`) débloque l'intégration et les tests du mode `modele` en local hors-ligne, tout en gardant `train.py` prêt à produire `ner-v1` sur GPU Colab/Kaggle avec exactement la même interface.
2. **Calibration stricte sur la validation disjointe (Addendum §4)** : la température `T` n'est jamais estimée sur `train.jsonl` ni sur le jeu de test manuel ; la paramétrisation `T > 0` réduit l'ECE validation de `0.0090` à `0.0083` (`T = 0.963264`) sans modifier les prédictions argmax.
3. **Isolation des poids hors Git (§7.11)** : les dossiers `ai/modeles/ner-v1/` et `ai/modeles/crf-v1/` sont ignorés par `.gitignore` (vérifié via `git check-ignore -v`).

### Vérifications et tests
- Commande entraînement CPU : `.\.venv\Scripts\python.exe -m ai.entrainement.crf_backup`
- Résultats `crf-v1` sur `val.jsonl` (12 gabarits inédits, 1 186 messages) :
  - `f1_val` (seqeval strict) : **`0.9149`**
  - `temperature` : **`0.963264`**
  - `ece_val_avant` : **`0.0090`** → `ece_val_apres` : **`0.0083`**
  - Artefacts générés : `ai/modeles/crf-v1/crf_model.joblib` (227 757 octets) + `calibration.json` (251 octets) — tous deux vérifiés ignorés par `.gitignore`.
- Commande tests : `.\.venv\Scripts\python.exe -m pytest tests/ai -q`
- Résultat : **`117 passed in 1.22s`** (100 % vert).

---

## Étape 6b — Inférence modèle (`modele.py`), téléchargement SHA-256 et tests (Jalon H12 atteint)

### Réalisations
- Création de `ai/extraction/modele.py` :
  - Cascade de chargement déterministe : priorité à `ai/modeles/ner-v1/` (`ModeleTransformer`, DistilCamemBERT calibré, `version_modele = "ner-v1"`), bascule automatique sur `ai/modeles/crf-v1/` (`ModeleCRF`, `version_modele = "crf-v1"`), puis repli gracieux vers `baseline-1.0` orchestré par `ai/extraction/__init__.py` si aucun modèle entraîné n'est présent.
  - Exposition stricte de la signature officielle `extraire_brut(messages)` (§7.8), cache indexé par `(type, chemin_resolu)` et utilitaires `disponible()`, `source_disponible()`, `version_active()`, `reinitialiser_cache()`.
- Création de `scripts/telecharger_modele.py` :
  - Lecture de l'URL publique via la variable `BWAI_MODELE_URL` ou argument CLI (zéro secret dans le dépôt, §7.11).
  - Vérification obligatoire de l'empreinte SHA-256 avant toute extraction (`calculer_sha256()`, `lire_sha256_attendu()`), suppression immédiate de toute archive corrompue en cas de divergence, et protection contre le Zip-Slip (`_extraire_zip_securise()`).
- Correction lexique dans `ai/entrainement/generateur.py` et ré-entraînement `crf-v1` :
  - Le premier test bout-en-bout du cas d'Awa (CDC §3.4) en mode `modele` a révélé une fusion de frontière sur `"1 robe M"` (`PRODUIT = "robe M"`, confiance orange `0.8898`) car les formes courtes d'`alias.yaml` (`robe`, `sac`, `ensemble`) manquaient dans `PRODUITS_SING`/`PRODUITS_PLUR`.
  - L'alignement de `generateur.py` avec `alias.yaml` + régénération (`train.jsonl`: 4 817 msg, `val.jsonl`: 1 183 msg) + ré-entraînement `crf-v1` (`f1_val = 0.8869`, `T = 1.061443`, `ece_val: 0.0157 -> 0.0138`) a résolu proprement la séparation `"robe" (PRODUIT) + "M" (VARIANTE)`.
- Mise à jour de `tests/ai/test_garde_fous.py` (isolation via `monkeypatch` du test de repli baseline maintenant que `crf-v1` est présent sur disque) et création de `tests/ai/test_modele.py` (6 tests : inférence calibrée `crf-v1`, cas Awa bout-en-bout en mode `modele`, déterminisme et 0 faux positif sur message neutre, cascade `ner-v1 -> crf-v1 -> baseline`, téléchargement SHA-256 valide/invalide + protection Zip-Slip).

### Justifications techniques
1. **Cascade à 3 niveaux sans point de défaillance unique (§6.2 & §7.8)** : le code d'appel (Bénito) invoque toujours `extraire(messages, mode=None)` ; le module sélectionne automatiquement `ner-v1` (si poids Transformer installés) → `crf-v1` (plan B CPU) → `baseline-1.0` (règles), en traçant systématiquement `version_modele` sur chaque champ.
2. **Sécurité de l'installation des poids (§7.11, E18)** : la vérification SHA-256 avant extraction + suppression automatique en cas d'échec + contrôle Zip-Slip garantissent l'intégrité du checkpoint installé sur une machine propre.
3. **Diagnostic guidé par le cas CDC §3.4 (sans toucher au jeu de test manuel)** : utiliser l'exemple public du cahier des charges (Awa) pour repérer l'omission des noms courts (`robe`, `sac`, `ensemble`) dans le générateur améliore la généralisation du modèle sans jamais contaminer `data/test_manuel.jsonl`.

### Vérifications et tests
- Commande : `.\.venv\Scripts\python.exe -m ai.entrainement.generateur; .\.venv\Scripts\python.exe -m ai.entrainement.crf_backup; .\.venv\Scripts\python.exe -m pytest tests/ai -q`
- Résultat : **`123 passed in 7.07s`** (117 existants + 6 nouveaux tests `test_modele.py`, 100 % verts).
- **Jalon H12 atteint** : premier modèle statistique calibré (`crf-v1`) intégré, évalué sur validation disjointe et validé de bout en bout sur le cas d'Awa.

---

## Étape 7a — Évaluation comparative (`evaluation.py`) et analyse d'erreurs (Jalon H19)

### Réalisations
- Création de `ai/entrainement/evaluation.py` :
  - Chargeur unifié `charger_corpus()` compatible à la fois avec `data/test_manuel.jsonl` (format balisé `markup`) et `val.jsonl` (format pré-parsé `text` + `spans`) avec validation `valider_spans()`.
  - Calcul de **F1 strict** (label + début + fin exacts) et **F1 souple** (même label + chevauchement) par entité + moyennes micro et macro (`prf()`, appariement bijectif 1-à-1 sur `extraire_brut()`).
  - Calcul de la **calibration** (`calibration()` : ECE + 10 tranches de fiabilité) et des **taux de revue humaine** (`taux_revue()` : `vert` / `orange` / `rouge` après garde-fous sur `extraire()`).
  - **Catégorisation automatique des erreurs** (`analyser_erreurs()` : `confusion_classe`, `frontiere_decalee`, `entite_manquee`, `faux_positif_sans_entite`, `faux_positif_autre`) avec exemples concrets.
  - Double entrée CLI (`--corpus auto | test | val`) avec marqueur explicite `est_score_final_publiable` (`False` tant que `data/test_manuel.jsonl` ≥ 80 messages n'est pas évalué).
- Création de `tests/ai/test_evaluation.py` : 5 tests couvrant le chargement double format, F1 strict vs souple, ECE, les 5 catégories d'erreurs et l'évaluation comparative `baseline-1.0` vs `crf-v1`.
- Exécution du premier benchmark interne (`--corpus val`, 1 183 messages sur 12 gabarits inédits) archivé dans `docs/resultats_ia.json`.

### Justifications techniques
1. **Séparation stricte entre `extraire_brut()` (F1/ECE) et `extraire()` (taux de revue)** : les métriques de qualité d'extraction (F1, ECE) mesurent la performance intrinsèque des passages prédits avant rejet, tandis que les taux `vert`/`orange`/`rouge` reflètent exactement l'expérience de revue de la vendeuse après garde-fous (§7.8 & Guide §12).
2. **Honnêteté scientifique sur la source des scores** : `docs/resultats_ia.json` porte `source_corpus = "val_synthetique"` et `est_score_final_publiable = false` avec un avertissement explicite rappelant que seul `data/test_manuel.jsonl` (≥ 80 messages rédigés par les 4 membres) donnera les scores publiés.
3. **Diagnostic comparatif objectif Baseline vs CRF-v1 (benchmark interne `val.jsonl`)** :
   - **F1 strict micro** : `0.6345` (`baseline-1.0`) → **`0.8869`** (`crf-v1`, **+25,2 pts**) ; **F1 souple micro** : `0.7673` → **`0.9567`** (**+18,9 pts**).
   - **Taux de revue attentive (`orange + rouge`)** : `100 %` (`baseline-1.0`, confiance figée à `0.75`) → **`20,72 %`** (`crf-v1`, 79,28 % en `vert`).
   - **Limites observées honnêtement** : `crf-v1` présente un ECE span de `0.0524` (légère sur-confiance sur les frontières multi-tokens) et `27` faux positifs sur messages sans entité (contre `0` pour la baseline) — points documentés pour `docs/fiche_ia.md` et pour le passage éventuel à `ner-v1` (DistilCamemBERT).

### Vérifications et tests
- Commande benchmark : `.\.venv\Scripts\python.exe -m ai.entrainement.evaluation --corpus val` → `docs/resultats_ia.json` généré.
- Commande tests : `.\.venv\Scripts\python.exe -m pytest tests/ai -q`
- Résultat : **`128 passed in 7.92s`** (123 existants + 5 nouveaux tests `test_evaluation.py`, 100 % verts).

---

## Étape 7b — Fiche IA, Licences, Épinglage E18 et Audit final avant gel (Jalons H19–H24)

### Réalisations
- Rédaction complète de `docs/fiche_ia.md` conforme au Guide §15 et à l'Addendum v1.1 :
  - Architecture en cascade (`ner-v1` → `crf-v1` → `baseline-1.0`), empreinte SHA-256 du checkpoint local `crf-v1` (`f532d821...`), traçabilité (`version_modele`, offsets Unicode, `valeur_brute` + `ref`).
  - Séparation explicite entre le **benchmark interne sur validation synthétique** (`val.jsonl`, 1 183 messages, `est_score_final_publiable = false`) et la section réservée aux **scores finaux sur `data/test_manuel.jsonl` (≥ 80 messages)** à produire dès livraison du lot équipe.
  - Analyse d'erreurs réelle sourcée depuis `docs/resultats_ia.json` (frontières décalées, entités manquées sur contextes inédits comme `DATE_LIVRAISON`, 27 faux positifs sur messages sans entité neutralisés par la normalisation aval, légère sur-confiance d'environ 5 pts sur spans multi-tokens).
  - Documentation transparente des seuils de revue humaine (`0.90` / `0.60`), des garde-fous anti-hallucination et des limites assumées (socle français uniquement — Fon/code-switching hors socle, médias non transcrits, gabarit pédagogique non fiscalement conforme, variabilité GPU).
- Création de `LICENSES.md` recensant le modèle de base (`cmarkea/distilcamembert-base`) et l'ensemble des bibliothèques Python directes et transitives du Bloc IA avec leurs licences open source permissives (MIT, BSD-3-Clause, Apache-2.0) et versions épinglées.
- Épinglage complet de `requirements.txt` via `pip freeze` de `.venv` (65 paquets, exigence de reproductibilité E18).
- Audit final d'isolation et de sécurité avant gel :
  - Zéro import de `app.*` ou `ui/` dans `ai/` (règle de dépendance §7.2).
  - Zéro secret, jeton ou donnée personnelle réelle dans le dépôt ; poids de modèles et documents de travail exclus par `.gitignore`.

### Vérifications et tests
- Audit imports (`Select-String` sur `ai/**/*.py` pour `import app` / `import ui`) : **0 correspondance (OK)**.
- Audit secrets/données personnelles réelles : **0 détection (OK)**.
- Commande tests finale : `.\.venv\Scripts\python.exe -m pytest tests/ai -q` → **128 passed (100 % verts)**.
- **Bloc IA prêt pour le gel H22** : il ne restera qu'à exécuter `.\.venv\Scripts\python.exe -m ai.entrainement.evaluation --corpus test` dès que Primel et l'équipe déposeront `data/test_manuel.jsonl` (≥ 80 messages).



