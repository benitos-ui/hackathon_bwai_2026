# Fiche IA — Assistant de facturation Boutique X

## Besoin et rôle de l'IA

Le système préremplit des champs d'une conversation WhatsApp pour préparer un brouillon de facture. L'IA extrait des passages du texte ; elle ne calcule pas les montants et ne valide aucune facture. Les valeurs sont vérifiées par des règles métier, puis confirmées par une vendeuse et validées par un gérant.

## Modèle et tâche

- **Modèle principal :** `cmarkea/distilcamembert-base`, ajusté pour la reconnaissance d'entités nommées (NER), version `ner-v1`.
- **Étiquetage :** BIO, 23 étiquettes couvrant 11 catégories : produit, variante, quantité, prix cité, code promo, zone, date de livraison, paiement, refus, motif de refus et client.
- **Entraînement :** 5 époques, graine `42`, sur GPU Colab. La température de confiance est calibrée sur le jeu de validation (`T = 1.124413`).
- **Repli :** CRF `crf-v1` sur CPU, puis baseline déterministe à règles si aucun modèle entraîné n'est disponible.
- **Licence du modèle de base :** à confirmer sur la carte officielle du modèle avant diffusion des poids.

## Données et séparation

Les données sont synthétiques et fictives. Le générateur utilise 60 gabarits en 12 familles, avec un split disjoint par gabarit :

| Jeu | Exemples | Gabarits |
|---|---:|---:|
| Entraînement | 4 817 | 48 |
| Validation | 1 183 | 12 |

Le corpus manuel consolidé `data/test_manuel.jsonl` n'est pas présent. Les résultats ci-dessous mesurent donc uniquement la validation synthétique et ne constituent pas une mesure de performance sur des conversations réelles.

## Protocole et résultats internes

Évaluation le 26 novembre 2026 avec `python -m ai.entrainement.evaluation --corpus val`. La baseline et `ner-v1` sont comparés sur les mêmes exemples ; F1 strict exige l'égalité du type et des offsets, F1 souple accepte un chevauchement de même type.

| Mesure sur `val.jsonl` | Baseline | `ner-v1` |
|---|---:|---:|
| F1 strict micro | 0.6345 | **0.9759** |
| F1 strict macro | 0.6582 | **0.9857** |
| F1 souple micro | 0.7673 | **0.9797** |
| ECE sur les prédictions | 0.0230 | 0.0271 |
| Part des champs nécessitant une revue attentive | 100 % | 2.38 % |

L'analyse a relevé 1 confusion de classe, 17 erreurs de frontière, 2 entités manquées et 168 faux positifs sur d'autres exemples pour `ner-v1`. La réduction apparente du taux de revue sur ce corpus synthétique ne supprime pas la confirmation humaine obligatoire.

## Contrôles humains et garde-fous

- Chaque extraction conserve sa source et ses offsets dans le message.
- Une extraction absente du texte source ou non normalisable est rejetée ou laissée à renseigner.
- Les ambiguïtés et anomalies sont présentées pour revue ; une anomalie ouverte bloque la validation.
- Aucun champ extrait n'est confirmé automatiquement ; la vendeuse confirme les champs et un gérant distinct valide la facture.

## Limites et reproduction

Le français est le périmètre évalué. Le Fon, le code-switching, ainsi que l'interprétation d'images, de pièces jointes et de messages vocaux ne sont pas pris en charge. La validation synthétique ne permet pas de conclure sur la performance terrain. Le prototype, ses factures et ses paiements sont pédagogiques et simulés ; ils ne constituent pas un dispositif de facturation légale.

Pour reproduire l'évaluation interne :

```bash
python -m ai.entrainement.evaluation --corpus val
```

Après ajout d'un corpus manuel annoté et tenu à l'écart de l'entraînement, mesurer séparément les résultats finaux avec :

```bash
python -m ai.entrainement.evaluation --corpus test
```
