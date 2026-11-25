"""Tests d'alignement avec l'Addendum v1.1 (§3.2, §3.3, §4, §8, T11, T12, T13, T20)."""

import pytest

from ai.extraction import extraire
from ai.normalisation import normaliser_dossier
from ai.normalisation.rapprochement import charger_alias, match_produit
from ai.parseur import FormatInvalide, TYPES_MESSAGE, analyser, classifier_message

ROLES = {"Vendeuse": "vendeuse", "Boutique X": "vendeuse", "Livreur": "livreur"}
SEUILS = {"vert": 0.90, "rouge": 0.60}


# ---- 1. Typologie des messages (§3.2) ----
@pytest.mark.parametrize(
    "texte,role,attendu",
    [
        ("Bonjour, je veux 2 robes Ayoka en M svp", "client", "COMMANDE"),
        ("Oui c'est bon, je confirme la commande", "client", "CONFIRMATION"),
        ("Bonjour Awa, c'est noté.", "vendeuse", "CONFIRMATION"),
        ("Finalement mets la taille L", "client", "MODIFICATION"),
        ("Non plutôt 3 sérums vitamine C", "client", "MODIFICATION"),
        ("J'annule la commande svp", "client", "ANNULATION"),
        ("Livré chez Awa. Elle a refusé la robe L (trop petite).", "livreur", "LIVRAISON"),
        ("J'ai envoyé 15000 par MoMo MTN", "client", "PAIEMENT"),
        ("Le sac reçu est déchiré, je demande un retour", "client", "RECLAMATION_RETOUR"),
        ("Merci beaucoup, bonne soirée !", "client", "INFORMATION"),
    ],
)
def test_typologie_messages(texte, role, attendu):
    res = classifier_message(texte, role)
    assert res in TYPES_MESSAGE
    assert res == attendu


def test_analyser_renseigne_type_message():
    fil = """[25/11/2026 10:02:00] Awa: Bonjour, je veux 1 robe Ayoka en M
[25/11/2026 10:03:00] Awa: Finalement mets la taille L
[25/11/2026 10:05:00] Vendeuse: C'est noté
[25/11/2026 16:40:00] Livreur: Livré chez Awa, 1 robe L livrée."""
    a = analyser(texte_brut=fil, roles=ROLES, clients=[])
    assert [m["type_message"] for m in a["messages"]] == [
        "COMMANDE",
        "MODIFICATION",
        "CONFIRMATION",
        "LIVRAISON",
    ]


# ---- 2. Médias non pris en charge (§3.3 / D8) ----
def test_medias_non_pris_en_charge_signales_export():
    fil = """[25/11/2026 10:00:00] Boutique X: Les messages et appels sont chiffrés de bout en bout.
[25/11/2026 10:01:00] Awa: <Médias omis>
[25/11/2026 10:01:30] Awa: PTT-20261125-WA0001.opus (fichier joint)
[25/11/2026 10:02:00] Awa: image omitted
[25/11/2026 10:03:00] Awa: Bonjour, je veux 1 sac Lagune"""
    a = analyser(texte_brut=fil, roles=ROLES, clients=[])
    assert len(a["messages"]) == 1
    assert a["messages"][0]["texte"] == "Bonjour, je veux 1 sac Lagune"

    medias = a["medias_non_pris_en_charge"]
    assert len(medias) == 3
    assert [m["type_media"] for m in medias] == ["media", "audio", "image"]
    assert all(m["motif"] == "media_non_pris_en_charge" for m in medias)
    assert all(m["auteur"] == "Awa" for m in medias)


def test_medias_non_pris_en_charge_simulateur():
    items = [
        {"auteur": "Awa", "role": "client", "texte": "audio omis", "horodatage": "2026-11-25T10:01:00"},
        {"auteur": "Awa", "role": "client", "texte": "Je veux 1 sérum vitamine C", "horodatage": "2026-11-25T10:02:00"},
    ]
    a = analyser(items_simulateur=items, clients=[])
    assert len(a["messages"]) == 1
    assert len(a["medias_non_pris_en_charge"]) == 1
    assert a["medias_non_pris_en_charge"][0]["type_media"] == "audio"


def test_uniquement_medias_leve_format_invalide():
    fil = "[25/11/2026 10:01:00] Awa: <Médias omis>\n[25/11/2026 10:02:00] Awa: image omitted"
    with pytest.raises(FormatInvalide, match="médias non pris en charge"):
        analyser(texte_brut=fil, roles=ROLES, clients=[])


