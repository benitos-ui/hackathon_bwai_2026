"""Tests unitaires du module d'évaluation comparative et d'analyse d'erreurs (Étape 7a)."""

import json

import pytest

from ai.entrainement.evaluation import (
    analyser_erreurs,
    calibration,
    charger_corpus,
    evaluer_corpus,
    prf,
    taux_revue,
)


def test_charger_corpus_markup_et_preparse(tmp_path):
    f_markup = tmp_path / "test_manuel.jsonl"
    f_markup.write_text(
        json.dumps(
            {"role": "client", "markup": "Je veux [[2|QUANTITE]] [[robes Ayoka|PRODUIT]]"},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    c1 = charger_corpus(f_markup)
    assert len(c1) == 1
    assert c1[0]["text"] == "Je veux 2 robes Ayoka"
    assert len(c1[0]["gold"]) == 2

    f_val = tmp_path / "val.jsonl"
    f_val.write_text(
        json.dumps(
            {
                "role": "client",
                "text": "Merci beaucoup",
                "spans": [],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    c2 = charger_corpus(f_val)
    assert len(c2) == 1 and c2[0]["gold"] == []


def test_prf_strict_vs_souple():
    corpus = [
        {
            "text": "Je veux 2 robes Ayoka",
            "role": "client",
            "gold": [
                {"label": "QUANTITE", "debut": 8, "fin": 9, "texte": "2"},
                {"label": "PRODUIT", "debut": 10, "fin": 21, "texte": "robes Ayoka"},
            ],
        }
    ]

    # Frontière décalée sur PRODUIT ("Ayoka" au lieu de "robes Ayoka")
    def pred_decale(_ex):
        return [
            {"label": "QUANTITE", "debut": 8, "fin": 9, "texte": "2", "confiance": 0.95},
            {"label": "PRODUIT", "debut": 16, "fin": 21, "texte": "Ayoka", "confiance": 0.85},
        ]

    strict = prf(corpus, pred_decale, strict=True)
    souple = prf(corpus, pred_decale, strict=False)

    assert strict["par_entite"]["QUANTITE"]["f1"] == 1.0
    assert strict["par_entite"]["PRODUIT"]["f1"] == 0.0
    assert strict["micro"]["f1"] == 0.5
    assert souple["par_entite"]["PRODUIT"]["f1"] == 1.0
    assert souple["micro"]["f1"] == 1.0


def test_calibration_ece():
    corpus = [
        {
            "text": "2 robes",
            "role": "client",
            "gold": [{"label": "QUANTITE", "debut": 0, "fin": 1, "texte": "2"}],
        }
    ]

    # Prédiction exacte avec confiance 0.95 -> ECE = |1.0 - 0.95| = 0.05
    cal = calibration(
        corpus,
        lambda _ex: [{"label": "QUANTITE", "debut": 0, "fin": 1, "texte": "2", "confiance": 0.95}],
    )
    assert cal["nb_predictions"] == 1
    assert cal["ece"] == pytest.approx(0.05, abs=1e-4)


def test_analyser_erreurs_toutes_categories():
    corpus = [
        {
            "text": "2 robes Ayoka à Calavi",
            "role": "client",
            "gold": [
                {"label": "QUANTITE", "debut": 0, "fin": 1, "texte": "2"},
                {"label": "PRODUIT", "debut": 2, "fin": 13, "texte": "robes Ayoka"},
                {"label": "ZONE", "debut": 16, "fin": 22, "texte": "Calavi"},
            ],
        },
        {
            "text": "Merci beaucoup",
            "role": "client",
            "gold": [],
        },
    ]

    def pred_fn(ex):
        if ex["gold"]:
            return [
                # Confusion de classe (VARIANTE au lieu de QUANTITE)
                {"label": "VARIANTE", "debut": 0, "fin": 1, "texte": "2", "confiance": 0.8},
                # Frontière décalée sur PRODUIT
                {"label": "PRODUIT", "debut": 2, "fin": 7, "texte": "robes", "confiance": 0.8},
                # ZONE manquée !
            ]
        # Faux positif sur message sans entité
        return [{"label": "CLIENT", "debut": 0, "fin": 5, "texte": "Merci", "confiance": 0.7}]

    err = analyser_erreurs(corpus, pred_fn)
    c = err["compteurs"]
    assert c["confusion_classe"] == 1
    assert c["frontiere_decalee"] == 1
    assert c["entite_manquee"] == 1
    assert c["faux_positif_sans_entite"] == 1
    assert err["total_erreurs"] == 4


def test_evaluer_corpus_baseline_vs_modele_et_taux_revue():
    corpus = [
        {
            "text": "Bonjour, je veux 2 robes Ayoka en M",
            "role": "client",
            "gold": [
                {"label": "QUANTITE", "debut": 17, "fin": 18, "texte": "2"},
                {"label": "PRODUIT", "debut": 19, "fin": 30, "texte": "robes Ayoka"},
                {"label": "VARIANTE", "debut": 34, "fin": 35, "texte": "M"},
            ],
        },
        {
            "text": "Merci beaucoup, bonne soirée",
            "role": "client",
            "gold": [],
        },
    ]
    res = evaluer_corpus(corpus, source_corpus="val_synthetique")
    assert res["est_score_final_publiable"] is False
    assert res["avertissement"] is not None
    assert res["version_baseline"] == "baseline-1.0"
    assert res["version_modele"] in ("crf-v1", "ner-v1")
    assert res["taux_revue"]["baseline"]["taux_orange"] == 1.0
    assert res["taux_revue"]["modele"]["taux_vert"] > 0.0

    rev = taux_revue(corpus, mode="baseline", seuils={"vert": 0.90, "rouge": 0.60})
    assert rev["nb_orange"] == rev["total"] and rev["total"] > 0
