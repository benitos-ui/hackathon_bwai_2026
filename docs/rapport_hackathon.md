# Boutique X — Assistant IA de facturation
## Rapport de prototype · BWAI 2026 · Cas pratique 2

**Version de travail : 26 novembre 2026**  
**Principe :** l’IA extrait, les règles calculent, l’humain décide.  
**Périmètre :** démonstrateur local de préparation, validation et suivi simulé de factures à partir de conversations WhatsApp.

> **Résumé.** Boutique X transforme un fil WhatsApp textuel en dossier de facturation contrôlable. L’interface montre les sources des extractions, les anomalies, le brouillon et les étapes de validation. Les données, factures, émissions et règlements sont fictifs. Le prototype ne se connecte pas à WhatsApp/Meta et ne constitue pas un système de facturation réglementaire.

## 1. Besoin et parcours métier

Dans une petite activité commerciale, les informations de commande, livraison et paiement peuvent être dispersées dans les messages. Leur ressaisie peut entraîner des oublis, doublons et écarts de montant. Le cas pratique demande de transformer une source commerciale en projet de facture vérifiable, puis de tracer les validations et règlements.

Le parcours démontré est le suivant :

1. Une vendeuse importe un export WhatsApp `.txt`, colle son contenu ou compose un fil dans le simulateur local.
2. Le système parse les messages, classe leur typologie, extrait les champs et les rapproche des référentiels.
3. La vendeuse consulte la source de chaque champ, corrige ou confirme les valeurs proposées.
4. Les contrôles signalent les anomalies — par exemple client inconnu, produit ambigu, prix inhabituel ou écart commande/livraison — et demandent une justification avant résolution.
5. Le moteur produit un brouillon PDF et calcule les montants à partir des règles configurées.
6. Un gérant différent de l’initiatrice valide la facture. Le numéro est attribué à cette étape, le contenu est figé, puis l’émission et le règlement peuvent être simulés.
7. Le journal d’audit permet de consulter les actions et de vérifier l’intégrité de sa chaîne.

**Scénario de référence Awa.** La cliente commande deux robes Ayoka (tailles M et L) et un sérum. Le fil indique que la robe L est refusée et qu’une robe M ainsi que le sérum sont acceptés. Le parcours de test vérifie la prise en compte des articles acceptés et un total TTC de **27 553 FCFA** selon les règles de démonstration. La simulation de messagerie ne transmet aucun message à un service externe.

\newpage

## 2. Architecture et contrôles

### Architecture

- **Interface :** Streamlit (`ui/`) pour le tableau de bord, l’import/simulateur de conversation, la revue, les anomalies, le brouillon, la facture et l’audit.
- **API :** FastAPI (`app/api/`) reliant l’interface au workflow.
- **Workflow et persistance :** service métier et SQLite (`app/workflow/`, `app/db/`) avec étapes reprenables, clés d’idempotence, contrôle de version et écritures transactionnelles.
- **Calcul et documents :** moteur déterministe en FCFA entiers, règles externes YAML, contrôles métier et génération PDF (`app/calcul/`, `app/controles/`, `app/pdf/`).
- **IA :** parseur WhatsApp, NER DistilCamemBERT `ner-v1`, repli CRF `crf-v1`, puis baseline à règles ; normalisation et rapprochement des valeurs avec les référentiels (`ai/`).

### Contrôles métier et sécurité des décisions

- L’extraction conserve les offsets et l’identifiant du message source. Une valeur qui n’existe pas à ces offsets, ou qui ne peut pas être normalisée, est rejetée ou laissée à renseigner.
- Le modèle n’invente pas de champ manquant, ne choisit pas silencieusement une référence ambiguë et ne calcule pas le montant de facture.
- Les prix, remises, frais de livraison et taxes proviennent des règles/référentiels. Le calcul est déterministe, effectué en entiers FCFA et utilise un arrondi explicite.
- Les quantités commandées, livrées, acceptées, refusées et manquantes sont contrôlées. Une anomalie ouverte bloque la validation.
- Les champs extraits requièrent une confirmation humaine. La validation applique le principe des quatre yeux (gérant distinct de l’initiateur).
- La validation est transactionnelle ; le document figé reçoit un hash SHA-256. L’import et les écritures concernées utilisent l’idempotence. Une outbox simule la reprise d’émission hors connexion.
- Les échanges, les paiements et les comptes de démonstration sont fictifs. Le sélecteur de rôle de l’interface n’est pas une authentification de production ; l’application n’est pas destinée à être exposée sur Internet.

**Exemple de calcul vérifié par le test bout-en-bout Awa :** sous-total articles 23 000 FCFA ; remise fidélité 1 150 FCFA ; livraison 1 500 FCFA ; base HT 23 350 FCFA ; TVA 4 203 FCFA ; total TTC 27 553 FCFA. Ces montants illustrent la configuration pédagogique, pas une conformité fiscale légale.

\newpage

## 3. Protocole de test et résultats

