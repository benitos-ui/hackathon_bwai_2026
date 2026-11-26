import csv
import hashlib
from pathlib import Path

import yaml


DATA_DIR = Path(__file__).resolve().parents[2] / "data"

DEFAULT_RULES = {
    "currency": "FCFA",
    "tax_rate_percent": 18,
    "discounts": {
        "fidelity_percent": 5,
        "quantity_percent": 10,
        "quantity_units_threshold": 3,
        "welcome_code": "BIENVENUE10",
        "welcome_percent": 10,
    },
    "delivery_fees_ht": {
        "Cotonou": 1000,
        "Abomey-Calavi": 1500,
        "Porto-Novo": 2000,
    },
    "unusual_price_tolerance_percent": 10,
    "rounding": "half_up",
    "seuils_confiance": {
        "vert": 0.90,
        "rouge": 0.60,
    },
    "vendor": {
        "name": "Boutique X",
        "address": "Adresse commerciale fictive — Cotonou",
        "phone": "+229 01 00 00 00 00 (fictif)",
        "ifu": "non renseigné — prototype",
        "footer": "Document pédagogique — données fictives — paiements simulés",
    },
}


def load_catalogue(data_dir: Path | None = None) -> dict:
    base = data_dir or DATA_DIR
    catalogue = {}
    with (base / "catalogue.csv").open(encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            catalogue[row["reference"]] = {
                "name": row["name"],
                "variants": [item.strip() for item in row["variants"].split(",") if item.strip()],
                "price_ht": int(row["price_ht"]),
            }
    return catalogue


def load_clients(data_dir: Path | None = None) -> dict:
    base = data_dir or DATA_DIR
    clients = {}
    with (base / "clients.csv").open(encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            clients[row["id"]] = {
                "name": row["name"],
                "phone": row["phone"],
                "zone": row["zone"],
                "faithful": row["faithful"].lower() in ("true", "oui", "1", "yes"),
            }
    return clients


def load_rules(data_dir: Path | None = None) -> dict:
    base = data_dir or DATA_DIR
    rules_path = base / "rules.yaml"
    if not rules_path.is_file():
        return dict(DEFAULT_RULES)
    with rules_path.open(encoding="utf-8") as file:
        loaded = yaml.safe_load(file) or {}
    merged = {**DEFAULT_RULES, **loaded}
    merged["discounts"] = {**DEFAULT_RULES["discounts"], **(loaded.get("discounts") or {})}
    merged["delivery_fees_ht"] = {
        **DEFAULT_RULES["delivery_fees_ht"],
        **(loaded.get("delivery_fees_ht") or {}),
    }
    merged["seuils_confiance"] = {
        **DEFAULT_RULES["seuils_confiance"],
        **(loaded.get("seuils_confiance") or {}),
    }
    merged["vendor"] = {**DEFAULT_RULES["vendor"], **(loaded.get("vendor") or {})}
    return merged


def get_config_hash(data_dir: Path | None = None) -> str:
    """Compute a deterministic SHA-256 fingerprint of catalogue, clients, and rules."""
    base = data_dir or DATA_DIR
    hasher = hashlib.sha256()
    for filename in ("catalogue.csv", "clients.csv", "rules.yaml"):
        file_path = base / filename
        hasher.update(filename.encode("utf-8"))
        if file_path.is_file():
            hasher.update(file_path.read_bytes())
    return hasher.hexdigest()
