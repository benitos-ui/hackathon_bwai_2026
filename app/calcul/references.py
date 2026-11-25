import csv
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def load_catalogue() -> dict:
    catalogue = {}
    with (DATA_DIR / "catalogue.csv").open(encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            catalogue[row["reference"]] = {
                "name": row["name"],
                "variants": [item.strip() for item in row["variants"].split(",")],
                "price_ht": int(row["price_ht"]),
            }
    return catalogue


def load_clients() -> dict:
    clients = {}
    with (DATA_DIR / "clients.csv").open(encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            clients[row["id"]] = {
                "name": row["name"],
                "phone": row["phone"],
                "zone": row["zone"],
                "faithful": row["faithful"].lower() == "true",
            }
    return clients
