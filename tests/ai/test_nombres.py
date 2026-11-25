"""Tests unitaires de la normalisation et du rapprochement (Étape 3, exigence E3 : ≥ 30 formulations)."""

import pytest

from ai.normalisation import en_contrat, normaliser_dossier
from ai.normalisation.nombres import parse_montant, parse_quantite
from ai.normalisation.rapprochement import (
    charger_alias,
    match_produit,
    match_variante,
    match_zone,
    normaliser_paiement,
)

ALIAS = charger_alias()

CATALOGUE = {
    "ART-001": {"reference": "ART-001", "nom": "Robe wax Ayoka"},
    "ART-002": {"reference": "ART-002", "nom": "Ensemble pagne Sènami"},
    "ART-003": {"reference": "ART-003", "nom": "Sac à main Lagune"},
    "ART-004": {"reference": "ART-004", "nom": "Sérum vitamine C 30 ml"},
    "ART-005": {"reference": "ART-005", "nom": "Beurre de karité 200 ml"},
}


# ---- 1. Montants (19 formulations) ----
@pytest.mark.parametrize(
    "txt,attendu",
    [
        ("15.000", 15000),
        ("15 000", 15000),
        ("15\u202f000", 15000),
        ("15000", 15000),
        ("15000f", 15000),
        ("15k", 15000),
        ("15 mille", 15000),
        ("quinze mille", 15000),
        ("quinze mille francs", 15000),
        ("8k", 8000),
        ("8.000 fcfa", 8000),
        ("8 000 f cfa", 8000),
        ("vingt-deux mille cinq cents", 22500),
        ("trois mille cinq cents", 3500),
        ("douze mille", 12000),
        ("22000 f", 22000),
        ("22000 XOF", 22000),
        ("3 500", 3500),
        ("3.500", 3500),
    ],
)
def test_montants(txt, attendu):
    assert parse_montant(txt) == attendu


# ---- 2. Quantités (12 formulations) ----
@pytest.mark.parametrize(
    "txt,attendu",
    [
        ("2", 2),
        ("deux", 2),
        ("une", 1),
        ("un", 1),
        ("x3", 3),
        ("3x", 3),
        ("six", 6),
        ("dix", 10),
        ("quatre-vingt-dix", 90),
        ("soixante-quinze", 75),
        ("cent vingt", 120),
        ("zéro", 0),
        ("vingt et un", 21),
        ("quatre-vingts", 80),
    ],
)
def test_quantites(txt, attendu):
    assert parse_quantite(txt) == attendu


# ---- 3. Alias de zones (9 formulations) ----
@pytest.mark.parametrize(
    "txt,attendu",
    [
        ("Calavi", "Abomey-Calavi"),
        ("Abomey-Calavi", "Abomey-Calavi"),
        ("à calavi", "Abomey-Calavi"),
        ("abc", "Abomey-Calavi"),
        ("calavie", "Abomey-Calavi"),
        ("Cotonou", "Cotonou"),
        ("cotonu", "Cotonou"),
        ("Porto-Novo", "Porto-Novo"),
        ("pn", "Porto-Novo"),
    ],
)
def test_alias_zones(txt, attendu):
    m = match_zone(txt, ALIAS)
    assert m is not None and m["zone"] == attendu


# ---- 4. Produits approchants (9 formulations) ----
@pytest.mark.parametrize(
    "txt,attendu",
    [
        ("robes Ayoka", "ART-001"),
        ("rbe wax", "ART-001"),
        ("ayoka", "ART-001"),
        ("ensemble pagne sènami", "ART-002"),
        ("pagne senami", "ART-002"),
        ("sac à main lagune", "ART-003"),
        ("sac lagun", "ART-003"),
        ("serum vit c", "ART-004"),
        ("beurre de karité", "ART-005"),
    ],
)
def test_produits_approchants(txt, attendu):
    m = match_produit(txt, ALIAS)
    assert m is not None and m["ref"] == attendu


# ---- 5. Variantes & paiements (10 formulations) ----
@pytest.mark.parametrize(
    "txt,attendu",
    [
        ("M", "M"),
        ("taille L", "L"),
        ("en S", "S"),
        ("grande", "L"),
        ("moyenne", "M"),
        ("XL", "XL"),
    ],
)
def test_variantes(txt, attendu):
    assert match_variante(txt, ALIAS) == attendu


@pytest.mark.parametrize(
    "txt,attendu",
    [
        ("paiement à la livraison", "a_la_livraison"),
        ("cash", "especes"),
        ("espèces", "especes"),
        ("MoMo MTN", "mobile_money"),
    ],
)
def test_paiements(txt, attendu):
    assert normaliser_paiement(txt) == attendu


# ---- 6. Sécurité : valeurs indéchiffrables -> None (jamais de devinette) ----
def test_indechiffrables():
    assert parse_montant("beaucoup") is None
    assert parse_quantite("quelques-unes") is None
    assert match_zone("Paris", ALIAS) is None
    assert match_produit("voiture", ALIAS) is None
    assert match_produit("a", ALIAS) is None
    assert match_variante("XXL", ALIAS) is None
    assert normaliser_paiement("chèque") is None


