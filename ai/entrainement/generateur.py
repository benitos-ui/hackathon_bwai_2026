"""Générateur reproductible de conversations synthétiques annotées (Étape 5 — Jalon H8).

Caractéristiques clés (Guide §10.1 & Addendum v1.1 §3.2–§3.3) :
- **60 gabarits variés** répartis équitablement sur **12 familles** (5 gabarits/famille)
  sur le socle linguistique français (le Fon / code-switching reste hors socle).
- **Split strictement disjoint par gabarit** : les gabarits ``tid % 5 == 0`` (1 par famille,
  soit 12 gabarits / 20 %) alimentent exclusivement ``val.jsonl`` et les 48 autres (80 %)
  alimentent exclusivement ``train.jsonl``. Toutes les 12 familles et les 11 entités NER
  sont représentées dans les deux jeux sans aucune fuite de gabarit.
- **Bruit orthographique contrôlé** (suppression/doublement/inversion de lettres, suppression
  d'accents, variations de casse et de format numérique) appliqué avant le balisage afin de
  garantir des offsets Unicode strictement exacts via ``parse_markup`` + ``valider_spans``.
- **Fonction pure et déterministe** : ``generer(n=6000, seed=42)`` produit toujours la même
  sortie à graine identique (aucun effet de bord disque ; écriture isolée dans ``main()``).
"""

import argparse
import json
import random
from pathlib import Path
from typing import Union

from ai.config import CHEMIN_DONNEES, SEED
from ai.entrainement.markup import parse_markup, valider_spans
from ai.normalisation.nombres import sans_accents

# ---- Lexiques fictifs (socle français, contexte Boutique X) ----

PRODUITS_SING: tuple[str, ...] = (
    "robe Ayoka",
    "robe wax Ayoka",
    "robe wax",
    "robe",
    "ensemble pagne Sènami",
    "ensemble Sènami",
    "pagne Sènami",
    "ensemble",
    "sac Lagune",
    "sac à main Lagune",
    "sac à main",
    "sac",
    "sérum vitamine C",
    "sérum vit C",
    "sérum",
    "beurre de karité",
    "beurre de karité 200ml",
    "karité",
)

PRODUITS_PLUR: tuple[str, ...] = (
    "robes Ayoka",
    "robes wax Ayoka",
    "robes wax",
    "robes",
    "ensembles pagne Sènami",
    "ensembles Sènami",
    "ensembles",
    "sacs Lagune",
    "sacs à main Lagune",
    "sacs",
    "sérums vitamine C",
    "sérums vit C",
    "beurres de karité",
)

PRODUITS_COURT_REFUS: tuple[str, ...] = (
    "la robe",
    "la robe Ayoka",
    "la robe wax",
    "l'ensemble Sènami",
    "le sac Lagune",
)

TAILLES: tuple[str, ...] = ("S", "M", "L", "XL")

VARIANTES_LIBRES: tuple[str, ...] = (
    "S",
    "M",
    "L",
    "XL",
    "taille S",
    "taille M",
    "taille L",
    "taille XL",
    "petite",
    "moyenne",
    "grande",
)

ZONES: tuple[str, ...] = (
    "Calavi",
    "Abomey-Calavi",
    "Cotonou",
    "Porto-Novo",
    "porto novo",
    "Cotonou ville",
)

PAIEMENTS: tuple[str, ...] = (
    "paiement à la livraison",
    "à la livraison",
    "cash",
    "espèces",
    "en espèces",
    "momo",
    "MoMo MTN",
    "mobile money",
    "Moov",
    "Celtiis",
)

MOTIFS_REFUS: tuple[str, ...] = (
    "trop petite",
    "trop grande",
    "pas la bonne taille",
    "trop courte",
    "trop serrée",
    "défectueuse",
    "couleur différente",
    "abîmée",
)

NOMBRES_SING: tuple[str, ...] = ("1", "un", "une", "x1")
NOMBRES_PLUR: tuple[str, ...] = (
    "2",
    "deux",
    "x2",
    "3",
    "trois",
    "x3",
    "4",
    "quatre",
    "5",
    "cinq",
)

