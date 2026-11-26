"""Inférence NER calibrée (DistilCamemBERT ``ner-v1`` -> repli local CRF ``crf-v1``).

Cascade de chargement déterministe (Étape 6b — Jalon H12, Guide §9.5 & §11.2) :
1. Si les poids DistilCamemBERT (``ai/modeles/ner-v1/``) sont présents sur disque,
   le service charge ``ModeleTransformer`` (``version_modele = "ner-v1"``).
2. Sinon, si le modèle CRF CPU (``ai/modeles/crf-v1/``) est présent sur disque,
   le service charge ``ModeleCRF`` (``version_modele = "crf-v1"``).
3. Sinon, ``disponible()`` retourne ``False`` et ``ai/extraction/__init__.py`` se replie
   automatiquement sur ``baseline-1.0`` avec journalisation ``WARNING``.

Respecte strictement la signature officielle ``extraire_brut(messages)`` (§7.8).
"""

import json
import logging
from pathlib import Path
from typing import Optional, Union

from ai.config import CHEMIN_MODELE, SEED
from ai.entrainement.crf_backup import (
    CHEMIN_CRF as _CHEMIN_CRF_DEFAUT,
    decoder_spans_crf,
    feats,
    tokeniser,
)
from .champ import champ_brut

log = logging.getLogger("ai.extraction")

CHEMIN_TRANSFORMER: Path = Path(CHEMIN_MODELE)
CHEMIN_CRF: Path = Path(_CHEMIN_CRF_DEFAUT)

_CACHE: dict[tuple[str, str], object] = {}


def _transformer_present(chemin: Union[str, Path]) -> bool:
    dossier = Path(chemin)
    if not (dossier / "calibration.json").is_file():
        return False
    if not (dossier / "config.json").is_file():
        return False
    poids = ("model.safetensors", "pytorch_model.bin")
    return any((dossier / nom).is_file() for nom in poids)


def _crf_present(chemin: Union[str, Path]) -> bool:
    dossier = Path(chemin)
    return (dossier / "calibration.json").is_file() and (dossier / "crf_model.joblib").is_file()


def source_disponible() -> Optional[tuple[str, Path]]:
    """Retourne ``(type_modele, chemin)`` selon la priorité ``ner-v1`` -> ``crf-v1``."""
    if _transformer_present(CHEMIN_TRANSFORMER):
        return ("transformer", Path(CHEMIN_TRANSFORMER))
    if _crf_present(CHEMIN_CRF):
        return ("crf", Path(CHEMIN_CRF))
    return None


def disponible() -> bool:
    """Indique si au moins un modèle entraîné (``ner-v1`` ou ``crf-v1``) est prêt."""
    return source_disponible() is not None


def reinitialiser_cache() -> None:
    """Vide le cache mémoire des modèles chargés (utile pour les tests)."""
    _CACHE.clear()


class ModeleTransformer:
    """Inférence DistilCamemBERT NER avec calibration par température sur CPU/GPU."""

    def __init__(self, chemin: Union[str, Path] = CHEMIN_TRANSFORMER):
        import torch
        from transformers import AutoModelForTokenClassification, AutoTokenizer

        torch.manual_seed(SEED)
        dossier = Path(chemin)
        self.tok = AutoTokenizer.from_pretrained(str(dossier), use_fast=True)
        self.model = AutoModelForTokenClassification.from_pretrained(str(dossier)).eval()
        with open(dossier / "calibration.json", encoding="utf-8") as f:
            cal = json.load(f)
        self.T: float = max(float(cal.get("temperature", 1.0)), 0.05)
        self.version: str = str(cal.get("version", "ner-v1"))
        self.id2label: dict[int, str] = {
            int(k): v for k, v in self.model.config.id2label.items()
        }

    def predict(self, texte: str) -> list[dict]:
        import torch

        if not texte or not texte.strip():
            return []

        enc = self.tok(
            texte,
            return_offsets_mapping=True,
            return_tensors="pt",
            truncation=True,
            max_length=128,
        )
        offs = enc.pop("offset_mapping")[0].tolist()
        with torch.no_grad():
            logits = self.model(**enc).logits[0]
            probs = torch.softmax(logits / self.T, dim=-1)
            conf, ids = probs.max(-1)

        spans: list[dict] = []
        cur: Optional[dict] = None
        for (start, end), idx, c in zip(offs, ids.tolist(), conf.tolist()):
            if start == end:
                continue
            lab = self.id2label[idx]
            if lab == "O":
                cur = None
                continue
            pref, ent = lab.split("-", 1)
            if pref == "B" or cur is None or cur["label"] != ent:
                cur = {"label": ent, "debut": start, "fin": end, "_c": [c]}
                spans.append(cur)
            else:
                cur["fin"] = end
                cur["_c"].append(c)

        out: list[dict] = []
        for sp in spans:
            confs = sp.pop("_c")
            sp["confiance"] = round(sum(confs) / len(confs), 4)
            while sp["debut"] < sp["fin"] and texte[sp["debut"]].isspace():
                sp["debut"] += 1
            while sp["fin"] > sp["debut"] and texte[sp["fin"] - 1].isspace():
                sp["fin"] -= 1
            if sp["debut"] < sp["fin"]:
                sp["texte"] = texte[sp["debut"]:sp["fin"]]
                out.append(sp)
        return out


class ModeleCRF:
    """Inférence CRF CPU (``sklearn-crfsuite``) avec calibration des marginales."""

    def __init__(self, chemin: Union[str, Path] = CHEMIN_CRF):
        import joblib

        dossier = Path(chemin)
        self.crf = joblib.load(dossier / "crf_model.joblib")
        with open(dossier / "calibration.json", encoding="utf-8") as f:
            cal = json.load(f)
        self.T: float = max(float(cal.get("temperature", 1.0)), 0.05)
        self.version: str = str(cal.get("version", "crf-v1"))

    def predict(self, texte: str) -> list[dict]:
        if not texte or not texte.strip():
            return []
        toks = tokeniser(texte)
        if not toks:
            return []
        x = [feats(toks, i) for i in range(len(toks))]
        labels = self.crf.predict_single(x)
        marginals = self.crf.predict_marginals_single(x)
        return decoder_spans_crf(texte, toks, labels, marginals, temperature=self.T)


def _charger_modele():
    src = source_disponible()
    if src is None:
        raise FileNotFoundError(
            "Aucun modèle NER entraîné disponible (ni ner-v1 ni crf-v1)."
        )
    type_mod, dossier = src
    cle = (type_mod, str(dossier.resolve()))
    if cle not in _CACHE:
        if type_mod == "transformer":
            log.info("Chargement du modèle Transformer NER (%s)", dossier)
            _CACHE[cle] = ModeleTransformer(dossier)
        else:
            log.info(
                "Modèle Transformer ner-v1 absent : chargement du modèle CRF (%s)",
                dossier,
            )
            _CACHE[cle] = ModeleCRF(dossier)
    return _CACHE[cle]


def version_active() -> Optional[str]:
    """Retourne le ``version_modele`` actif (``ner-v1``, ``crf-v1``) ou ``None``."""
    if not disponible():
        return None
    return _charger_modele().version


def extraire_brut(messages: list[dict]) -> list[dict]:
    """Extrait les champs bruts avec le modèle actif (interface officielle §7.8)."""
    modele = _charger_modele()
    return [
        champ_brut(sp, msg, modele.version)
        for msg in messages
        for sp in modele.predict(msg["texte"])
    ]
