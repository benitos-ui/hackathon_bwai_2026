from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from app.workflow.service import WorkflowError, WorkflowService
from app.calcul.calculator import calculate_invoice
from app.calcul.references import load_catalogue, load_clients
from app.controles.anomalies import detect_anomalies


DATABASE = Path(__file__).resolve().parents[2] / "boutique_x.sqlite3"
service = WorkflowService(DATABASE)

app = FastAPI(title="Boutique X - API de facturation")


class LoginRequest(BaseModel):
    identifier: str
    password: str


class DossierRequest(BaseModel):
    dossier_id: str
    conversation_id: str
    created_by: str


class PrepareRequest(BaseModel):
    content: dict
    version: int


class ResolveRequest(BaseModel):
    resolved_by: str
    justification: str


class ValidateRequest(BaseModel):
    validator_id: str
    validator_role: str
    version: int


class PaymentRequest(BaseModel):
    amount: int = Field(ge=0)
    mode: str
    reference: str
    entered_by: str


class CalculationRequest(BaseModel):
    lines: list[dict]
    zone: str
    faithful_customer: bool = False
    first_order: bool = False
    promo_code: str | None = None
    delivery_failed: bool = False


class DossierControlRequest(BaseModel):
    client: str | None = None
    lines: list[dict] = Field(default_factory=list)
    conversation_has_multiple_clients: bool = False


def handle_error(error: WorkflowError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.detail)


@app.post("/auth/login")
def login(payload: LoginRequest):
    if payload.identifier not in {"USR-VEND", "USR-GER", "USR-AUD"}:
        raise HTTPException(status_code=401, detail="Authentification refusée")
    if payload.password != "demo":
        raise HTTPException(status_code=401, detail="Authentification refusée")
    role = {
        "USR-VEND": "vendeuse",
        "USR-GER": "gerant",
        "USR-AUD": "auditeur",
    }[payload.identifier]
    return {"identifier": payload.identifier, "role": role, "token": f"{role}-token"}


@app.post("/dossiers")
def create_dossier(payload: DossierRequest,
                   idempotency_key: str = Header(..., alias="Idempotency-Key")):
    try:
        return service.create_dossier(
            payload.dossier_id,
            payload.conversation_id,
            payload.created_by,
            idempotency_key,
        )
    except WorkflowError as error:
        raise handle_error(error)


@app.post("/dossiers/{dossier_id}/traiter")
def prepare_dossier(dossier_id: str, payload: PrepareRequest):
    try:
        return service.prepare_dossier(dossier_id, payload.content, payload.version)
    except WorkflowError as error:
        raise handle_error(error)


@app.post("/anomalies/{anomaly_id}/resoudre")
def resolve_anomaly(anomaly_id: str, payload: ResolveRequest):
    try:
        return service.resolve_anomaly(
            anomaly_id,
            payload.resolved_by,
            payload.justification,
        )
    except WorkflowError as error:
        raise handle_error(error)


@app.post("/dossiers/{dossier_id}/valider")
def validate_invoice(dossier_id: str, payload: ValidateRequest,
                     idempotency_key: str = Header(..., alias="Idempotency-Key")):
    del idempotency_key
    try:
        return service.validate_invoice(
            dossier_id,
            payload.validator_id,
            payload.validator_role,
            payload.version,
        )
    except WorkflowError as error:
        raise handle_error(error)


@app.post("/factures/{invoice_id}/reglements")
def add_payment(invoice_id: str, payload: PaymentRequest,
                idempotency_key: str = Header(..., alias="Idempotency-Key")):
    try:
        return service.add_payment(
            invoice_id,
            payload.amount,
            payload.mode,
            payload.reference,
            payload.entered_by,
            idempotency_key,
        )
    except WorkflowError as error:
        raise handle_error(error)


@app.get("/factures/{invoice_id}/solde")
def get_balance(invoice_id: str):
    try:
        return service.get_balance(invoice_id)
    except WorkflowError as error:
        raise handle_error(error)


@app.get("/audit/verifier")
def verify_audit():
    return service.verify_audit()


@app.get("/referentiels/catalogue")
def get_catalogue():
    return load_catalogue()


@app.get("/referentiels/clients")
def get_clients():
    return load_clients()


@app.post("/calcul")
def calculate(payload: CalculationRequest):
    try:
        return calculate_invoice(
            payload.lines,
            payload.zone,
            faithful_customer=payload.faithful_customer,
            first_order=payload.first_order,
            promo_code=payload.promo_code,
            delivery_failed=payload.delivery_failed,
        )
    except (KeyError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error))


@app.post("/controles/anomalies")
def control_dossier(payload: DossierControlRequest):
    return detect_anomalies(
        payload.model_dump(),
        load_catalogue(),
        load_clients(),
    )
