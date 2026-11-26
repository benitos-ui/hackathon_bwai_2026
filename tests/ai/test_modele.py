"""Tests du service d'inférence modèle (cascade ner-v1 -> crf-v1 -> baseline) et téléchargement SHA-256."""

import logging
import zipfile

import pytest

from ai.extraction import extraire, get_mode
from ai.extraction import modele as mod_ner
from ai.normalisation import normaliser_dossier
from ai.parseur import analyser
from scripts.telecharger_modele import (
    calculer_sha256,
    lire_sha256_attendu,
    telecharger_et_installer,
)

SEUILS = {"vert": 0.90, "rouge": 0.60}

FIL_AWA = """[25/11/2026 10:02:00] Awa: Bonjour, je veux 2 robes Ayoka, une en M et une en L, et 1 sérum vitamine C svp
[25/11/2026 10:05:00] Vendeuse: Bonjour Awa, c'est noté. Livraison à Calavi ?
[25/11/2026 10:06:00] Awa: Oui à Calavi, paiement à la livraison
[25/11/2026 16:40:00] Livreur: Livré chez Awa. Elle a refusé la robe L (trop petite). 1 robe M + 1 sérum livrés, payé en espèces."""

ROLES = {"Vendeuse": "vendeuse", "Livreur": "livreur"}


@pytest.mark.skipif(
    not mod_ner.disponible(),
    reason="Poids modèle absents sur disque (lancer python -m ai.entrainement.crf_backup ou scripts/telecharger_modele.py)",
)
def test_crf_v1_charge_et_confiances_calibrees():
    mod_ner.reinitialiser_cache()
    assert mod_ner.disponible() is True
    assert get_mode("modele") == "modele"
    assert mod_ner.version_active() in ("ner-v1", "crf-v1")

    a = analyser(texte_brut=FIL_AWA, roles=ROLES, clients=[])
    champs = extraire(a["messages"], mode="modele", seuils=SEUILS)
    assert len(champs) >= 8

    # Chaque champ respecte le schéma §7.8, les offsets Unicode et porte version_modele calibrée
    textes = {m["message_id"]: m["texte"] for m in a["messages"]}
    versions = {c["version_modele"] for c in champs}
    assert versions == {mod_ner.version_active()}

    confiances = {c["confiance"] for c in champs if c["valeur"] is not None}
    assert confiances != {0.75}, "Le modèle calibré ne doit pas être figé à 0.75 comme la baseline"
    assert any(c["couleur"] == "vert" for c in champs)

    for c in champs:
        if c["valeur"] is not None:
            assert textes[c["message_id"]][c["debut"]:c["fin"]] == c["valeur"]


def test_cas_awa_bout_en_bout_en_mode_modele():
    a = analyser(texte_brut=FIL_AWA, roles=ROLES, clients=[])
    champs = extraire(a["messages"], mode="modele", seuils=SEUILS)
    d = normaliser_dossier(a["messages"], champs, client=None)

    robe = next(l for l in d["lignes"] if l["ref"] == "ART-001")
    serum = next(l for l in d["lignes"] if l["ref"] == "ART-004")

    assert robe["quantite_commandee"] == 2
    assert robe["quantite_livree"] == 1
    assert robe["variantes"]["commandees"] == ["M", "L"]
    assert robe["variantes"]["livrees"] == ["M"]
    assert "L" not in robe["variantes"]["livrees"]

    assert serum["quantite_commandee"] == 1
    assert serum["quantite_livree"] == 1
    assert d["zone"]["valeur"] == "Abomey-Calavi"
    assert d["signaux"]["refus"] and d["signaux"]["refus"][0]["variante"] == "L"


def test_modele_deterministe_et_sans_faux_positifs_sur_neutre():
    msgs = [
        {"message_id": "m1", "rang": 0, "role": "client", "texte": "Bonjour, je veux 2 robes Ayoka en M"},
        {"message_id": "m2", "rang": 1, "role": "client", "texte": "Merci beaucoup, bonne soirée"},
    ]
    c1 = extraire(msgs, mode="modele", seuils=SEUILS)
    c2 = extraire(msgs, mode="modele", seuils=SEUILS)
    assert c1 == c2
    assert [c for c in c1 if c["message_id"] == "m2"] == []