### Tests fonctionnels et reproductibilité

La suite `pytest -q` a été exécutée le 26 novembre 2026 après intégration du simulateur de conversation : **153 tests réussis**. Les tests couvrent les modules IA, le calcul et les anomalies, le workflow API et le parcours de bout en bout. Les scénarios automatisés comprennent notamment l’import idempotent, la correction/confirmation humaine, la résolution justifiée d’anomalies, les versions périmées, la concurrence de validations, la reprise après interruption, l’immuabilité du document et la vérification d’audit. Le test E2E vérifie également le PDF et les totaux du scénario Awa.

Commande de reproduction :

```bash
pytest -q
```

Le dépôt contient des données de démonstration réinitialisables et une interface locale. Les artefacts de modèle doivent être présents dans `ai/modeles/ner-v1/` pour charger le Transformer ; le service dispose de replis CRF et baseline.

### Évaluation de l’extraction

Le script `python -m ai.entrainement.evaluation --corpus val` compare le modèle à la baseline à règles sur les mêmes **1 183 exemples synthétiques** de validation, séparés de l’entraînement par gabarits. Les mesures d’extraction sont distinctes des tests métier et des calculs de facture.

| Mesure (validation synthétique) | Baseline | `ner-v1` |
|---|---:|---:|
| F1 strict micro | 0,6345 | **0,9759** |
| F1 strict macro | 0,6582 | **0,9857** |
| F1 souple micro | 0,7673 | **0,9797** |
| ECE sur les prédictions | 0,0230 | 0,0271 |
| Champs nécessitant une revue attentive | 100 % | 2,38 % |

Le F1 strict exige le bon type d’entité et des offsets exactement égaux ; le F1 souple accepte un chevauchement de même type. L’ECE résume l’écart entre confiance annoncée et précision observée. La baseline sert de référence technique d’extraction, pas de mesure chronométrée du travail humain antérieur.

\newpage

## 4. Limites, coûts et suites proposées

### Limites des résultats

Les jeux d’entraînement et de validation sont synthétiques. Le F1 élevé de `ner-v1` mesure la performance sur les gabarits de validation inédits dans ce corpus, **pas** sur des conversations réelles. L’évaluation a aussi relevé, pour `ner-v1`, 1 confusion de classe, 17 erreurs de frontière, 2 entités manquées et 168 faux positifs sur d’autres exemples. Le taux de revue attentive de 2,38 % est donc propre à ces données ; il ne justifie pas de retirer la confirmation humaine.

Le corpus manuel annoté `data/test_manuel.jsonl` (au moins 80 messages) n’est pas présent. Aucun score final terrain n’est donc publié, et aucun gain de temps par rapport à la saisie manuelle n’a été mesuré. Le socle évalué est en français ; le Fon, le code-switching, l’interprétation des images, pièces jointes et vocaux ne sont pas pris en charge. La facture est pédagogique et n’est pas présentée comme conforme au dispositif légal béninois. Les canaux de paiement et d’émission restent simulés.

### Coûts d’usage estimatifs

- **Démonstration locale :** aucun frais d’API d’IA, de WhatsApp, de paiement ou d’envoi par conversation n’est observé dans le prototype, car ces services ne sont pas appelés. Cette estimation exclut l’ordinateur, l’électricité, la connexion et le temps de l’équipe.
- **Entraînement :** le fine-tuning a été réalisé sur Colab GPU ; les journaux fournis indiquent environ 172 secondes d’entraînement effectif. Le type exact de GPU et le coût/crédit Colab consommé ne sont pas consignés : aucun montant monétaire fiable ne peut être donné à ce stade.
- **Expérimentation réelle :** coûts d’hébergement, sauvegarde, sécurisation et support à estimer après choix d’une infrastructure et d’un volume pilote.

### Étapes avant expérimentation

1. Constituer et faire annoter un corpus manuel d’au moins 80 messages fictifs ou anonymisés, séparé du train et de la validation.
2. Évaluer `ner-v1` et la baseline sur ce corpus, documenter les erreurs par entité et recalibrer les seuils de revue.
3. Mesurer le temps et les erreurs évitées sur un protocole comparant traitement manuel et parcours assisté, sans confondre qualité IA et exactitude des règles de calcul.
4. Faire valider les règles métier, les taxes, remises et mentions documentaires par les professionnels concernés.
5. Avant tout pilote : remplacer la sélection de rôle de démonstration par une authentification réelle, restreindre les accès, organiser sauvegardes/migrations de base et définir une politique de conservation des données.
6. Geler une version du dépôt accessible au jury, puis enregistrer la démonstration vidéo demandée.

**Conclusion.** Le prototype montre un parcours complet de facturation assistée sur le cas choisi et ses contrôles principaux sont couverts par des tests automatisés. Il constitue une base de démonstration réexécutable, mais une expérimentation métier nécessite une évaluation humaine indépendante, une sécurité de production et une validation réglementaire qui restent hors du périmètre actuel.
