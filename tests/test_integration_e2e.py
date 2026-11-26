"""End-to-end integration and acceptance tests (E1..E18, T11..T22)."""
import concurrent.futures
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.api.main as api_main
from app.workflow.service import WorkflowService

AWA_THREAD = """25/11/2026 10:02 - Awa: Bonjour, je veux 2 robes Ayoka, une en M et une en L, et 1 sérum vitamine C svp
25/11/2026 10:05 - Vendeuse: Bonjour Awa, c'est noté. Livraison à Calavi ?
25/11/2026 10:06 - Awa: Oui à Calavi, paiement à la livraison
25/11/2026 16:40 - Livreur: Livré chez Awa. Elle a refusé la robe L (trop petite). 1 robe M + 1 sérum livrés, payé en espèces."""


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "e2e.sqlite3"
    svc = WorkflowService(db_file)
    monkeypatch.setattr(api_main, "service", svc)
    return TestClient(api_main.app), svc, db_file


def test_full_awa_journey_live_api(client):
    http, svc, _ = client

    # 1. Import raw WhatsApp thread (role vendeuse required)
    denied = http.post(
        "/dossiers/import",
        json={"raw_text": AWA_THREAD, "created_by": "USR-AUD"},
        headers={"Idempotency-Key": "imp-aud"},
    )
    assert denied.status_code == 403

    imp = http.post(
        "/dossiers/import",
        json={"raw_text": AWA_THREAD, "created_by": "USR-VEND"},
        headers={"Idempotency-Key": "imp-awa-1"},
    )
    assert imp.status_code == 200
    body = imp.json()
    dossier_id = body["dossier_id"]
    assert body["duplicate"] is False
    assert body["version"] == 1
    assert body["doc_status"] == "A_REVOIR"

    # Re-importing the exact same text (even with another key) returns the same dossier (E1)
    dup = http.post(
        "/dossiers/import",
        json={"raw_text": AWA_THREAD, "created_by": "USR-VEND"},
        headers={"Idempotency-Key": "imp-awa-2"},
    )
    assert dup.status_code == 200
    assert dup.json()["duplicate"] is True
    assert dup.json()["dossier_id"] == dossier_id

    # 2. Read dossier, messages, extractions, anomalies, delivery, draft invoice, draft PDF
    dossier = http.get(f"/dossiers/{dossier_id}").json()
    assert dossier["dossier_id"] == dossier_id
    assert dossier["doc_status"] == "A_REVOIR"
    assert dossier["financial_status"] == "NON_REGLEE"
    assert dossier["invoice_number"] is None
    assert dossier["initiator"] == "USR-VEND"

    messages = http.get(f"/dossiers/{dossier_id}/messages").json()
    assert len(messages) == 4
    assert messages[0]["id"] == "m1"
    assert messages[0]["type_message"] == "COMMANDE"
    assert messages[3]["type_message"] == "LIVRAISON"

    extractions = http.get(f"/dossiers/{dossier_id}/extractions").json()
    field_names = {f["field"] for f in extractions}
    assert {"client", "produit_1", "zone", "paiement", "code_promo"} <= field_names
    promo = next(f for f in extractions if f["field"] == "code_promo")
    assert promo["value"] is None and promo["status"] == "missing"

    anomalies = http.get(f"/dossiers/{dossier_id}/anomalies").json()
    assert len(anomalies) >= 1
    assert any(a["code"] == "A_LIVRAISON" and not a["resolved"] for a in anomalies)

    delivery = http.get(f"/dossiers/{dossier_id}/livraison").json()
    assert len(delivery) == 3
    refused_line = next(d for d in delivery if d["refused"] == 1)
    assert refused_line["variant"] == "L"

    facture = http.get(f"/dossiers/{dossier_id}/facture").json()
    assert facture["totals"]["subtotal"] == 23000
    assert facture["totals"]["discount"] == 1150
    assert facture["totals"]["delivery"] == 1500
    assert facture["totals"]["base_ht"] == 23350
    assert facture["totals"]["vat"] == 4203
    assert facture["totals"]["total_ttc"] == 27553

    draft_pdf = http.get(f"/dossiers/{dossier_id}/brouillon.pdf")
    assert draft_pdf.status_code == 200
    assert draft_pdf.content.startswith(b"%PDF")

    # 3. Confirm fields (and test correction preserves original value)
    corr = http.post(
        f"/dossiers/{dossier_id}/champs/zone/confirmer",
        json={"user": "USR-VEND", "new_value": "Abomey-Calavi"},
    )
    assert corr.status_code == 200
    assert corr.json()["confirmed"] is True
    assert corr.json()["corrected"] is True
    assert corr.json()["raw_value"] == "Calavi"

    # Confirm remaining required fields
    for f in extractions:
        if f["status"] != "missing" and f["field"] != "zone":
            r = http.post(
                f"/dossiers/{dossier_id}/champs/{f['field']}/confirmer",
                json={"user": "USR-VEND"},
            )
            assert r.status_code == 200

    # Still blocked in A_REVOIR because anomaly is open
    assert http.get(f"/dossiers/{dossier_id}").json()["doc_status"] == "A_REVOIR"

    # Resolve anomaly without justification -> 422
    anom_id = anomalies[0]["id"]
    bad_res = http.post(
        f"/anomalies/{anom_id}/resoudre",
        json={"resolved_by": "USR-VEND", "justification": "   "},
    )
    assert bad_res.status_code == 422

    # Resolve all open anomalies with justification -> transitions to PRET_A_VALIDER
    for a in anomalies:
        res = http.post(
            f"/anomalies/{a['id']}/resoudre",
            json={
                "resolved_by": "USR-VEND",
                "justification": "Cliente a refusé la taille L (trop petite), facturation sur livré accepté.",
            },
        )
        assert res.status_code == 200
        assert res.json()["resolved"] is True

    ready = http.get(f"/dossiers/{dossier_id}").json()
    assert ready["doc_status"] == "PRET_A_VALIDER"

    # 4. Validate invoice: four-eyes & role checks (E7)
    r_vend = http.post(
        f"/dossiers/{dossier_id}/valider",
        json={"validator_id": "USR-VEND", "validator_role": "vendeuse", "version": ready["version"]},
        headers={"Idempotency-Key": "val-1"},
    )
    assert r_vend.status_code == 403

    r_stale = http.post(
        f"/dossiers/{dossier_id}/valider",
        json={"validator_id": "USR-GER", "validator_role": "gerant", "version": ready["version"] - 1},
        headers={"Idempotency-Key": "val-stale"},
    )
    assert r_stale.status_code == 409

    val = http.post(
        f"/dossiers/{dossier_id}/valider",
        json={"validator_id": "USR-GER", "validator_role": "gerant", "version": ready["version"]},
        headers={"Idempotency-Key": "val-ok"},
    )
    assert val.status_code == 200
    invoice_id = val.json()["id"]
    invoice_number = val.json()["number"]
    assert invoice_number == "FAC-2026-000001"

    # Frozen PDF available with X-Content-Hash header
    inv_pdf = http.get(f"/factures/{invoice_id}/pdf")
    assert inv_pdf.status_code == 200
    assert inv_pdf.content.startswith(b"%PDF")
    assert inv_pdf.headers["X-Content-Hash"] == val.json()["content_hash"]

    # 5. Simulated emission in offline mode + idempotent sync (E11 & E13)
    em = http.post(
        f"/factures/{invoice_id}/emettre",
        json={"channel": "whatsapp", "actor": "USR-VEND", "offline": True},
        headers={"Idempotency-Key": "emit-1"},
    )
    assert em.status_code == 200
    assert em.json()["status"] == "en_attente"
    assert http.get(f"/dossiers/{dossier_id}").json()["doc_status"] == "VALIDEE"

    sync1 = http.post("/outbox/synchroniser", json={"actor": "USR-VEND"}).json()
    assert sync1["synced_count"] == 1
    sync2 = http.post("/outbox/synchroniser", json={"actor": "USR-VEND"}).json()
    assert sync2["synced_count"] == 0
    assert http.get(f"/dossiers/{dossier_id}").json()["doc_status"] == "EMISE"

    # 6. Payments: partial, replay idempotency, rejected excluded (T14, T15, T16)
    p1 = http.post(
        f"/factures/{invoice_id}/reglements",
        json={"amount": 15000, "mode": "espèces", "reference": "CASH-1", "entered_by": "USR-VEND"},
        headers={"Idempotency-Key": "pay-1"},
    )
    assert p1.status_code == 200
    assert p1.json()["reference"].startswith("FICTIF")

    # Replay same idempotency key does NOT double-count
    p1_replay = http.post(
        f"/factures/{invoice_id}/reglements",
        json={"amount": 15000, "mode": "espèces", "reference": "CASH-1", "entered_by": "USR-VEND"},
        headers={"Idempotency-Key": "pay-1"},
    )
    assert p1_replay.json()["id"] == p1.json()["id"]

    # Rejected payment kept as event, excluded from balance (T16)
    p_rej = http.post(
        f"/factures/{invoice_id}/reglements",
        json={
            "amount": 5000,
            "mode": "mobile_money",
            "reference": "MOMO-ERR",
            "entered_by": "USR-VEND",
            "status": "rejete",
        },
        headers={"Idempotency-Key": "pay-rej"},
    )
    assert p_rej.status_code == 200
    bal1 = http.get(f"/factures/{invoice_id}/solde").json()
    assert bal1["paid"] == 15000
    assert bal1["balance"] == 12553
    assert bal1["financial_status_code"] == "PARTIELLEMENT_REGLEE"

    # 7. Partial credit note (avoir) — gérant only (T17, T18)
    crd_denied = http.post(
        f"/factures/{invoice_id}/avoirs",
        json={"amount": 2553, "reason": "Geste commercial", "created_by": "USR-VEND", "creator_role": "vendeuse"},
        headers={"Idempotency-Key": "crd-denied"},
    )
    assert crd_denied.status_code == 403

    crd = http.post(
        f"/factures/{invoice_id}/avoirs",
        json={"amount": 2553, "reason": "Retour partiel", "created_by": "USR-GER", "creator_role": "gerant"},
        headers={"Idempotency-Key": "crd-1"},
    )
    assert crd.status_code == 200
    assert crd.json()["number"] == "AV-2026-000001"

    crd_pdf = http.get(f"/avoirs/{crd.json()['id']}/pdf")
    assert crd_pdf.status_code == 200
    assert crd_pdf.content.startswith(b"%PDF")

    # Second payment settles remaining 10 000 FCFA
    p2 = http.post(
        f"/factures/{invoice_id}/reglements",
        json={"amount": 10000, "mode": "mobile_money", "reference": "MOMO-2", "entered_by": "USR-VEND"},
        headers={"Idempotency-Key": "pay-2"},
    )
    assert p2.status_code == 200
    bal2 = http.get(f"/factures/{invoice_id}/solde").json()
    assert bal2["credits"] == 2553
    assert bal2["paid"] == 25000
    assert bal2["balance"] == 0
    assert bal2["financial_status_code"] == "REGLEE"

    # 8. Audit trail contains every action and chain is valid
    audit_entries = http.get("/audit", params={"dossier_id": dossier_id}).json()
    actions = {e["action"] for e in audit_entries}
    assert {
        "IMPORT",
        "FIELD_CORRECTED",
        "FIELD_CONFIRMED",
        "ANOMALY_RESOLVED",
        "INVOICE_VALIDATED",
        "INVOICE_EMITTED",
        "PAYMENT_ADDED",
        "PAYMENT_REJECTED",
        "CREDIT_CREATED",
    } <= actions

    verify = http.get("/audit/verifier").json()
    assert verify["valid"] is True
    assert verify["entries"] == len(audit_entries)


