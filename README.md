# Boutique X - Assistant IA de facturation

Prototype local du hackathon BWAI 2026.

## Demarrage

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.api.main:app --reload
```

Documentation interactive: `http://127.0.0.1:8000/docs`

## Repartition actuelle

Bénito réalise le socle transactionnel:

- base SQLite et contraintes d'intégrité;
- workflow des dossiers et de la facture;
- validation avec séparation des rôles;
- idempotence et concurrence;
- journal d'audit chaîné;
- API FastAPI;
- paiements et remboursements simulés.

## Partie Primel

Les services métier de référence sont disponibles dans :

- `data/catalogue.csv` : articles, variantes et prix HT;
- `data/clients.csv` : clients fictifs et zones;
- `data/rules.yaml` : remises, TVA, livraison et arrondis;
- `app/calcul/calculator.py` : calcul déterministe en entiers FCFA;
- `app/controles/anomalies.py` : contrôles commerciaux;
- `app/pdf/invoice_pdf.py` : brouillon et facture pédagogique PDF.