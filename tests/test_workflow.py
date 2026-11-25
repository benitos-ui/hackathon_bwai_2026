import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.main import app
from app.workflow.service import WorkflowError, WorkflowService


@pytest.fixture
def database(tmp_path):
    return tmp_path / "test.sqlite3"


@pytest.fixture
def service(database):
    return WorkflowService(database)


def ready_dossier(service, dossier_id="DOS-001"):
    service.create_dossier(dossier_id, "CONV-001", "USR-VEND", "idem-dossier")
    content = {
        "lines": [{
            "product_id": "ART-001",
            "description": "Robe wax Ayoka",
            "variant": "M",
            "quantity": 1,
            "unit_price_ht": 15000,
            "amount_ht": 15000,
        }],
        "total_ttc": 17700,
    }
    return service.prepare_dossier(dossier_id, content, 1)


def test_validation_requires_four_eyes_and_is_immutable(service):
    dossier = ready_dossier(service)

    with pytest.raises(WorkflowError) as error:
        service.validate_invoice(
            dossier["id"], "USR-VEND", "gerant", 2
        )
    assert error.value.status_code == 403

    invoice = service.validate_invoice(
        dossier["id"], "USR-GER", "gerant", 2
    )
    assert invoice["number"] == "FAC-2026-000001"

    replay = service.validate_invoice(
        dossier["id"], "USR-GER", "gerant", 2
    )
    assert replay["number"] == "FAC-2026-000001"


def test_payment_idempotency_and_balance(database, service):
    dossier = ready_dossier(service)
    invoice = service.validate_invoice(dossier["id"], "USR-GER", "gerant", 2)

    first = service.add_payment(
        invoice["id"], 10000, "espèces", "TEST-1",
        "USR-VEND", "pay-1"
    )
    replay = service.add_payment(
        invoice["id"], 10000, "espèces", "TEST-1",
        "USR-VEND", "pay-1"
    )
    assert first["id"] == replay["id"]

    balance = service.get_balance(invoice["id"])
    assert balance["confirmed_payments"] == 10000
    assert balance["balance"] == 7700
    assert balance["financial_status"] == "PARTIELLEMENT_RÉGLÉE"


def test_open_anomaly_blocks_validation(service):
    dossier = ready_dossier(service)
    with service._connection() as connection:
        connection.execute(
            """INSERT INTO anomalies
               (id, dossier_id, code, description, status)
               VALUES ('ANO-1', ?, 'A_QUANTITE', 'Quantité ambiguë', 'ouverte')""",
            (dossier["id"],),
        )

    with pytest.raises(WorkflowError) as error:
        service.validate_invoice(dossier["id"], "USR-GER", "gerant", 2)
    assert error.value.status_code == 422


def test_api_login_and_audit(database):
    client = TestClient(app)
    response = client.post("/auth/login", json={
        "identifier": "USR-GER",
        "password": "demo",
    })
    assert response.status_code == 200
    assert response.json()["role"] == "gerant"

    audit = client.get("/audit/verifier")
    assert audit.status_code == 200
    assert audit.json()["valid"] is True