def test_cascade_priorite_ner_v1_puis_crf_v1_puis_baseline(monkeypatch, tmp_path, caplog):
    # 1. Aucun modèle disponible -> repli baseline journalisé
    monkeypatch.setattr(mod_ner, "CHEMIN_TRANSFORMER", tmp_path / "ner_absent")
    monkeypatch.setattr(mod_ner, "CHEMIN_CRF", tmp_path / "crf_absent")
    mod_ner.reinitialiser_cache()
    assert mod_ner.disponible() is False
    assert mod_ner.version_active() is None

    with caplog.at_level(logging.WARNING, logger="ai.extraction"):
        assert get_mode("modele") == "baseline"

    # 2. ner-v1 simulé complet sur disque -> prioritaire sur crf-v1
    faux_ner = tmp_path / "ner-v1"
    faux_ner.mkdir()
    (faux_ner / "calibration.json").write_text('{"temperature": 1.0, "version": "ner-v1"}', encoding="utf-8")
    (faux_ner / "config.json").write_text("{}", encoding="utf-8")
    (faux_ner / "model.safetensors").write_bytes(b"fake")
    monkeypatch.setattr(mod_ner, "CHEMIN_TRANSFORMER", faux_ner)
    mod_ner.reinitialiser_cache()

    src = mod_ner.source_disponible()
    assert src == ("transformer", faux_ner)


def test_telecharger_modele_sha256_valide_et_invalide(tmp_path):
    # Création d'une archive ZIP locale de test
    archive_src = tmp_path / "source_ner.zip"
    with zipfile.ZipFile(archive_src, "w") as zf:
        zf.writestr("ner-v1/calibration.json", '{"temperature": 1.05, "version": "ner-v1"}')

    empreinte = calculer_sha256(archive_src)
    fichier_sha = tmp_path / "ner-v1.sha256"
    fichier_sha.write_text(empreinte + "\n", encoding="utf-8")
    assert lire_sha256_attendu(fichier_sha) == empreinte

    url_locale = archive_src.resolve().as_uri()
    dossier_ok = tmp_path / "dest_ok"
    archive_dl = tmp_path / "dl_ok.zip"
    telecharger_et_installer(
        url=url_locale,
        sha256_attendu=empreinte,
        archive=archive_dl,
        dossier_sortie=dossier_ok,
    )
    assert (dossier_ok / "ner-v1" / "calibration.json").is_file()
    assert not archive_dl.exists()

    # Empreinte fausse -> ValueError + suppression obligatoire de l'archive corrompue
    archive_bad = tmp_path / "dl_bad.zip"
    dossier_bad = tmp_path / "dest_bad"
    with pytest.raises(ValueError, match="SHA-256 différente"):
        telecharger_et_installer(
            url=url_locale,
            sha256_attendu="0" * 64,
            archive=archive_bad,
            dossier_sortie=dossier_bad,
        )
    assert not archive_bad.exists()
    assert not (dossier_bad / "ner-v1" / "calibration.json").exists()


def test_telecharger_modele_bloque_zip_slip(tmp_path):
    archive_mal = tmp_path / "malicious.zip"
    with zipfile.ZipFile(archive_mal, "w") as zf:
        zf.writestr("../evasion.txt", "interdit")

    empreinte = calculer_sha256(archive_mal)
    archive_dl = tmp_path / "dl_slip.zip"
    with pytest.raises(ValueError, match="Zip-Slip"):
        telecharger_et_installer(
            url=archive_mal.resolve().as_uri(),
            sha256_attendu=empreinte,
            archive=archive_dl,
            dossier_sortie=tmp_path / "cible",
        )
    assert not archive_dl.exists()
    assert not (tmp_path / "evasion.txt").exists()
