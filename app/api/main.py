import tempfile
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.calcul.calculator import calculate_invoice
from app.calcul.references import get_config_hash, load_catalogue, load_clients, load_rules
from app.controles.anomalies import detect_anomalies
from app.pdf.invoice_pdf import generate_credit_pdf, generate_invoice_pdf
from app.workflow.service import WorkflowError, WorkflowService


DATABASE = Path(__file__).resolve().parents[2] / "boutique_x.sqlite3"
service = WorkflowService(DATABASE)

app = FastAPI(title="Boutique X - API de facturation", version="1.1.0")


class LoginRequest(BaseModel):
    identifier: str
    password: str


class DossierRequest(BaseModel):
    dossier_id: str
    conversation_id: str
    created_by: str


class ImportDossierRequest(BaseModel):
    raw_text: str
    created_by: str
    mode: str | None = None
    telephone: str | None = None


class PrepareRequest(BaseModel):
    content: dict
    version: int


class ConfirmFieldRequest(BaseModel):
    user: str
    new_value: str | int | float | None = None
    version: int | None = None


class ConfirmAllRequest(BaseModel):
    user: str
    version: int | None = None


class CancelDossierRequest(BaseModel):
    cancelled_by: str
    reason: str


class ResumeDossierRequest(BaseModel):
    actor: str = "USR-VEND"
    mode: str | None = None


class ResolveRequest(BaseModel):
    resolved_by: str
    justification: str


class ValidateRequest(BaseModel):
    validator_id: str
    validator_role: str
    version: int


class EmitRequest(BaseModel):
    channel: str = "whatsapp"
    actor: str
    offline: bool = False


class SyncOutboxRequest(BaseModel):
    actor: str = "USR-VEND"


class PaymentRequest(BaseModel):
    amount: int = Field(ge=0)
    mode: str
    reference: str
    entered_by: str
    status: str = "confirme"


class CreditRequest(BaseModel):
    amount: int = Field(gt=0)
    reason: str
    created_by: str
    creator_role: str = "gerant"
    lines: list[dict] = Field(default_factory=list)


class RefundRequest(BaseModel):
    amount: int = Field(gt=0)
    reason: str
    created_by: str
    creator_role: str = "gerant"
    payment_id: str | None = None
    credit_id: str | None = None
    status: str = "confirme"


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


class SimulateInterruptionRequest(BaseModel):
    raw_text: str
    created_by: str = "USR-VEND"
    stop_after_step: str = "EXTRAIT"


class SimulateConcurrencyRequest(BaseModel):
    dossier_id: str
    validator_id: str = "USR-GER"
    validator_role: str = "gerant"
    n_requests: int = Field(default=20, ge=2, le=50)


def handle_error(error: WorkflowError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.detail)


# ----------------------------------------------------------------------- Auth
@app.post("/auth/login")
def login(payload: LoginRequest):
    try:
        return service.authenticate(payload.identifier, payload.password)
    except WorkflowError as error:
        raise handle_error(error)


