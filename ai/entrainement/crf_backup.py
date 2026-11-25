"""Plan de secours CPU NER par CRF (``sklearn-crfsuite``) + calibration (Étape 6 — Jalon H12).

Points clés (Guide §11.2 & Addendum v1.1 §4) :
- Entraînable en quelques secondes sur CPU local sans GPU ni accès réseau.
- Utilise exactement le même schéma BIO (23 labels) et la même séparation disjointe par
  gabarit (``train.jsonl`` / ``val.jsonl``) que ``train.py``.
- Calibration des probabilités marginales par mise à l'échelle de la température sur
  ``val.jsonl`` (optimisation convexe 1D bornée sur la log-vraisemblance négative).
- Artefacts sauvegardés dans ``ai/modeles/crf-v1/`` (``crf_model.joblib`` +
  ``calibration.json``, ignorés par ``.gitignore``) avec ``version = "crf-v1"``.
"""

import argparse
import json
import math
import re
from pathlib import Path
from typing import Union

import joblib
import numpy as np
from scipy.optimize import minimize_scalar
from seqeval.metrics import f1_score
import sklearn_crfsuite

from ai.config import CHEMIN_DONNEES, SEED
from ai.normalisation.nombres import sans_accents

VERSION_CRF: str = "crf-v1"
CHEMIN_CRF: Path = Path("ai/modeles/crf-v1")

TOK = re.compile(r"\w+|[^\w\s]", re.UNICODE)

_NOMBRES_MOTS = frozenset({
    "zero", "un", "une", "deux", "trois", "quatre", "cinq", "six", "sept",
    "huit", "neuf", "dix", "onze", "douze", "treize", "quatorze", "quinze",
    "seize", "vingt", "trente", "quarante", "cinquante", "soixante", "cent", "mille",
})
_DEVISES = frozenset({"f", "fcfa", "cfa", "franc", "francs", "xof", "k", "mille"})
_TAILLES = frozenset({"S", "M", "L", "XL"})


def tokeniser(texte: str) -> list[tuple[str, int, int]]:
    """Découpe un texte en triplets ``(token, debut_unicode, fin_unicode)``."""
    return [(m.group(), m.start(), m.end()) for m in TOK.finditer(texte)]


def feats(toks: list[tuple[str, int, int]], i: int) -> dict[str, object]:
    """Construit les attributs lexicaux et contextuels (fenêtre ±2) du token ``i``."""
    w = toks[i][0]
    wl = w.lower()
    wsa = sans_accents(wl)
    has_digit = any(ch.isdigit() for ch in w)
    has_alpha = any(ch.isalpha() for ch in w)

    f: dict[str, object] = {
        "bias": 1.0,
        "w": wl,
        "wsa": wsa,
        "pre2": wsa[:2],
        "pre3": wsa[:3],
        "suf2": wsa[-2:],
        "suf3": wsa[-3:],
        "maj": w.isupper(),
        "titre": w.istitle(),
        "chiffre": w.isdigit(),
        "has_digit": has_digit,
        "alnum_mix": has_digit and has_alpha,
        "ponct": not w.isalnum(),
        "long": min(len(w), 10),
        "est_taille": w in _TAILLES,
        "est_nb_mot": wsa in _NOMBRES_MOTS,
        "est_devise": wsa in _DEVISES,
        "est_emoji": any(ord(ch) > 0xFFFF for ch in w),
    }

    for d in (-2, -1, 1, 2):
        j = i + d
        if 0 <= j < len(toks):
            wj = toks[j][0]
            wjl = wj.lower()
            wjsa = sans_accents(wjl)
            f[f"w{d}"] = wjl
            f[f"wsa{d}"] = wjsa
            f[f"chiffre{d}"] = wj.isdigit()
            f[f"titre{d}"] = wj.istitle()
            f[f"maj{d}"] = wj.isupper()
        else:
            f[f"w{d}"] = "<BOS>" if d < 0 else "<EOS>"

    if i > 0:
        f["bg_prev"] = sans_accents(toks[i - 1][0].lower()) + "_" + wsa
    else:
        f["BOS"] = True

    if i + 1 < len(toks):
        f["bg_next"] = wsa + "_" + sans_accents(toks[i + 1][0].lower())
    else:
        f["EOS"] = True

    return f