PRIX: tuple[str, ...] = (
    "15000",
    "15.000",
    "15 000",
    "15k",
    "15 mille",
    "quinze mille",
    "15000f",
    "8k",
    "8.000 fcfa",
    "8 000 f cfa",
    "12.000 FCFA",
    "douze mille",
    "22 000 f",
    "22000 XOF",
    "6 500 fcfa",
    "3 500",
)

DATES: tuple[str, ...] = (
    "demain",
    "aujourd'hui",
    "ce soir",
    "demain matin",
    "lundi",
    "mardi",
    "mercredi",
    "jeudi",
    "vendredi",
    "samedi",
    "28/11",
    "02/12",
)

PROMOS: tuple[str, ...] = (
    "BIENVENUE10",
    "bienvenue10",
    "PROMO10",
    "FIDELITE5",
    "WAX2026",
    "BOUTIQUE15",
)

CLIENTS_FICTIFS: tuple[str, ...] = (
    "Awa",
    "Koffi",
    "Nadège",
    "Sènan",
    "Chantal",
    "Rodrigue",
    "Mireille",
    "Yao",
    "Gisèle",
    "Brice",
    "Clarisse",
    "Tanguy",
)

EMOJIS: tuple[str, ...] = ("🙏", "😊", "👗", "🛍️", "✅", "📦", "👍")

PHRASES_SANS_ENTITE: dict[int, tuple[str, ...]] = {
    56: (
        "Merci beaucoup, bonne soirée",
        "Merci bien, bonne journée à vous",
        "Super merci beaucoup 😊",
        "Merci pour votre réactivité 🙏",
    ),
    57: (
        "Ok c'est noté",
        "D'accord, je m'en occupe",
        "Bien reçu, on prépare cela",
        "Parfait, je vous tiens informée",
    ),
    58: (
        "Bonjour, vous êtes ouverts ?",
        "Bonsoir, vous faites la livraison ?",
        "Salut, quels modèles avez-vous en stock ?",
        "Allô, quelqu'un est disponible svp ?",
    ),
    59: (
        "D'accord j'attends votre retour",
        "Pas de souci, tenez-moi au courant",
        "Je vous reviens dans 10 minutes",
        "J'annule finalement, désolée",
    ),
    60: (
        "C'est bien reçu, tout est impeccable !",
        "Nickel, je recommande votre boutique 👍",
        "Merci encore et à bientôt",
        "Ok parfait, on fait comme ça",
    ),
}

