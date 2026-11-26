# Boutique X — Assistant IA de facturation (Hackathon BWAI 2026 · Cas pratique 2)

Prototype local complet de facturation assistée par IA pour une boutique e-commerce vendant par WhatsApp.

**Principe directeur** : *l'IA extrait, les règles calculent, l'humain décide.*
Toutes les données (clients, catalogue, prix, paiements, envois) sont **fictives et simulées**.

## Architecture (4 couches)

- `ui/` — Interface web Streamlit connectée en direct à l'API (`API_MODE=live` par défaut, `API_MODE=mock` en repli)
- `app/api/` — API REST FastAPI (contrôle des rôles, verrou optimiste, idempotence, PDF, audit)
- `app/workflow/` & `app/db/` — Machine à états, SQLite WAL, reprise après interruption en 7 étapes (`processing_steps`), immutabilité par triggers, journal d'audit chaîné SHA-256, file d'envoi hors-ligne (`outbox`)
- `app/calcul/`, `app/controles/`, `app/pdf/` — Moteur déterministe en entiers FCFA (règles externes dans `data/rules.yaml`), détection d'anomalies métier, génération PDF pédagogique
- `ai/` — Parseur WhatsApp (typologie, médias non pris en charge, empreinte SHA-256), extraction NER (modèle calibré DistilCamemBERT / CRF avec repli automatique sur la baseline à règles), garde-fous anti-hallucination, normalisation & rapprochement flou (`rapidfuzz`)
- `data/` — Référentiels versionnés (`catalogue.csv`, `clients.csv`, `rules.yaml`) et scénario d'exemple (`data/scenarios/awa_dossou.txt`)

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Lancement

### Commande unique (API + Interface web)

```bash
chmod +x run.sh
./run.sh
```

- API FastAPI & Swagger : `http://127.0.0.1:8000/docs`
- Interface Streamlit : `http://127.0.0.1:8501`

## Démonstration du simulateur WhatsApp

Dans l'interface, ouvre la page **Chat** puis choisis **Simuler WhatsApp**. Ajoute les messages
dans l'ordre chronologique en sélectionnant l'intervenant (client, vendeuse ou livreur), saisis le
texte et sa date/heure, puis clique sur **Créer le dossier depuis la conversation simulée**.
Le fil est converti au format texte WhatsApp accepté par le même endpoint d'import que les exports
`.txt` ; le pipeline backend reste la source de vérité pour l'analyse et la facturation.

Ce simulateur est local et pédagogique : il n'envoie aucun message à WhatsApp ou à Meta. Les
conversations, clients et paiements de démonstration sont fictifs. L'import d'un export WhatsApp
existant par collage ou fichier `.txt` reste disponible dans la même page.

### Lancement séparé

```bash
uvicorn app.api.main:app --reload
API_MODE=live API_URL=http://127.0.0.1:8000 streamlit run ui/app.py
```

## Comptes de démonstration (aucun secret, mots de passe hachés PBKDF2-SHA256)

| Identifiant | Rôle | Mot de passe de test | Droits principaux |
| --- | --- | --- | --- |
| `USR-VEND` | `vendeuse` | `demo` | Importer, corriger/confirmer les champs, résoudre anomalies, émettre, enregistrer règlements |
| `USR-GER` | `gerant` | `demo` | Valider la facture (principe des 4 yeux), créer avoirs/remboursements, consulter l'audit |
| `USR-AUD` | `auditeur` | `demo` | Consulter les factures et vérifier l'intégrité du journal d'audit (lecture seule) |

## Routes API principales

- `POST /auth/login` — Authentification
- `POST /dossiers/import` (alias `POST /conversations`) — Import WhatsApp idempotent + pipeline complet 7 étapes + persistance messages, champs extraits, anomalies et brouillon
- `GET /dossiers`, `GET /dossiers/{id}`, `GET /dossiers/{id}/messages`, `GET /dossiers/{id}/extractions`, `GET /dossiers/{id}/anomalies`, `GET /dossiers/{id}/livraison`, `GET /dossiers/{id}/facture`, `GET /dossiers/{id}/brouillon.pdf`
- `POST /dossiers/{id}/champs/{field}/confirmer` (alias `PATCH`) & `POST /dossiers/{id}/confirmer`
- `POST /anomalies/{id}/resoudre` — Levée d'anomalie avec justification obligatoire
- `POST /dossiers/{id}/valider` — Validation transactionnelle exclusive (`BEGIN IMMEDIATE`), numérotation atomique `FAC-2026-XXXXXX`, figeage et empreinte SHA-256
- `GET /factures/{id}`, `GET /factures/{id}/pdf`, `POST /factures/{id}/emettre`, `POST /factures/{id}/reglements`, `POST /factures/{id}/avoirs`, `POST /factures/{id}/remboursements`, `GET /factures/{id}/solde`, `GET /avoirs/{id}/pdf`
- `GET /outbox`, `POST /outbox/synchroniser` — File d'envoi hors-ligne simulée
- `GET /audit?dossier_id=`, `GET /dossiers/{id}/audit`, `GET /audit/verifier` — Journal chaîné SHA-256 et vérification d'intégrité
- `GET /tableau-de-bord`, `POST /demo/reinitialiser`, `POST /demo/simuler-interruption`, `POST /dossiers/{id}/reprendre`, `POST /demo/simuler-concurrence`

## Tests automatisés

```bash
pytest -q
```

Couvre les tests unitaires IA (`tests/ai/`), le moteur de calcul et les contrôles (`tests/test_primel.py`), le socle workflow (`tests/test_workflow.py`) et le parcours complet bout-en-bout, concurrence à 50 requêtes, reprise après interruption, immutabilité SQLite et détection d'altération d'audit (`tests/test_integration_e2e.py`).
