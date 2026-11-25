from pathlib import Path

from app.calcul.calculator import calculate_invoice, percentage, round_half_up
from app.calcul.references import load_catalogue, load_clients
from app.controles.anomalies import detect_anomalies
from app.pdf.invoice_pdf import generate_invoice_pdf
from fastapi.testclient import TestClient
from app.api.main import app


def test_known_example_calculation():
    calculation = calculate_invoice(
        [
            {
                "product_id": "ART-001",
                "description": "Robe wax Ayoka",
                "variant": "M",
                "quantity_accepted": 1,
                "unit_price_ht": 15000,
            },
            {
                "product_id": "ART-004",
                "description": "Serum vitamine C 30 ml",
                "variant": None,
                "quantity_accepted": 1,
                "unit_price_ht": 8000,
            },
        ],
        "Abomey-Calavi",
        faithful_customer=True,
    )

    assert calculation["subtotal_articles"] == 23000
    assert calculation["discount_amount"] == 1150
    assert calculation["articles_base"] == 21850
    assert calculation["delivery_ht"] == 1500
    assert calculation["base_ht"] == 23350
    assert calculation["vat_amount"] == 4203
    assert calculation["total_ttc"] == 27553


def test_round_half_up():
    assert round_half_up(1, 2) == 1
    assert round_half_up(1, 3) == 0
    assert percentage(23350, 18) == 4203


def test_quantity_discount_uses_accepted_units():
    calculation = calculate_invoice(
        [{
            "product_id": "ART-001",
            "description": "Robe wax Ayoka",
            "variant": "M",
            "quantity_accepted": 3,
            "unit_price_ht": 15000,
        }],
        "Cotonou",
    )
    assert calculation["discount_name"] == "quantité"
    assert calculation["discount_amount"] == 4500


def test_delivery_mismatch_detected():
    anomalies = detect_anomalies(
        {
            "client": "CLI-0012",
            "lines": [{
                "product_id": "ART-001",
                "quantity_ordered": 2,
                "quantity_delivered": 2,
                "quantity_accepted": 1,
                "quantity_refused": 1,
                "quantity_missing": 1,
                "cited_price_ht": 15000,
            }],
        },
        load_catalogue(),
        load_clients(),
    )
    codes = {item["code"] for item in anomalies}
    assert "A_LIVRAISON" in codes


def test_unusual_price_detected():
    anomalies = detect_anomalies(
        {
            "client": "CLI-0012",
            "lines": [{
                "product_id": "ART-001",
                "quantity_ordered": 1,
                "quantity_delivered": 1,
                "quantity_accepted": 1,
                "quantity_refused": 0,
                "quantity_missing": 0,
                "cited_price_ht": 17000,
            }],
        },
        load_catalogue(),
        load_clients(),
    )
    assert "A_PRIX" in {item["code"] for item in anomalies}


def test_pdf_is_generated(tmp_path):
    calculation = calculate_invoice(
        [{
            "product_id": "ART-001",
            "description": "Robe wax Ayoka",
            "variant": "M",
            "quantity_accepted": 1,
            "unit_price_ht": 15000,
        }],
        "Cotonou",
    )
    path = generate_invoice_pdf(
        tmp_path / "draft.pdf",
        calculation,
        status="BROUILLON",
        dossier_reference="DOS-001",
        client={"name": "Awa Dossou", "phone": "+229...", "address": "Abomey-Calavi"},
    )
    assert Path(path).is_file()
    assert Path(path).stat().st_size > 100


def test_calculation_api_and_references():
    client = TestClient(app)

    catalogue = client.get("/referentiels/catalogue")
    assert catalogue.status_code == 200
    assert catalogue.json()["ART-001"]["price_ht"] == 15000

    result = client.post("/calcul", json={
        "lines": [{
            "product_id": "ART-001",
            "description": "Robe wax Ayoka",
            "variant": "M",
            "quantity_accepted": 1,
            "unit_price_ht": 15000,
        }],
        "zone": "Cotonou",
        "faithful_customer": False,
    })
    assert result.status_code == 200
    assert result.json()["total_ttc"] == 18880