# ---- 60 gabarits (12 familles x 5 gabarits) ----
# Convention stricte : tid % 5 == 0 -> VALIDATION (1 gabarit par famille), sinon TRAIN.
# Tuple : (tid, famille, role, template)
GABARITS: tuple[tuple[int, str, str, str], ...] = (
    # 1. Commande simple (1-5)
    (1, "commande_simple", "client", "Bonjour, je veux [[{q}|QUANTITE]] [[{p}|PRODUIT]] svp"),
    (2, "commande_simple", "client", "Salut je voudrais [[{q}|QUANTITE]] [[{p}|PRODUIT]] en [[{t}|VARIANTE]]"),
    (3, "commande_simple", "client", "Bonsoir, mettez-moi [[{q}|QUANTITE]] [[{p}|PRODUIT]] [[{v}|VARIANTE]] merci"),
    (4, "commande_simple", "client", "Je commande [[{q}|QUANTITE]] [[{p}|PRODUIT]] pour moi svp"),
    (5, "commande_simple", "client", "Bonjour c'est [[{cli}|CLIENT]], je prends [[{q}|QUANTITE]] [[{p}|PRODUIT]] en [[{t}|VARIANTE]]"),

    # 2. Multi-produits (6-10)
    (6, "multi_produits", "client", "Je prends [[{q}|QUANTITE]] [[{p}|PRODUIT]] et [[{q2}|QUANTITE]] [[{p2}|PRODUIT]]"),
    (7, "multi_produits", "client", "Bonjour je veux [[{q}|QUANTITE]] [[{p}|PRODUIT]] en [[{t}|VARIANTE]] + [[{q2}|QUANTITE]] [[{p2}|PRODUIT]]"),
    (8, "multi_produits", "client", "Envoyez-moi [[{q}|QUANTITE]] [[{p}|PRODUIT]], [[{q2}|QUANTITE]] [[{p2}|PRODUIT]] svp"),
    (9, "multi_produits", "client", "Pour ma commande : [[{q}|QUANTITE]] [[{p}|PRODUIT]] et aussi [[{q2}|QUANTITE]] [[{p2}|PRODUIT]] en [[{t2}|VARIANTE]]"),
    (10, "multi_produits", "client", "Salut, je souhaite [[{q}|QUANTITE]] [[{p}|PRODUIT]] [[{v}|VARIANTE]] avec [[{q2}|QUANTITE]] [[{p2}|PRODUIT]]"),

    # 3. Variantes séparées (11-15)
    (11, "variantes_separees", "client", "Je veux [[2|QUANTITE]] [[{pp}|PRODUIT]], [[une|QUANTITE]] en [[{t}|VARIANTE]] et [[une|QUANTITE]] en [[{t2}|VARIANTE]]"),
    (12, "variantes_separees", "client", "Mets-moi [[2|QUANTITE]] [[{pp}|PRODUIT]] : [[1|QUANTITE]] en [[{t}|VARIANTE]] + [[1|QUANTITE]] en [[{t2}|VARIANTE]]"),
    (13, "variantes_separees", "client", "Bonjour, [[3|QUANTITE]] [[{pp}|PRODUIT]] dont [[2|QUANTITE]] en [[{t}|VARIANTE]] et [[1|QUANTITE]] en [[{t2}|VARIANTE]]"),
    (14, "variantes_separees", "client", "Je prends [[2|QUANTITE]] [[{pp}|PRODUIT]], [[1|QUANTITE]] [[taille {t}|VARIANTE]] et [[1|QUANTITE]] [[taille {t2}|VARIANTE]]"),
    (15, "variantes_separees", "client", "Pour les [[{pp}|PRODUIT]], j'en veux [[2|QUANTITE]] : [[une|QUANTITE]] [[taille {t}|VARIANTE]] et [[une|QUANTITE]] en [[{t2}|VARIANTE]]"),

    # 4. Zone + paiement (16-20)
    (16, "zone_paiement", "client", "Oui à [[{z}|ZONE]], [[{pay}|PAIEMENT]]"),
    (17, "zone_paiement", "client", "Livraison sur [[{z}|ZONE]] svp, je règle par [[{pay}|PAIEMENT]]"),
    (18, "zone_paiement", "client", "Je suis vers [[{z}|ZONE]] et je paie en [[{pay}|PAIEMENT]]"),
    (19, "zone_paiement", "vendeuse", "C'est noté [[{cli}|CLIENT]]. Livraison à [[{z}|ZONE]] et règlement [[{pay}|PAIEMENT]] ?"),
    (20, "zone_paiement", "client", "Adresse à [[{z}|ZONE]], paiement prévu par [[{pay}|PAIEMENT]]"),

    # 5. Prix cité (21-25)
    (21, "prix_cite", "client", "[[{p}|PRODUIT]] c'est [[{prix}|PRIX_CITE]] non ?"),
    (22, "prix_cite", "client", "On m'avait dit [[{prix}|PRIX_CITE]] pour [[{p}|PRODUIT]]"),
    (23, "prix_cite", "vendeuse", "Le tarif pour [[{p}|PRODUIT]] est de [[{prix}|PRIX_CITE]]"),
    (24, "prix_cite", "client", "Je prends [[{q}|QUANTITE]] [[{p}|PRODUIT]] à [[{prix}|PRIX_CITE]] l'unité ?"),
    (25, "prix_cite", "client", "Vous confirmez [[{prix}|PRIX_CITE]] pour le [[{p}|PRODUIT]] ?"),

    # 6. Code promo (26-30)
    (26, "code_promo", "client", "J'ai le code [[{promo}|CODE_PROMO]]"),
    (27, "code_promo", "client", "Est-ce que le code promo [[{promo}|CODE_PROMO]] marche sur [[{p}|PRODUIT]] ?"),
    (28, "code_promo", "client", "Merci d'appliquer [[{promo}|CODE_PROMO]] sur ma commande de [[{q}|QUANTITE]] [[{p}|PRODUIT]]"),
    (29, "code_promo", "client", "Code [[{promo}|CODE_PROMO]] pour la réduction svp"),
    (30, "code_promo", "client", "Je commande [[{q}|QUANTITE]] [[{p}|PRODUIT]] avec le code [[{promo}|CODE_PROMO]]"),

    # 7. Corrections de quantité, taille ou zone (31-35)
    (31, "correction", "client", "Non plutôt [[{q}|QUANTITE]] [[{p}|PRODUIT]] svp"),
    (32, "correction", "client", "Finalement mets la [[taille {t}|VARIANTE]]"),
    (33, "correction", "client", "En fait change pour [[{q}|QUANTITE]] [[{p}|PRODUIT]] en [[{t}|VARIANTE]]"),
    (34, "correction", "client", "Finalement livre plutôt à [[{z}|ZONE]] stp"),
    (35, "correction", "client", "Plutôt [[{q}|QUANTITE]] [[{p}|PRODUIT]] en [[{t}|VARIANTE]] finalement"),

    # 8. Messages courts, familiers et avec émojis (36-40)
    (36, "court_familier", "client", "[[{q}|QUANTITE]] [[{p}|PRODUIT]] stp {emo}"),
    (37, "court_familier", "client", "Bjr [[{q}|QUANTITE]] [[{p}|PRODUIT]] [[{t}|VARIANTE]] pr [[{z}|ZONE]] {emo}"),
    (38, "court_familier", "client", "Slt, [[{q}|QUANTITE]] [[{p}|PRODUIT]] + [[{q2}|QUANTITE]] [[{p2}|PRODUIT]] svp {emo}"),
    (39, "court_familier", "client", "{emo} [[{p}|PRODUIT]] en [[{t}|VARIANTE]], je paie [[{pay}|PAIEMENT]]"),
    (40, "court_familier", "client", "{emo} Slt je prends [[{q}|QUANTITE]] [[{p}|PRODUIT]] en [[{t}|VARIANTE]] vers [[{z}|ZONE]]"),

    # 9. Livraison complète ou partielle (41-45)
    (41, "livraison", "livreur", "Livré chez [[{cli}|CLIENT]], [[{q}|QUANTITE]] [[{p}|PRODUIT]] livrés, payé en [[{pay}|PAIEMENT]]"),
    (42, "livraison", "livreur", "Colis remis à [[{cli}|CLIENT]] : [[{q}|QUANTITE]] [[{p}|PRODUIT]] [[{t}|VARIANTE]] livrée"),
    (43, "livraison", "livreur", "Livraison faite à [[{z}|ZONE]] chez [[{cli}|CLIENT]], [[{q}|QUANTITE]] [[{p}|PRODUIT]] + [[{q2}|QUANTITE]] [[{p2}|PRODUIT]] livrés"),
    (44, "livraison", "livreur", "[[{q}|QUANTITE]] [[{p}|PRODUIT]] livrés, cliente a réglé [[{pay}|PAIEMENT]]"),
    (45, "livraison", "livreur", "Passage chez [[{cli}|CLIENT]] ok : [[{q}|QUANTITE]] [[{p}|PRODUIT]] [[{t}|VARIANTE]] livrés, payé [[{pay}|PAIEMENT]]"),

    # 10. Refus et motif de refus (46-50)
    (46, "refus_motif", "livreur", "Livré chez [[{cli}|CLIENT]]. Elle a [[{refus}|REFUS]] ([[{motif}|MOTIF_REFUS]])."),
    (47, "refus_motif", "livreur", "Cliente a [[{refus}|REFUS]] car [[{motif}|MOTIF_REFUS]]. [[{q}|QUANTITE]] [[{p}|PRODUIT]] livré."),
    (48, "refus_motif", "livreur", "Retour partiel chez [[{cli}|CLIENT]] : [[{refus}|REFUS]], motif [[{motif}|MOTIF_REFUS]]"),
    (49, "refus_motif", "livreur", "Elle a [[{refus}|REFUS]] parce que [[{motif}|MOTIF_REFUS]], reste payé en [[{pay}|PAIEMENT]]"),
    (50, "refus_motif", "livreur", "Chez [[{cli}|CLIENT]], elle a [[{refus}|REFUS]] ([[{motif}|MOTIF_REFUS]]), [[{q}|QUANTITE]] [[{p}|PRODUIT]] accepté"),

    # 11. Date de livraison (51-55)
    (51, "date_livraison", "vendeuse", "Livraison [[{d}|DATE_LIVRAISON]] ok ?"),
    (52, "date_livraison", "client", "Vous pouvez livrer [[{d}|DATE_LIVRAISON]] à [[{z}|ZONE]] svp ?"),
    (53, "date_livraison", "vendeuse", "Bonjour [[{cli}|CLIENT]], le livreur passe [[{d}|DATE_LIVRAISON]]"),
    (54, "date_livraison", "client", "Je suis disponible [[{d}|DATE_LIVRAISON]] pour recevoir ma commande"),
    (55, "date_livraison", "vendeuse", "Confirmation pour [[{cli}|CLIENT]] : passage prévu [[{d}|DATE_LIVRAISON]] sur [[{z}|ZONE]]"),

    # 12. Messages sans entité (56-60)
    (56, "sans_entite", "client", "{neutre}"),
    (57, "sans_entite", "vendeuse", "{neutre}"),
    (58, "sans_entite", "client", "{neutre}"),
    (59, "sans_entite", "client", "{neutre}"),
    (60, "sans_entite", "client", "{neutre}"),
)

