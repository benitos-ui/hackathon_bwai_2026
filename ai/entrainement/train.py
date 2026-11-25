"""Fine-tuning NER DistilCamemBERT + calibration par température (Étape 6 — Jalon H12).

Script conçu pour s'exécuter sur Colab/Kaggle (GPU recommandé, 15–30 min) ou en local :
    ``python -m ai.entrainement.train``

Points clés (Guide §11.1 & Addendum v1.1 §4) :
- Modèle de base : ``cmarkea/distilcamembert-base`` (tokenizer rapide obligatoire pour
  ``return_offsets_mapping=True``).
- Graine fixée (``SEED = 42``) pour la reproductibilité (E18).
- Compatibilité automatique ``eval_strategy`` / ``evaluation_strategy`` selon la version
  de ``transformers``.
- Calibration par mise à l'échelle de la température (L-BFGS) ajustée **exclusivement**
  sur ``val.jsonl`` et enregistrée dans ``calibration.json`` (``version = "ner-v1"``).
- Aucun téléchargement ni effet de bord à l'import du module.
"""

import argparse
import inspect
import json
import random
from pathlib import Path
from typing import Union

import numpy as np
import torch

from ai.config import CHEMIN_DONNEES, CHEMIN_MODELE, SEED
from ai.extraction.schema import ID2LABEL, LABEL2ID, LABELS

MODELE_BASE: str = "cmarkea/distilcamembert-base"
VERSION_MODELE: str = "ner-v1"