def bio(toks: list[tuple[str, int, int]], spans: list[dict]) -> list[str]:
    """Aligne une liste de spans caractères sur les étiquettes BIO des tokens."""
    labels: list[str] = []
    prev_idx = None
    for _, start, end in toks:
        idx = next(
            (k for k, sp in enumerate(spans) if start < sp["fin"] and end > sp["debut"]),
            None,
        )
        if idx is None:
            labels.append("O")
            prev_idx = None
        else:
            prefix = "I-" if idx == prev_idx else "B-"
            labels.append(prefix + spans[idx]["label"])
            prev_idx = idx
    return labels


def _lire_jsonl(path: Union[str, Path]) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(ligne) for ligne in f if ligne.strip()]


def calibrer_proba_marginale(
    prob_dict: dict[str, float],
    temperature: float,
) -> dict[str, float]:
    """Applique la mise à l'échelle par température sur une distribution marginale CRF."""
    if not prob_dict:
        return {}
    t = max(float(temperature), 0.05)
    labels = list(prob_dict.keys())
    log_p = np.array([math.log(max(float(prob_dict[k]), 1e-12)) for k in labels], dtype=np.float64)
    scaled = log_p / t
    scaled -= np.max(scaled)
    exps = np.exp(scaled)
    probs = exps / np.sum(exps)
    return {lab: float(p) for lab, p in zip(labels, probs)}


def _calculer_ece_tokens(
    marginals_seq: list[list[dict[str, float]]],
    y_true_seq: list[list[str]],
    temperature: float,
    nb_bins: int = 10,
) -> float:
    """Calcule l'ECE au niveau token (sur les entités prédites ou tous tokens non-O/tous)."""
    bins = [[0, 0, 0.0] for _ in range(nb_bins)]  # [count, correct, sum_conf]
    for seq_m, seq_y in zip(marginals_seq, y_true_seq):
        for md, y_t in zip(seq_m, seq_y):
            cal = calibrer_proba_marginale(md, temperature)
            pred_lab, conf = max(cal.items(), key=lambda kv: kv[1])
            b = min(int(conf * nb_bins), nb_bins - 1)
            bins[b][0] += 1
            bins[b][1] += int(pred_lab == y_t)
            bins[b][2] += conf
    total = sum(c for c, _, _ in bins) or 1
    ece = sum(abs(ok / c - s_conf / c) * c for c, ok, s_conf in bins if c > 0) / total
    return round(float(ece), 4)


def calibrer_temperature_crf(
    marginals_seq: list[list[dict[str, float]]],
    y_true_seq: list[list[str]],
) -> float:
    """Optimise la température T > 0 minimisant la log-vraisemblance négative sur ``val``."""
    classes = sorted({lab for seq in marginals_seq for md in seq for lab in md})
    idx_map = {lab: i for i, lab in enumerate(classes)}

    log_probs_rows: list[np.ndarray] = []
    target_indices: list[int] = []

    for seq_m, seq_y in zip(marginals_seq, y_true_seq):
        for md, y_t in zip(seq_m, seq_y):
            if y_t not in idx_map:
                continue
            row = np.array(
                [math.log(max(float(md.get(lab, 1e-12)), 1e-12)) for lab in classes],
                dtype=np.float64,
            )
            log_probs_rows.append(row)
            target_indices.append(idx_map[y_t])

    if not log_probs_rows:
        return 1.0

    mat_logp = np.vstack(log_probs_rows)
    targets = np.array(target_indices, dtype=np.int64)
    rows_idx = np.arange(len(targets))

    def nll(temp: float) -> float:
        scaled = mat_logp / temp
        max_s = np.max(scaled, axis=1, keepdims=True)
        lse = max_s[:, 0] + np.log(np.sum(np.exp(scaled - max_s), axis=1))
        return float(np.mean(lse - scaled[rows_idx, targets]))

    res = minimize_scalar(nll, bounds=(0.05, 10.0), method="bounded")
    return round(float(res.x), 6)