FAMILLES: tuple[str, ...] = tuple(dict.fromkeys(fam for _, fam, _, _ in GABARITS))


def est_validation(tid: int) -> bool:
    """Retourne True si le gabarit ``tid`` appartient au jeu de validation (split par gabarit)."""
    return tid % 5 == 0


def typo(s: str, rng: random.Random, p: float = 0.06) -> str:
    """Applique un bruit orthographique contrôlé tout en préservant une chaîne non vide valide.

    Opérations possibles (uniquement sur des caractères alphabétiques) :
    - suppression d'une lettre (uniquement si ``len(s) >= 6``) ;
    - doublement d'une lettre ;
    - inversion de deux lettres adjacentes ;
    - suppression d'accents (25 %) ou passage en minuscules (30 %).
    """
    if not s or p <= 0:
        return s

    chars = list(s)
    out: list[str] = []
    i = 0
    while i < len(chars):
        c = chars[i]
        r = rng.random()
        if c.isalpha() and r < p / 3 and len(chars) >= 6 and len(out) > 0:
            # Suppression contrôlée (jamais le premier caractère, jamais un mot court)
            i += 1
            continue
        if c.isalpha() and r < 2 * p / 3:
            out.append(c)
            out.append(c)
            i += 1
            continue
        if (
            c.isalpha()
            and i + 1 < len(chars)
            and chars[i + 1].isalpha()
            and r < p
        ):
            out.append(chars[i + 1])
            out.append(c)
            i += 2
            continue
        out.append(c)
        i += 1

    res = "".join(out).strip() or s
    if rng.random() < 0.25:
        res = sans_accents(res)
    if rng.random() < 0.30:
        res = res.lower()
    return res


