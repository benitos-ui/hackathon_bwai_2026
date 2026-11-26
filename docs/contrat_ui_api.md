# Contrat d'interface UI / API (v0.1)

Proposition de Femi, à valider avec Bénito et Jean-Arthur. En cas de conflit avec l'addendum v1.1, l'addendum prévaut.

## 1. Principes

- L'interface ne calcule ni montant ni droit : elle envoie du texte et des décisions humaines, et affiche ce que l'API renvoie.
- Identifiants utilisateurs : `USR-VEND`, `USR-GER`, `USR-AUD`. Rôles : `vendeuse`, `gerant`, `auditeur`.
- Montants : entiers, en FCFA.
- Erreurs : codes HTTP 401, 403, 404, 409, 422, avec le corps `{"detail": "message en français"}`.
- `Idempotency-Key` obligatoire sur l'import, la validation et les règlements.
- Codes de statut sans accent, comme dans l'addendum.
  - Documentaire : `BROUILLON`, `A_REVOIR`, `PRET_A_VALIDER`, `VALIDEE`, `EMISE`.
  - Financier : `NON_REGLEE`, `PARTIELLEMENT_REGLEE`, `REGLEE`, `TROP_PERCU`, `REMBOURSEMENT_EN_COURS`.
  - Le service actuel renvoie des codes accentués (`PRÊT_À_VALIDER`) : à aligner sur l'addendum. À défaut, l'interface les normalise.

## 2. Routes

| Méthode | Route | Corps ou paramètres | Réponse | État |
|---|---|---|---|---|
| POST | `/dossiers/import` | `{raw_text, created_by}` + `Idempotency-Key` | `{dossier_id, version, duplicate}` | à créer |
| GET | `/dossiers/{id}` | | Dossier | à créer |
| GET | `/dossiers/{id}/messages` | | liste de Message | à créer |
| GET | `/dossiers/{id}/extractions` | | liste de Champ | à créer |
| POST | `/dossiers/{id}/champs/{field}/confirmer` | `{user, new_value?}` | Champ | à créer |
| GET | `/dossiers/{id}/anomalies` | | liste d'Anomalie | à créer |
| POST | `/anomalies/{id}/resoudre` | `{resolved_by, justification}` | Anomalie | existe |
| GET | `/dossiers/{id}/livraison` | | liste de LigneLivraison | à créer |
| GET | `/dossiers/{id}/facture` | | Facture | à créer |
| POST | `/dossiers/{id}/valider` | `{validator_id, validator_role, version}` + `Idempotency-Key` | `{invoice_id, number, ...}` | existe |
| POST | `/factures/{id}/reglements` | `{amount, mode, reference, entered_by}` + `Idempotency-Key` | Règlement | existe |
| GET | `/factures/{id}/solde` | | Solde | existe, à compléter |
| GET | `/dossiers/{id}/audit` | | liste d'EntréeAudit | à créer |
| GET | `/audit/verifier` | | `{valid, entries, broken_at}` | existe |

## 3. Formats

### Dossier
```json
{"dossier_id": "DOS-2026-0007", "doc_status": "A_REVOIR", "financial_status": "NON_REGLEE",
 "invoice_number": null, "invoice_id": null, "initiator": "USR-VEND", "version": 1}
```

### Message
```json
{"id": "m1", "time": "10:02", "author": "Awa", "text": "Bonjour, je veux 2 robes Ayoka...", "type_message": "COMMANDE"}
```

### Champ extrait (addendum section 4)
```json
{"field": "product_1", "value": "Robe wax Ayoka",
 "source": {"message_id": "m1", "text": "robes Ayoka", "start": 19, "end": 30},
 "confidence": 0.97, "couleur": "vert", "origin": "conversation",
 "status": "extracted", "model_version": "crf-v1", "confirmed": false}
```
- `status` : `extracted`, `needs_review`, `missing`, `ambiguous`.
- `origin` : `conversation`, `referentiel`, `systeme`.
- `start` et `end` : indices en caractères Unicode, `end` exclu. `source.message_id` peut être `null` si le champ est vide.
- `couleur` est fournie par l'API (`vert`, `orange`, `rouge`) : l'interface ne code aucun seuil.

### Anomalie
```json
{"id": "A1", "type": "commande_vs_livre", "resolved": false, "resolution": "", "message": "..."}
```

### LigneLivraison
```json
{"label": "Robe wax Ayoka, taille L", "ordered": 1, "delivered": 1, "accepted": 0, "refused": 1, "missing": 0, "reason": "Taille trop petite"}
```

### Facture
```json
{"lines": [{"label": "...", "qty": 1, "unit": 15000, "amount": 15000}],
 "totals": {"subtotal": 23000, "discount_label": "Remise fidélité 5 %", "discount": 1150,
            "base_after_discount": 21850, "delivery": 1500, "base_ht": 23350, "vat": 4203, "total_ttc": 27553}}
```

### Solde
```json
{"invoice_id": "INV-DOS-2026-0007", "total_ttc": 27553, "credits": 0, "paid": 0, "balance": 27553,
 "financial_status": "NON_REGLEE"}
```

### EntréeAudit
```json
{"n": 1, "timestamp": "2026-11-26T09:12:03+00:00", "action": "FIELD_CONFIRMED", "user": "USR-VEND", "detail": "client"}
```
Actions utilisées : `IMPORT`, `FIELD_CONFIRMED`, `FIELD_CORRECTED`, `ANOMALY_RESOLVED`, `INVOICE_VALIDATED`, `PAYMENT_ADDED`.

## 4. Règles côté serveur

- Après chaque confirmation de champ ou résolution d'anomalie, le statut documentaire est recalculé : anomalie ouverte donne `A_REVOIR`, tout confirmé donne `PRET_A_VALIDER`, sinon `BROUILLON`.
- Les anomalies détectées à l'import sont persistées, avec un identifiant stable.
- Résoudre une anomalie sans justification renvoie 422. La justification est enregistrée.
- Validation : 403 si le rôle n'est pas `gerant` ou si le validateur est l'initiateur, 409 si la version est périmée, 422 si le statut n'est pas `PRET_A_VALIDER`.
- Chaque écriture (import, confirmation, correction, résolution, validation, règlement) ajoute une entrée à l'audit.

## 5. Correspondance avec le format d'extraction de Jean-Arthur

| Format Jean-Arthur | Format de l'interface |
|---|---|
| `nom` | `field` |
| `valeur` (+ `ref`) | `value` |
| `valeur_brute` | affichée à côté de `value` (clé `raw_value`, optionnelle) |
| `source.debut` / `source.fin` | `source.start` / `source.end` |
| `confiance` | `confidence` |
| `couleur` | `couleur` (inchangé) |
| `statut` = `prerempli` avec couleur verte | `status` = `extracted` |
| `statut` = `prerempli` avec couleur orange | `status` = `needs_review` |
| `statut` = `a_renseigner` | `status` = `missing` |
| `version_modele` | `model_version` |

La traduction se fait à un seul endroit, dans la route `/extractions`, côté serveur.