def decoder_spans_crf(
    texte: str,
    toks: list[tuple[str, int, int]],
    labels: list[str],
    marginals: list[dict[str, float]],
    temperature: float = 1.0,
) -> list[dict]:
    """Reconstruit les spans Unicode ``{label, debut, fin, texte, confiance}`` depuis le CRF."""
    spans: list[dict] = []
    cur: dict | None = None

    for (_, start, end), lab, md in zip(toks, labels, marginals):
        if lab == "O":
            cur = None
            continue
        cal = calibrer_proba_marginale(md, temperature)
        conf = cal.get(lab, 0.0)
        pref, ent = lab.split("-", 1)
        if pref == "B" or cur is None or cur["label"] != ent:
            cur = {"label": ent, "debut": start, "fin": end, "_c": [conf]}
            spans.append(cur)
        else:
            cur["fin"] = end
            cur["_c"].append(conf)

    for sp in spans:
        confs = sp.pop("_c")
        sp["confiance"] = round(sum(confs) / len(confs), 4)
        while sp["debut"] < sp["fin"] and texte[sp["debut"]].isspace():
            sp["debut"] += 1
        while sp["fin"] > sp["debut"] and texte[sp["fin"] - 1].isspace():
            sp["fin"] -= 1
        sp["texte"] = texte[sp["debut"]:sp["fin"]]

    return [sp for sp in spans if sp["debut"] < sp["fin"]]


def entrainer_modele_crf(
    lignes: list[dict],
    c1: float = 0.1,
    c2: float = 0.1,
    max_iterations: int = 120,
) -> sklearn_crfsuite.CRF:
    """Entraîne un modèle CRF linéaire (L-BFGS) sur une liste d'exemples annotés."""
    X: list[list[dict]] = []
    Y: list[list[str]] = []
    for ligne in lignes:
        toks = tokeniser(ligne["text"])
        if not toks:
            continue
        X.append([feats(toks, i) for i in range(len(toks))])
        Y.append(bio(toks, ligne["spans"]))

    crf = sklearn_crfsuite.CRF(
        algorithm="lbfgs",
        c1=c1,
        c2=c2,
        max_iterations=max_iterations,
        all_possible_transitions=True,
    )
    crf.fit(X, Y)
    return crf


def entrainer_et_sauvegarder(
    chemin_train: Union[str, Path] = CHEMIN_DONNEES / "train.jsonl",
    chemin_val: Union[str, Path] = CHEMIN_DONNEES / "val.jsonl",
    sortie: Union[str, Path] = CHEMIN_CRF,
    version: str = VERSION_CRF,
    seed: int = SEED,
) -> dict:
    """Entraîne le CRF sur ``train.jsonl``, calibre sur ``val.jsonl`` et sauvegarde."""
    train_lignes = _lire_jsonl(chemin_train)
    val_lignes = _lire_jsonl(chemin_val)

    crf = entrainer_modele_crf(train_lignes)

    X_val: list[list[dict]] = []
    Y_val: list[list[str]] = []
    for ligne in val_lignes:
        toks = tokeniser(ligne["text"])
        if not toks:
            continue
        X_val.append([feats(toks, i) for i in range(len(toks))])
        Y_val.append(bio(toks, ligne["spans"]))

    Y_pred = crf.predict(X_val)
    f1_val = round(float(f1_score(Y_val, Y_pred)), 4)

    marginals_val = [crf.predict_marginals_single(x) for x in X_val]
    ece_avant = _calculer_ece_tokens(marginals_val, Y_val, temperature=1.0)
    temperature = calibrer_temperature_crf(marginals_val, Y_val)
    ece_apres = _calculer_ece_tokens(marginals_val, Y_val, temperature=temperature)

    dossier = Path(sortie)
    dossier.mkdir(parents=True, exist_ok=True)
    joblib.dump(crf, dossier / "crf_model.joblib")

    calibration = {
        "type": "crf",
        "version": version,
        "temperature": temperature,
        "seed": seed,
        "modele_base": "sklearn-crfsuite (L-BFGS)",
        "nb_train": len(train_lignes),
        "nb_val": len(val_lignes),
        "f1_val": f1_val,
        "ece_val_avant": ece_avant,
        "ece_val_apres": ece_apres,
    }
    with open(dossier / "calibration.json", "w", encoding="utf-8") as f:
        json.dump(calibration, f, ensure_ascii=False, indent=2)

    return calibration


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Entraîne le plan B NER CRF sur CPU et calibre les marginales sur val.jsonl."
    )
    parser.add_argument("--train", default=str(CHEMIN_DONNEES / "train.jsonl"))
    parser.add_argument("--val", default=str(CHEMIN_DONNEES / "val.jsonl"))
    parser.add_argument("--sortie", default=str(CHEMIN_CRF))
    cli_args = parser.parse_args()

    res = entrainer_et_sauvegarder(
        chemin_train=cli_args.train,
        chemin_val=cli_args.val,
        sortie=cli_args.sortie,
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
