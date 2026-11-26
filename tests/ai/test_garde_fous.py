"""Tests unitaires des garde-fous anti-hallucination, du repli baseline et du surlignage (E2, §7.8)."""

import logging

from ai.extraction import extraire, get_mode
from ai.extraction.garde_fous import appliquer_garde_fous
from ai.extraction.surlignage import surligner

SEUILS = {"vert": 0.90, "rouge": 0.60}
MSG = [{"message_id": "m1", "rang": 0, "role": "client", "texte": "je veux 2 robes"}]


def champ(**kw):
    return {
        "nom": "quantite",
        "valeur": "2",
        "message_id": "m1",
        "debut": 8,
        "fin": 9,
        "confiance": 0.95,
        "version_modele": "t",
        **kw,
    }


def test_present_et_vert():
    c = appliquer_garde_fous([champ()], MSG, SEUILS)[0]
    assert c["valeur"] == "2"
    assert c["couleur"] == "vert"
    assert c["statut"] == "prerempli"


def test_orange():
    c = appliquer_garde_fous([champ(confiance=0.75)], MSG, SEUILS)[0]
    assert c["valeur"] == "2"
    assert c["couleur"] == "orange"
    assert c["statut"] == "prerempli"


def test_rouge_laisse_vide():
    c = appliquer_garde_fous([champ(confiance=0.40)], MSG, SEUILS)[0]
    assert c["valeur"] is None
    assert c["statut"] == "a_renseigner"
    assert c["couleur"] == "rouge"
    assert c["rejet"] == "confiance_basse"


def test_valeur_absente_du_texte_rejetee():
    c = appliquer_garde_fous([champ(valeur="3")], MSG, SEUILS)[0]
    assert c["valeur"] is None
    assert c["message_id"] is None
    assert c["debut"] is None and c["fin"] is None
    assert c["confiance"] == 0.0
    assert c["statut"] == "a_renseigner"
    assert c["couleur"] == "rouge"
    assert c["rejet"] == "absent_du_texte"


def test_offsets_hors_limites():
    c = appliquer_garde_fous([champ(fin=99)], MSG, SEUILS)[0]
    assert c["valeur"] is None
    assert c["statut"] == "a_renseigner"
    assert c["rejet"] == "absent_du_texte"


def test_message_id_inconnu_rejete():
    c = appliquer_garde_fous([champ(message_id="m99")], MSG, SEUILS)[0]
    assert c["valeur"] is None
    assert c["rejet"] == "absent_du_texte"


def test_repli_automatique_sur_baseline(caplog, monkeypatch, tmp_path):
    from ai.extraction import modele as mod_ner

    monkeypatch.setattr(mod_ner, "CHEMIN_TRANSFORMER", tmp_path / "absent_ner")
    monkeypatch.setattr(mod_ner, "CHEMIN_CRF", tmp_path / "absent_crf")
    mod_ner.reinitialiser_cache()

    with caplog.at_level(logging.WARNING, logger="ai.extraction"):
        assert get_mode("modele") == "baseline"
        champs = extraire(MSG, mode="modele", seuils=SEUILS)
    assert champs and all(c["version_modele"] == "baseline-1.0" for c in champs)
    assert any("repli automatique sur la baseline" in r.message.lower() for r in caplog.records)


def test_message_sans_entite_ne_cree_rien():
    msgs = [{"message_id": "m1", "rang": 0, "role": "client", "texte": "Merci beaucoup, bonne soirée"}]
    assert extraire(msgs, mode="baseline", seuils=SEUILS) == []


def test_surlignage_unicode_et_echappement_html():
    texte = "🙏 Je veux <2> robes"
    debut = texte.index("2")
    champs = [{"id": "c1", "debut": debut, "fin": debut + 1, "couleur": "vert"}]
    res = surligner(texte, champs)
    assert "<mark data-champ='c1' class='conf-vert'>2</mark>" in res
    assert "&lt;" in res and "&gt;" in res
    assert res.startswith("🙏 Je veux ")