# ---- 3. T11 — Modification de taille / quantité sans doublon silencieux ----
def test_t11_modification_taille_ligne_unique():
    fil = """[25/11/2026 10:02:00] Awa: Bonjour, je veux 1 robe Ayoka en M
[25/11/2026 10:04:00] Awa: Finalement mets la taille L"""
    a = analyser(texte_brut=fil, roles=ROLES, clients=[])
    champs = extraire(a["messages"], mode="baseline", seuils=SEUILS)
    d = normaliser_dossier(a["messages"], champs, client=None)

    assert len(d["lignes"]) == 1
    robe = d["lignes"][0]
    assert robe["ref"] == "ART-001"
    assert robe["quantite_commandee"] == 1
    assert robe["variantes"]["commandees"] == ["L"]
    assert d["signaux"]["ambiguite"] is False
    assert d["signaux"]["corrections"] == [
        {
            "type": "variante",
            "ref": "ART-001",
            "ancienne": "M",
            "nouvelle": "L",
            "message_id": "m2",
        }
    ]


def test_t11_modification_quantite_sans_repeter_produit():
    fil = """[25/11/2026 10:02:00] Awa: Bonjour, je veux 1 robe Ayoka en M
[25/11/2026 10:04:00] Awa: Non plutôt 3"""
    a = analyser(texte_brut=fil, roles=ROLES, clients=[])
    champs = extraire(a["messages"], mode="baseline", seuils=SEUILS)
    d = normaliser_dossier(a["messages"], champs, client=None)

    assert len(d["lignes"]) == 1
    assert d["lignes"][0]["quantite_commandee"] == 3
    assert d["signaux"]["ambiguite"] is False
    assert d["signaux"]["corrections"] == [
        {
            "type": "quantite",
            "ref": "ART-001",
            "ancienne": 1,
            "nouvelle": 3,
            "message_id": "m2",
        }
    ]


def test_t11_modification_taille_ambigue_multi_produits():
    fil = """[25/11/2026 10:02:00] Awa: Bonjour, je veux 1 robe Ayoka en M et 1 ensemble pagne Sènami en S
[25/11/2026 10:04:00] Awa: Finalement mets la taille L"""
    a = analyser(texte_brut=fil, roles=ROLES, clients=[])
    champs = extraire(a["messages"], mode="baseline", seuils=SEUILS)
    d = normaliser_dossier(a["messages"], champs, client=None)

    assert d["signaux"]["ambiguite"] is True
    assert any("modification de variante ambiguë" in m for m in d["signaux"]["motifs_ambiguite"])


def test_t11_modification_taille_ambigue_multi_variantes_meme_produit():
    fil = """[25/11/2026 10:02:00] Awa: Bonjour, je veux 2 robes Ayoka, une en M et une en L
[25/11/2026 10:04:00] Awa: Finalement mets la taille XL"""
    a = analyser(texte_brut=fil, roles=ROLES, clients=[])
    champs = extraire(a["messages"], mode="baseline", seuils=SEUILS)
    d = normaliser_dossier(a["messages"], champs, client=None)

    assert d["signaux"]["ambiguite"] is True
    assert any("plusieurs variantes existantes" in m for m in d["signaux"]["motifs_ambiguite"])


# ---- 4. T12 — Produits proches ambigus (A_PRODUIT_AMBIGU) & conservation valeur_brute (§4) ----
def test_t12_produits_proches_ambigus():
    alias_proches = {
        **charger_alias(),
        "produits": {
            "ART-001": ["robe wax ayoka", "robe ayoka"],
            "ART-006": ["robe wax amina", "robe amina"],
        },
    }
    catalogue_proches = {
        "ART-001": {"reference": "ART-001", "nom": "Robe wax Ayoka"},
        "ART-006": {"reference": "ART-006", "nom": "Robe wax Amina"},
    }

    # Mention générique ambiguë -> aucune sélection automatique
    res_match = match_produit("robe wax", alias_proches)
    assert res_match is not None
    assert res_match["ambigu"] is True
    assert res_match["ref"] is None
    assert {c["ref"] for c in res_match["candidats"]} == {"ART-001", "ART-006"}

    # Mention précise -> sélection sans ambiguïté
    res_precis = match_produit("robe wax ayoka", alias_proches)
    assert res_precis is not None
    assert res_precis["ambigu"] is False
    assert res_precis["ref"] == "ART-001"

    # Parcours complet normaliser_dossier : ambiguïté levée, aucune ligne auto-sélectionnée
    fil = "[25/11/2026 10:02:00] Awa: Bonjour, je veux 2 robes wax svp"
    a = analyser(texte_brut=fil, roles=ROLES, clients=[])
    champs = extraire(a["messages"], mode="baseline", seuils=SEUILS)
    d = normaliser_dossier(
        a["messages"], champs, client=None, alias=alias_proches, catalogue=catalogue_proches
    )

    assert d["lignes"] == []
    assert d["signaux"]["ambiguite"] is True
    assert any("A_PRODUIT_AMBIGU" in m for m in d["signaux"]["motifs_ambiguite"])
    assert len(d["signaux"]["produits_ambigus"]) == 1
    assert d["signaux"]["produits_ambigus"][0]["valeur_brute"] == "robes wax"

    champ_prod = next(c for c in d["champs"] if c["nom"] == "produit")
    assert champ_prod["valeur"] is None
    assert champ_prod["ref"] is None
    assert champ_prod["valeur_brute"] == "robes wax"
    assert champ_prod["statut"] == "a_renseigner"
    assert champ_prod["couleur"] == "rouge"