def fixer_graines(seed: int = SEED) -> None:
    """Fixe les graines Python, NumPy et PyTorch pour la reproductibilité."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def lire_jsonl(path: Union[str, Path]) -> list[dict]:
    """Charge un jeu JSONL (``text``, ``spans``, ``role``, ``tid``)."""
    with open(path, encoding="utf-8") as f:
        return [json.loads(ligne) for ligne in f if ligne.strip()]


def aligner_exemple(exemple: dict, tokenizer, max_length: int = 128) -> dict:
    """Aligne les spans caractères (Unicode) sur les sous-tokens BIO du tokenizer rapide."""
    enc = tokenizer(
        exemple["text"],
        truncation=True,
        max_length=max_length,
        return_offsets_mapping=True,
    )
    labels: list[int] = []
    prev_idx = None
    spans = exemple.get("spans", [])

    for start, end in enc["offset_mapping"]:
        if start == end:
            labels.append(-100)
            prev_idx = None
            continue
        idx = next(
            (k for k, sp in enumerate(spans) if start < sp["fin"] and end > sp["debut"]),
            None,
        )
        if idx is None:
            labels.append(LABEL2ID["O"])
            prev_idx = None
        else:
            prefix = "I-" if idx == prev_idx else "B-"
            labels.append(LABEL2ID[prefix + spans[idx]["label"]])
            prev_idx = idx

    enc["labels"] = labels
    enc.pop("offset_mapping")
    return enc


def calibrer_temperature(
    logits: torch.Tensor,
    labels: torch.Tensor,
    max_iter: int = 100,
) -> float:
    """Estime la température optimale T > 0 par L-BFGS sur la validation (NLL minimale).

    Paramétrisation ``T = exp(log_T)`` garantissant ``T > 0`` à chaque itération.
    """
    masque = labels != -100
    logits_f = logits[masque].detach().float()
    labels_f = labels[masque].detach().long()
    if logits_f.numel() == 0:
        return 1.0

    log_t = torch.nn.Parameter(torch.zeros(1, dtype=torch.float32))
    optimizer = torch.optim.LBFGS([log_t], lr=0.1, max_iter=max_iter)
    criterion = torch.nn.CrossEntropyLoss()

    def closure() -> torch.Tensor:
        optimizer.zero_grad()
        temp = torch.exp(log_t).clamp(min=0.05, max=20.0)
        loss = criterion(logits_f / temp, labels_f)
        loss.backward()
        return loss

    optimizer.step(closure)
    return round(float(torch.exp(log_t).clamp(min=0.05, max=20.0).item()), 6)


def _construire_training_args(
    sortie: str,
    epochs: int,
    batch_size: int,
    lr: float,
    seed: int,
):
    from transformers import TrainingArguments

    params = inspect.signature(TrainingArguments.__init__).parameters
    cle_eval = "eval_strategy" if "eval_strategy" in params else "evaluation_strategy"

    kwargs = {
        "output_dir": sortie,
        "num_train_epochs": epochs,
        "per_device_train_batch_size": batch_size,
        "per_device_eval_batch_size": batch_size,
        "learning_rate": lr,
        "weight_decay": 0.01,
        "seed": seed,
        "fp16": torch.cuda.is_available(),
        cle_eval: "epoch",
        "save_strategy": "epoch",
        "load_best_model_at_end": True,
        "metric_for_best_model": "f1",
        "save_total_limit": 2,
        "report_to": "none",
    }
    return TrainingArguments(**kwargs)


def entrainer(
    chemin_train: Union[str, Path] = CHEMIN_DONNEES / "train.jsonl",
    chemin_val: Union[str, Path] = CHEMIN_DONNEES / "val.jsonl",
    sortie: Union[str, Path] = CHEMIN_MODELE,
    modele_base: str = MODELE_BASE,
    version: str = VERSION_MODELE,
    epochs: int = 5,
    batch_size: int = 32,
    lr: float = 5e-5,
    seed: int = SEED,
) -> dict:
    """Entraîne DistilCamemBERT NER, calibre la température sur ``val.jsonl`` et sauvegarde."""
    from datasets import Dataset
    from seqeval.metrics import f1_score
    from transformers import (
        AutoModelForTokenClassification,
        AutoTokenizer,
        DataCollatorForTokenClassification,
        Trainer,
    )

    fixer_graines(seed)
    dossier_sortie = Path(sortie)
    dossier_sortie.mkdir(parents=True, exist_ok=True)

    tokenizer = AutoTokenizer.from_pretrained(modele_base, use_fast=True)

    def preparer_dataset(chemin: Union[str, Path]) -> Dataset:
        ds = Dataset.from_list(lire_jsonl(chemin))
        return ds.map(
            lambda ex: aligner_exemple(ex, tokenizer),
            remove_columns=ds.column_names,
        )

    train_ds = preparer_dataset(chemin_train)
    val_ds = preparer_dataset(chemin_val)

    model = AutoModelForTokenClassification.from_pretrained(
        modele_base,
        num_labels=len(LABELS),
        id2label=ID2LABEL,
        label2id=LABEL2ID,
    )

    def compute_metrics(eval_pred):
        logits, label_ids = eval_pred
        preds = np.argmax(logits, axis=-1)
        y_true = [
            [ID2LABEL[int(l)] for l in row if l != -100]
            for row in label_ids
        ]
        y_pred = [
            [ID2LABEL[int(p)] for p, l in zip(pred_row, row) if l != -100]
            for pred_row, row in zip(preds, label_ids)
        ]
        return {"f1": round(float(f1_score(y_true, y_pred)), 4)}

    args = _construire_training_args(
        sortie=str(dossier_sortie),
        epochs=epochs,
        batch_size=batch_size,
        lr=lr,
        seed=seed,
    )
    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        data_collator=DataCollatorForTokenClassification(tokenizer),
        compute_metrics=compute_metrics,
    )

    trainer.train()
    trainer.save_model(str(dossier_sortie))
    tokenizer.save_pretrained(str(dossier_sortie))

    # Calibration par température exclusivement sur la validation (val.jsonl)
    val_out = trainer.predict(val_ds)
    logits_t = torch.tensor(val_out.predictions, dtype=torch.float32).reshape(-1, len(LABELS))
    labels_t = torch.tensor(val_out.label_ids, dtype=torch.long).reshape(-1)
    temperature = calibrer_temperature(logits_t, labels_t)
    f1_val = float((val_out.metrics or {}).get("test_f1", 0.0))

    calibration = {
        "type": "transformer",
        "version": version,
        "temperature": temperature,
        "seed": seed,
        "modele_base": modele_base,
        "f1_val": round(f1_val, 4),
    }
    with open(dossier_sortie / "calibration.json", "w", encoding="utf-8") as f:
        json.dump(calibration, f, ensure_ascii=False, indent=2)

    return calibration


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fine-tuning DistilCamemBERT NER + calibration par température."
    )
    parser.add_argument("--train", default=str(CHEMIN_DONNEES / "train.jsonl"))
    parser.add_argument("--val", default=str(CHEMIN_DONNEES / "val.jsonl"))
    parser.add_argument("--sortie", default=str(CHEMIN_MODELE))
    parser.add_argument("--modele", default=MODELE_BASE)
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=5e-5)
    parser.add_argument("--seed", type=int, default=SEED)
    cli_args = parser.parse_args()

    res = entrainer(
        chemin_train=cli_args.train,
        chemin_val=cli_args.val,
        sortie=cli_args.sortie,
        modele_base=cli_args.modele,
        epochs=cli_args.epochs,
        batch_size=cli_args.batch_size,
        lr=cli_args.lr,
        seed=cli_args.seed,
    )
    print(json.dumps(res, ensure_ascii=False, indent=2))