def _tirer_variables(tid: int, rng: random.Random) -> dict[str, str]:
    """Tire aléatoirement un jeu cohérent de variables pour instancier un gabarit."""
    est_sing_1 = rng.random() < 0.45
    q1 = rng.choice(NOMBRES_SING if est_sing_1 else NOMBRES_PLUR)
    p1 = typo(rng.choice(PRODUITS_SING if est_sing_1 else PRODUITS_PLUR), rng, p=0.06)

    est_sing_2 = rng.random() < 0.50
    q2 = rng.choice(NOMBRES_SING if est_sing_2 else NOMBRES_PLUR)
    p2 = typo(rng.choice(PRODUITS_SING if est_sing_2 else PRODUITS_PLUR), rng, p=0.06)

    pp = typo(rng.choice(PRODUITS_PLUR), rng, p=0.06)
    t1 = rng.choice(TAILLES)
    autres_tailles = [t for t in TAILLES if t != t1]
    t2 = rng.choice(autres_tailles)

    prod_refus = rng.choice(PRODUITS_COURT_REFUS)
    if "sac" in prod_refus:
        refus_str = f"refusé {prod_refus}"
    else:
        refus_str = f"refusé {prod_refus} {t1}"
    if rng.random() < 0.20:
        refus_str = sans_accents(refus_str)

    neutre = rng.choice(PHRASES_SANS_ENTITE.get(tid, ("Ok c'est noté",)))

    return {
        "q": q1,
        "q2": q2,
        "p": p1,
        "p2": p2,
        "pp": pp,
        "t": t1,
        "t2": t2,
        "v": rng.choice(VARIANTES_LIBRES),
        "z": typo(rng.choice(ZONES), rng, p=0.04),
        "pay": typo(rng.choice(PAIEMENTS), rng, p=0.03),
        "prix": rng.choice(PRIX),
        "promo": rng.choice(PROMOS),
        "motif": typo(rng.choice(MOTIFS_REFUS), rng, p=0.04),
        "refus": refus_str,
        "d": rng.choice(DATES),
        "cli": rng.choice(CLIENTS_FICTIFS),
        "emo": rng.choice(EMOJIS),
        "neutre": neutre,
    }