def test_conservation_ref_et_valeur_brute_et_t13():
    fil = """[25/11/2026 10:02:00] Awa: Bonjour, je veux 2 robes Ayoka, une en M et une en L
[25/11/2026 16:40:00] Livreur: Livré chez Awa. Elle a refusé la robe L (trop petite). 1 robe M livrée."""
    a = analyser(texte_brut=fil, roles=ROLES, clients=[])
    champs = extraire(a["messages"], mode="baseline", seuils=SEUILS)
    d = normaliser_dossier(a["messages"], champs, client=None)

    robe = d["lignes"][0]
    assert robe["quantite_commandee"] == 2
    assert robe["quantite_livree"] == 1
    assert robe["quantite_refusee"] == 1
    assert "robes Ayoka" in robe["mentions_brutes"]

    champ_prod = next(c for c in d["champs"] if c["nom"] == "produit" and c["ref"] == "ART-001")
    assert champ_prod["ref"] == "ART-001"
    assert champ_prod["valeur"] == "Robe wax Ayoka"
    assert champ_prod["valeur_brute"] == "robes Ayoka"
    assert d["signaux"]["multi_commandes"] is False


# ---- 5. T20 — Détection multi-commandes / multi-clients (A_CONVERSATION) ----
def test_t20_deux_commandes_apres_livraison():
    fil = """[25/11/2026 10:02:00] Awa: Bonjour, je veux 1 robe Ayoka en M
[25/11/2026 16:40:00] Livreur: Livré chez Awa, 1 robe M livrée.
[26/11/2026 09:15:00] Awa: Bonjour, je veux 1 sac Lagune svp"""
    a = analyser(texte_brut=fil, roles=ROLES, clients=[])
    champs = extraire(a["messages"], mode="baseline", seuils=SEUILS)
    d = normaliser_dossier(a["messages"], champs, client=None)

    assert d["signaux"]["ambiguite"] is True
    assert d["signaux"]["multi_commandes"] is True
    assert any("A_CONVERSATION" in m for m in d["signaux"]["motifs_ambiguite"])


def test_t20_deux_clients_dans_meme_fil():
    fil = """[25/11/2026 10:02:00] Awa: Bonjour, je veux 1 robe Ayoka en M
[25/11/2026 10:05:00] Koffi: Bonjour, je prends 1 sac Lagune"""
    a = analyser(texte_brut=fil, roles=ROLES, clients=[])
    champs = extraire(a["messages"], mode="baseline", seuils=SEUILS)
    d = normaliser_dossier(a["messages"], champs, client=None)

    assert d["signaux"]["ambiguite"] is True
    assert d["signaux"]["multi_commandes"] is True
    assert any("plusieurs clients" in m for m in d["signaux"]["motifs_ambiguite"])


def test_t20_mention_explicite_deuxieme_commande():
    fil = """[25/11/2026 10:02:00] Awa: Bonjour, je veux 1 robe Ayoka en M
[25/11/2026 10:10:00] Awa: Pour une deuxième commande, je veux 1 sac Lagune (facture séparée)"""
    a = analyser(texte_brut=fil, roles=ROLES, clients=[])
    champs = extraire(a["messages"], mode="baseline", seuils=SEUILS)
    d = normaliser_dossier(a["messages"], champs, client=None)

    assert d["signaux"]["ambiguite"] is True
    assert d["signaux"]["multi_commandes"] is True
    assert any("A_CONVERSATION" in m for m in d["signaux"]["motifs_ambiguite"])


def test_t20_deux_commandes_espacees_24h():
    fil = """[25/11/2026 10:02:00] Awa: Bonjour, je veux 1 robe Ayoka en M
[27/11/2026 11:00:00] Awa: Bonjour, je prends 1 sérum vitamine C"""
    a = analyser(texte_brut=fil, roles=ROLES, clients=[])
    champs = extraire(a["messages"], mode="baseline", seuils=SEUILS)
    d = normaliser_dossier(a["messages"], champs, client=None)

    assert d["signaux"]["ambiguite"] is True
    assert d["signaux"]["multi_commandes"] is True
    assert any("espacées" in m for m in d["signaux"]["motifs_ambiguite"])
