"""Évaluation comparative Baseline vs Modèle, calibration et analyse d'erreurs (Étape 7 — Jalon H19).

Trois familles de mesures, strictement séparées des métriques métier (CDC §6.4 & Guide §12) :
1. **F1 strict** (label + début + fin exacts) et **F1 souple** (même label + chevauchement)
   par entité (+ micro/macro), sur ``extraire_brut()``, comparant ``baseline-1.0`` au modèle
   actif (``ner-v1`` ou ``crf-v1``).
2. **Calibration (ECE + diagramme de fiabilité par tranches)** sur les prédictions brutes.
3. **Taux de revue humaine** (``vert`` / ``orange`` / ``rouge``) après garde-fous sur ``extraire()``.
4. **Catégorisation automatique des erreurs** (confusion de classe, frontières décalées,
   entités manquées, faux positifs sur messages sans entité, autres faux positifs).

Honnêteté scientifique (Guide §10.1 & §12) :
- Seul ``data/test_manuel.jsonl`` (≥ 80 messages rédigés par l'équipe) produit des scores
  publiables (``est_score_final_publiable = True``).
- L'option ``--corpus val`` permet un benchmark interne immédiat sur ``val.jsonl`` (12 gabarits
  disjoints), explicitement marqué ``est_score_final_publiable = False``.
"""

import argparse
from collections import defaultdict
import json
from pathlib import Path
from typing import Callable, Optional, Union

from ai.config import CHEMIN_DONNEES, CHEMIN_TEST_MANUEL, charger_seuils
from ai.entrainement.markup import parse_markup, valider_spans
from ai.extraction import extraire, extraire_brut, get_mode
from ai.extraction import baseline as mod_baseline
from ai.extraction import modele as mod_modele

CHEMIN_SORTIE_DEFAUT: Path = Path("docs/resultats_ia.json")


def charger_corpus(path: Union[str, Path]) -> list[dict]:
    """Charge un corpus JSONL au format balisé (``markup``) ou pré-parsé (``text`` + ``spans``)."""
    chemin = Path(path)
    if not chemin.is_file():
        raise FileNotFoundError(f"Corpus d'évaluation introuvable : {chemin}")

    out: list[dict] = []
    with open(chemin, encoding="utf-8") as f:
        for num_ligne, brut in enumerate(f, 1):
            brut = brut.strip()
            if not brut:
                continue
            d = json.loads(brut)
            if "markup" in d:
                texte, spans = parse_markup(d["markup"])
            elif "text" in d and "spans" in d:
                texte, spans = d["text"], d["spans"]
            else:
                raise ValueError(
                    f"{chemin}:{num_ligne} — format inconnu (attendu 'markup' ou 'text'+'spans')."
                )
            erreurs = valider_spans(texte, spans)
            if erreurs:
                raise ValueError(f"{chemin}:{num_ligne} — spans invalides : {erreurs}")
            out.append({
                "text": texte,
                "gold": spans,
                "role": d.get("role", "client"),
                "famille": d.get("famille"),
            })
    return out


def predire_mode(mode: str) -> Callable[[dict], list[dict]]:
    """Construit une fonction de prédiction brute (``extraire_brut``) pour ``mode``."""
    def _pred(ex: dict) -> list[dict]:
        msg = [{"message_id": "m1", "rang": 0, "role": ex["role"], "texte": ex["text"]}]
        return [
            {
                "label": c["nom"].upper(),
                "debut": c["debut"],
                "fin": c["fin"],
                "texte": c["valeur"],
                "confiance": c["confiance"],
            }
            for c in extraire_brut(msg, mode=mode)
        ]

    return _pred


def _correspond(p: dict, g: dict, strict: bool) -> bool:
    if p["label"] != g["label"]:
        return False
    if strict:
        return (p["debut"], p["fin"]) == (g["debut"], g["fin"])
    return p["debut"] < g["fin"] and p["fin"] > g["debut"]


def _chevauche(a: dict, b: dict) -> bool:
    return a["debut"] < b["fin"] and a["fin"] > b["debut"]


