# Boutique X — Assistant IA de facturation (Hackathon BWAI 2026 · Cas pratique 2)

Prototype local complet de **facturation assistée par IA** pour une boutique e-commerce béninoise vendant par WhatsApp.

> **Principe directeur** : *« L'IA extrait, les règles calculent, l'humain décide. »*  
> Toutes les données (clients, catalogue, prix, paiements, envois et comptes) sont **fictives, pédagogiques et simulées**. Le prototype ne se connecte pas à WhatsApp/Meta et ne constitue pas un système de facturation fiscale légale.

---

## Architecture des modules

| Module | Rôle principal |
| --- | --- |
| `ui/` | Interface web **Streamlit Showcase** (thème Dual-Tone Obsidienne/Albâtre, monogramme **BX**, zéro logique métier) connectée en direct à l'API (`API_MODE=live` par défaut, `API_MODE=mock` en repli), avec export **PDF** et **Word (`.doc`)** des brouillons et factures. |
| `app/` | Backend **FastAPI** (`app/api/`), machine à états et SQLite WAL (`app/workflow/`, `app/db/`) avec reprise après interruption en 7 étapes (`processing_steps`), contrôle des rôles (4 yeux), verrou optimiste, idempotence, immutabilité par triggers, journal d'audit chaîné **SHA-256**, file d'envoi hors-ligne (`outbox`), moteur de calcul déterministe en entiers **FCFA** (`app/calcul/`), contrôles d'anomalies (`app/controles/`) et génération PDF (`app/pdf/`). |
| `ai/` | Parseur WhatsApp (typologie, médias non pris en charge, empreinte SHA-256), extraction NER calibrée (`DistilCamemBERT` `ner-v1` → repli `CRF` `crf-v1` → repli baseline à règles), garde-fous anti-hallucination (vérification stricte par offsets), normalisation et rapprochement flou (`rapidfuzz`). |
| `data/` | Référentiels versionnés (`catalogue.csv`, `clients.csv`, `rules.yaml`) et scénario de référence (`data/scenarios/awa_dossou.txt`). |
| `scripts/` | Outil de téléchargement vérifié **SHA-256** et anti Zip-Slip des poids du modèle (`scripts/telecharger_modele.py`). |
| `tests/` | Suite automatisée complète (`tests/ai/`, `tests/test_primel.py`, `tests/test_workflow.py`, `tests/test_ui_simulator.py`, `tests/test_integration_e2e.py`). |

---

## Installation

### 1. Environnement virtuel et dépendances épinglées

**Linux / macOS :**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows (PowerShell) :**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Installation optionnelle des poids du modèle NER (`ner-v1`)

Les poids volumineux ne sont pas versionnés dans Git. Pour installer l'archive du modèle `ner-v1` avec contrôle d'intégrité **SHA-256** (`ai/modeles/ner-v1.sha256`) :

```bash
BWAI_MODELE_URL="https://..." python scripts/telecharger_modele.py
```

En l'absence des poids `ner-v1/`, l'application bascule automatiquement et de manière transparente sur le modèle local `crf-v1` (CPU) puis sur la baseline déterministe à règles.

---

## Lancement

### Option A — Commande unique (Linux / macOS)

```bash
chmod +x run.sh
./run.sh
```

### Option B — Lancement séparé (Windows / Linux / macOS)

**Terminal 1 — API FastAPI :**

```bash
# Linux / macOS
uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --reload

# Windows (PowerShell)
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

**Terminal 2 — Interface Web Streamlit Showcase :**

```bash
# Linux / macOS
API_MODE=live API_URL=http://127.0.0.1:8000 streamlit run ui/app.py --server.port 8501

# Windows (PowerShell)
.\.venv\Scripts\python.exe -m streamlit run ui/app.py --server.address 127.0.0.1 --server.port 8501
```

### URLs locales

- **Interface Web (Streamlit)** : `http://127.0.0.1:8501`
- **Documentation interactive API (Swagger)** : `http://127.0.0.1:8000/docs`

---

## Comptes de démonstration

> Aucun secret réel : mots de passe locaux hachés en **PBKDF2-SHA256** (`POST /auth/login`), uniquement destinés à la démonstration locale.

| Identifiant | Rôle | Mot de passe | Droits principaux |
| --- | --- | --- | --- |
| `USR-VEND` | `vendeuse` | `demo` | Importer / simuler WhatsApp, corriger et confirmer les champs extraits, résoudre les anomalies avec justification, émettre, enregistrer les règlements |
| `USR-GER` | `gerant` | `demo` | Valider la facture (principe des 4 yeux, distinct de la vendeuse), figer le numéro `FAC-2026-XXXXXX` et l'empreinte SHA-256, créer avoirs/remboursements, consulter l'audit |
| `USR-AUD` | `auditeur` | `demo` | Consulter les dossiers/factures et vérifier cryptographiquement l'intégrité du journal d'audit (lecture seule) |