def test_50_concurrent_validations_create_single_invoice(client):
    """E8: 50 simultaneous validations of the same draft create exactly 1 invoice & 1 number."""
    http, svc, _ = client
    imp = http.post(
        "/dossiers/import",
        json={"raw_text": AWA_THREAD, "created_by": "USR-VEND"},
        headers={"Idempotency-Key": "conc-imp"},
    ).json()
    dossier_id = imp["dossier_id"]
    http.post(f"/dossiers/{dossier_id}/confirmer", json={"user": "USR-VEND"})
    for a in http.get(f"/dossiers/{dossier_id}/anomalies").json():
        http.post(
            f"/anomalies/{a['id']}/resoudre",
            json={"resolved_by": "USR-VEND", "justification": "Vérifié pour concurrence"},
        )
    ready = http.get(f"/dossiers/{dossier_id}").json()
    assert ready["doc_status"] == "PRET_A_VALIDER"

    res = svc.simulate_concurrency(dossier_id, "USR-GER", "gerant", n_requests=50)
    assert res["invoices_in_db"] == 1
    assert len(res["unique_numbers"]) == 1
    assert res["unique_numbers"][0] == "FAC-2026-000001"


def test_interruption_and_resume_without_duplicates(client):
    """E12: Stopping mid-pipeline and resuming completes cleanly with zero duplicate rows."""
    http, _, _ = client
    interrupted = http.post(
        "/demo/simuler-interruption",
        json={"raw_text": AWA_THREAD, "created_by": "USR-VEND", "stop_after_step": "EXTRAIT"},
        headers={"Idempotency-Key": "int-1"},
    )
    assert interrupted.status_code == 200
    dossier_id = interrupted.json()["dossier_id"]
    assert set(interrupted.json()["steps"]) == {"IMPORTE", "ANALYSE", "EXTRAIT"}
    assert http.get(f"/dossiers/{dossier_id}/anomalies").json() == []

    resumed = http.post(
        f"/dossiers/{dossier_id}/reprendre",
        json={"actor": "USR-VEND"},
    )
    assert resumed.status_code == 200
    assert len(resumed.json()["steps"]) == 7

    # Calling resume a second time creates zero duplicate messages/fields/anomalies/audits
    msgs_before = len(http.get(f"/dossiers/{dossier_id}/messages").json())
    fields_before = len(http.get(f"/dossiers/{dossier_id}/extractions").json())
    anoms_before = len(http.get(f"/dossiers/{dossier_id}/anomalies").json())
    audit_before = len(http.get("/audit", params={"dossier_id": dossier_id}).json())

    http.post(f"/dossiers/{dossier_id}/reprendre", json={"actor": "USR-VEND"})
    assert len(http.get(f"/dossiers/{dossier_id}/messages").json()) == msgs_before
    assert len(http.get(f"/dossiers/{dossier_id}/extractions").json()) == fields_before
    assert len(http.get(f"/dossiers/{dossier_id}/anomalies").json()) == anoms_before
    assert len(http.get("/audit", params={"dossier_id": dossier_id}).json()) == audit_before