def prf(
    corpus: list[dict],
    pred_fn: Callable[[dict], list[dict]],
    strict: bool = True,
) -> dict:
    """Calcule précision, rappel, F1 et support par entité + moyennes micro et macro.

    Utilise un appariement bijectif (1 prédiction ↔ au plus 1 span gold) pour éviter
    tout double comptage de vrais positifs.
    """
    tp: dict[str, int] = defaultdict(int)
    fp: dict[str, int] = defaultdict(int)
    fn: dict[str, int] = defaultdict(int)

    for ex in corpus:
        gold = ex["gold"]
        pred = pred_fn(ex)
        gold_apparies: set[int] = set()
        pred_apparies: set[int] = set()

        for ip, p in enumerate(pred):
            for ig, g in enumerate(gold):
                if ig in gold_apparies:
                    continue
                if _correspond(p, g, strict=strict):
                    tp[g["label"]] += 1
                    gold_apparies.add(ig)
                    pred_apparies.add(ip)
                    break

        for ig, g in enumerate(gold):
            if ig not in gold_apparies:
                fn[g["label"]] += 1
        for ip, p in enumerate(pred):
            if ip not in pred_apparies:
                fp[p["label"]] += 1

    par_entite: dict[str, dict] = {}
    labels = sorted(set(tp) | set(fp) | set(fn))
    for lab in labels:
        t_p, f_p, f_n = tp[lab], fp[lab], fn[lab]
        prec = t_p / (t_p + f_p) if (t_p + f_p) else 0.0
        rapp = t_p / (t_p + f_n) if (t_p + f_n) else 0.0
        f1 = (2 * prec * rapp / (prec + rapp)) if (prec + rapp) else 0.0
        par_entite[lab] = {
            "precision": round(prec, 4),
            "rappel": round(rapp, 4),
            "f1": round(f1, 4),
            "support": t_p + f_n,
        }

    tot_tp = sum(tp.values())
    tot_fp = sum(fp.values())
    tot_fn = sum(fn.values())
    micro_p = tot_tp / (tot_tp + tot_fp) if (tot_tp + tot_fp) else 0.0
    micro_r = tot_tp / (tot_tp + tot_fn) if (tot_tp + tot_fn) else 0.0
    micro_f1 = (2 * micro_p * micro_r / (micro_p + micro_r)) if (micro_p + micro_r) else 0.0

    actifs = [m for m in par_entite.values() if m["support"] > 0]
    macro_f1 = sum(m["f1"] for m in actifs) / len(actifs) if actifs else 0.0

    return {
        "par_entite": par_entite,
        "micro": {
            "precision": round(micro_p, 4),
            "rappel": round(micro_r, 4),
            "f1": round(micro_f1, 4),
            "support": tot_tp + tot_fn,
        },
        "macro_f1": round(macro_f1, 4),
    }


def calibration(
    corpus: list[dict],
    pred_fn: Callable[[dict], list[dict]],
    nb_bins: int = 10,
) -> dict:
    """Calcule la courbe de calibration (``bins``) et l'ECE sur les spans exacts."""
    compteurs = [[0, 0, 0.0] for _ in range(nb_bins)]  # [n, correct, sum_conf]

    for ex in corpus:
        gold_set = {(g["label"], g["debut"], g["fin"]) for g in ex["gold"]}
        for p in pred_fn(ex):
            conf = max(0.0, min(1.0, float(p["confiance"])))
            b = min(int(conf * nb_bins), nb_bins - 1)
            est_ok = int((p["label"], p["debut"], p["fin"]) in gold_set)
            compteurs[b][0] += 1
            compteurs[b][1] += est_ok
            compteurs[b][2] += conf

    total = sum(n for n, _, _ in compteurs)
    bins_out: list[dict] = []
    ece_acc = 0.0
    for i, (n, ok, sum_c) in enumerate(compteurs):
        acc = (ok / n) if n else None
        mean_c = (sum_c / n) if n else None
        if n and total:
            ece_acc += abs(acc - mean_c) * (n / total)
        bins_out.append({
            "bin": i,
            "borne_inf": round(i / nb_bins, 2),
            "borne_sup": round((i + 1) / nb_bins, 2),
            "n": n,
            "correct": ok,
            "precision_empirique": round(acc, 4) if acc is not None else None,
            "confiance_moyenne": round(mean_c, 4) if mean_c is not None else None,
        })

    return {
        "nb_predictions": total,
        "ece": round(ece_acc, 4),
        "bins": bins_out,
    }


def taux_revue(
    corpus: list[dict],
    mode: str,
    seuils: Optional[dict[str, float]] = None,
) -> dict:
    """Mesure la répartition vert/orange/rouge après garde-fous (``extraire()``)."""
    seuils_actifs = seuils if seuils is not None else charger_seuils()
    nb_vert = nb_orange = nb_rouge = 0

    for ex in corpus:
        msg = [{"message_id": "m1", "rang": 0, "role": ex["role"], "texte": ex["text"]}]
        for c in extraire(msg, mode=mode, seuils=seuils_actifs):
            if c["couleur"] == "vert":
                nb_vert += 1
            elif c["couleur"] == "orange":
                nb_orange += 1
            else:
                nb_rouge += 1

    total = nb_vert + nb_orange + nb_rouge
    return {
        "total": total,
        "nb_vert": nb_vert,
        "nb_orange": nb_orange,
        "nb_rouge": nb_rouge,
        "taux_vert": round(nb_vert / total, 4) if total else 0.0,
        "taux_orange": round(nb_orange / total, 4) if total else 0.0,
        "taux_rouge": round(nb_rouge / total, 4) if total else 0.0,
        "taux_revue_attentive": round((nb_orange + nb_rouge) / total, 4) if total else 0.0,
        "seuils": seuils_actifs,
    }


