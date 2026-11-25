# Fiche IA — Assistant de facturation Boutique X (Hackathon BWAI 2026)

> **Principe directeur strict** : *« L'IA extrait, les règles calculent, l'humain décide. »*  
> **Responsable Bloc IA** : Jean-Arthur (suppléant : Femi)  
> **Périmètre** : Bibliothèque pure et déterministe (`ai/`), sans accès base de données ni calcul de montant, conforme au Cahier des charges v1.0 (§6 & §7) et à l'Addendum v1.1.

---

## 1. Modèles, versions et architecture en cascade

Le service d'extraction (`ai/extraction/__init__.py`) expose une signature unique `extraire(messages, mode=None, seuils=None)` (§7.8) et résout le moteur actif en cascade déterministe sans point de défaillance unique :

1. **Modèle principal (GPU Colab/Kaggle)** : `cmarkea/distilcamembert-base` (licence **MIT**, à reconfirmer sur la carte modèle Hugging Face lors de l'export des poids), fine-tuning NER BIO 23 étiquettes (`ai/entrainement/train.py`, `SEED = 42`), version `ner-v1`.
   - Statut actuel local : script prêt et testé sans téléchargement à l'import ; poids hors Git, installables via `scripts/telecharger_modele.py` avec vérification obligatoire SHA-256 (`ai/modeles/ner-v1.sha256`).
2. **Modèle statistique CPU actif (Plan B opérationnel)** : CRF linéaire `sklearn-crfsuite` (algorithme L-BFGS, licence **MIT**), version **`crf-v1`**, `SEED = 42`.
   - Entraîné et calibré localement hors-ligne (`ai/entrainement/crf_backup.py`).
   - Température calibrée sur `val.jsonl` : **`T = 1.061443`** (`ece_val_token` : `0.0157` → `0.0138`).
   - Empreinte SHA-256 du checkpoint local `ai/modeles/crf-v1/crf_model.joblib` (hors Git) :  
     `f532d82169a5a93eeef2ade0b63b70920adb421925c5929a4e53e3351139a66e`
3. **Baseline de référence et repli ultime** : lexique + expressions régulières déterministes (`ai/extraction/baseline.py`), version **`baseline-1.0`**, confiance fixe `0.75` (`orange`).
   - Bascule automatique et tracée (`WARNING` sur le logger `ai.extraction`, exigence E17) si aucun poids entraîné n'est présent sur disque.
4. **Traçabilité** : chaque champ extrait porte obligatoirement `version_modele` (`ner-v1`, `crf-v1` ou `baseline-1.0`), `source` (`message_id`, `debut`, `fin` en caractères Unicode, fin exclue), `confiance`, `couleur`, `statut`, ainsi que `valeur_brute` et `ref` catalogue après normalisation (Addendum §4).
5. **Aucune API externe** : tout s'exécute 100 % localement hors connexion (choix d'équipe : coût, confidentialité, disponibilité démo).

---

## 2. Tâche couverte par le Bloc IA

Le Bloc IA couvre exclusivement les étapes **2 (ANALYSÉ)**, **3 (EXTRAIT)** et **4 (NORMALISÉ)** :

- **Parseur (`ai/parseur/`)** : lecture des exports WhatsApp (iOS/Android, multi-lignes) et du simulateur web, empreinte logique SHA-256 déterministe (`empreinte_fil`), identification du client par téléphone (8 derniers chiffres) puis rapprochement flou sur le nom (`rapidfuzz.WRatio ≥ 85`, sinon `None`), classification déterministe de la typologie des messages en 8 catégories (Addendum §3.2) et signalement explicite des médias non pris en charge (`medias_non_pris_en_charge`, Addendum §3.3 / D8).
- **Extraction NER (`ai/extraction/`)** : repérage par étiquetage de séquences BIO de **11 entités métier** : `PRODUIT`, `VARIANTE`, `QUANTITE`, `PRIX_CITE`, `CODE_PROMO`, `ZONE`, `DATE_LIVRAISON`, `PAIEMENT`, `REFUS`, `MOTIF_REFUS`, `CLIENT`. Le modèle extrait uniquement des passages présents dans le texte source ; il ne génère ni ne calcule jamais de valeur.
- **Normalisation & assemblage (`ai/normalisation/`)** : normalisation déterministe des montants/quantités en chiffres ou en lettres françaises, rapprochement catalogue/zones/variantes/paiements, séparation déterministe `quantite_commandee` / `quantite_livree` selon le rôle (D3) + `quantite_refusee` (T13), exclusion stricte des passages `REFUS` des lignes, résolution contrôlée des modifications ultérieures (T11), détection des produits proches ambigus (`A_PRODUIT_AMBIGU`, T12) et des fils multi-commandes/multi-clients (`A_CONVERSATION`, T20).