def test_immutability_triggers_and_audit_tamper_detection(client):
    """E9 & E10: SQLite triggers block updates/deletes on invoices, lines, credits, audit_log."""
    http, svc, db_file = client
    imp = http.post(
        "/dossiers/import",
        json={"raw_text": AWA_THREAD, "created_by": "USR-VEND"},
    ).json()
    did = imp["dossier_id"]
    http.post(f"/dossiers/{did}/confirmer", json={"user": "USR-VEND"})
    for a in http.get(f"/dossiers/{did}/anomalies").json():
        http.post(f"/anomalies/{a['id']}/resoudre", json={"resolved_by": "USR-VEND", "justification": "OK"})
    ver = http.get(f"/dossiers/{did}").json()["version"]
    inv = http.post(
        f"/dossiers/{did}/valider",
        json={"validator_id": "USR-GER", "validator_role": "gerant", "version": ver},
        headers={"Idempotency-Key": "imm-1"},
    ).json()
    http.post(
        f"/factures/{inv['id']}/avoirs",
        json={"amount": 1000, "reason": "Test", "created_by": "USR-GER", "creator_role": "gerant"},
        headers={"Idempotency-Key": "imm-crd"},
    )

    conn = sqlite3.connect(str(db_file))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE invoices SET total_ttc = 1 WHERE id = ?", (inv["id"],))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM invoice_lines WHERE invoice_id = ?", (inv["id"],))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE credits SET amount = 0")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("DELETE FROM audit_log")

    # Simulate database-level tampering (bypassing trigger) -> verify_audit MUST detect it
    conn.execute("DROP TRIGGER prevent_audit_update")
    conn.execute("UPDATE audit_log SET actor = 'HACKER' WHERE id = 1")
    conn.commit()
    conn.close()

    check = svc.verify_audit()
    assert check["valid"] is False
    assert check["broken_at"] == 1


