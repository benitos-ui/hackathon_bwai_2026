"""Test de bout en bout du cas complet d'Awa (CDC §3.4) avec la baseline (Jalon H6)."""

from ai.extraction import extraire
from ai.normalisation import normaliser_dossier
from ai.parseur import analyser

FIL = """[25/11/2026 10:02:00] Awa: Bonjour, je veux 2 robes Ayoka, une en M et une en L, et 1 sérum vitamine C svp
[25/11/2026 10:05:00] Vendeuse: Bonjour Awa, c'est noté. Livraison à Calavi ?
[25/11/2026 10:06:00] Awa: Oui à Calavi, paiement à la livraison
[25/11/2026 16:40:00] Livreur: Livré chez Awa. Elle a refusé la robe L (trop petite). 1 robe M + 1 sérum livrés, payé en espèces."""

ROLES = {"Vendeuse": "vendeuse", "Livreur": "livreur"}

CLIENTS = [
    {
        "identifiant": "CLI-0012",
        "nom": "Awa Dossou",
        "telephone": "+229 01 00 00 00 12",
        "zone": "Abomey-Calavi",
        "fidele": "oui",
    }
]


def test_exemple_awa():
    a = analyser(texte_brut=FIL, roles=ROLES, clients=CLIENTS)
    assert a["client"] is not None and a["client"]["id"] == "CLI-0012"

    champs = extraire(a["messages"], mode="baseline", seuils={"vert": 0.90, "rouge": 0.60})
    assert champs
    # Vérification du schéma plat §7.8 sur tous les champs extraits
    for c in champs:
        assert {"nom", "valeur", "message_id", "debut", "fin", "confiance", "version_modele", "statut", "couleur"} <= set(c)
        assert c["version_modele"] == "baseline-1.0"

    d = normaliser_dossier(a["messages"], champs, a["client"])

    robe = next(l for l in d["lignes"] if l["ref"] == "ART-001")
    serum = next(l for l in d["lignes"] if l["ref"] == "ART-004")

    # Commandé != livré (détecté ensuite par Primel, jamais tranché par l'IA)
    assert robe["quantite_commandee"] == 2
    assert robe["quantite_livree"] == 1
    assert robe["variantes"]["commandees"] == ["M", "L"]
    assert robe["repartition_commandee"] == [
        {"variante": "M", "quantite": 1},
        {"variante": "L", "quantite": 1},
    ]
    assert robe["variantes"]["livrees"] == ["M"]
    assert "L" not in robe["variantes"]["livrees"]  # le refus n'entre jamais dans les lignes

    assert serum["quantite_commandee"] == 1
    assert serum["quantite_livree"] == 1

    assert d["zone"]["valeur"] == "Abomey-Calavi"
    assert d["paiement"]["valeur"] in ("a_la_livraison", "especes")
    assert d["signaux"]["refus"]
    assert d["signaux"]["refus"][0]["ref"] == "ART-001"
    assert d["signaux"]["refus"][0]["variante"] == "L"
    assert d["signaux"]["refus"][0]["motif"] == "taille"

    # Format contrat Annexe A (source imbriquée)
    assert all("source" in c and "message_id" not in c for c in d["champs"])


def test_determinisme_bout_en_bout():
    def executer():
        a = analyser(texte_brut=FIL, roles=ROLES, clients=CLIENTS)
        champs = extraire(a["messages"], mode="baseline", seuils={"vert": 0.90, "rouge": 0.60})
        return normaliser_dossier(a["messages"], champs, a["client"])

    assert executer() == executer()