def analyser_erreurs(
    corpus: list[dict],
    pred_fn: Callable[[dict], list[dict]],
    max_exemples: int = 5,
) -> dict:
    """Catégorise automatiquement les erreurs de prédiction avec exemples concrets."""
    categories = (
        "confusion_classe",
        "frontiere_decalee",
        "entite_manquee",
        "faux_positif_sans_entite",
        "faux_positif_autre",
    )
    compteurs = {cat: 0 for cat in categories}
    exemples: dict[str, list[dict]] = {cat: [] for cat in categories}

    def enregistrer(cat: str, detail: dict) -> None:
        compteurs[cat] += 1
        if len(exemples[cat]) < max_exemples:
            exemples[cat].append(detail)

    for ex in corpus:
        gold = ex["gold"]
        pred = pred_fn(ex)

        gold_exact: set[int] = set()
        pred_exact: set[int] = set()
        for ip, p in enumerate(pred):
            for ig, g in enumerate(gold):
                if ig not in gold_exact and _correspond(p, g, strict=True):
                    gold_exact.add(ig)
                    pred_exact.add(ip)
                    break

        gold_expliques: set[int] = set(gold_exact)

        for ip, p in enumerate(pred):
            if ip in pred_exact:
                continue
            chev = [
                (ig, g)
                for ig, g in enumerate(gold)
                if ig not in gold_exact and _chevauche(p, g)
            ]
            if chev:
                meme_label = next(((ig, g) for ig, g in chev if g["label"] == p["label"]), None)
                if meme_label is not None:
                    ig, g = meme_label
                    gold_expliques.add(ig)
                    enregistrer("frontiere_decalee", {
                        "texte": ex["text"],
                        "attendu": {"label": g["label"], "texte": g["texte"]},
                        "predit": {"label": p["label"], "texte": p["texte"]},
                    })
                else:
                    ig, g = chev[0]
                    gold_expliques.add(ig)
                    enregistrer("confusion_classe", {
                        "texte": ex["text"],
                        "attendu": {"label": g["label"], "texte": g["texte"]},
                        "predit": {"label": p["label"], "texte": p["texte"]},
                    })
            elif not gold:
                enregistrer("faux_positif_sans_entite", {
                    "texte": ex["text"],
                    "attendu": None,
                    "predit": {"label": p["label"], "texte": p["texte"]},
                })
            else:
                enregistrer("faux_positif_autre", {
                    "texte": ex["text"],
                    "attendu": None,
                    "predit": {"label": p["label"], "texte": p["texte"]},
                })

        for ig, g in enumerate(gold):
            if ig not in gold_expliques:
                enregistrer("entite_manquee", {
                    "texte": ex["text"],
                    "attendu": {"label": g["label"], "texte": g["texte"]},
                    "predit": None,
                })

    return {
        "compteurs": compteurs,
        "total_erreurs": sum(compteurs.values()),
        "exemples": exemples,
    }


