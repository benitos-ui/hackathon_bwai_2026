"""Tests unitaires du parseur WhatsApp et de l'identification client (Étape 2, exigence E1)."""

import pytest

from ai.parseur import FormatInvalide, analyser

FIL = """[25/11/2026 10:02:11] Awa: Bonjour, je veux 2 robes Ayoka
et 1 sérum
[25/11/2026 16:40:03] Livreur Marc: Livré chez Awa, 1 robe M livrée"""

ROLES = {"Livreur Marc": "livreur", "Boutique X": "vendeuse"}

CLIENTS = [
    {
        "identifiant": "CLI-0012",
        "nom": "Awa Dossou",
        "telephone": "+229 01 00 00 00 12",
        "zone": "Abomey-Calavi",
        "fidele": "oui",
    },
    {
        "identifiant": "CLI-0027",
        "nom": "Koffi Adjovi",
        "telephone": "+229 01 00 00 00 27",
        "zone": "Cotonou",
        "fidele": "non",
    },
]


def test_parse_basique():
    a = analyser(texte_brut=FIL, roles=ROLES, clients=CLIENTS)
    assert len(a["messages"]) == 2
    assert a["messages"][0]["rang"] == 0
    assert a["messages"][0]["message_id"] == "m1"
    assert a["messages"][0]["role"] == "client"
    assert "sérum" in a["messages"][0]["texte"]
    assert a["messages"][1]["rang"] == 1
    assert a["messages"][1]["message_id"] == "m2"
    assert a["messages"][1]["role"] == "livreur"


def test_format_alternatif():
    a = analyser(texte_brut="25/11/2026, 10:02 - Awa: Bonjour", roles={}, clients=CLIENTS)
    assert len(a["messages"]) == 1
    assert a["messages"][0]["auteur"] == "Awa"
    assert a["messages"][0]["horodatage"] == "2026-11-25T10:02:00"


def test_fichier_mal_forme():
    with pytest.raises(FormatInvalide):
        analyser(texte_brut="n'importe quoi", roles={}, clients=CLIENTS)


def test_entree_vide_ou_absente():
    with pytest.raises(FormatInvalide):
        analyser(texte_brut="   \n  ", roles={}, clients=CLIENTS)
    with pytest.raises(FormatInvalide):
        analyser(roles={}, clients=CLIENTS)


def test_empreinte_stable():
    a1 = analyser(texte_brut=FIL, roles=ROLES, clients=CLIENTS)
    a2 = analyser(texte_brut=FIL, roles=ROLES, clients=CLIENTS)
    assert a1["empreinte"].startswith("sha256:")
    assert a1["empreinte"] == a2["empreinte"]
    assert a1 == a2


def test_messages_systeme_ignores():
    fil = """\ufeff\u200e[25/11/2026 10:00:00] Boutique X: Les messages et appels sont chiffrés de bout en bout.
[25/11/2026 10:01:00] Awa: <Médias omis>
[25/11/2026 10:02:00] Awa: Bonjour, je veux 1 sac Lagune"""
    a = analyser(texte_brut=fil, roles=ROLES, clients=CLIENTS)
    assert len(a["messages"]) == 1
    assert a["messages"][0]["texte"] == "Bonjour, je veux 1 sac Lagune"


def test_simulateur_et_empreinte_commune():
    items = [
        {
            "auteur": "Awa",
            "role": "client",
            "texte": "Bonjour, je veux 2 robes Ayoka\net 1 sérum",
            "horodatage": "2026-11-25T10:02:00",
        },
        {
            "auteur": "Livreur Marc",
            "role": "livreur",
            "texte": "Livré chez Awa, 1 robe M livrée",
            "horodatage": "2026-11-25T16:40:00",
        },
    ]
    a_sim = analyser(items_simulateur=items, telephone="+229 01 00 00 00 12", clients=CLIENTS)
    a_exp = analyser(texte_brut=FIL, roles=ROLES, clients=CLIENTS)
    assert a_sim["empreinte"] == a_exp["empreinte"]
    assert a_sim["client"]["id"] == "CLI-0012"
    assert a_sim["client"]["methode"] == "telephone"


def test_simulateur_vide():
    with pytest.raises(FormatInvalide):
        analyser(items_simulateur=[], clients=CLIENTS)


def test_client_par_numero():
    fil = "[25/11/2026 10:02:11] +229 01 00 00 00 12: Bonjour"
    client = analyser(texte_brut=fil, roles={}, clients=CLIENTS)["client"]
    assert client["id"] == "CLI-0012"
    assert client["methode"] == "telephone"
    assert client["confiance"] == 0.96


def test_client_par_nom():
    fil = "[25/11/2026 10:02:11] Awa: Bonjour"
    client = analyser(texte_brut=fil, roles={}, clients=CLIENTS)["client"]
    assert client["id"] == "CLI-0012"
    assert client["methode"] == "nom"
    assert client["confiance"] >= 0.85


def test_client_inconnu():
    fil = "[25/11/2026 10:02:11] +229 99 99 99 99 99: Bonjour"
    assert analyser(texte_brut=fil, roles={}, clients=CLIENTS)["client"] is None


def test_roles_yaml_par_defaut():
    fil = "[25/11/2026 10:05:00] Vendeuse: Bonjour Awa\n[25/11/2026 16:40:00] Livreur: Livré"
    a = analyser(texte_brut=fil, clients=CLIENTS)
    assert a["messages"][0]["role"] == "vendeuse"
    assert a["messages"][1]["role"] == "livreur"
