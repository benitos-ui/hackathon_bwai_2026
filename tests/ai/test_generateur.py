"""Tests unitaires du générateur de données synthétiques (Étape 5 — Jalon H8)."""

import pytest

from ai.entrainement.generateur import (
    FAMILLES,
    GABARITS,
    est_validation,
    generer,
)
from ai.entrainement.markup import valider_spans
from ai.extraction.schema import ENTITES


def test_couverture_gabarits_et_familles():
    assert len(GABARITS) >= 40
    tids = [tid for tid, _, _, _ in GABARITS]
    assert len(tids) == len(set(tids)), "Les identifiants tid doivent être uniques"
    assert len(FAMILLES) >= 10

    # Chaque famille dispose d'au moins 4 gabarits et d'au moins 1 gabarit en train et en val
    for fam in FAMILLES:
        tids_fam = [tid for tid, f, _, _ in GABARITS if f == fam]
        assert len(tids_fam) >= 4, f"Famille '{fam}' a moins de 4 gabarits"
        assert any(not est_validation(t) for t in tids_fam), f"Famille '{fam}' absente de train"
        assert any(est_validation(t) for t in tids_fam), f"Famille '{fam}' absente de val"


def test_determinisme_meme_graine():
    tr1, va1 = generer(n=400, seed=42)
    tr2, va2 = generer(n=400, seed=42)
    assert tr1 == tr2
    assert va1 == va2


def test_split_strictement_disjoint_par_gabarit():
    tr, va = generer(n=1200, seed=42)
    assert len(tr) + len(va) == 1200
    assert len(tr) > 0 and len(va) > 0

    tids_train = {ex["tid"] for ex in tr}
    tids_val = {ex["tid"] for ex in va}
    assert tids_train.isdisjoint(tids_val), "Fuite de gabarits entre train et val !"

    # Toutes les familles sont présentes dans train et dans val
    fams_train = {ex["famille"] for ex in tr}
    fams_val = {ex["famille"] for ex in va}
    assert fams_train == set(FAMILLES)
    assert fams_val == set(FAMILLES)


def test_toutes_les_entites_presentes_dans_train_et_val():
    tr, va = generer(n=2000, seed=42)
    entites_train = {sp["label"] for ex in tr for sp in ex["spans"]}
    entites_val = {sp["label"] for ex in va for sp in ex["spans"]}
    assert entites_train == set(ENTITES)
    assert entites_val == set(ENTITES)


def test_offsets_unicode_et_messages_sans_entite():
    tr, va = generer(n=1000, seed=42)
    tous = tr + va

    # Offsets Unicode strictement exacts sur 100 % des messages générés
    for ex in tous:
        assert valider_spans(ex["text"], ex["spans"]) == []
        assert "[[" not in ex["text"] and "]]" not in ex["text"]

    # Présence effective de messages sans entité (essentiel contre les faux positifs)
    sans_entite_tr = [ex for ex in tr if not ex["spans"]]
    sans_entite_va = [ex for ex in va if not ex["spans"]]
    assert len(sans_entite_tr) > 0
    assert len(sans_entite_va) > 0

    # Présence d'exemples contenant des émojis Unicode multi-octets avec spans exacts
    avec_emojis = [ex for ex in tous if any(ord(ch) > 0xFFFF for ch in ex["text"]) and ex["spans"]]
    assert len(avec_emojis) > 0
    for ex in avec_emojis:
        for sp in ex["spans"]:
            assert ex["text"][sp["debut"]:sp["fin"]] == sp["texte"]


def test_generer_n_invalide():
    with pytest.raises(ValueError):
        generer(n=0, seed=42)