# ------------------------------------------------------------------- Dossiers
@app.post("/dossiers/import")
@app.post("/conversations")
def import_dossier(
    payload: ImportDossierRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    try:
        return service.import_dossier(
            payload.raw_text,
            payload.created_by,
            idempotency_key,
            mode=payload.mode,
            telephone=payload.telephone,
        )
    except WorkflowError as error:
        raise handle_error(error)


@app.post("/dossiers")
def create_dossier(
    payload: DossierRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    try:
        return service.create_dossier(
            payload.dossier_id,
            payload.conversation_id,
            payload.created_by,
            idempotency_key,
        )
    except WorkflowError as error:
        raise handle_error(error)


@app.get("/dossiers")
def list_dossiers():
    return service.list_dossiers()


@app.get("/dossiers/{dossier_id}")
def get_dossier(dossier_id: str):
    try:
        return service.get_dossier(dossier_id)
    except WorkflowError as error:
        raise handle_error(error)


@app.get("/dossiers/{dossier_id}/messages")
def get_messages(dossier_id: str):
    try:
        return service.get_messages(dossier_id)
    except WorkflowError as error:
        raise handle_error(error)


@app.get("/dossiers/{dossier_id}/extractions")
def get_extractions(dossier_id: str):
    try:
        return service.get_extractions(dossier_id)
    except WorkflowError as error:
        raise handle_error(error)


@app.get("/dossiers/{dossier_id}/anomalies")
def get_anomalies(dossier_id: str):
    try:
        return service.get_anomalies(dossier_id)
    except WorkflowError as error:
        raise handle_error(error)


@app.get("/dossiers/{dossier_id}/livraison")
def get_delivery(dossier_id: str):
    try:
        return service.get_delivery(dossier_id)
    except WorkflowError as error:
        raise handle_error(error)


@app.get("/dossiers/{dossier_id}/facture")
def get_dossier_invoice(dossier_id: str):
    try:
        return service.get_invoice_view(dossier_id)
    except WorkflowError as error:
        raise handle_error(error)


@app.get("/dossiers/{dossier_id}/brouillon.pdf")
def get_draft_pdf(dossier_id: str):
    try:
        dossier = service.get_dossier(dossier_id)
        view = service.get_invoice_view(dossier_id)
    except WorkflowError as error:
        raise handle_error(error)

    calc = view.get("calculation")
    if not calc:
        raise HTTPException(status_code=422, detail="Aucun calcul disponible pour ce dossier.")

    is_validated = dossier["doc_status"] in ("VALIDEE", "EMISE")
    status_label = "FACTURE" if is_validated else "BROUILLON"
    inv_num = dossier["invoice_number"] or "À attribuer"
    payments_summary = None
    if dossier.get("invoice_id"):
        payments_summary = service.get_balance(dossier["invoice_id"])

    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        generate_invoice_pdf(
            tmp.name,
            calc,
            status=status_label,
            invoice_number=inv_num,
            dossier_reference=dossier_id,
            client=view.get("client"),
            vendor=view.get("vendor"),
            payments_summary=payments_summary,
            issued_at=view.get("validated_at"),
        )
        pdf_bytes = Path(tmp.name).read_bytes()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="brouillon_{dossier_id}.pdf"',
        },
    )


@app.post("/dossiers/{dossier_id}/champs/{field}/confirmer")
@app.patch("/dossiers/{dossier_id}/champs/{field}")
def confirm_field(dossier_id: str, field: str, payload: ConfirmFieldRequest):
    try:
        return service.confirm_field(
            dossier_id,
            field,
            payload.user,
            new_value=payload.new_value,
            version=payload.version,
        )
    except WorkflowError as error:
        raise handle_error(error)


@app.post("/dossiers/{dossier_id}/confirmer")
def confirm_all_fields(dossier_id: str, payload: ConfirmAllRequest):
    try:
        return service.confirm_all_fields(dossier_id, payload.user, version=payload.version)
    except WorkflowError as error:
        raise handle_error(error)


@app.post("/dossiers/{dossier_id}/traiter")
def prepare_dossier(dossier_id: str, payload: PrepareRequest):
    try:
        return service.prepare_dossier(dossier_id, payload.content, payload.version)
    except WorkflowError as error:
        raise handle_error(error)


@app.post("/dossiers/{dossier_id}/reprendre")
def resume_dossier(dossier_id: str, payload: ResumeDossierRequest):
    try:
        return service.resume_dossier(dossier_id, payload.actor, mode=payload.mode)
    except WorkflowError as error:
        raise handle_error(error)


@app.post("/dossiers/{dossier_id}/annuler")
def cancel_dossier(dossier_id: str, payload: CancelDossierRequest):
    try:
        return service.cancel_dossier(dossier_id, payload.cancelled_by, payload.reason)
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
def validate_invoice(
    dossier_id: str,
    payload: ValidateRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
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


# ------------------------------------------------------------------- Factures
@app.get("/factures/{invoice_id}")
def get_invoice_detail(invoice_id: str):
    try:
        return service.get_invoice_detail(invoice_id)
    except WorkflowError as error:
        raise handle_error(error)


@app.get("/factures/{invoice_id}/pdf")
def get_invoice_pdf(invoice_id: str):
    try:
        detail = service.get_invoice_detail(invoice_id)
    except WorkflowError as error:
        raise handle_error(error)

    calc = detail.get("calculation")
    if not calc:
        raise HTTPException(status_code=422, detail="Contenu figé incomplet pour la génération PDF.")

    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        generate_invoice_pdf(
            tmp.name,
            calc,
            status="FACTURE",
            invoice_number=detail["invoice_number"],
            dossier_reference=detail["dossier_id"],
            client=detail.get("client"),
            vendor=detail.get("vendor"),
            payments_summary=detail.get("balance"),
            issued_at=detail.get("validated_at"),
        )
        pdf_bytes = Path(tmp.name).read_bytes()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{detail["invoice_number"]}.pdf"',
            "X-Content-Hash": detail["content_hash"],
        },
    )