# ---- 7. Assemblage : exclusion stricte des REFUS, séparation commandé/livré, contrat ----
def test_refus_strictement_exclu_des_lignes():
    messages = [
        {
            "rang": 0,
            "message_id": "m1",
            "role": "client",
            "texte": "Bonjour, je veux 2 robes Ayoka, une en M et une en L",
        },
        {
            "rang": 1,
            "message_id": "m2",
            "role": "livreur",
            "texte": "Elle a refusé la robe L (trop petite). 1 robe M livrée.",
        },
    ]
    champs = [
        {"nom": "quantite", "valeur": "2", "message_id": "m1", "debut": 17, "fin": 18, "confiance": 0.98, "version_modele": "t", "statut": "prerempli", "couleur": "vert"},
        {"nom": "produit", "valeur": "robes Ayoka", "message_id": "m1", "debut": 19, "fin": 30, "confiance": 0.97, "version_modele": "t", "statut": "prerempli", "couleur": "vert"},
        {"nom": "quantite", "valeur": "une", "message_id": "m1", "debut": 32, "fin": 35, "confiance": 0.95, "version_modele": "t", "statut": "prerempli", "couleur": "vert"},
        {"nom": "variante", "valeur": "M", "message_id": "m1", "debut": 39, "fin": 40, "confiance": 0.95, "version_modele": "t", "statut": "prerempli", "couleur": "vert"},
        {"nom": "quantite", "valeur": "une", "message_id": "m1", "debut": 44, "fin": 47, "confiance": 0.95, "version_modele": "t", "statut": "prerempli", "couleur": "vert"},
        {"nom": "variante", "valeur": "L", "message_id": "m1", "debut": 51, "fin": 52, "confiance": 0.95, "version_modele": "t", "statut": "prerempli", "couleur": "vert"},
        # Passages dans m2 : le refus englobe "robe" et "L" qui ne doivent PAS entrer dans les lignes
        {"nom": "refus", "valeur": "refusé la robe L", "message_id": "m2", "debut": 7, "fin": 23, "confiance": 0.90, "version_modele": "t", "statut": "prerempli", "couleur": "vert"},
        {"nom": "produit", "valeur": "robe", "message_id": "m2", "debut": 17, "fin": 21, "confiance": 0.90, "version_modele": "t", "statut": "prerempli", "couleur": "vert"},
        {"nom": "variante", "valeur": "L", "message_id": "m2", "debut": 22, "fin": 23, "confiance": 0.90, "version_modele": "t", "statut": "prerempli", "couleur": "vert"},
        {"nom": "motif_refus", "valeur": "trop petite", "message_id": "m2", "debut": 25, "fin": 36, "confiance": 0.88, "version_modele": "t", "statut": "prerempli", "couleur": "orange"},
        {"nom": "quantite", "valeur": "1", "message_id": "m2", "debut": 39, "fin": 40, "confiance": 0.96, "version_modele": "t", "statut": "prerempli", "couleur": "vert"},
        {"nom": "produit", "valeur": "robe", "message_id": "m2", "debut": 41, "fin": 45, "confiance": 0.96, "version_modele": "t", "statut": "prerempli", "couleur": "vert"},
        {"nom": "variante", "valeur": "M", "message_id": "m2", "debut": 46, "fin": 47, "confiance": 0.96, "version_modele": "t", "statut": "prerempli", "couleur": "vert"},
    ]

    dossier = normaliser_dossier(messages, champs, client=None, alias=ALIAS, catalogue=CATALOGUE)
    assert len(dossier["lignes"]) == 1
    robe = dossier["lignes"][0]
    assert robe["ref"] == "ART-001"
    assert robe["quantite_commandee"] == 2
    assert robe["quantite_livree"] == 1
    assert robe["variantes"]["commandees"] == ["M", "L"]
    assert robe["variantes"]["livrees"] == ["M"]
    assert "L" not in robe["variantes"]["livrees"]
    assert dossier["signaux"]["refus"] == [
        {"ref": "ART-001", "variante": "L", "motif": "taille", "message_id": "m2"}
    ]
    assert dossier["signaux"]["ambiguite"] is False

    # Vérification du format contrat (Annexe A)
    premier_champ = dossier["champs"][0]
    assert "source" in premier_champ and premier_champ["source"] == {
        "message_id": "m1",
        "debut": 17,
        "fin": 18,
    }
    assert "message_id" not in premier_champ


def test_en_contrat_champ_vide():
    c = {
        "id": "c3",
        "nom": "variante",
        "valeur": None,
        "ref": None,
        "message_id": None,
        "debut": None,
        "fin": None,
        "confiance": 0.0,
        "couleur": "rouge",
        "statut": "a_renseigner",
        "version_modele": "ner-v1",
        "rejet": "absent_du_texte",
    }
    res = en_contrat(c)
    assert res["source"] is None
    assert "rejet" not in res
    assert "message_id" not in res
    assert res["statut"] == "a_renseigner"