def generer(n: int = 6000, seed: int = SEED) -> tuple[list[dict], list[dict]]:
    """Génère ``n`` messages annotés découpés par gabarit en ``(train, val)``.

    Fonction pure et déterministe :
    - mêmes ``n`` et ``seed`` -> sortie strictement identique ;
    - chaque span généré est vérifié par ``valider_spans()`` ;
    - aucun ``tid`` n'apparaît à la fois dans ``train`` et ``val``.
    """
    if n <= 0:
        raise ValueError("n doit être strictement positif.")

    rng = random.Random(seed)
    train: list[dict] = []
    val: list[dict] = []

    for _ in range(n):
        tid, famille, role, tpl = rng.choice(GABARITS)
        brut_balise = tpl.format(**_tirer_variables(tid, rng))
        texte, spans = parse_markup(brut_balise)
        erreurs = valider_spans(texte, spans)
        if erreurs:
            raise ValueError(f"Span invalide généré (tid={tid}): {erreurs}")

        exemple = {
            "tid": tid,
            "famille": famille,
            "role": role,
            "text": texte,
            "spans": spans,
        }
        if est_validation(tid):
            val.append(exemple)
        else:
            train.append(exemple)

    return train, val


def ecrire_jsonl(chemin: Union[str, Path], lignes: list[dict]) -> Path:
    """Écrit une liste de dictionnaires au format JSON Lines UTF-8."""
    dest = Path(chemin)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        for ligne in lignes:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
    return dest


def main(
    n: int = 6000,
    seed: int = SEED,
    dossier: Union[str, Path] = CHEMIN_DONNEES,
) -> tuple[Path, Path, int, int]:
    """Point d'entrée CLI : génère et écrit ``train.jsonl`` et ``val.jsonl``."""
    train, val = generer(n=n, seed=seed)
    base = Path(dossier)
    p_train = ecrire_jsonl(base / "train.jsonl", train)
    p_val = ecrire_jsonl(base / "val.jsonl", val)
    return p_train, p_val, len(train), len(val)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Génère train.jsonl et val.jsonl synthétiques (split par gabarit)."
    )
    parser.add_argument("--n", type=int, default=6000, help="Nombre total de messages à générer")
    parser.add_argument("--seed", type=int, default=SEED, help="Graine aléatoire")
    parser.add_argument(
        "--dossier",
        type=str,
        default=str(CHEMIN_DONNEES),
        help="Dossier de sortie pour train.jsonl et val.jsonl",
    )
    args = parser.parse_args()
    p_tr, p_va, n_tr, n_va = main(n=args.n, seed=args.seed, dossier=args.dossier)
    print(f"Généré : {p_tr} ({n_tr} messages) | {p_va} ({n_va} messages) | {len(GABARITS)} gabarits")