@app.post("/factures/{invoice_id}/emettre")
def emit_invoice(
    invoice_id: str,
    payload: EmitRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    try:
        return service.emit_invoice(
            invoice_id,
            payload.channel,
            payload.actor,
            idempotency_key,
            offline=payload.offline,
        )
    except WorkflowError as error:
        raise handle_error(error)


@app.post("/factures/{invoice_id}/reglements")
def add_payment(
    invoice_id: str,
    payload: PaymentRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    try:
        return service.add_payment(
            invoice_id,
            payload.amount,
            payload.mode,
            payload.reference,
            payload.entered_by,
            idempotency_key,
            status=payload.status,
        )
    except WorkflowError as error:
        raise handle_error(error)


@app.post("/factures/{invoice_id}/avoirs")
def add_credit(
    invoice_id: str,
    payload: CreditRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    try:
        return service.add_credit(
            invoice_id,
            payload.amount,
            payload.reason,
            payload.created_by,
            payload.creator_role,
            idempotency_key,
            lines=payload.lines,
        )
    except WorkflowError as error:
        raise handle_error(error)


@app.post("/factures/{invoice_id}/remboursements")
def add_refund(
    invoice_id: str,
    payload: RefundRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    try:
        return service.add_refund(
            invoice_id,
            payload.amount,
            payload.reason,
            payload.created_by,
            payload.creator_role,
            idempotency_key,
            payment_id=payload.payment_id,
            credit_id=payload.credit_id,
            status=payload.status,
        )
    except WorkflowError as error:
        raise handle_error(error)


@app.get("/factures/{invoice_id}/solde")
def get_balance(invoice_id: str):
    try:
        return service.get_balance(invoice_id)
    except WorkflowError as error:
        raise handle_error(error)


@app.get("/avoirs/{credit_id}/pdf")
def get_credit_pdf(credit_id: str):
    try:
        credit, invoice = service.get_credit_with_invoice(credit_id)
    except WorkflowError as error:
        raise handle_error(error)

    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
        generate_credit_pdf(tmp.name, credit, invoice)
        pdf_bytes = Path(tmp.name).read_bytes()

    filename = credit.get("number") or credit["id"]
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'},
    )


# ----------------------------------------------------------- Outbox & Audit
@app.get("/outbox")
def get_outbox():
    return service.get_outbox()


@app.post("/outbox/synchroniser")
def sync_outbox(payload: SyncOutboxRequest):
    try:
        return service.sync_outbox(payload.actor)
    except WorkflowError as error:
        raise handle_error(error)


@app.get("/audit")
def list_audit(dossier_id: str | None = Query(default=None)):
    return service.get_audit(dossier_id=dossier_id)


@app.get("/dossiers/{dossier_id}/audit")
def get_dossier_audit(dossier_id: str):
    try:
        service.get_dossier(dossier_id)
    except WorkflowError as error:
        raise handle_error(error)
    return service.get_audit(dossier_id=dossier_id)


@app.get("/audit/verifier")
def verify_audit():
    return service.verify_audit()


@app.get("/tableau-de-bord")
def get_dashboard():
    return service.get_dashboard()


# ------------------------------------------------------- Référentiels & Calcul
@app.get("/referentiels/catalogue")
def get_catalogue():
    return load_catalogue()


@app.get("/referentiels/clients")
def get_clients():
    return load_clients()


@app.get("/referentiels/regles")
def get_rules():
    return {"rules": load_rules(), "config_hash": get_config_hash()}


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


# ----------------------------------------------------------------------- Demo
@app.post("/demo/reinitialiser")
def reset_demo():
    return service.reset_demo()


@app.post("/demo/simuler-interruption")
def simulate_interruption(
    payload: SimulateInterruptionRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    try:
        return service.import_dossier(
            payload.raw_text,
            payload.created_by,
            idempotency_key,
            stop_after_step=payload.stop_after_step,
        )
    except WorkflowError as error:
        raise handle_error(error)


@app.post("/demo/simuler-concurrence")
def simulate_concurrency(payload: SimulateConcurrencyRequest):
    try:
        return service.simulate_concurrency(
            payload.dossier_id,
            payload.validator_id,
            payload.validator_role,
            payload.n_requests,
        )
    except WorkflowError as error:
        raise handle_error(error)
