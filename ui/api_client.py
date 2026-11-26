"""Single access layer between the UI and the FastAPI backend.

API_MODE=live (default) calls the FastAPI backend over HTTP (httpx).
API_MODE=mock keeps the in-memory mock fallback from mock_data.py.
The UI never computes amounts or permissions: it only displays what the API returns.
"""
import copy
import hashlib
import os
import unicodedata
import uuid

import httpx

from ui import mock_data as md

API_MODE = os.getenv("API_MODE", "live")
API_URL = os.getenv("API_URL", "http://127.0.0.1:8000").rstrip("/")


class ApiError(Exception):
    """Business or permission error, mirrors the HTTP codes of the spec."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def _norm_code(value):
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(value))
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).upper()


def _request(method, path, *, json_body=None, params=None, headers=None, binary=False):
    url = f"{API_URL}{path}"
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.request(method, url, json=json_body, params=params, headers=headers)
    except httpx.RequestError as exc:
        raise ApiError(
            503,
            f"Impossible de joindre l'API ({API_URL}). Vérifie que FastAPI est lancé. ({exc})",
        )

    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text or f"Erreur HTTP {resp.status_code}"
        raise ApiError(resp.status_code, str(detail))

    if binary:
        return resp.content
    return resp.json()


# ---------------------------------------------------------------- mock state
_state = {}
_seen_hashes = {}


def _fresh_state():
    return {
        "dossier_id": "DOS-2026-0007",
        "initiator": None,
        "version": 1,
        "messages": copy.deepcopy(md.CHAT),
        "fields": copy.deepcopy(md.FIELDS),
        "anomalies": copy.deepcopy(md.ANOMALIES),
        "delivery": copy.deepcopy(md.DELIVERY),
        "lines": copy.deepcopy(md.INVOICE_LINES),
        "totals": copy.deepcopy(md.TOTALS),
        "balance": copy.deepcopy(md.BALANCE),
        "doc_status": md.DOC_STATUS,
        "financial_status": md.FINANCIAL_STATUS,
        "invoice_number": md.INVOICE_NUMBER,
        "invoice_id": None,
        "audit": [],
    }


def _log(action, user, detail=""):
    _state["audit"].append({
        "n": len(_state["audit"]) + 1,
        "timestamp": "",
        "action": action,
        "user": user,
        "detail": detail,
    })


def _refresh_doc_status():
    if _state["doc_status"] in ("VALIDEE", "EMISE"):
        return
    open_anomalies = any(not a["resolved"] for a in _state["anomalies"])
    all_confirmed = all(f["confirmed"] for f in _state["fields"] if f["status"] != "missing")
    if open_anomalies:
        _state["doc_status"] = "A_REVOIR"
    elif all_confirmed:
        _state["doc_status"] = "PRET_A_VALIDER"
    else:
        _state["doc_status"] = "BROUILLON"


# ------------------------------------------------------------------ public API
def login(identifier, password):
    if API_MODE == "mock":
        roles = {
            "USR-VEND": ("Vendeuse", "vendeuse"),
            "USR-GER": ("Gérant", "gerant"),
            "USR-AUD": ("Auditeur", "auditeur"),
        }
        if identifier not in roles or not password:
            raise ApiError(401, "Authentification refusée")
        name, role = roles[identifier]
        return {"identifier": identifier, "name": name, "role": role}
    return _request("POST", "/auth/login", json_body={"identifier": identifier, "password": password})


def check_api_health():
    """Return True if the live API responds cleanly, or True in mock mode."""
    if API_MODE == "mock":
        return True
    try:
        with httpx.Client(timeout=2.0) as client:
            resp = client.get(f"{API_URL}/tableau-de-bord")
        return resp.status_code < 500
    except httpx.RequestError:
        return False


def reset_demo():
    if API_MODE == "mock":
        _state.clear()
        _state.update(_fresh_state())
        _seen_hashes.clear()
        return {"reset": True}
    return _request("POST", "/demo/reinitialiser")


def list_dossiers():
    if API_MODE == "mock":
        return [get_dossier(_state["dossier_id"])] if _state.get("initiator") else []
    return _request("GET", "/dossiers")


def import_conversation(raw_text, user):
    if API_MODE == "mock":
        if not raw_text.strip():
            raise ApiError(422, "Fichier vide ou mal formé.")
        digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        if digest in _seen_hashes:
            return {"dossier_id": _seen_hashes[digest], "version": _state["version"], "duplicate": True}
        _state["initiator"] = user
        _seen_hashes[digest] = _state["dossier_id"]
        _log("IMPORT", user, f"sha256:{digest[:12]}")
        return {"dossier_id": _state["dossier_id"], "version": _state["version"], "duplicate": False}

    digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    return _request(
        "POST",
        "/dossiers/import",
        json_body={"raw_text": raw_text, "created_by": user},
        headers={"Idempotency-Key": f"import-{digest[:24]}"},
    )


def simulate_interruption(raw_text, user, stop_after_step="EXTRAIT"):
    if API_MODE == "mock":
        return import_conversation(raw_text, user)
    digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    return _request(
        "POST",
        "/demo/simuler-interruption",
        json_body={"raw_text": raw_text, "created_by": user, "stop_after_step": stop_after_step},
        headers={"Idempotency-Key": f"interrupt-{digest[:20]}"},
    )


def resume_dossier(dossier_id, actor="USR-VEND"):
    if API_MODE == "mock":
        return get_dossier(dossier_id)
    return _request("POST", f"/dossiers/{dossier_id}/reprendre", json_body={"actor": actor})


def get_dossier(dossier_id):
    if API_MODE == "mock":
        return {
            "dossier_id": dossier_id,
            "doc_status": _state["doc_status"],
            "financial_status": _state["financial_status"],
            "invoice_number": _state["invoice_number"],
            "invoice_id": _state["invoice_id"],
            "initiator": _state["initiator"],
            "version": _state["version"],
            "steps": ["IMPORTE", "ANALYSE", "EXTRAIT", "NORMALISE", "CONTROLE", "CALCULE", "BROUILLON"],
        }
    data = _request("GET", f"/dossiers/{dossier_id}")
    data["doc_status"] = _norm_code(data.get("doc_status"))
    data["financial_status"] = _norm_code(data.get("financial_status"))
    return data


def get_messages(dossier_id):
    if API_MODE == "mock":
        return _state["messages"]
    return _request("GET", f"/dossiers/{dossier_id}/messages")


def get_extractions(dossier_id):
    if API_MODE == "mock":
        return _state["fields"]
    return _request("GET", f"/dossiers/{dossier_id}/extractions")


def get_anomalies(dossier_id):
    if API_MODE == "mock":
        return _state["anomalies"]
    return _request("GET", f"/dossiers/{dossier_id}/anomalies")


def get_delivery(dossier_id):
    if API_MODE == "mock":
        return _state["delivery"]
    return _request("GET", f"/dossiers/{dossier_id}/livraison")


def get_invoice(dossier_id):
    if API_MODE == "mock":
        return {"lines": _state["lines"], "totals": _state["totals"]}
    return _request("GET", f"/dossiers/{dossier_id}/facture")


def get_draft_pdf(dossier_id):
    if API_MODE == "mock":
        raise ApiError(501, "PDF disponible uniquement en mode live.")
    return _request("GET", f"/dossiers/{dossier_id}/brouillon.pdf", binary=True)


def get_invoice_pdf(invoice_id):
    if API_MODE == "mock":
        raise ApiError(501, "PDF disponible uniquement en mode live.")
    return _request("GET", f"/factures/{invoice_id}/pdf", binary=True)


def get_invoice_detail(invoice_id):
    if API_MODE == "mock":
        return {
            "invoice_id": invoice_id,
            "invoice_number": _state["invoice_number"],
            "lines": _state["lines"],
            "totals": _state["totals"],
            "balance": _state["balance"],
            "events": [],
            "payments": [],
            "credits": [],
            "refunds": [],
        }
    return _request("GET", f"/factures/{invoice_id}")


def get_balance(invoice_id):
    if API_MODE == "mock":
        return _state["balance"]
    data = _request("GET", f"/factures/{invoice_id}/solde")
    data["financial_status"] = _norm_code(data.get("financial_status_code") or data.get("financial_status"))
    return data


def get_audit(dossier_id=None):
    if API_MODE == "mock":
        return _state["audit"]
    params = {"dossier_id": dossier_id} if dossier_id else None
    return _request("GET", "/audit", params=params)


def verify_audit():
    if API_MODE == "mock":
        return {"valid": True, "entries": len(_state["audit"]), "broken_at": None}
    return _request("GET", "/audit/verifier")


def get_dashboard():
    if API_MODE == "mock":
        return {
            "dossiers_total": 1 if _state.get("initiator") else 0,
            "dossiers_by_status": {_state["doc_status"]: 1} if _state.get("initiator") else {},
            "invoices_count": 1 if _state.get("invoice_number") else 0,
            "total_invoiced_ttc": _state["totals"]["total_ttc"] if _state.get("invoice_number") else 0,
            "total_paid": _state["balance"]["paid"],
            "total_credits": _state["balance"]["credits"],
            "open_anomalies": sum(1 for a in _state["anomalies"] if not a["resolved"]),
            "pending_outbox": 0,
            "audit_valid": True,
            "audit_entries": len(_state["audit"]),
        }
    return _request("GET", "/tableau-de-bord")


def confirm_field(dossier_id, field_name, user, new_value=None):
    if API_MODE == "mock":
        for f in _state["fields"]:
            if f["field"] == field_name:
                if new_value is not None:
                    f["value"] = new_value
                    _log("FIELD_CORRECTED", user, field_name)
                f["confirmed"] = True
                _log("FIELD_CONFIRMED", user, field_name)
        _refresh_doc_status()
        return {"field": field_name, "confirmed": True}

    body = {"user": user}
    if new_value is not None:
        body["new_value"] = new_value
    return _request("POST", f"/dossiers/{dossier_id}/champs/{field_name}/confirmer", json_body=body)


def confirm_all_fields(dossier_id, user):
    if API_MODE == "mock":
        for f in _state["fields"]:
            if f["status"] != "missing" and not f["confirmed"]:
                f["confirmed"] = True
                _log("FIELD_CONFIRMED", user, f["field"])
        _refresh_doc_status()
        return get_dossier(dossier_id)
    return _request("POST", f"/dossiers/{dossier_id}/confirmer", json_body={"user": user})


def resolve_anomaly(dossier_id, anomaly_id, user, justification):
    if API_MODE == "mock":
        if not justification.strip():
            raise ApiError(422, "Une justification est obligatoire.")
        for a in _state["anomalies"]:
            if a["id"] == anomaly_id:
                a["resolved"] = True
                a["resolution"] = justification
                _log("ANOMALY_RESOLVED", user, f"{anomaly_id}: {justification}")
        _refresh_doc_status()
        return {"id": anomaly_id, "resolved": True}

    return _request(
        "POST",
        f"/anomalies/{anomaly_id}/resoudre",
        json_body={"resolved_by": user, "justification": justification},
    )


def validate_invoice(dossier_id, user, role, version=None):
    if API_MODE == "mock":
        if role != "gerant":
            raise ApiError(403, "Seul le gérant peut valider.")
        if user == _state["initiator"]:
            raise ApiError(403, "Le validateur doit être différent de l'initiateur.")
        if _state["doc_status"] != "PRET_A_VALIDER":
            raise ApiError(422, "Le dossier n'est pas PRÊT_À_VALIDER.")
        _state["invoice_number"] = "FAC-2026-000001"
        _state["invoice_id"] = f"INV-{dossier_id}"
        _state["doc_status"] = "VALIDEE"
        _log("INVOICE_VALIDATED", user, _state["invoice_number"])
        return {"invoice_number": _state["invoice_number"]}

    if version is None:
        dossier = get_dossier(dossier_id)
        version = dossier["version"]
    return _request(
        "POST",
        f"/dossiers/{dossier_id}/valider",
        json_body={"validator_id": user, "validator_role": role, "version": version},
        headers={"Idempotency-Key": f"val-{dossier_id}-v{version}"},
    )


def simulate_concurrency(dossier_id, validator_id="USR-GER", validator_role="gerant", n_requests=20):
    if API_MODE == "mock":
        raise ApiError(501, "Disponible en mode live uniquement.")
    return _request(
        "POST",
        "/demo/simuler-concurrence",
        json_body={
            "dossier_id": dossier_id,
            "validator_id": validator_id,
            "validator_role": validator_role,
            "n_requests": n_requests,
        },
    )


def emit_invoice(invoice_id, channel, actor, offline=False, idempotency_key=None):
    if API_MODE == "mock":
        _state["doc_status"] = "EMISE"
        _log("INVOICE_EMITTED", actor, f"{channel} (simulé)")
        return {"status": "en_attente" if offline else "envoye", "channel": channel}
    key = idempotency_key or f"emit-{invoice_id}-{channel}-{uuid.uuid4().hex[:8]}"
    return _request(
        "POST",
        f"/factures/{invoice_id}/emettre",
        json_body={"channel": channel, "actor": actor, "offline": offline},
        headers={"Idempotency-Key": key},
    )


def get_outbox():
    if API_MODE == "mock":
        return []
    return _request("GET", "/outbox")


def sync_outbox(actor):
    if API_MODE == "mock":
        return {"synced_count": 0, "synced": []}
    return _request("POST", "/outbox/synchroniser", json_body={"actor": actor})


def add_payment(invoice_id, amount, mode, reference, entered_by, status="confirme", idempotency_key=None):
    if API_MODE == "mock":
        _state["balance"]["paid"] += amount
        _state["balance"]["balance"] -= amount
        _log("PAYMENT_ADDED", entered_by, f"{amount} FCFA ({reference})")
        return {"amount": amount, "mode": mode, "reference": f"FICTIF - {reference}"}
    key = idempotency_key or f"pay-{invoice_id}-{uuid.uuid4().hex[:12]}"
    return _request(
        "POST",
        f"/factures/{invoice_id}/reglements",
        json_body={
            "amount": int(amount),
            "mode": mode,
            "reference": reference,
            "entered_by": entered_by,
            "status": status,
        },
        headers={"Idempotency-Key": key},
    )


def add_credit(invoice_id, amount, reason, created_by, creator_role, idempotency_key=None):
    if API_MODE == "mock":
        if creator_role != "gerant":
            raise ApiError(403, "Seul un gérant peut créer un avoir.")
        _state["balance"]["credits"] += amount
        _state["balance"]["balance"] -= amount
        _log("CREDIT_CREATED", created_by, f"{amount} FCFA ({reason})")
        return {"amount": amount, "reason": reason}
    key = idempotency_key or f"crd-{invoice_id}-{uuid.uuid4().hex[:12]}"
    return _request(
        "POST",
        f"/factures/{invoice_id}/avoirs",
        json_body={
            "amount": int(amount),
            "reason": reason,
            "created_by": created_by,
            "creator_role": creator_role,
        },
        headers={"Idempotency-Key": key},
    )


if API_MODE == "mock":
    reset_demo()
