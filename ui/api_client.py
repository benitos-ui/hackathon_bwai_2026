"""Single access layer between the UI and the backend.

API_MODE=mock (default) uses in-memory data from mock_data.py.
API_MODE=live will call the FastAPI backend (to be filled once routes are ready).
The UI never computes amounts or permissions: it only displays what this module returns.
"""
import copy
import hashlib
import os

from ui import mock_data as md

API_MODE = os.getenv("API_MODE", "mock")
API_URL = os.getenv("API_URL", "http://localhost:8000")


class ApiError(Exception):
    """Business or permission error, mirrors the HTTP codes of the spec."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


# ---------------------------------------------------------------- mock state
_state = {}
_seen_hashes = {}


def _fresh_state():
    return {
        "dossier_id": "DOS-2026-0007",
        "initiator": None,
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
        "audit": [],
    }


def _log(action, user, detail=""):
    _state["audit"].append({"n": len(_state["audit"]) + 1, "action": action,
                            "user": user, "detail": detail})


def _refresh_doc_status():
    """Mock of the backend rule: status depends on anomalies and confirmations."""
    if _state["doc_status"] in ("VALIDEE", "EMISE"):
        return
    open_anomalies = any(not a["resolved"] for a in _state["anomalies"])
    all_confirmed = all(f["confirmed"] for f in _state["fields"]
                        if f["status"] != "missing")
    if open_anomalies:
        _state["doc_status"] = "A_REVOIR"
    elif all_confirmed:
        _state["doc_status"] = "PRET_A_VALIDER"
    else:
        _state["doc_status"] = "BROUILLON"


# ------------------------------------------------------------------ public API
def reset_demo():
    _state.clear()
    _state.update(_fresh_state())
    _seen_hashes.clear()


def import_conversation(raw_text, user):
    """Send the raw WhatsApp text. Same text twice returns the same dossier."""
    if API_MODE != "mock":
        raise NotImplementedError("live mode: POST /dossiers/import")
    if not raw_text.strip():
        raise ApiError(422, "Fichier vide ou mal formé.")
    digest = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    if digest in _seen_hashes:
        return {"dossier_id": _seen_hashes[digest], "duplicate": True}
    _state["initiator"] = user
    _seen_hashes[digest] = _state["dossier_id"]
    _log("IMPORT", user, f"sha256:{digest[:12]}")
    return {"dossier_id": _state["dossier_id"], "duplicate": False}


def get_dossier(dossier_id):
    return {"dossier_id": dossier_id, "doc_status": _state["doc_status"],
            "financial_status": _state["financial_status"],
            "invoice_number": _state["invoice_number"],
            "initiator": _state["initiator"]}


def get_messages(dossier_id):
    return _state["messages"]


def get_extractions(dossier_id):
    return _state["fields"]


def get_anomalies(dossier_id):
    return _state["anomalies"]


def get_delivery(dossier_id):
    return _state["delivery"]


def get_invoice(dossier_id):
    return {"lines": _state["lines"], "totals": _state["totals"]}


def get_balance(invoice_id):
    return _state["balance"]


def get_audit(dossier_id):
    return _state["audit"]


def confirm_field(dossier_id, field_name, user, new_value=None):
    for f in _state["fields"]:
        if f["field"] == field_name:
            if new_value is not None:
                f["value"] = new_value
                _log("FIELD_CORRECTED", user, field_name)
            f["confirmed"] = True
            _log("FIELD_CONFIRMED", user, field_name)
    _refresh_doc_status()


def resolve_anomaly(dossier_id, anomaly_id, user, justification):
    if not justification.strip():
        raise ApiError(422, "Une justification est obligatoire.")
    for a in _state["anomalies"]:
        if a["id"] == anomaly_id:
            a["resolved"] = True
            a["resolution"] = justification
            _log("ANOMALY_RESOLVED", user, f"{anomaly_id}: {justification}")
    _refresh_doc_status()


def validate_invoice(dossier_id, user, role):
    """Mock of the backend checks: role, four-eyes principle, status."""
    if role != "gerant":
        raise ApiError(403, "Seul le gérant peut valider.")
    if user == _state["initiator"]:
        raise ApiError(403, "Le validateur doit être différent de l'initiateur.")
    if _state["doc_status"] != "PRET_A_VALIDER":
        raise ApiError(422, "Le dossier n'est pas PRÊT_À_VALIDER.")
    _state["invoice_number"] = "FAC-2026-000001"
    _state["doc_status"] = "VALIDEE"
    _log("INVOICE_VALIDATED", user, _state["invoice_number"])
    return {"invoice_number": _state["invoice_number"]}


reset_demo()