---

## 3. Données et séparation stricte des jeux

- **Données 100 % fictives (§12)** : aucun vrai numéro de téléphone, nom réel ou transaction commerciale réelle.
- **Génération synthétique reproductible (`ai/entrainement/generateur.py`, `seed = 42`)** :
  - **60 gabarits variés** répartis en **12 familles × 5 gabarits** (`commande_simple`, `multi_produits`, `variantes_separees`, `zone_paiement`, `prix_cite`, `code_promo`, `correction`, `court_familier` avec abréviations/émojis, `livraison`, `refus_motif`, `date_livraison`, `sans_entite`).
  - **Bruit orthographique contrôlé** (suppressions sécurisées, doublements, inversions, retrait d'accents, variations de casse et formats numériques) appliqué avant `parse_markup()` et validé par `valider_spans()`.
  - **Entraînement (`ai/entrainement/donnees/train.jsonl`)** : **4 817 messages** issus de **48 gabarits** (`tid % 5 != 0`).
  - **Validation (`ai/entrainement/donnees/val.jsonl`)** : **1 183 messages** issus de **12 gabarits strictement disjoints** (`tid % 5 == 0`, 1 gabarit inédit par famille, couvrant les 12 familles et les 11 entités, dont 95 messages sans entité).
- **Jeu de test manuel officiel (`data/test_manuel.jsonl`, ≥ 80 messages)** :
  - Rédigé à la main par les 4 membres (20 messages chacun, coordonnés par Primel).
  - **Jamais** utilisé pour entraîner, calibrer la température, régler les regex de la baseline ou ajuster les gabarits.
  - **Statut au moment du gel IA** : *en attente de dépôt du lot consolidé `data/test_manuel.jsonl` par l'équipe*. Dès réception, une seule commande mettra à jour `docs/resultats_ia.json` avec les scores finaux publiables (voir §9).

---

## 4. Méthode d'évaluation

Les résultats IA sont strictement séparés des résultats métier (contrôles/calculs de Primel) et produits par `ai/entrainement/evaluation.py` :

1. **F1 strict** (égalité exacte `(label, debut, fin)`) et **F1 souple** (même label + chevauchement) par entité, micro et macro, mesurés sur `extraire_brut()` (appariement bijectif 1-à-1).
2. **Calibration (ECE + 10 tranches de fiabilité)** : température optimisée uniquement sur `val.jsonl` ; l'ECE span est mesuré sans réajustement.
3. **Taux de revue humaine** (`vert` / `orange` / `rouge`) mesuré après garde-fous sur `extraire()`.
4. **Analyse automatique des erreurs** : répartition en 5 catégories (`confusion_classe`, `frontiere_decalee`, `entite_manquee`, `faux_positif_sans_entite`, `faux_positif_autre`).

---

## 5. Résultats

> **Avertissement de transparence (Guide §10.1 & §12)** :  
> Le tableau ci-dessous présente le **benchmark interne sur la validation synthétique disjointe par gabarit** (`val.jsonl`, 1 183 messages, archivé dans `docs/resultats_ia.json` avec `est_score_final_publiable: false`). **Ces scores ne doivent pas être présentés comme scores finaux de test** : ils servent de référence interne comparative en attendant l'exécution sur `data/test_manuel.jsonl` (≥ 80 messages réels).

### 5.1 Benchmark interne (`val.jsonl` — 12 gabarits inédits, 1 183 messages, 4 157 entités)

| Entité | F1 strict `baseline-1.0` | F1 strict `crf-v1` | F1 souple `crf-v1` | Support |
|---|---:|---:|---:|---:|
| `CLIENT` | 0.0000 | **0.8458** | 0.8458 | 423 |
| `CODE_PROMO` | 0.7974 | **1.0000** | 1.0000 | 92 |
| `DATE_LIVRAISON` | **0.9027** | 0.4933 | 0.4933 | 113 |
| `MOTIF_REFUS` | 0.5874 | **1.0000** | 1.0000 | 101 |
| `PAIEMENT` | 0.6463 | **0.6842** | 0.9158 | 179 |
| `PRIX_CITE` | 0.6839 | **1.0000** | 1.0000 | 102 |
| `PRODUIT` | 0.5124 | **0.7324** | 0.9824 | 981 |
| `QUANTITE` | 0.7059 | **0.9649** | 0.9649 | 1 073 |
| `REFUS` | 1.0000 | 1.0000 | 1.0000 | 101 |
| `VARIANTE` | 0.7490 | **0.9846** | 0.9846 | 694 |
| `ZONE` | 0.6550 | **1.0000** | 1.0000 | 298 |
| **Micro global** | **0.6345** | **0.8869** | **0.9567** | **4 157** |
| **Macro global** | **0.6582** | **0.8823** | **0.9261** | **4 157** |

- **Apport mesuré du modèle** : `+25,24 pts` en F1 strict micro (`+22,41 pts` en macro) par rapport à la baseline à règles ; réduction de **69,7 %** du nombre total d'erreurs (`2 109` → `639`).
- **Exception honnête à signaler** : sur `DATE_LIVRAISON`, la baseline à règles (`0.9027`) devance `crf-v1` (`0.4933`) sur le gabarit de validation inédit (`"passage prévu demain"`), illustrant la sensibilité d'un CRF linéaire aux nouveaux contextes lexicaux.
- **Calibration (span exact)** : `ECE crf-v1 = 0.0524` (`93,74 %` de précision empirique dans la tranche `[0,90 ; 1,00]` pour une confiance moyenne de `98,89 %`, soit une légère sur-confiance d'environ 5 points sur les spans multi-tokens). L'ECE apparent de la baseline (`0.0230`) est un artefact de sa confiance constante `0.75` (non discriminante).
- **Taux de revue humaine (`extraire()`, seuils `0.90 / 0.60`)** :
  - `baseline-1.0` : `0,0 %` vert · **`100,0 %` orange** · `0,0 %` rouge (`100 %` en revue attentive).
  - `crf-v1` : **`79,28 %` vert** (`3 180`) · **`16,40 %` orange** (`658`) · **`4,31 %` rouge** (`173`) → **`20,72 %`** en revue attentive.

### 5.2 Scores finaux sur `data/test_manuel.jsonl` (≥ 80 messages)

*À compléter immédiatement après exécution de `python -m ai.entrainement.evaluation --corpus test` sur le fichier consolidé par l'équipe.*

---

## 6. Analyse d'erreurs réelle (issue de `docs/resultats_ia.json`)

| Type d'erreur | `baseline-1.0` | `crf-v1` | Exemples réels observés (`crf-v1`) |
|---|---:|---:|---|
| **Confusion de classe** | 0 | 0 | Aucune confusion de classe observée sur `val.jsonl`. |
| **Frontières décalées** | 481 | 285 | `"1 paagne Senami accepté"` → prédit `PRODUIT="paagne Senami accepté"` (inclut le participe inédit `"accepté"`). `"payé paiement a la livraison"` → prédit `PAIEMENT="a la livraison"` (tronque `"paiement"`). |
| **Entités manquées** | 1 452 | 250 | `"passage prévu demain sur Cootonou"` → `DATE_LIVRAISON="demain"` manquée (contexte `"passage prévu"` absent du train). `"Bonjour c'est Koffi..."` → `CLIENT="Koffi"` manqué. |
| **Faux positifs sur messages sans entité** | 0 | 27 | `"Merci encore et à bientôt"` → prédit `PAIEMENT="bientôt"` après la préposition `"à"`. **Sécurité aval** : `normaliser_paiement("bientôt")` retourne `None` → champ basculé en `rouge`/`a_renseigner`. |
| **Autres faux positifs** | 176 | 77 | `"Vous confirmez 15k pour le sacs Lagune ?"` → prédit `QUANTITE="le"` devant un nom produit. **Sécurité aval** : `parse_quantite("le")` retourne `None` → champ rejeté en `rouge`/`a_renseigner`. |

*Observation complémentaire sur le cas public d'Awa (CDC §3.4)* : lors du premier essai en mode `modele`, `crf-v1` fusionnait `"1 robe M"` en `PRODUIT="robe M"` (`0.8898` orange) car les noms courts (`robe`, `sac`, `ensemble`) manquaient dans le lexique du générateur. Leur ajout (aligné sur `alias.yaml`) a corrigé proprement la frontière `PRODUIT="robe"` + `VARIANTE="M"`.

---

## 7. Seuils de revue humaine et garde-fous

- **Seuils externalisés** dans `data/regles.yaml` (clé `seuils_confiance`, défaut sûr dans `ai/config.py`) :
  - **`vert` (≥ 0,90)** : prérempli, à confirmer par la vendeuse.
  - **`orange` ([0,60 ; 0,90[)** : prérempli, confirmation attentive signalée.
  - **`rouge` (< 0,60)** : valeur vidée (`None`), statut `a_renseigner`, saisie manuelle obligatoire.
- **Confirmation humaine systématique** : quelle que soit la confiance (`vert`, `orange` ou `rouge`), **aucun champ n'est validé automatiquement** ; la vendeuse confirme et le gérant valide la facture.
- **Garde-fous anti-hallucination (`ai/extraction/garde_fous.py`, §7.8, E2)** :
  - Vérification stricte `texte[debut:fin] == valeur` sur le message source ; tout décalage ou texte inventé est rejeté (`rejet = "absent_du_texte"`, `valeur = None`, `rouge`).
  - Toute valeur non normalisable (montant, quantité, variante, produit, zone, paiement) passe en `None` / `rouge` / `a_renseigner`.
  - Toute ambiguïté métier (produit proche `A_PRODUIT_AMBIGU`, fil multi-commandes/clients `A_CONVERSATION`, modification ambiguë) lève `signaux.ambiguite = True` → dossier en `À_REVOIR`.

---

## 8. Limites assumées et transparence

1. **Données synthétiques** : le modèle actuel (`crf-v1`) est entraîné sur des conversations synthétiques ; un recul de F1 et une dégradation de calibration (ECE) sont attendus sur le jeu de test manuel réel (domaine différent).
2. **Périmètre linguistique (Addendum §3.3 / D2)** : le socle validé est **le français** (fautes, abréviations, variantes numériques). Le **Fon** et le **code-switching Fon/français** ne sont **pas** pris en charge dans ce socle et constituent une extension séparée à évaluer uniquement avec un jeu de test dédié.
3. **Médias hors périmètre (Addendum §3.3 / D8)** : les messages vocaux, images, vidéos et pièces jointes ne sont ni transcrits ni interprétés ; ils sont explicitement signalés dans `medias_non_pris_en_charge` pour revue humaine.
4. **Fils complexes et références implicites** : les fils mélangeant plusieurs commandes ou clients ne sont pas découpés automatiquement mais bloqués pour arbitrage humain (`A_CONVERSATION`).
5. **Reproductibilité matérielle** : `crf-v1` sur CPU est bit-à-bit reproductible (`seed = 42`). Un ré-entraînement GPU de `DistilCamemBERT` (`train.py`) peut varier légèrement selon le matériel ; les scores publiés doivent toujours correspondre au **checkpoint livré** (empreinte SHA-256 indiquée), réévalué sur CPU.
6. **Portée réglementaire (Addendum §2.4)** : la facture générée par le prototype est un **gabarit pédagogique** (données et paiements fictifs), non conforme au dispositif légal de facturation normalisée au Bénin.

---

## 9. Commandes de reproductibilité (E18)

```bash
# 1. Installation sur environnement propre (versions épinglées)
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. Génération reproductible des données synthétiques (seed=42, split par gabarit)
.\.venv\Scripts\python.exe -m ai.entrainement.generateur

# 3. Entraînement CPU (plan B crf-v1) OU fine-tuning GPU Colab/Kaggle (ner-v1)
.\.venv\Scripts\python.exe -m ai.entrainement.crf_backup
# python -m ai.entrainement.train   # sur GPU Colab/Kaggle -> ai/modeles/ner-v1/

# 4. Évaluation officielle sur le jeu de test manuel (dès dépôt de data/test_manuel.jsonl)
.\.venv\Scripts\python.exe -m ai.entrainement.evaluation --corpus test

#    (Benchmark interne sur validation synthétique, non publiable comme score final)
.\.venv\Scripts\python.exe -m ai.entrainement.evaluation --corpus val

# 5. Suite complète des tests automatisés du Bloc IA
.\.venv\Scripts\python.exe -m pytest tests/ai -q

# 6. Installation vérifiée (SHA-256) des poids ner-v1 depuis une URL publique
# BWAI_MODELE_URL="https://..." python scripts/telecharger_modele.py
```