def evaluer_corpus(
    corpus: list[dict],
    source_corpus: str,
    seuils: Optional[dict[str, float]] = None,
) -> dict:
    """Exécute l'évaluation complète Baseline vs Modèle sur un corpus déjà chargé."""
    seuils_actifs = seuils if seuils is not None else charger_seuils()
    pred_base = predire_mode("baseline")
    mode_effectif = get_mode("modele")
    pred_mod = predire_mode("modele")
    ver_mod = mod_modele.version_active() if mode_effectif == "modele" else mod_baseline.VERSION

    # Cache par exemple pour éviter de ré-exécuter 4 fois les mêmes prédictions
    cache_base = [pred_base(ex) for ex in corpus]
    cache_mod = [pred_mod(ex) for ex in corpus]
    idx_par_id = {id(ex): i for i, ex in enumerate(corpus)}

    fn_base = lambda ex: cache_base[idx_par_id[id(ex)]]  # noqa: E731
    fn_mod = lambda ex: cache_mod[idx_par_id[id(ex)]]    # noqa: E731

    est_publiable = source_corpus == "test_manuel" and len(corpus) >= 80
    avertissement = (
        None
        if est_publiable
        else (
            "Benchmark interne sur corpus de validation synthétique (non publiable comme "
            "score final : seul data/test_manuel.jsonl >= 80 messages fait foi, Guide §12)."
            if source_corpus != "test_manuel"
            else "Corpus test_manuel.jsonl inférieur à 80 messages : compléter avant publication."
        )
    )

    return {
        "source_corpus": source_corpus,
        "est_score_final_publiable": est_publiable,
        "avertissement": avertissement,
        "nb_messages": len(corpus),
        "nb_sans_entite": sum(1 for ex in corpus if not ex["gold"]),
        "version_baseline": mod_baseline.VERSION,
        "version_modele": ver_mod,
        "f1_strict": {
            "baseline": prf(corpus, fn_base, strict=True),
            "modele": prf(corpus, fn_mod, strict=True),
        },
        "f1_souple": {
            "baseline": prf(corpus, fn_base, strict=False),
            "modele": prf(corpus, fn_mod, strict=False),
        },
        "calibration": {
            "baseline": calibration(corpus, fn_base),
            "modele": calibration(corpus, fn_mod),
        },
        "taux_revue": {
            "baseline": taux_revue(corpus, mode="baseline", seuils=seuils_actifs),
            "modele": taux_revue(corpus, mode="modele", seuils=seuils_actifs),
        },
        "analyse_erreurs": {
            "baseline": analyser_erreurs(corpus, fn_base),
            "modele": analyser_erreurs(corpus, fn_mod),
        },
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Évalue baseline vs modèle (F1 strict/souple, ECE, taux de revue, erreurs)."
    )
    parser.add_argument(
        "--corpus",
        choices=("auto", "test", "val"),
        default="auto",
        help="'test' = data/test_manuel.jsonl, 'val' = val.jsonl synthétique, 'auto' = test sinon val.",
    )
    parser.add_argument(
        "--chemin",
        default=None,
        help="Chemin explicite vers un fichier JSONL (remplace --corpus si fourni).",
    )
    parser.add_argument(
        "--sortie",
        default=str(CHEMIN_SORTIE_DEFAUT),
        help="Fichier JSON de sortie (défaut : docs/resultats_ia.json).",
    )
    args = parser.parse_args(argv)

    if args.chemin:
        chemin_corpus = Path(args.chemin)
        source_nom = "test_manuel" if chemin_corpus.name == "test_manuel.jsonl" else chemin_corpus.stem
    elif args.corpus == "test":
        chemin_corpus = Path(CHEMIN_TEST_MANUEL)
        source_nom = "test_manuel"
    elif args.corpus == "val":
        chemin_corpus = Path(CHEMIN_DONNEES) / "val.jsonl"
        source_nom = "val_synthetique"
    else:
        if Path(CHEMIN_TEST_MANUEL).is_file():
            chemin_corpus = Path(CHEMIN_TEST_MANUEL)
            source_nom = "test_manuel"
        else:
            chemin_corpus = Path(CHEMIN_DONNEES) / "val.jsonl"
            source_nom = "val_synthetique"

    corpus = charger_corpus(chemin_corpus)
    resultats = evaluer_corpus(corpus, source_corpus=source_nom)

    dest = Path(args.sortie)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(resultats, f, ensure_ascii=False, indent=2)

    resume = {
        "source_corpus": resultats["source_corpus"],
        "est_score_final_publiable": resultats["est_score_final_publiable"],
        "nb_messages": resultats["nb_messages"],
        "version_modele": resultats["version_modele"],
        "f1_strict_micro_baseline": resultats["f1_strict"]["baseline"]["micro"]["f1"],
        "f1_strict_micro_modele": resultats["f1_strict"]["modele"]["micro"]["f1"],
        "f1_strict_macro_baseline": resultats["f1_strict"]["baseline"]["macro_f1"],
        "f1_strict_macro_modele": resultats["f1_strict"]["modele"]["macro_f1"],
        "f1_souple_micro_baseline": resultats["f1_souple"]["baseline"]["micro"]["f1"],
        "f1_souple_micro_modele": resultats["f1_souple"]["modele"]["micro"]["f1"],
        "ece_baseline": resultats["calibration"]["baseline"]["ece"],
        "ece_modele": resultats["calibration"]["modele"]["ece"],
        "taux_revue_attentive_baseline": resultats["taux_revue"]["baseline"]["taux_revue_attentive"],
        "taux_revue_attentive_modele": resultats["taux_revue"]["modele"]["taux_revue_attentive"],
        "erreurs_baseline": resultats["analyse_erreurs"]["baseline"]["compteurs"],
        "erreurs_modele": resultats["analyse_erreurs"]["modele"]["compteurs"],
    }
    print(json.dumps(resume, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
