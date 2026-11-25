import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.db.database import connect


class WorkflowError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def audit_hash(previous: str, actor: str, action: str, object_name: str,
               before: Any, after: Any, timestamp: str) -> str:
    payload = json.dumps({
        "previous": previous,
        "actor": actor,
        "action": action,
        "object": object_name,
        "before": before,
        "after": after,
        "timestamp": timestamp,
    }, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class WorkflowService:
    def __init__(self, database: str | Path):
        self.database = str(database)
        with connect(self.database) as connection:
            connection.executescript("")

    def _connection(self) -> sqlite3.Connection:
        return connect(self.database)

    def create_dossier(self, dossier_id: str, conversation_id: str,
                       created_by: str, idempotency_key: str) -> dict:
        now = utc_now()
        with self._connection() as connection:
            existing = connection.execute(
                "SELECT * FROM dossiers WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing:
                return dict(existing)

            connection.execute(
                """INSERT INTO dossiers
                   (id, conversation_id, idempotency_key, status, version,
                    created_by, content, created_at, updated_at)
                   VALUES (?, ?, ?, 'BROUILLON', 1, ?, '{}', ?, ?)""",
                (dossier_id, conversation_id, idempotency_key, created_by, now, now),
            )
            result = connection.execute(
                "SELECT * FROM dossiers WHERE id = ?", (dossier_id,)
            ).fetchone()
            return dict(result)

    def prepare_dossier(self, dossier_id: str, content: dict,
                        version: int) -> dict:
        now = utc_now()
        with self._connection() as connection:
            dossier = connection.execute(
                "SELECT * FROM dossiers WHERE id = ?", (dossier_id,)
            ).fetchone()
            if dossier is None:
                raise WorkflowError(404, "Dossier inconnu")
            if dossier["version"] != version:
                raise WorkflowError(409, "Version du dossier périmée")

            open_anomalies = connection.execute(
                "SELECT COUNT(*) FROM anomalies WHERE dossier_id = ? AND status = 'ouverte'",
                (dossier_id,),
            ).fetchone()[0]
            status = "PRÊT_À_VALIDER" if open_anomalies == 0 else "À_REVOIR"
            connection.execute(
                """UPDATE dossiers
                   SET content = ?, status = ?, version = version + 1, updated_at = ?
                   WHERE id = ?""",
                (json.dumps(content, ensure_ascii=False), status, now, dossier_id),
            )
            result = connection.execute(
                "SELECT * FROM dossiers WHERE id = ?", (dossier_id,)
            ).fetchone()
            return dict(result)

    def resolve_anomaly(self, anomaly_id: str, resolved_by: str,
                        justification: str) -> dict:
        if not justification.strip():
            raise WorkflowError(422, "Une justification est obligatoire")

        now = utc_now()
        with self._connection() as connection:
            anomaly = connection.execute(
                "SELECT * FROM anomalies WHERE id = ?", (anomaly_id,)
            ).fetchone()
            if anomaly is None:
                raise WorkflowError(404, "Anomalie inconnue")

            connection.execute(
                """UPDATE anomalies
                   SET status = 'résolue', justification = ?, resolved_by = ?, resolved_at = ?
                   WHERE id = ?""",
                (justification, resolved_by, now, anomaly_id),
            )
            return dict(connection.execute(
                "SELECT * FROM anomalies WHERE id = ?", (anomaly_id,)
            ).fetchone())

    def validate_invoice(self, dossier_id: str, validator_id: str,
                         validator_role: str, version: int) -> dict:
        if validator_role != "gerant":
            raise WorkflowError(403, "Seul un gérant peut valider une facture")

        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")

            dossier = connection.execute(
                "SELECT * FROM dossiers WHERE id = ?", (dossier_id,)
            ).fetchone()
            if dossier is None:
                raise WorkflowError(404, "Dossier inconnu")

            existing = connection.execute(
                "SELECT * FROM invoices WHERE dossier_id = ?", (dossier_id,)
            ).fetchone()
            if existing:
                return dict(existing)

            if dossier["version"] != version:
                raise WorkflowError(409, "Version du dossier périmée")
            if dossier["status"] != "PRÊT_À_VALIDER":
                raise WorkflowError(422, "Le dossier n'est pas prêt à être validé")

            open_anomalies = connection.execute(
                "SELECT COUNT(*) FROM anomalies WHERE dossier_id = ? AND status = 'ouverte'",
                (dossier_id,),
            ).fetchone()[0]
            if open_anomalies:
                raise WorkflowError(422, "Une anomalie bloquante reste ouverte")
            if validator_id == dossier["created_by"]:
                raise WorkflowError(403, "Le validateur doit être différent de l'initiateur")

            counter = connection.execute(
                "UPDATE counters SET value = value + 1 WHERE name = 'invoice' "
                "RETURNING value"
            ).fetchone()
            number = f"FAC-2026-{counter['value']:06d}"

            content = json.loads(dossier["content"])
            total_ttc = int(content.get("total_ttc", 0))
            invoice_id = f"INV-{dossier_id}"
            now = utc_now()
            invoice_content = json.dumps(content, sort_keys=True, ensure_ascii=False)
            content_hash = hashlib.sha256(invoice_content.encode("utf-8")).hexdigest()

            connection.execute(
                """INSERT INTO invoices
                   (id, dossier_id, number, total_ttc, content, content_hash,
                    validated_by, validated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (invoice_id, dossier_id, number, total_ttc, invoice_content,
                 content_hash, validator_id, now),
            )
            for position, line in enumerate(content.get("lines", []), start=1):
                connection.execute(
                    """INSERT INTO invoice_lines
                       (id, invoice_id, position, product_id, description, variant,
                        quantity, unit_price_ht, amount_ht)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        f"{invoice_id}-L{position}",
                        invoice_id,
                        position,
                        line.get("product_id"),
                        line["description"],
                        line.get("variant"),
                        int(line["quantity"]),
                        int(line["unit_price_ht"]),
                        int(line["amount_ht"]),
                    ),
                )

            connection.execute(
                "UPDATE dossiers SET status = 'VALIDÉE', version = version + 1, updated_at = ? "
                "WHERE id = ?",
                (now, dossier_id),
            )

            previous_row = connection.execute(
                "SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1"
            ).fetchone()
            previous_hash = previous_row["hash"] if previous_row else "0" * 64
            hash_value = audit_hash(
                previous_hash, validator_id, "VALIDER_FACTURE", dossier_id,
                {"status": "PRÊT_À_VALIDER"}, {"status": "VALIDÉE", "number": number},
                now,
            )
            connection.execute(
                """INSERT INTO audit_log
                   (timestamp, actor, action, object, before, after,
                    previous_hash, hash)
                   VALUES (?, ?, 'VALIDER_FACTURE', ?, ?, ?, ?, ?)""",
                (now, validator_id, dossier_id,
                 json.dumps({"status": "PRÊT_À_VALIDER"}),
                 json.dumps({"status": "VALIDÉE", "number": number}),
                 previous_hash, hash_value),
            )
            connection.commit()

            result = connection.execute(
                "SELECT * FROM invoices WHERE id = ?", (invoice_id,)
            ).fetchone()
            return dict(result)

    def add_payment(self, invoice_id: str, amount: int, mode: str,
                    reference: str, entered_by: str,
                    idempotency_key: str) -> dict:
        if amount < 0:
            raise WorkflowError(422, "Le montant ne peut pas être négatif")
        now = utc_now()
        with self._connection() as connection:
            existing = connection.execute(
                "SELECT * FROM payments WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing:
                return dict(existing)

            invoice = connection.execute(
                "SELECT * FROM invoices WHERE id = ?", (invoice_id,)
            ).fetchone()
            if invoice is None:
                raise WorkflowError(404, "Facture inconnue")

            payment_id = f"PAY-{idempotency_key}"
            connection.execute(
                """INSERT INTO payments
                   (id, invoice_id, amount, mode, reference, status,
                    paid_at, entered_by, idempotency_key)
                   VALUES (?, ?, ?, ?, ?, 'confirme', ?, ?, ?)""",
                (payment_id, invoice_id, amount, mode,
                 f"FICTIF - {reference}", now, entered_by, idempotency_key),
            )
            result = connection.execute(
                "SELECT * FROM payments WHERE id = ?", (payment_id,)
            ).fetchone()
            connection.commit()
            return dict(result)

    def get_balance(self, invoice_id: str) -> dict:
        with self._connection() as connection:
            invoice = connection.execute(
                "SELECT * FROM invoices WHERE id = ?", (invoice_id,)
            ).fetchone()
            if invoice is None:
                raise WorkflowError(404, "Facture inconnue")
            total_paid = connection.execute(
                """SELECT COALESCE(SUM(amount), 0) FROM payments
                   WHERE invoice_id = ? AND status = 'confirme'""",
                (invoice_id,),
            ).fetchone()[0]
            total_refunds = connection.execute(
                """SELECT COALESCE(SUM(amount), 0) FROM credits
                   WHERE invoice_id = ?""",
                (invoice_id,),
            ).fetchone()[0]
            net_due = invoice["total_ttc"] - total_refunds
            balance = net_due - total_paid
            if balance > 0:
                financial_status = "PARTIELLEMENT_RÉGLÉE" if total_paid else "NON_RÉGLÉE"
            elif balance == 0:
                financial_status = "RÉGLÉE"
            else:
                financial_status = "TROP_PERÇU"
            return {
                "invoice_id": invoice_id,
                "total_ttc": invoice["total_ttc"],
                "net_due": net_due,
                "confirmed_payments": total_paid,
                "refund_credits": total_refunds,
                "balance": balance,
                "financial_status": financial_status,
            }

    def verify_audit(self) -> dict:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM audit_log ORDER BY id"
            ).fetchall()

        previous = "0" * 64
        for row in rows:
            if row["previous_hash"] != previous:
                return {"valid": False, "entries": len(rows), "broken_at": row["id"]}
            expected = audit_hash(
                row["previous_hash"], row["actor"], row["action"], row["object"],
                json.loads(row["before"]) if row["before"] else None,
                json.loads(row["after"]) if row["after"] else None,
                row["timestamp"],
            )
            if expected != row["hash"]:
                return {"valid": False, "entries": len(rows), "broken_at": row["id"]}
            previous = row["hash"]
        return {"valid": True, "entries": len(rows), "broken_at": None}