---

## Parcours de démonstration (scénario Awa Dossou)

1. **Connexion (`Vendeuse`)** puis ouverture de **Chat & Import**.
2. **Simulateur WhatsApp ou import `.txt`** : charger le scénario de référence *Awa Dossou* (2 robes Ayoka M et L + 1 sérum vitamine C ; robe L refusée à la livraison) et cliquer sur **Créer le dossier depuis ce fil**. Le simulateur est 100 % local et n'envoie aucun message à WhatsApp/Meta.
3. **Revue IA** : inspecter les extractions surlignées avec leur message source et confirmer les champs.
4. **Anomalies** : vérifier l'écart commandé/livré/accepté (robe L refusée) et lever l'anomalie avec une justification obligatoire.
5. **Brouillon & Validation (`Gérant` — 4 yeux)** : se connecter en `Gérant`, vérifier le calcul déterministe (**23 000 FCFA** sous-total − **1 150 FCFA** fidélité 5 % + **1 500 FCFA** livraison Abomey-Calavi = **23 350 FCFA HT** + **4 203 FCFA** TVA 18 % = **27 553 FCFA TTC**), télécharger le brouillon en **PDF** ou **Word (`.doc`)**, puis **Valider la facture**.
6. **Facture & Règlements** : consulter le numéro définitif `FAC-2026-XXXXXX`, l'empreinte **SHA-256**, exporter en **PDF** / **Word**, simuler l'émission et enregistrer le règlement.
7. **Journal d'audit** : cliquer sur **Vérifier l'intégrité de la chaîne d'audit** pour contrôler l'enchaînement SHA-256.

---

## Routes API principales

- `POST /auth/login` — Authentification des comptes de démonstration
- `POST /dossiers/import` (alias `POST /conversations`) — Import WhatsApp idempotent + pipeline complet 7 étapes + persistance messages, extractions, anomalies et brouillon
- `GET /dossiers`, `GET /dossiers/{id}`, `GET /dossiers/{id}/messages`, `GET /dossiers/{id}/extractions`, `GET /dossiers/{id}/anomalies`, `GET /dossiers/{id}/livraison`, `GET /dossiers/{id}/facture`, `GET /dossiers/{id}/brouillon.pdf`
- `POST /dossiers/{id}/champs/{field}/confirmer` (alias `PATCH`) & `POST /dossiers/{id}/confirmer`
- `POST /anomalies/{id}/resoudre` — Levée d'anomalie avec justification obligatoire
- `POST /dossiers/{id}/valider` — Validation transactionnelle exclusive (`BEGIN IMMEDIATE`), numérotation atomique `FAC-2026-XXXXXX`, figeage et empreinte SHA-256
- `GET /factures/{id}`, `GET /factures/{id}/pdf`, `POST /factures/{id}/emettre`, `POST /factures/{id}/reglements`, `POST /factures/{id}/avoirs`, `POST /factures/{id}/remboursements`, `GET /factures/{id}/solde`, `GET /avoirs/{id}/pdf`
- `GET /outbox`, `POST /outbox/synchroniser` — File d'envoi hors-ligne simulée
- `GET /audit?dossier_id=`, `GET /dossiers/{id}/audit`, `GET /audit/verifier` — Journal chaîné SHA-256 et vérification d'intégrité
- `GET /tableau-de-bord`, `POST /demo/reinitialiser`, `POST /demo/simuler-interruption`, `POST /dossiers/{id}/reprendre`, `POST /demo/simuler-concurrence`

---

## Tests automatisés et évaluation IA

```bash
# Suite complète (IA, calcul, contrôles, workflow, simulateur UI, E2E)
pytest -q

# Tests unitaires du Bloc IA uniquement
pytest tests/ai -q

# Évaluation comparative de l'extraction NER sur le jeu de validation synthétique
python -m ai.entrainement.evaluation --corpus val
```

La suite couvre les modules IA (`tests/ai/`), le moteur de calcul et les anomalies (`tests/test_primel.py`), le socle workflow (`tests/test_workflow.py`), le simulateur UI (`tests/test_ui_simulator.py`) ainsi que le parcours complet bout-en-bout, concurrence à 50 requêtes, reprise après interruption, immutabilité SQLite et détection d'altération d'audit (`tests/test_integration_e2e.py`).

---

## Livrables et documentation

- [Fiche IA](docs/fiche_ia.md) — Modèle, séparation par gabarits, calibration, métriques de validation synthétique et limites
- [Licences open source (`LICENSES.md`)](LICENSES.md) — Inventaire des modèles et bibliothèques tiers épinglés
- [Rapport du prototype BWAI 2026 (PDF, 4 pages)](docs/rapport_hackathon_bwai_2026.pdf) — source éditable : [rapport_hackathon.md](docs/rapport_hackathon.md)
- [Résultats détaillés de l'évaluation IA](docs/resultats_ia.json)