def test_cancel_before_validation_and_unknown_client_anomaly(client):
    """T19 & A_CLIENT_INCONNU: Unknown client triggers anomaly; cancel audited and blocks validation."""
    http, _, _ = client
    unknown_thread = "25/11/2026 11:00 - Inconnu999: Je veux 1 sac Lagune à Cotonou pour 25000 fcfa"
    imp = http.post(
        "/dossiers/import",
        json={"raw_text": unknown_thread, "created_by": "USR-VEND"},
    )
    assert imp.status_code == 200
    did = imp.json()["dossier_id"]
    codes = {a["code"] for a in http.get(f"/dossiers/{did}/anomalies").json()}
    assert "A_CLIENT_INCONNU" in codes
    assert "A_PRIX" in codes

    cancelled = http.post(
        f"/dossiers/{did}/annuler",
        json={"cancelled_by": "USR-VEND", "reason": "Client a annulé avant expédition"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["doc_status"] == "ANNULE"

    audit = http.get("/audit", params={"dossier_id": did}).json()
    assert any(e["action"] == "DOSSIER_CANCELLED" for e in audit)


def test_t21_catalog_change_does_not_alter_validated_invoice(client, monkeypatch):
    """T21: Changing the catalogue after validation leaves the frozen invoice and its hash untouched."""
    http, _, _ = client
    imp = http.post("/dossiers/import", json={"raw_text": AWA_THREAD, "created_by": "USR-VEND"}).json()
    did = imp["dossier_id"]
    http.post(f"/dossiers/{did}/confirmer", json={"user": "USR-VEND"})
    for a in http.get(f"/dossiers/{did}/anomalies").json():
        http.post(f"/anomalies/{a['id']}/resoudre", json={"resolved_by": "USR-VEND", "justification": "OK"})
    ver = http.get(f"/dossiers/{did}").json()["version"]
    inv = http.post(
        f"/dossiers/{did}/valider",
        json={"validator_id": "USR-GER", "validator_role": "gerant", "version": ver},
        headers={"Idempotency-Key": "t21-val"},
    ).json()

    before_detail = http.get(f"/factures/{inv['id']}").json()
    before_pdf = http.get(f"/factures/{inv['id']}/pdf")

    # Simulate a subsequent catalogue price change (15 000 -> 99 000 FCFA)
    import app.workflow.service as svc_mod
    monkeypatch.setattr(
        svc_mod,
        "load_catalogue",
        lambda: {
            "ART-001": {"name": "Robe wax Ayoka V2", "variants": ["M", "L"], "price_ht": 99000},
            "ART-004": {"name": "Serum vitamine C V2", "variants": ["Unique"], "price_ht": 88000},
        },
    )

    after_detail = http.get(f"/factures/{inv['id']}").json()
    after_pdf = http.get(f"/factures/{inv['id']}/pdf")
    assert after_detail["content_hash"] == before_detail["content_hash"]
    assert after_detail["totals"]["total_ttc"] == before_detail["totals"]["total_ttc"] == 27553
    assert after_detail["lines"] == before_detail["lines"]
    assert after_pdf.headers["X-Content-Hash"] == before_pdf.headers["X-Content-Hash"]


def test_ui_api_client_live_end_to_end(client, monkeypatch):
    """Verify ui.api_client in live mode speaks seamlessly to every FastAPI endpoint."""
    from ui import api_client

    http, _, _ = client

    class _SyncTestClientProxy:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, method, url, **kwargs):
            path = url.replace("http://testserver", "")
            return http.request(method, path, **kwargs)

    monkeypatch.setattr(api_client, "API_MODE", "live")
    monkeypatch.setattr(api_client, "API_URL", "http://testserver")
    monkeypatch.setattr(api_client.httpx, "Client", _SyncTestClientProxy)

    res = api_client.import_conversation(AWA_THREAD, "USR-VEND")
    did = res["dossier_id"]
    assert res["duplicate"] is False

    assert len(api_client.get_messages(did)) == 4
    fields = api_client.get_extractions(did)
    assert len(fields) >= 6
    api_client.confirm_all_fields(did, "USR-VEND")

    for anom in api_client.get_anomalies(did):
        api_client.resolve_anomaly(did, anom["id"], "USR-VEND", "Confirmé via UI live")

    dos = api_client.get_dossier(did)
    assert dos["doc_status"] == "PRET_A_VALIDER"
    assert len(api_client.get_delivery(did)) == 3
    assert api_client.get_invoice(did)["totals"]["total_ttc"] == 27553

    val = api_client.validate_invoice(did, "USR-GER", "gerant", version=dos["version"])
    inv_id = val["id"]
    api_client.emit_invoice(inv_id, "whatsapp", "USR-VEND")
    api_client.add_payment(inv_id, 27553, "espèces", "UI-CASH-1", "USR-VEND")

    bal = api_client.get_balance(inv_id)
    assert bal["balance"] == 0
    assert bal["financial_status"] == "REGLEE"

    audit = api_client.get_audit(did)
    assert len(audit) >= 5
    assert api_client.verify_audit()["valid"] is True
    assert api_client.get_dashboard()["invoices_count"] == 1

