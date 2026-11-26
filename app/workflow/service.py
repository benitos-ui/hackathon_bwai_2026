import concurrent.futures
import hashlib
import json
import logging
import os
import sqlite3
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai.extraction import extraire
from ai.normalisation import normaliser_dossier
from ai.parseur import FormatInvalide, analyser
from app.calcul.calculator import calculate_invoice
from app.calcul.references import get_config_hash, load_catalogue, load_clients, load_rules
from app.controles.anomalies import detect_anomalies
from app.db.database import connect, verify_password

log = logging.getLogger("app.workflow")

MAX_IMPORT_BYTES = 512 * 1024  # 512 KB limit (Addendum §12)
PIPELINE_STEPS = (
    "IMPORTE",
    "ANALYSE",
    "EXTRAIT",
    "NORMALISE",
    "CONTROLE",
    "CALCULE",
    "BROUILLON",
)


class WorkflowError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def strip_accents_code(value: str | None) -> str:
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).upper()


def audit_hash(
    previous: str,
    actor: str,
    action: str,
    object_name: str,
    before: Any,
    after: Any,
    timestamp: str,
) -> str:
    payload = json.dumps(
        {
            "previous": previous,
            "actor": actor,
            "action": action,
            "object": object_name,
            "before": before,
            "after": after,
            "timestamp": timestamp,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _extract_time_hm(ts: str | None) -> str:
    if not ts:
        return ""
    if "T" in ts:
        return ts.split("T", 1)[1][:5]
    return ts[:5]


def _translate_ai_status(champ: dict) -> str:
    if champ.get("ambiguite_produit"):
        return "ambiguous"
    statut = champ.get("statut")
    couleur = champ.get("couleur")
    if statut == "a_renseigner" or champ.get("valeur") is None:
        return "missing"
    if couleur == "vert":
        return "extracted"
    return "needs_review"


def _source_from_champ(champ: dict | None, messages_by_id: dict[str, str]) -> tuple[str | None, str | None, int | None, int | None]:
    if not champ:
        return None, None, None, None
    src = champ.get("source")
    if not src or not src.get("message_id"):
        return None, None, None, None
    mid = src["message_id"]
    start = src.get("debut")
    end = src.get("fin")
    msg_text = messages_by_id.get(mid, "")
    src_text = None
    if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(msg_text):
        src_text = msg_text[start:end]
    return mid, src_text, start, end


def _discount_label(calc: dict) -> str:
    name = calc.get("discount_name")
    if not name or not calc.get("discount_amount"):
        return "Remise (aucune)"
    pct = calc.get("discount_percent")
    if name == "fidélité":
        return f"Remise fidélité {pct or 5} %"
    if name == "quantité":
        return f"Remise quantité {pct or 10} %"
    return f"Remise {name} {pct or 10} %"


def _format_totals(calc: dict) -> dict:
    return {
        "subtotal": int(calc["subtotal_articles"]),
        "discount_label": _discount_label(calc),
        "discount": int(calc["discount_amount"]),
        "base_after_discount": int(calc["articles_base"]),
        "delivery": int(calc["delivery_ht"]),
        "base_ht": int(calc["base_ht"]),
        "vat_rate": int(calc["vat_rate"]),
        "vat": int(calc["vat_amount"]),
        "total_ttc": int(calc["total_ttc"]),
    }


def _format_invoice_lines(calc: dict) -> list[dict]:
    out = []
    for line in calc.get("lines", []):
        label = line["description"]
        if line.get("variant"):
            label = f"{label}, taille {line['variant']}"
        out.append({
            "product_id": line.get("product_id"),
            "label": label,
            "description": line["description"],
            "variant": line.get("variant"),
            "qty": int(line["quantity"]),
            "unit": int(line["unit_price_ht"]),
            "amount": int(line["amount_ht"]),
        })
    return out


class WorkflowService:
    def __init__(self, database: str | Path):
        self.database = str(database)
        with connect(self.database) as connection:
            connection.executescript("")

    def _connection(self) -> sqlite3.Connection:
        return connect(self.database)

    def _append_audit(
        self,
        connection: sqlite3.Connection,
        actor: str,
        action: str,
        object_name: str,
        before: Any,
        after: Any,
        timestamp: str | None = None,
    ) -> dict:
        ts = timestamp or utc_now()
        previous_row = connection.execute(
            "SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        previous_hash = previous_row["hash"] if previous_row else "0" * 64
        hash_value = audit_hash(previous_hash, actor, action, object_name, before, after, ts)
        connection.execute(
            """INSERT INTO audit_log
               (timestamp, actor, action, object, before, after, previous_hash, hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ts,
                actor,
                action,
                object_name,
                json.dumps(before, ensure_ascii=False) if before is not None else None,
                json.dumps(after, ensure_ascii=False) if after is not None else None,
                previous_hash,
                hash_value,
            ),
        )
        return {"timestamp": ts, "hash": hash_value, "previous_hash": previous_hash}

    def _user_role(self, connection: sqlite3.Connection, user_id: str) -> str | None:
        row = connection.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
        return row["role"] if row else None

    def _require_role(
        self,
        connection: sqlite3.Connection,
        user_id: str,
        allowed_roles: set[str],
        error_msg: str,
    ) -> str:
        role = self._user_role(connection, user_id)
        if role is None:
            raise WorkflowError(401, f"Utilisateur inconnu : {user_id}")
        if role not in allowed_roles:
            raise WorkflowError(403, error_msg)
        return role

    def authenticate(self, identifier: str, password: str) -> dict:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT id, name, role, password_hash FROM users WHERE id = ?",
                (identifier,),
            ).fetchone()
        if row is None or not verify_password(password, row["password_hash"]):
            raise WorkflowError(401, "Authentification refusée")
        return {
            "identifier": row["id"],
            "name": row["name"],
            "role": row["role"],
            "token": f"{row['role']}-token",
        }

    def _step_done(self, connection: sqlite3.Connection, dossier_id: str, step: str) -> bool:
        row = connection.execute(
            "SELECT status FROM processing_steps WHERE dossier_id = ? AND step = ?",
            (dossier_id, step),
        ).fetchone()
        return row is not None and row["status"] == "terminee"

    def _mark_step_done(
        self, connection: sqlite3.Connection, dossier_id: str, step: str, now: str | None = None
    ) -> None:
        connection.execute(
            """INSERT OR REPLACE INTO processing_steps (dossier_id, step, status, completed_at)
               VALUES (?, ?, 'terminee', ?)""",
            (dossier_id, step, now or utc_now()),
        )

    def _compute_doc_status(self, connection: sqlite3.Connection, dossier_id: str, current_status: str) -> str:
        norm = strip_accents_code(current_status)
        if norm in ("VALIDEE", "EMISE", "ANNULE"):
            return current_status

        open_anomalies = connection.execute(
            "SELECT COUNT(*) FROM anomalies WHERE dossier_id = ? AND status = 'ouverte'",
            (dossier_id,),
        ).fetchone()[0]
        if open_anomalies > 0:
            return "À_REVOIR"

        fields = connection.execute(
            "SELECT status, confirmed FROM extracted_fields WHERE dossier_id = ?",
            (dossier_id,),
        ).fetchall()
        if not fields:
            return "PRÊT_À_VALIDER"

        required = [f for f in fields if f["status"] != "missing"]
        if required and all(int(f["confirmed"]) == 1 for f in required):
            return "PRÊT_À_VALIDER"
        return "BROUILLON"

    def _clients_for_parser(self) -> list[dict]:
        clients = load_clients()
        return [
            {
                "identifiant": cid,
                "id": cid,
                "nom": info["name"],
                "name": info["name"],
                "telephone": info["phone"],
                "phone": info["phone"],
                "zone": info["zone"],
                "fidele": "oui" if info["faithful"] else "non",
            }
            for cid, info in clients.items()
        ]

    def _is_first_order(self, connection: sqlite3.Connection, client_id: str | None) -> bool:
        if not client_id:
            return True
        rows = connection.execute("SELECT content FROM invoices").fetchall()
        for row in rows:
            try:
                content = json.loads(row["content"])
            except json.JSONDecodeError:
                continue
            snap = content.get("client_snapshot") or content.get("client") or {}
            if snap.get("id") == client_id:
                return False
        return True

    def _build_extracted_fields(
        self,
        messages: list[dict],
        norm: dict,
        clients_ref: dict,
    ) -> list[dict]:
        messages_by_id = {m["message_id"]: m["texte"] for m in messages}
        first_client_msg = next((m["message_id"] for m in messages if m.get("role") == "client"), None)
        champs_by_id = {c["id"]: c for c in norm.get("champs", []) if c.get("id")}
        model_version = next(
            (c.get("version_modele") for c in norm.get("champs", []) if c.get("version_modele")),
            "baseline-1.0",
        )

        rows: list[dict] = []
        used_champ_ids: set[str] = set()

        # 1. Client field
        client = norm.get("client")
        if client and client.get("id"):
            conf = float(client.get("confiance", 0.90))
            couleur = "vert" if conf >= 0.90 else ("orange" if conf >= 0.60 else "rouge")
            rows.append({
                "field_name": "client",
                "raw_value": client.get("nom"),
                "normalized_value": f"{client['id']} ({client['nom']})",
                "ref": client["id"],
                "message_id": first_client_msg,
                "source_text": None,
                "start_pos": None,
                "end_pos": None,
                "confidence": conf,
                "couleur": couleur,
                "origin": "referentiel",
                "status": "extracted" if couleur == "vert" else "needs_review",
                "model_version": model_version,
            })
        else:
            rows.append({
                "field_name": "client",
                "raw_value": None,
                "normalized_value": None,
                "ref": None,
                "message_id": first_client_msg,
                "source_text": None,
                "start_pos": None,
                "end_pos": None,
                "confidence": 0.0,
                "couleur": "rouge",
                "origin": "conversation",
                "status": "missing",
                "model_version": model_version,
            })

        # 2. Assembled product lines
        for idx, ligne in enumerate(norm.get("lignes", []), start=1):
            line_champs = [champs_by_id[cid] for cid in ligne.get("champs_ids", []) if cid in champs_by_id]
            used_champ_ids.update(ligne.get("champs_ids", []))

            prod_c = next((c for c in line_champs if c["nom"] == "produit"), None)
            mid, stxt, sp, ep = _source_from_champ(prod_c, messages_by_id)
            rows.append({
                "field_name": f"produit_{idx}",
                "raw_value": (prod_c or {}).get("valeur_brute") or (ligne.get("mentions_brutes") or [None])[0],
                "normalized_value": ligne["produit"],
                "ref": ligne["ref"],
                "message_id": mid,
                "source_text": stxt,
                "start_pos": sp,
                "end_pos": ep,
                "confidence": float((prod_c or {}).get("confiance", 0.75)),
                "couleur": (prod_c or {}).get("couleur", "orange"),
                "origin": "conversation",
                "status": _translate_ai_status(prod_c) if prod_c else "needs_review",
                "model_version": (prod_c or {}).get("version_modele", model_version),
            })

            if ligne.get("quantite_commandee") is not None:
                qc = next((c for c in line_champs if c["nom"] == "quantite_commandee"), None)
                mid, stxt, sp, ep = _source_from_champ(qc, messages_by_id)
                rows.append({
                    "field_name": f"quantite_commandee_{idx}",
                    "raw_value": (qc or {}).get("valeur_brute"),
                    "normalized_value": str(ligne["quantite_commandee"]),
                    "ref": ligne["ref"],
                    "message_id": mid,
                    "source_text": stxt,
                    "start_pos": sp,
                    "end_pos": ep,
                    "confidence": float((qc or {}).get("confiance", 0.75)),
                    "couleur": (qc or {}).get("couleur", "orange"),
                    "origin": "conversation",
                    "status": _translate_ai_status(qc) if qc else "needs_review",
                    "model_version": (qc or {}).get("version_modele", model_version),
                })

            vars_cmd = (ligne.get("variantes") or {}).get("commandees") or []
            if vars_cmd:
                vc = next((c for c in line_champs if c["nom"] == "variante"), None)
                mid, stxt, sp, ep = _source_from_champ(vc, messages_by_id)
                rows.append({
                    "field_name": f"variante_{idx}",
                    "raw_value": ", ".join(vars_cmd),
                    "normalized_value": ", ".join(vars_cmd),
                    "ref": ligne["ref"],
                    "message_id": mid,
                    "source_text": stxt,
                    "start_pos": sp,
                    "end_pos": ep,
                    "confidence": float((vc or {}).get("confiance", 0.75)),
                    "couleur": (vc or {}).get("couleur", "orange"),
                    "origin": "conversation",
                    "status": _translate_ai_status(vc) if vc else "needs_review",
                    "model_version": (vc or {}).get("version_modele", model_version),
                })

            if ligne.get("quantite_livree") is not None:
                ql = next((c for c in line_champs if c["nom"] == "quantite_livree"), None)
                mid, stxt, sp, ep = _source_from_champ(ql, messages_by_id)
                rows.append({
                    "field_name": f"quantite_livree_{idx}",
                    "raw_value": (ql or {}).get("valeur_brute"),
                    "normalized_value": str(ligne["quantite_livree"]),
                    "ref": ligne["ref"],
                    "message_id": mid,
                    "source_text": stxt,
                    "start_pos": sp,
                    "end_pos": ep,
                    "confidence": float((ql or {}).get("confiance", 0.75)),
                    "couleur": (ql or {}).get("couleur", "orange"),
                    "origin": "conversation",
                    "status": _translate_ai_status(ql) if ql else "needs_review",
                    "model_version": (ql or {}).get("version_modele", model_version),
                })

            if ligne.get("prix_cite") is not None:
                pc = next((c for c in line_champs if c["nom"] == "prix_cite"), None)
                mid, stxt, sp, ep = _source_from_champ(pc, messages_by_id)
                rows.append({
                    "field_name": f"prix_cite_{idx}",
                    "raw_value": (pc or {}).get("valeur_brute"),
                    "normalized_value": str(ligne["prix_cite"]),
                    "ref": ligne["ref"],
                    "message_id": mid,
                    "source_text": stxt,
                    "start_pos": sp,
                    "end_pos": ep,
                    "confidence": float((pc or {}).get("confiance", 0.75)),
                    "couleur": (pc or {}).get("couleur", "orange"),
                    "origin": "conversation",
                    "status": _translate_ai_status(pc) if pc else "needs_review",
                    "model_version": (pc or {}).get("version_modele", model_version),
                })

        # 3. Ambiguous products (T12)
        for idx, amb in enumerate((norm.get("signaux") or {}).get("produits_ambigus", []), start=1):
            c = champs_by_id.get(amb.get("champ_id"))
            if c:
                used_champ_ids.add(c["id"])
            mid, stxt, sp, ep = _source_from_champ(c, messages_by_id)
            cands = ", ".join(cand.get("ref", "") for cand in amb.get("candidats", []))
            rows.append({
                "field_name": f"produit_ambigu_{idx}",
                "raw_value": amb.get("valeur_brute"),
                "normalized_value": None,
                "ref": cands or None,
                "message_id": mid,
                "source_text": stxt,
                "start_pos": sp,
                "end_pos": ep,
                "confidence": 0.0,
                "couleur": "rouge",
                "origin": "conversation",
                "status": "ambiguous",
                "model_version": (c or {}).get("version_modele", model_version),
            })

        # 4. Zone
        zone_info = norm.get("zone")
        if zone_info and zone_info.get("valeur"):
            zc = champs_by_id.get(zone_info.get("champ_id"))
            if zc:
                used_champ_ids.add(zc["id"])
            mid, stxt, sp, ep = _source_from_champ(zc, messages_by_id)
            rows.append({
                "field_name": "zone",
                "raw_value": (zc or {}).get("valeur_brute"),
                "normalized_value": zone_info["valeur"],
                "ref": None,
                "message_id": mid,
                "source_text": stxt,
                "start_pos": sp,
                "end_pos": ep,
                "confidence": float((zc or {}).get("confiance", 0.75)),
                "couleur": (zc or {}).get("couleur", "orange"),
                "origin": "conversation",
                "status": _translate_ai_status(zc) if zc else "needs_review",
                "model_version": (zc or {}).get("version_modele", model_version),
            })
        elif client and client.get("id") in clients_ref:
            ref_zone = clients_ref[client["id"]]["zone"]
            rows.append({
                "field_name": "zone",
                "raw_value": None,
                "normalized_value": ref_zone,
                "ref": client["id"],
                "message_id": None,
                "source_text": None,
                "start_pos": None,
                "end_pos": None,
                "confidence": 0.85,
                "couleur": "orange",
                "origin": "referentiel",
                "status": "needs_review",
                "model_version": model_version,
            })
        else:
            rows.append({
                "field_name": "zone",
                "raw_value": None,
                "normalized_value": None,
                "ref": None,
                "message_id": None,
                "source_text": None,
                "start_pos": None,
                "end_pos": None,
                "confidence": 0.0,
                "couleur": "rouge",
                "origin": "conversation",
                "status": "missing",
                "model_version": model_version,
            })

        # 5. Payment mode
        pay_info = norm.get("paiement")
        if pay_info and pay_info.get("valeur"):
            pc = champs_by_id.get(pay_info.get("champ_id"))
            if pc:
                used_champ_ids.add(pc["id"])
            mid, stxt, sp, ep = _source_from_champ(pc, messages_by_id)
            rows.append({
                "field_name": "paiement",
                "raw_value": (pc or {}).get("valeur_brute"),
                "normalized_value": pay_info["valeur"],
                "ref": None,
                "message_id": mid,
                "source_text": stxt,
                "start_pos": sp,
                "end_pos": ep,
                "confidence": float((pc or {}).get("confiance", 0.75)),
                "couleur": (pc or {}).get("couleur", "orange"),
                "origin": "conversation",
                "status": _translate_ai_status(pc) if pc else "needs_review",
                "model_version": (pc or {}).get("version_modele", model_version),
            })
        else:
            rows.append({
                "field_name": "paiement",
                "raw_value": None,
                "normalized_value": None,
                "ref": None,
                "message_id": None,
                "source_text": None,
                "start_pos": None,
                "end_pos": None,
                "confidence": 0.0,
                "couleur": "rouge",
                "origin": "conversation",
                "status": "missing",
                "model_version": model_version,
            })

        # 6. Refusals
        refus_champs = [c for c in norm.get("champs", []) if c["nom"] == "refus" and c.get("valeur")]
        sig_refus = (norm.get("signaux") or {}).get("refus", [])
        for idx, ref_sig in enumerate(sig_refus, start=1):
            rc = next(
                (c for c in refus_champs if (c.get("source") or {}).get("message_id") == ref_sig.get("message_id")),
                refus_champs[idx - 1] if idx - 1 < len(refus_champs) else None,
            )
            if rc:
                used_champ_ids.add(rc["id"])
            mid, stxt, sp, ep = _source_from_champ(rc, messages_by_id)
            parts = []
            if ref_sig.get("ref"):
                parts.append(ref_sig["ref"])
            if ref_sig.get("variante"):
                parts.append(f"taille {ref_sig['variante']}")
            if ref_sig.get("motif"):
                parts.append(f"motif : {ref_sig['motif']}")
            val = ", ".join(parts) if parts else (rc or {}).get("valeur")
            rows.append({
                "field_name": f"refus_{idx}" if len(sig_refus) > 1 else "refus",
                "raw_value": (rc or {}).get("valeur_brute"),
                "normalized_value": val,
                "ref": ref_sig.get("ref"),
                "message_id": mid,
                "source_text": stxt,
                "start_pos": sp,
                "end_pos": ep,
                "confidence": float((rc or {}).get("confiance", 0.75)),
                "couleur": (rc or {}).get("couleur", "orange"),
                "origin": "conversation",
                "status": _translate_ai_status(rc) if rc else "needs_review",
                "model_version": (rc or {}).get("version_modele", model_version),
            })

        # 7. Promo code (explicitly absent = missing, never invented)
        promo_c = next((c for c in norm.get("champs", []) if c["nom"] == "code_promo" and c.get("valeur")), None)
        if promo_c:
            used_champ_ids.add(promo_c["id"])
            mid, stxt, sp, ep = _source_from_champ(promo_c, messages_by_id)
            rows.append({
                "field_name": "code_promo",
                "raw_value": promo_c.get("valeur_brute"),
                "normalized_value": promo_c["valeur"],
                "ref": None,
                "message_id": mid,
                "source_text": stxt,
                "start_pos": sp,
                "end_pos": ep,
                "confidence": float(promo_c.get("confiance", 0.75)),
                "couleur": promo_c.get("couleur", "orange"),
                "origin": "conversation",
                "status": _translate_ai_status(promo_c),
                "model_version": promo_c.get("version_modele", model_version),
            })
        else:
            rows.append({
                "field_name": "code_promo",
                "raw_value": None,
                "normalized_value": None,
                "ref": None,
                "message_id": None,
                "source_text": None,
                "start_pos": None,
                "end_pos": None,
                "confidence": 0.0,
                "couleur": "rouge",
                "origin": "conversation",
                "status": "missing",
                "model_version": model_version,
            })

        # 8. Delivery date if present
        date_c = next((c for c in norm.get("champs", []) if c["nom"] == "date_livraison" and c.get("valeur")), None)
        if date_c:
            used_champ_ids.add(date_c["id"])
            mid, stxt, sp, ep = _source_from_champ(date_c, messages_by_id)
            rows.append({
                "field_name": "date_livraison",
                "raw_value": date_c.get("valeur_brute"),
                "normalized_value": str(date_c["valeur"]),
                "ref": None,
                "message_id": mid,
                "source_text": stxt,
                "start_pos": sp,
                "end_pos": ep,
                "confidence": float(date_c.get("confiance", 0.75)),
                "couleur": date_c.get("couleur", "orange"),
                "origin": "conversation",
                "status": _translate_ai_status(date_c),
                "model_version": date_c.get("version_modele", model_version),
            })

        # 9. Keep any rejected/low-confidence field (T22) visible for human review
        rejected_idx = 0
        for c in norm.get("champs", []):
            if c.get("id") in used_champ_ids:
                continue
            if c.get("statut") == "a_renseigner" and not c.get("ambiguite_produit"):
                rejected_idx += 1
                mid, stxt, sp, ep = _source_from_champ(c, messages_by_id)
                rows.append({
                    "field_name": f"{c['nom']}_a_renseigner_{rejected_idx}",
                    "raw_value": c.get("valeur_brute"),
                    "normalized_value": None,
                    "ref": None,
                    "message_id": mid,
                    "source_text": stxt,
                    "start_pos": sp,
                    "end_pos": ep,
                    "confidence": 0.0,
                    "couleur": "rouge",
                    "origin": "conversation",
                    "status": "missing",
                    "model_version": c.get("version_modele", model_version),
                })

        return rows

    def _build_delivery_and_control(
        self,
        norm: dict,
        catalogue: dict,
        medias: list[dict],
    ) -> tuple[list[dict], list[dict], dict]:
        """Build delivery rows (for UI/GET /livraison), calc lines, and anomaly-control payload."""
        refus_list = (norm.get("signaux") or {}).get("refus", [])
        delivery_rows: list[dict] = []
        calc_lines: list[dict] = []
        control_lines: list[dict] = []

        for ligne in norm.get("lignes", []):
            ref = ligne["ref"]
            cat_item = catalogue.get(ref, {})
            prod_name = cat_item.get("name") or ligne["produit"]
            unit_price = int(cat_item.get("price_ht", 0))
            q_cmd = ligne.get("quantite_commandee")
            q_liv = ligne.get("quantite_livree")
            q_ref = int(ligne.get("quantite_refusee") or 0)
            rep_cmd = ligne.get("repartition_commandee") or []
            vars_cmd = (ligne.get("variantes") or {}).get("commandees") or []
            vars_liv = (ligne.get("variantes") or {}).get("livrees") or []
            line_refusals = [r for r in refus_list if r.get("ref") == ref]
            refusal_reason = "; ".join(
                filter(None, [r.get("motif") for r in line_refusals])
            )

            # Expand per variant when detailed breakdown is available (e.g. Awa's M & L dresses)
            if rep_cmd:
                # Deduplicate variant entries when seller echoes the recap (keep last qty per variant)
                dedup_rep: dict[str, int] = {}
                for item in rep_cmd:
                    dedup_rep[item["variante"]] = int(item["quantite"])
                refused_vars = {r.get("variante"): r.get("motif", "") for r in line_refusals if r.get("variante")}
                for var, ordered in dedup_rep.items():
                    if var in refused_vars:
                        refused = ordered
                        accepted = 0
                        delivered = ordered
                        missing = 0
                        reason = refused_vars[var] or "Refusé par le client"
                    else:
                        refused = 0
                        accepted = ordered
                        delivered = ordered
                        missing = 0
                        reason = ""
                    delivery_rows.append({
                        "product_id": ref,
                        "label": f"{prod_name}, taille {var}",
                        "variant": var,
                        "ordered": ordered,
                        "delivered": delivered,
                        "accepted": accepted,
                        "refused": refused,
                        "missing": missing,
                        "reason": reason,
                    })
                    if accepted > 0:
                        calc_lines.append({
                            "product_id": ref,
                            "description": prod_name,
                            "variant": var,
                            "quantity_accepted": accepted,
                            "unit_price_ht": unit_price,
                        })
                    control_lines.append({
                        "product_id": ref,
                        "description": f"{prod_name} ({var})",
                        "variant": var,
                        "variants_ordered": vars_cmd,
                        "quantity_ordered": ordered,
                        "quantity_delivered": delivered,
                        "quantity_accepted": accepted,
                        "quantity_refused": refused,
                        "quantity_missing": missing,
                        "refusal_reason": reason,
                        "cited_price_ht": ligne.get("prix_cite"),
                    })
            else:
                ordered = int(q_cmd) if q_cmd is not None else (int(q_liv) if q_liv is not None else 0)
                if q_liv is not None:
                    accepted = int(q_liv)
                    missing = max(0, ordered - accepted - q_ref)
                    delivered = accepted + q_ref + missing
                else:
                    # No delivery message yet: draft preview assumes ordered - refused
                    accepted = max(0, ordered - q_ref)
                    delivered = ordered
                    missing = 0
                variant = (vars_liv[0] if vars_liv else (vars_cmd[0] if len(vars_cmd) == 1 else None))
                label = f"{prod_name}, taille {variant}" if variant else prod_name
                delivery_rows.append({
                    "product_id": ref,
                    "label": label,
                    "variant": variant,
                    "ordered": ordered,
                    "delivered": delivered,
                    "accepted": accepted,
                    "refused": q_ref,
                    "missing": missing,
                    "reason": refusal_reason,
                })
                if accepted > 0:
                    calc_lines.append({
                        "product_id": ref,
                        "description": prod_name,
                        "variant": variant,
                        "quantity_accepted": accepted,
                        "unit_price_ht": unit_price,
                    })
                control_lines.append({
                    "product_id": ref,
                    "description": prod_name,
                    "variant": variant,
                    "variants_ordered": vars_cmd,
                    "quantity_ordered": ordered,
                    "quantity_delivered": delivered,
                    "quantity_accepted": accepted,
                    "quantity_refused": q_ref,
                    "quantity_missing": missing,
                    "refusal_reason": refusal_reason,
                    "cited_price_ht": ligne.get("prix_cite"),
                })

        client_id = (norm.get("client") or {}).get("id")
        signaux = norm.get("signaux") or {}
        control_payload = {
            "client": client_id,
            "lines": control_lines,
            "ambiguous_products": signaux.get("produits_ambigus", []),
            "conversation_has_multiple_clients": bool(signaux.get("multi_commandes")),
            "unsupported_media": medias,
        }
        return delivery_rows, calc_lines, control_payload

    def _run_pipeline_steps(
        self,
        dossier_id: str,
        actor: str,
        *,
        mode: str | None = None,
        telephone: str | None = None,
        stop_after_step: str | None = None,
    ) -> dict:
        t0 = time.time()
        catalogue = load_catalogue()
        clients_ref = load_clients()
        rules = load_rules()
        clients_parser = self._clients_for_parser()

        with self._connection() as connection:
            dossier = connection.execute(
                "SELECT * FROM dossiers WHERE id = ?", (dossier_id,)
            ).fetchone()
            if dossier is None:
                raise WorkflowError(404, "Dossier inconnu")
            conv = connection.execute(
                "SELECT * FROM conversations WHERE id = ?", (dossier["conversation_id"],)
            ).fetchone()
            raw_text = conv["raw_text"] if conv else ""
            content = json.loads(dossier["content"] or "{}")

            # Step 2: ANALYSE
            if not self._step_done(connection, dossier_id, "ANALYSE"):
                try:
                    analyse_res = analyser(
                        texte_brut=raw_text,
                        clients=clients_parser,
                        telephone=telephone,
                    )
                except FormatInvalide as exc:
                    raise WorkflowError(422, str(exc))
                for m in analyse_res["messages"]:
                    connection.execute(
                        """INSERT OR IGNORE INTO conversation_messages
                           (id, dossier_id, conversation_id, message_id, position,
                            timestamp, author, role, text, type_message)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            f"{dossier_id}-{m['message_id']}",
                            dossier_id,
                            dossier["conversation_id"],
                            m["message_id"],
                            int(m["rang"]),
                            m.get("horodatage"),
                            m["auteur"],
                            m["role"],
                            m["texte"],
                            m.get("type_message", "INFORMATION"),
                        ),
                    )
                content["client_match"] = analyse_res["client"]
                content["empreinte"] = analyse_res["empreinte"]
                content["medias_non_pris_en_charge"] = analyse_res["medias_non_pris_en_charge"]
                connection.execute(
                    "UPDATE dossiers SET content = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(content, ensure_ascii=False), utc_now(), dossier_id),
                )
                self._mark_step_done(connection, dossier_id, "ANALYSE")
                connection.commit()
            if stop_after_step == "ANALYSE":
                return self.get_dossier(dossier_id)

            # Reconstruct messages from DB for deterministic resume
            msg_rows = connection.execute(
                "SELECT * FROM conversation_messages WHERE dossier_id = ? ORDER BY position",
                (dossier_id,),
            ).fetchall()
            messages = [
                {
                    "rang": r["position"],
                    "message_id": r["message_id"],
                    "horodatage": r["timestamp"],
                    "auteur": r["author"],
                    "role": r["role"],
                    "texte": r["text"],
                    "type_message": r["type_message"],
                }
                for r in msg_rows
            ]

            # Step 3: EXTRAIT
            if not self._step_done(connection, dossier_id, "EXTRAIT"):
                raw_champs = extraire(messages, mode=mode, seuils=rules.get("seuils_confiance"))
                content["raw_champs"] = raw_champs
                connection.execute(
                    "UPDATE dossiers SET content = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(content, ensure_ascii=False), utc_now(), dossier_id),
                )
                self._mark_step_done(connection, dossier_id, "EXTRAIT")
                connection.commit()
            if stop_after_step == "EXTRAIT":
                return self.get_dossier(dossier_id)

            # Step 4: NORMALISE
            if not self._step_done(connection, dossier_id, "NORMALISE"):
                raw_champs = content.get("raw_champs", [])
                cat_for_ai = {
                    ref: {"reference": ref, "nom": item["name"]}
                    for ref, item in catalogue.items()
                }
                norm = normaliser_dossier(
                    messages,
                    raw_champs,
                    content.get("client_match"),
                    catalogue=cat_for_ai,
                )
                extracted_rows = self._build_extracted_fields(messages, norm, clients_ref)
                for pos, ef in enumerate(extracted_rows, start=1):
                    connection.execute(
                        """INSERT OR IGNORE INTO extracted_fields
                           (id, dossier_id, field_name, raw_value, normalized_value, ref,
                            message_id, source_text, start_pos, end_pos, confidence,
                            couleur, origin, status, model_version, position)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            f"{dossier_id}-F{pos}",
                            dossier_id,
                            ef["field_name"],
                            ef["raw_value"],
                            ef["normalized_value"],
                            ef["ref"],
                            ef["message_id"],
                            ef["source_text"],
                            ef["start_pos"],
                            ef["end_pos"],
                            ef["confidence"],
                            ef["couleur"],
                            ef["origin"],
                            ef["status"],
                            ef["model_version"],
                            pos,
                        ),
                    )
                content["normalized"] = norm
                connection.execute(
                    "UPDATE dossiers SET content = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(content, ensure_ascii=False), utc_now(), dossier_id),
                )
                self._mark_step_done(connection, dossier_id, "NORMALISE")
                connection.commit()
            if stop_after_step == "NORMALISE":
                return self.get_dossier(dossier_id)

            norm = content.get("normalized", {})
            delivery_rows, calc_lines, control_payload = self._build_delivery_and_control(
                norm, catalogue, content.get("medias_non_pris_en_charge", [])
            )

            # Step 5: CONTROLE
            if not self._step_done(connection, dossier_id, "CONTROLE"):
                detected = detect_anomalies(control_payload, catalogue, clients_ref, rules=rules)
                for idx, anom in enumerate(detected, start=1):
                    anom_id = f"{dossier_id}-A{idx}"
                    connection.execute(
                        """INSERT OR IGNORE INTO anomalies
                           (id, dossier_id, code, severity, description, status, concerned_value)
                           VALUES (?, ?, ?, ?, ?, 'ouverte', ?)""",
                        (
                            anom_id,
                            dossier_id,
                            anom["code"],
                            anom.get("severity", "bloquante"),
                            anom["description"],
                            anom.get("concerned_value"),
                        ),
                    )
                self._mark_step_done(connection, dossier_id, "CONTROLE")
                connection.commit()
            if stop_after_step == "CONTROLE":
                return self.get_dossier(dossier_id)

            # Step 6: CALCULE
            if not self._step_done(connection, dossier_id, "CALCULE"):
                client_match = content.get("client_match") or {}
                client_id = client_match.get("id")
                client_info = clients_ref.get(client_id, {}) if client_id else {}
                zone = (norm.get("zone") or {}).get("valeur") or client_info.get("zone") or ""
                promo_field = connection.execute(
                    "SELECT normalized_value FROM extracted_fields WHERE dossier_id = ? AND field_name = 'code_promo'",
                    (dossier_id,),
                ).fetchone()
                promo_code = promo_field["normalized_value"] if promo_field else None
                first_order = self._is_first_order(connection, client_id)
                faithful = bool(client_info.get("faithful", False))

                calculation = calculate_invoice(
                    calc_lines,
                    zone,
                    faithful_customer=faithful,
                    first_order=first_order,
                    promo_code=promo_code,
                    rules=rules,
                )
                content["client"] = {
                    "id": client_id,
                    "name": client_info.get("name") or client_match.get("nom") or "Client non identifié",
                    "phone": client_info.get("phone") or "Non renseigné",
                    "zone": zone or "Non renseignée",
                    "address": zone or "Non renseignée",
                    "faithful": faithful,
                }
                content["vendor"] = rules.get("vendor", {})
                content["delivery"] = delivery_rows
                content["calc_lines"] = calc_lines
                content["calculation"] = calculation
                content["lines"] = calculation["lines"]
                content["totals"] = _format_totals(calculation)
                content["total_ttc"] = calculation["total_ttc"]
                content["config_hash"] = get_config_hash()
                content["zone"] = zone
                content["promo_code"] = promo_code
                content["first_order"] = first_order
                connection.execute(
                    "UPDATE dossiers SET content = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(content, ensure_ascii=False), utc_now(), dossier_id),
                )
                self._mark_step_done(connection, dossier_id, "CALCULE")
                connection.commit()
            if stop_after_step == "CALCULE":
                return self.get_dossier(dossier_id)

            # Step 7: BROUILLON
            if not self._step_done(connection, dossier_id, "BROUILLON"):
                now = utc_now()
                new_status = self._compute_doc_status(connection, dossier_id, "BROUILLON")
                connection.execute(
                    "UPDATE dossiers SET status = ?, updated_at = ? WHERE id = ?",
                    (new_status, now, dossier_id),
                )
                self._append_audit(
                    connection,
                    actor,
                    "IMPORT",
                    dossier_id,
                    None,
                    {
                        "status": strip_accents_code(new_status),
                        "empreinte": content.get("empreinte"),
                        "messages": len(messages),
                        "total_ttc": content.get("total_ttc", 0),
                    },
                    now,
                )
                self._mark_step_done(connection, dossier_id, "BROUILLON", now)
                connection.commit()

        log.info("pipeline dossier=%s duree_ms=%d", dossier_id, int((time.time() - t0) * 1000))
        return self.get_dossier(dossier_id)

    def import_dossier(
        self,
        raw_text: str,
        created_by: str,
        idempotency_key: str | None = None,
        *,
        mode: str | None = None,
        telephone: str | None = None,
        stop_after_step: str | None = None,
    ) -> dict:
        if not isinstance(raw_text, str) or not raw_text.strip():
            raise WorkflowError(422, "Fichier vide ou mal formé.")
        if len(raw_text.encode("utf-8")) > MAX_IMPORT_BYTES:
            raise WorkflowError(422, "Fichier trop volumineux (limite 512 Ko).")

        # Pre-validate format and compute logical fingerprint before DB write
        try:
            preview = analyser(
                texte_brut=raw_text,
                clients=self._clients_for_parser(),
                telephone=telephone,
            )
        except FormatInvalide as exc:
            raise WorkflowError(422, str(exc))

        fingerprint = preview["empreinte"]

        with self._connection() as connection:
            self._require_role(
                connection,
                created_by,
                {"vendeuse"},
                "Seule une vendeuse peut importer une conversation.",
            )

            # Idempotency check 1: Idempotency-Key
            if idempotency_key:
                existing = connection.execute(
                    "SELECT * FROM dossiers WHERE idempotency_key = ?",
                    (idempotency_key,),
                ).fetchone()
                if existing:
                    return {
                        "dossier_id": existing["id"],
                        "version": existing["version"],
                        "duplicate": True,
                        "status": strip_accents_code(existing["status"]),
                        "doc_status": strip_accents_code(existing["status"]),
                    }

            # Idempotency check 2: conversation fingerprint (E1)
            existing_conv = connection.execute(
                "SELECT id FROM conversations WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
            if existing_conv:
                existing_dossier = connection.execute(
                    "SELECT * FROM dossiers WHERE conversation_id = ?",
                    (existing_conv["id"],),
                ).fetchone()
                if existing_dossier:
                    return {
                        "dossier_id": existing_dossier["id"],
                        "version": existing_dossier["version"],
                        "duplicate": True,
                        "status": strip_accents_code(existing_dossier["status"]),
                        "doc_status": strip_accents_code(existing_dossier["status"]),
                    }

            # Create conversation + dossier atomically
            connection.execute("BEGIN IMMEDIATE")
            # Re-check under write lock
            existing_conv = connection.execute(
                "SELECT id FROM conversations WHERE fingerprint = ?",
                (fingerprint,),
            ).fetchone()
            if existing_conv:
                existing_dossier = connection.execute(
                    "SELECT * FROM dossiers WHERE conversation_id = ?",
                    (existing_conv["id"],),
                ).fetchone()
                connection.commit()
                if existing_dossier:
                    return {
                        "dossier_id": existing_dossier["id"],
                        "version": existing_dossier["version"],
                        "duplicate": True,
                        "status": strip_accents_code(existing_dossier["status"]),
                        "doc_status": strip_accents_code(existing_dossier["status"]),
                    }

            counter = connection.execute(
                "UPDATE counters SET value = value + 1 WHERE name = 'dossier' RETURNING value"
            ).fetchone()
            seq = counter["value"]
            dossier_id = f"DOS-2026-{seq:04d}"
            conv_id = f"CONV-2026-{seq:04d}"
            now = utc_now()
            idem = idempotency_key or f"import-{fingerprint}"

            connection.execute(
                """INSERT INTO conversations (id, fingerprint, raw_text, imported_by, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (conv_id, fingerprint, raw_text, created_by, now),
            )
            connection.execute(
                """INSERT INTO dossiers
                   (id, conversation_id, idempotency_key, status, version,
                    created_by, content, created_at, updated_at)
                   VALUES (?, ?, ?, 'BROUILLON', 1, ?, '{}', ?, ?)""",
                (dossier_id, conv_id, idem, created_by, now, now),
            )
            self._mark_step_done(connection, dossier_id, "IMPORTE", now)
            connection.commit()

        if stop_after_step == "IMPORTE":
            info = self.get_dossier(dossier_id)
            return {
                "dossier_id": dossier_id,
                "version": info["version"],
                "duplicate": False,
                "status": info["doc_status"],
                "doc_status": info["doc_status"],
                "steps": info["steps"],
            }

        info = self._run_pipeline_steps(
            dossier_id,
            created_by,
            mode=mode,
            telephone=telephone,
            stop_after_step=stop_after_step,
        )
        return {
            "dossier_id": dossier_id,
            "version": info["version"],
            "duplicate": False,
            "status": info["doc_status"],
            "doc_status": info["doc_status"],
            "steps": info["steps"],
        }

    def resume_dossier(self, dossier_id: str, actor: str, *, mode: str | None = None) -> dict:
        with self._connection() as connection:
            self._require_role(
                connection,
                actor,
                {"vendeuse", "gerant"},
                "Rôle non autorisé pour reprendre le traitement.",
            )
        return self._run_pipeline_steps(dossier_id, actor, mode=mode)

    def create_dossier(
        self,
        dossier_id: str,
        conversation_id: str,
        created_by: str,
        idempotency_key: str,
    ) -> dict:
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
            self._append_audit(
                connection,
                created_by,
                "IMPORT",
                dossier_id,
                None,
                {"conversation_id": conversation_id, "status": "BROUILLON"},
                now,
            )
            result = connection.execute(
                "SELECT * FROM dossiers WHERE id = ?", (dossier_id,)
            ).fetchone()
            connection.commit()
            return dict(result)

    def prepare_dossier(self, dossier_id: str, content: dict, version: int) -> dict:
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
            connection.commit()
            return dict(result)

    def _recalculate_draft_content(self, connection: sqlite3.Connection, dossier_id: str) -> None:
        """Recompute draft invoice totals deterministically after a human field correction."""
        dossier = connection.execute("SELECT * FROM dossiers WHERE id = ?", (dossier_id,)).fetchone()
        if not dossier:
            return
        content = json.loads(dossier["content"] or "{}")
        if "calc_lines" not in content:
            return

        catalogue = load_catalogue()
        clients_ref = load_clients()
        rules = load_rules()

        fields = connection.execute(
            "SELECT * FROM extracted_fields WHERE dossier_id = ?", (dossier_id,)
        ).fetchall()
        by_name = {f["field_name"]: f for f in fields}

        # Effective client
        client_info = dict(content.get("client") or {})
        client_f = by_name.get("client")
        if client_f and client_f["corrected_value"]:
            corr = client_f["corrected_value"].strip()
            matched_cid = corr.split()[0] if corr.split()[0] in clients_ref else None
            if matched_cid:
                c = clients_ref[matched_cid]
                client_info = {
                    "id": matched_cid,
                    "name": c["name"],
                    "phone": c["phone"],
                    "zone": c["zone"],
                    "address": c["zone"],
                    "faithful": c["faithful"],
                }
            else:
                client_info["name"] = corr

        # Effective zone
        zone = content.get("zone") or client_info.get("zone") or ""
        zone_f = by_name.get("zone")
        if zone_f and zone_f["corrected_value"]:
            zone = zone_f["corrected_value"].strip()
            client_info["zone"] = zone
            client_info["address"] = zone

        # Effective promo code
        promo_code = content.get("promo_code")
        promo_f = by_name.get("code_promo")
        if promo_f and promo_f["corrected_value"] is not None:
            promo_code = promo_f["corrected_value"].strip().upper() or None

        # Effective delivered quantities if corrected
        calc_lines = list(content.get("calc_lines") or [])
        for idx, line in enumerate(calc_lines, start=1):
            ql_f = by_name.get(f"quantite_livree_{idx}")
            if ql_f and ql_f["corrected_value"] is not None:
                try:
                    new_qty = int(ql_f["corrected_value"])
                    if new_qty >= 0:
                        line["quantity_accepted"] = new_qty
                except ValueError:
                    pass
            # Always keep official catalogue unit price!
            pid = line.get("product_id")
            if pid in catalogue:
                line["unit_price_ht"] = catalogue[pid]["price_ht"]
                line["description"] = catalogue[pid]["name"]

        first_order = self._is_first_order(connection, client_info.get("id"))
        calculation = calculate_invoice(
            [l for l in calc_lines if int(l.get("quantity_accepted", 0)) > 0],
            zone,
            faithful_customer=bool(client_info.get("faithful", False)),
            first_order=first_order,
            promo_code=promo_code,
            rules=rules,
        )
        content["client"] = client_info
        content["zone"] = zone
        content["promo_code"] = promo_code
        content["calc_lines"] = calc_lines
        content["calculation"] = calculation
        content["lines"] = calculation["lines"]
        content["totals"] = _format_totals(calculation)
        content["total_ttc"] = calculation["total_ttc"]
        content["config_hash"] = get_config_hash()

        connection.execute(
            "UPDATE dossiers SET content = ? WHERE id = ?",
            (json.dumps(content, ensure_ascii=False), dossier_id),
        )

    def confirm_field(
        self,
        dossier_id: str,
        field_name: str,
        user: str,
        new_value: Any = None,
        version: int | None = None,
    ) -> dict:
        now = utc_now()
        with self._connection() as connection:
            self._require_role(
                connection,
                user,
                {"vendeuse"},
                "Seule une vendeuse peut confirmer ou corriger un champ.",
            )
            dossier = connection.execute(
                "SELECT * FROM dossiers WHERE id = ?", (dossier_id,)
            ).fetchone()
            if dossier is None:
                raise WorkflowError(404, "Dossier inconnu")
            if strip_accents_code(dossier["status"]) in ("VALIDEE", "EMISE", "ANNULE"):
                raise WorkflowError(422, "Impossible de modifier un dossier déjà validé ou annulé.")
            if version is not None and dossier["version"] != version:
                raise WorkflowError(409, "Version du dossier périmée")

            field = connection.execute(
                "SELECT * FROM extracted_fields WHERE dossier_id = ? AND field_name = ?",
                (dossier_id, field_name),
            ).fetchone()
            if field is None:
                raise WorkflowError(404, f"Champ inconnu : {field_name}")

            old_effective = field["corrected_value"] if field["corrected_value"] is not None else field["normalized_value"]

            if new_value is not None:
                new_val_str = str(new_value).strip()
                if not new_val_str:
                    raise WorkflowError(422, "La nouvelle valeur ne peut pas être vide.")
                # Original raw_value and normalized_value are NEVER overwritten (CDC §7.5)
                connection.execute(
                    """UPDATE extracted_fields
                       SET corrected_value = ?, status = 'extracted', confirmed = 1,
                           confirmed_by = ?, confirmed_at = ?
                       WHERE id = ?""",
                    (new_val_str, user, now, field["id"]),
                )
                self._append_audit(
                    connection,
                    user,
                    "FIELD_CORRECTED",
                    dossier_id,
                    {"field": field_name, "value": old_effective},
                    {"field": field_name, "value": new_val_str},
                    now,
                )
                self._recalculate_draft_content(connection, dossier_id)
            else:
                connection.execute(
                    """UPDATE extracted_fields
                       SET confirmed = 1, confirmed_by = ?, confirmed_at = ?
                       WHERE id = ?""",
                    (user, now, field["id"]),
                )

            self._append_audit(
                connection,
                user,
                "FIELD_CONFIRMED",
                dossier_id,
                {"field": field_name, "confirmed": bool(field["confirmed"])},
                {"field": field_name, "confirmed": True},
                now,
            )

            new_status = self._compute_doc_status(connection, dossier_id, dossier["status"])
            connection.execute(
                "UPDATE dossiers SET status = ?, version = version + 1, updated_at = ? WHERE id = ?",
                (new_status, now, dossier_id),
            )
            connection.commit()

            updated_dossier = self.get_dossier(dossier_id)
            updated_field = next(
                f for f in self.get_extractions(dossier_id) if f["field"] == field_name
            )
            return {
                **updated_field,
                "dossier_version": updated_dossier["version"],
                "doc_status": updated_dossier["doc_status"],
            }

    def confirm_all_fields(self, dossier_id: str, user: str, version: int | None = None) -> dict:
        now = utc_now()
        with self._connection() as connection:
            self._require_role(
                connection,
                user,
                {"vendeuse"},
                "Seule une vendeuse peut confirmer les champs.",
            )
            dossier = connection.execute(
                "SELECT * FROM dossiers WHERE id = ?", (dossier_id,)
            ).fetchone()
            if dossier is None:
                raise WorkflowError(404, "Dossier inconnu")
            if strip_accents_code(dossier["status"]) in ("VALIDEE", "EMISE", "ANNULE"):
                raise WorkflowError(422, "Impossible de modifier un dossier déjà validé ou annulé.")
            if version is not None and dossier["version"] != version:
                raise WorkflowError(409, "Version du dossier périmée")

            pending = connection.execute(
                """SELECT id, field_name FROM extracted_fields
                   WHERE dossier_id = ? AND confirmed = 0 AND status != 'missing'""",
                (dossier_id,),
            ).fetchall()
            for row in pending:
                connection.execute(
                    "UPDATE extracted_fields SET confirmed = 1, confirmed_by = ?, confirmed_at = ? WHERE id = ?",
                    (user, now, row["id"]),
                )
                self._append_audit(
                    connection,
                    user,
                    "FIELD_CONFIRMED",
                    dossier_id,
                    {"field": row["field_name"], "confirmed": False},
                    {"field": row["field_name"], "confirmed": True},
                    now,
                )

            new_status = self._compute_doc_status(connection, dossier_id, dossier["status"])
            connection.execute(
                "UPDATE dossiers SET status = ?, version = version + 1, updated_at = ? WHERE id = ?",
                (new_status, now, dossier_id),
            )
            connection.commit()

        return self.get_dossier(dossier_id)

    def resolve_anomaly(self, anomaly_id: str, resolved_by: str, justification: str) -> dict:
        if not justification or not justification.strip():
            raise WorkflowError(422, "Une justification est obligatoire")

        now = utc_now()
        with self._connection() as connection:
            self._require_role(
                connection,
                resolved_by,
                {"vendeuse", "gerant"},
                "Rôle non autorisé pour résoudre une anomalie.",
            )
            anomaly = connection.execute(
                "SELECT * FROM anomalies WHERE id = ?", (anomaly_id,)
            ).fetchone()
            if anomaly is None:
                raise WorkflowError(404, "Anomalie inconnue")

            dossier = connection.execute(
                "SELECT * FROM dossiers WHERE id = ?", (anomaly["dossier_id"],)
            ).fetchone()
            if dossier and strip_accents_code(dossier["status"]) in ("VALIDEE", "EMISE", "ANNULE"):
                raise WorkflowError(422, "Impossible de résoudre une anomalie sur un dossier figé.")

            clean_just = justification.strip()
            connection.execute(
                """UPDATE anomalies
                   SET status = 'résolue', justification = ?, resolved_by = ?, resolved_at = ?
                   WHERE id = ?""",
                (clean_just, resolved_by, now, anomaly_id),
            )
            self._append_audit(
                connection,
                resolved_by,
                "ANOMALY_RESOLVED",
                anomaly["dossier_id"],
                {"anomaly_id": anomaly_id, "code": anomaly["code"], "status": anomaly["status"]},
                {"anomaly_id": anomaly_id, "code": anomaly["code"], "status": "résolue", "justification": clean_just},
                now,
            )

            if dossier is not None:
                new_status = self._compute_doc_status(connection, dossier["id"], dossier["status"])
                connection.execute(
                    "UPDATE dossiers SET status = ?, version = version + 1, updated_at = ? WHERE id = ?",
                    (new_status, now, dossier["id"]),
                )

            updated = connection.execute(
                "SELECT * FROM anomalies WHERE id = ?", (anomaly_id,)
            ).fetchone()
            connection.commit()
            return self._format_anomaly(dict(updated))

    def cancel_dossier(self, dossier_id: str, cancelled_by: str, reason: str) -> dict:
        if not reason or not reason.strip():
            raise WorkflowError(422, "Un motif d'annulation est obligatoire.")
        now = utc_now()
        with self._connection() as connection:
            self._require_role(
                connection,
                cancelled_by,
                {"vendeuse", "gerant"},
                "Rôle non autorisé pour annuler un dossier.",
            )
            dossier = connection.execute(
                "SELECT * FROM dossiers WHERE id = ?", (dossier_id,)
            ).fetchone()
            if dossier is None:
                raise WorkflowError(404, "Dossier inconnu")
            if strip_accents_code(dossier["status"]) in ("VALIDEE", "EMISE"):
                raise WorkflowError(
                    422,
                    "Une facture déjà validée ne peut pas être annulée : créez un avoir lié.",
                )
            old_status = dossier["status"]
            connection.execute(
                "UPDATE dossiers SET status = 'ANNULE', version = version + 1, updated_at = ? WHERE id = ?",
                (now, dossier_id),
            )
            self._append_audit(
                connection,
                cancelled_by,
                "DOSSIER_CANCELLED",
                dossier_id,
                {"status": old_status},
                {"status": "ANNULE", "reason": reason.strip()},
                now,
            )
            connection.commit()
        return self.get_dossier(dossier_id)

    def validate_invoice(
        self,
        dossier_id: str,
        validator_id: str,
        validator_role: str,
        version: int,
    ) -> dict:
        if validator_role != "gerant":
            raise WorkflowError(403, "Seul un gérant peut valider une facture")

        with self._connection() as connection:
            db_role = self._user_role(connection, validator_id)
            if db_role is not None and db_role != "gerant":
                # Keep four-eyes error 403 priority when validator == initiator
                dossier_pre = connection.execute(
                    "SELECT created_by FROM dossiers WHERE id = ?", (dossier_id,)
                ).fetchone()
                if dossier_pre and validator_id == dossier_pre["created_by"]:
                    raise WorkflowError(403, "Le validateur doit être différent de l'initiateur")
                raise WorkflowError(403, "Seul un gérant peut valider une facture")

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
                connection.commit()
                return dict(existing)

            if dossier["version"] != version:
                raise WorkflowError(409, "Version du dossier périmée")
            if strip_accents_code(dossier["status"]) != "PRET_A_VALIDER":
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
                "UPDATE counters SET value = value + 1 WHERE name = 'invoice' RETURNING value"
            ).fetchone()
            number = f"FAC-2026-{counter['value']:06d}"

            content = json.loads(dossier["content"] or "{}")
            rules = load_rules()
            config_hash = content.get("config_hash") or get_config_hash()
            # Freeze snapshots of vendor, client, lines, calculation, config_hash (Addendum §10 & T21)
            frozen_payload = {
                **content,
                "invoice_number": number,
                "dossier_id": dossier_id,
                "config_hash": config_hash,
                "vendor_snapshot": content.get("vendor") or rules.get("vendor", {}),
                "client_snapshot": content.get("client") or {},
                "validated_by": validator_id,
            }
            total_ttc = int(frozen_payload.get("total_ttc", 0))
            invoice_id = f"INV-{dossier_id}"
            now = utc_now()
            invoice_content = json.dumps(frozen_payload, sort_keys=True, ensure_ascii=False)
            content_hash = hashlib.sha256(invoice_content.encode("utf-8")).hexdigest()

            connection.execute(
                """INSERT INTO invoices
                   (id, dossier_id, number, total_ttc, content, content_hash,
                    config_hash, validated_by, validated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    invoice_id,
                    dossier_id,
                    number,
                    total_ttc,
                    invoice_content,
                    content_hash,
                    config_hash,
                    validator_id,
                    now,
                ),
            )
            for position, line in enumerate(frozen_payload.get("lines", []), start=1):
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
                "UPDATE dossiers SET status = 'VALIDÉE', version = version + 1, updated_at = ? WHERE id = ?",
                (now, dossier_id),
            )

            self._append_audit(
                connection,
                validator_id,
                "INVOICE_VALIDATED",
                dossier_id,
                {"status": strip_accents_code(dossier["status"])},
                {"status": "VALIDEE", "number": number, "invoice_id": invoice_id, "content_hash": content_hash},
                now,
            )
            connection.commit()

            result = connection.execute(
                "SELECT * FROM invoices WHERE id = ?", (invoice_id,)
            ).fetchone()
            return dict(result)

    def emit_invoice(
        self,
        invoice_id: str,
        channel: str,
        actor: str,
        idempotency_key: str,
        *,
        offline: bool = False,
    ) -> dict:
        allowed_channels = {"whatsapp", "sms", "email", "courriel"}
        clean_channel = channel.strip().lower()
        if clean_channel not in allowed_channels:
            raise WorkflowError(422, f"Canal d'émission non supporté : {channel}")

        now = utc_now()
        with self._connection() as connection:
            self._require_role(
                connection,
                actor,
                {"vendeuse", "gerant"},
                "Rôle non autorisé pour émettre une facture.",
            )
            existing_outbox = connection.execute(
                "SELECT * FROM outbox WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing_outbox:
                return dict(existing_outbox)

            invoice = connection.execute(
                "SELECT * FROM invoices WHERE id = ? OR number = ?", (invoice_id, invoice_id)
            ).fetchone()
            if invoice is None:
                raise WorkflowError(404, "Facture inconnue")

            real_invoice_id = invoice["id"]
            payload = {
                "simulated": True,
                "invoice_id": real_invoice_id,
                "invoice_number": invoice["number"],
                "channel": clean_channel,
                "message": (
                    f"[SIMULATION - {clean_channel.upper()}] Facture {invoice['number']} "
                    f"(Total TTC : {invoice['total_ttc']} FCFA) prête — Boutique X."
                ),
            }
            outbox_id = f"OUT-{idempotency_key}"
            status = "en_attente" if offline else "envoye"
            sent_at = None if offline else now

            connection.execute(
                """INSERT INTO outbox
                   (id, invoice_id, channel, payload, status, created_by, created_at, sent_at, idempotency_key)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    outbox_id,
                    real_invoice_id,
                    clean_channel,
                    json.dumps(payload, ensure_ascii=False),
                    status,
                    actor,
                    now,
                    sent_at,
                    idempotency_key,
                ),
            )

            if not offline:
                connection.execute(
                    """INSERT OR IGNORE INTO status_events
                       (id, invoice_id, event_type, channel, detail, created_by, created_at, idempotency_key)
                       VALUES (?, ?, 'EMISE', ?, ?, ?, ?, ?)""",
                    (
                        f"EVT-{idempotency_key}",
                        real_invoice_id,
                        clean_channel,
                        payload["message"],
                        actor,
                        now,
                        idempotency_key,
                    ),
                )
                connection.execute(
                    "UPDATE dossiers SET status = 'ÉMISE', updated_at = ? WHERE id = ?",
                    (now, invoice["dossier_id"]),
                )
                self._append_audit(
                    connection,
                    actor,
                    "INVOICE_EMITTED",
                    invoice["dossier_id"],
                    {"status": "VALIDEE"},
                    {"status": "EMISE", "invoice_id": real_invoice_id, "channel": clean_channel, "simulated": True},
                    now,
                )
            else:
                self._append_audit(
                    connection,
                    actor,
                    "EMISSION_QUEUED_OFFLINE",
                    invoice["dossier_id"],
                    None,
                    {"invoice_id": real_invoice_id, "channel": clean_channel, "outbox_id": outbox_id},
                    now,
                )

            connection.commit()
            row = connection.execute("SELECT * FROM outbox WHERE id = ?", (outbox_id,)).fetchone()
            return dict(row)

    def sync_outbox(self, actor: str) -> dict:
        now = utc_now()
        synced: list[dict] = []
        with self._connection() as connection:
            self._require_role(
                connection,
                actor,
                {"vendeuse", "gerant"},
                "Rôle non autorisé pour synchroniser la file d'envoi.",
            )
            pending = connection.execute(
                "SELECT * FROM outbox WHERE status = 'en_attente' ORDER BY created_at"
            ).fetchall()
            for item in pending:
                invoice = connection.execute(
                    "SELECT * FROM invoices WHERE id = ?", (item["invoice_id"],)
                ).fetchone()
                connection.execute(
                    "UPDATE outbox SET status = 'envoye', sent_at = ? WHERE id = ?",
                    (now, item["id"]),
                )
                payload = json.loads(item["payload"])
                connection.execute(
                    """INSERT OR IGNORE INTO status_events
                       (id, invoice_id, event_type, channel, detail, created_by, created_at, idempotency_key)
                       VALUES (?, ?, 'EMISE', ?, ?, ?, ?, ?)""",
                    (
                        f"EVT-{item['idempotency_key']}",
                        item["invoice_id"],
                        item["channel"],
                        payload.get("message", ""),
                        actor,
                        now,
                        item["idempotency_key"],
                    ),
                )
                if invoice:
                    connection.execute(
                        "UPDATE dossiers SET status = 'ÉMISE', updated_at = ? WHERE id = ?",
                        (now, invoice["dossier_id"]),
                    )
                    self._append_audit(
                        connection,
                        actor,
                        "INVOICE_EMITTED",
                        invoice["dossier_id"],
                        {"outbox_status": "en_attente"},
                        {"status": "EMISE", "invoice_id": item["invoice_id"], "channel": item["channel"], "synced": True},
                        now,
                    )
                synced.append({"id": item["id"], "invoice_id": item["invoice_id"], "channel": item["channel"]})
            connection.commit()
        return {"synced_count": len(synced), "synced": synced}

    def get_outbox(self) -> list[dict]:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM outbox ORDER BY created_at DESC").fetchall()
        return [
            {**dict(r), "payload": json.loads(r["payload"])}
            for r in rows
        ]

    def add_payment(
        self,
        invoice_id: str,
        amount: int,
        mode: str,
        reference: str,
        entered_by: str,
        idempotency_key: str,
        *,
        status: str = "confirme",
    ) -> dict:
        if amount < 0:
            raise WorkflowError(422, "Le montant ne peut pas être négatif")
        if status not in ("confirme", "rejete", "annule"):
            raise WorkflowError(422, f"Statut de règlement invalide : {status}")

        now = utc_now()
        with self._connection() as connection:
            self._require_role(
                connection,
                entered_by,
                {"vendeuse", "gerant"},
                "Rôle non autorisé pour enregistrer un règlement.",
            )
            existing = connection.execute(
                "SELECT * FROM payments WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing:
                return dict(existing)

            invoice = connection.execute(
                "SELECT * FROM invoices WHERE id = ? OR number = ?", (invoice_id, invoice_id)
            ).fetchone()
            if invoice is None:
                raise WorkflowError(404, "Facture inconnue")

            real_invoice_id = invoice["id"]
            clean_ref = reference.strip() or "SIMULATION"
            fictive_ref = clean_ref if clean_ref.upper().startswith("FICTIF") else f"FICTIF - {clean_ref}"

            payment_id = f"PAY-{idempotency_key}"
            connection.execute(
                """INSERT INTO payments
                   (id, invoice_id, amount, mode, reference, status,
                    paid_at, entered_by, idempotency_key)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (payment_id, real_invoice_id, amount, mode, fictive_ref, status, now, entered_by, idempotency_key),
            )
            action = "PAYMENT_ADDED" if status == "confirme" else "PAYMENT_REJECTED"
            self._append_audit(
                connection,
                entered_by,
                action,
                invoice["dossier_id"],
                None,
                {
                    "payment_id": payment_id,
                    "invoice_id": real_invoice_id,
                    "amount": amount,
                    "mode": mode,
                    "reference": fictive_ref,
                    "status": status,
                },
                now,
            )
            result = connection.execute(
                "SELECT * FROM payments WHERE id = ?", (payment_id,)
            ).fetchone()
            connection.commit()
            return dict(result)

    def add_credit(
        self,
        invoice_id: str,
        amount: int,
        reason: str,
        created_by: str,
        creator_role: str,
        idempotency_key: str,
        lines: list[dict] | None = None,
    ) -> dict:
        if creator_role != "gerant":
            raise WorkflowError(403, "Seul un gérant peut créer un avoir.")
        if amount <= 0:
            raise WorkflowError(422, "Le montant de l'avoir doit être strictement positif.")
        if not reason or not reason.strip():
            raise WorkflowError(422, "Un motif est obligatoire pour créer un avoir.")

        now = utc_now()
        with self._connection() as connection:
            self._require_role(
                connection,
                created_by,
                {"gerant"},
                "Seul un gérant peut créer un avoir.",
            )
            existing = connection.execute(
                "SELECT * FROM credits WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing:
                return dict(existing)

            connection.execute("BEGIN IMMEDIATE")
            invoice = connection.execute(
                "SELECT * FROM invoices WHERE id = ? OR number = ?", (invoice_id, invoice_id)
            ).fetchone()
            if invoice is None:
                raise WorkflowError(404, "Facture inconnue")

            real_invoice_id = invoice["id"]
            existing_credits = connection.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM credits WHERE invoice_id = ?",
                (real_invoice_id,),
            ).fetchone()[0]
            if existing_credits + amount > invoice["total_ttc"]:
                raise WorkflowError(
                    422,
                    "Le cumul des avoirs ne peut pas dépasser le total TTC de la facture.",
                )

            counter = connection.execute(
                "UPDATE counters SET value = value + 1 WHERE name = 'credit' RETURNING value"
            ).fetchone()
            credit_number = f"AV-2026-{counter['value']:06d}"
            credit_id = f"CRD-{counter['value']:06d}"

            connection.execute(
                """INSERT INTO credits
                   (id, invoice_id, number, amount, reason, lines_json, created_by, created_at, idempotency_key)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    credit_id,
                    real_invoice_id,
                    credit_number,
                    amount,
                    reason.strip(),
                    json.dumps(lines or [], ensure_ascii=False),
                    created_by,
                    now,
                    idempotency_key,
                ),
            )
            self._append_audit(
                connection,
                created_by,
                "CREDIT_CREATED",
                invoice["dossier_id"],
                None,
                {
                    "credit_id": credit_id,
                    "number": credit_number,
                    "invoice_id": real_invoice_id,
                    "amount": amount,
                    "reason": reason.strip(),
                },
                now,
            )
            connection.commit()
            row = connection.execute("SELECT * FROM credits WHERE id = ?", (credit_id,)).fetchone()
            return dict(row)

    def add_refund(
        self,
        invoice_id: str,
        amount: int,
        reason: str,
        created_by: str,
        creator_role: str,
        idempotency_key: str,
        *,
        payment_id: str | None = None,
        credit_id: str | None = None,
        status: str = "confirme",
    ) -> dict:
        if creator_role != "gerant":
            raise WorkflowError(403, "Seul un gérant peut enregistrer un remboursement.")
        if amount <= 0:
            raise WorkflowError(422, "Le montant du remboursement doit être positif.")
        if not reason or not reason.strip():
            raise WorkflowError(422, "Un motif est obligatoire pour un remboursement.")

        now = utc_now()
        with self._connection() as connection:
            self._require_role(
                connection,
                created_by,
                {"gerant"},
                "Seul un gérant peut enregistrer un remboursement.",
            )
            existing = connection.execute(
                "SELECT * FROM refunds WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing:
                return dict(existing)

            invoice = connection.execute(
                "SELECT * FROM invoices WHERE id = ? OR number = ?", (invoice_id, invoice_id)
            ).fetchone()
            if invoice is None:
                raise WorkflowError(404, "Facture inconnue")

            real_invoice_id = invoice["id"]
            refund_id = f"RMB-{idempotency_key}"
            ref = f"FICTIF-RMB-{idempotency_key[:12]}"
            connection.execute(
                """INSERT INTO refunds
                   (id, invoice_id, payment_id, credit_id, amount, reason, reference,
                    status, created_by, created_at, idempotency_key)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    refund_id,
                    real_invoice_id,
                    payment_id,
                    credit_id,
                    amount,
                    reason.strip(),
                    ref,
                    status,
                    created_by,
                    now,
                    idempotency_key,
                ),
            )
            self._append_audit(
                connection,
                created_by,
                "REFUND_ADDED",
                invoice["dossier_id"],
                None,
                {
                    "refund_id": refund_id,
                    "invoice_id": real_invoice_id,
                    "amount": amount,
                    "reason": reason.strip(),
                    "reference": ref,
                    "status": status,
                },
                now,
            )
            connection.commit()
            row = connection.execute("SELECT * FROM refunds WHERE id = ?", (refund_id,)).fetchone()
            return dict(row)

    def get_balance(self, invoice_id: str) -> dict:
        with self._connection() as connection:
            invoice = connection.execute(
                "SELECT * FROM invoices WHERE id = ? OR number = ?", (invoice_id, invoice_id)
            ).fetchone()
            if invoice is None:
                raise WorkflowError(404, "Facture inconnue")
            real_id = invoice["id"]
            total_paid = connection.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE invoice_id = ? AND status = 'confirme'",
                (real_id,),
            ).fetchone()[0]
            total_credits = connection.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM credits WHERE invoice_id = ?",
                (real_id,),
            ).fetchone()[0]
            total_refunds = connection.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM refunds WHERE invoice_id = ? AND status = 'confirme'",
                (real_id,),
            ).fetchone()[0]
            pending_refunds = connection.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM refunds WHERE invoice_id = ? AND status = 'en_cours'",
                (real_id,),
            ).fetchone()[0]

            net_due = invoice["total_ttc"] - total_credits
            balance = net_due - total_paid + total_refunds
            if pending_refunds > 0:
                financial_status = "REMBOURSEMENT_EN_COURS"
            elif balance > 0:
                financial_status = "PARTIELLEMENT_RÉGLÉE" if total_paid else "NON_RÉGLÉE"
            elif balance == 0:
                financial_status = "RÉGLÉE"
            else:
                financial_status = "TROP_PERÇU"

            return {
                "invoice_id": real_id,
                "invoice_number": invoice["number"],
                "total_ttc": int(invoice["total_ttc"]),
                "net_due": int(net_due),
                "confirmed_payments": int(total_paid),
                "paid": int(total_paid),
                "refund_credits": int(total_credits),
                "credits": int(total_credits),
                "confirmed_refunds": int(total_refunds),
                "balance": int(balance),
                "financial_status": financial_status,
                "financial_status_code": strip_accents_code(financial_status),
            }

    # ------------------------------------------------------------------ Reads
    def list_dossiers(self) -> list[dict]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT id FROM dossiers ORDER BY created_at DESC"
            ).fetchall()
        return [self.get_dossier(r["id"]) for r in rows]

    def get_dossier(self, dossier_id: str) -> dict:
        with self._connection() as connection:
            dossier = connection.execute(
                "SELECT * FROM dossiers WHERE id = ?", (dossier_id,)
            ).fetchone()
            if dossier is None:
                raise WorkflowError(404, "Dossier inconnu")
            invoice = connection.execute(
                "SELECT * FROM invoices WHERE dossier_id = ?", (dossier_id,)
            ).fetchone()
            steps = [
                r["step"]
                for r in connection.execute(
                    "SELECT step FROM processing_steps WHERE dossier_id = ? AND status = 'terminee'",
                    (dossier_id,),
                ).fetchall()
            ]
            open_anomalies = connection.execute(
                "SELECT COUNT(*) FROM anomalies WHERE dossier_id = ? AND status = 'ouverte'",
                (dossier_id,),
            ).fetchone()[0]

        invoice_id = invoice["id"] if invoice else None
        invoice_number = invoice["number"] if invoice else None
        financial_status = "NON_REGLEE"
        if invoice_id:
            bal = self.get_balance(invoice_id)
            financial_status = bal["financial_status_code"]

        content = json.loads(dossier["content"] or "{}")
        return {
            "dossier_id": dossier["id"],
            "doc_status": strip_accents_code(dossier["status"]),
            "financial_status": financial_status,
            "invoice_number": invoice_number,
            "invoice_id": invoice_id,
            "initiator": dossier["created_by"],
            "version": int(dossier["version"]),
            "open_anomalies": int(open_anomalies),
            "total_ttc": int(content.get("total_ttc", 0)),
            "client_name": (content.get("client") or {}).get("name"),
            "steps": steps,
            "created_at": dossier["created_at"],
            "updated_at": dossier["updated_at"],
        }

    def get_messages(self, dossier_id: str) -> list[dict]:
        with self._connection() as connection:
            dossier = connection.execute("SELECT id FROM dossiers WHERE id = ?", (dossier_id,)).fetchone()
            if dossier is None:
                raise WorkflowError(404, "Dossier inconnu")
            rows = connection.execute(
                "SELECT * FROM conversation_messages WHERE dossier_id = ? ORDER BY position",
                (dossier_id,),
            ).fetchall()
        return [
            {
                "id": r["message_id"],
                "time": _extract_time_hm(r["timestamp"]),
                "timestamp": r["timestamp"],
                "author": r["author"],
                "role": r["role"],
                "text": r["text"],
                "type_message": r["type_message"],
            }
            for r in rows
        ]

    def get_extractions(self, dossier_id: str) -> list[dict]:
        with self._connection() as connection:
            dossier = connection.execute("SELECT id FROM dossiers WHERE id = ?", (dossier_id,)).fetchone()
            if dossier is None:
                raise WorkflowError(404, "Dossier inconnu")
            rows = connection.execute(
                "SELECT * FROM extracted_fields WHERE dossier_id = ? ORDER BY position",
                (dossier_id,),
            ).fetchall()

        out: list[dict] = []
        for r in rows:
            effective = r["corrected_value"] if r["corrected_value"] is not None else r["normalized_value"]
            out.append({
                "field": r["field_name"],
                "value": effective,
                "raw_value": r["raw_value"],
                "original_value": r["normalized_value"],
                "ref": r["ref"],
                "source": {
                    "message_id": r["message_id"],
                    "text": r["source_text"],
                    "start": r["start_pos"],
                    "end": r["end_pos"],
                },
                "confidence": float(r["confidence"]),
                "couleur": r["couleur"],
                "origin": r["origin"],
                "status": r["status"],
                "model_version": r["model_version"],
                "confirmed": bool(r["confirmed"]),
                "confirmed_by": r["confirmed_by"],
                "corrected": r["corrected_value"] is not None,
            })
        return out

    def _format_anomaly(self, row: dict) -> dict:
        is_resolved = strip_accents_code(row.get("status")) == "RESOLUE"
        return {
            "id": row["id"],
            "dossier_id": row["dossier_id"],
            "code": row["code"],
            "type": row["code"],
            "severity": row.get("severity", "bloquante"),
            "resolved": is_resolved,
            "resolution": row.get("justification") or "",
            "resolved_by": row.get("resolved_by"),
            "resolved_at": row.get("resolved_at"),
            "concerned_value": row.get("concerned_value"),
            "message": row["description"],
            "status": row["status"],
        }

    def get_anomalies(self, dossier_id: str) -> list[dict]:
        with self._connection() as connection:
            dossier = connection.execute("SELECT id FROM dossiers WHERE id = ?", (dossier_id,)).fetchone()
            if dossier is None:
                raise WorkflowError(404, "Dossier inconnu")
            rows = connection.execute(
                "SELECT * FROM anomalies WHERE dossier_id = ? ORDER BY id",
                (dossier_id,),
            ).fetchall()
        return [self._format_anomaly(dict(r)) for r in rows]

    def get_delivery(self, dossier_id: str) -> list[dict]:
        with self._connection() as connection:
            dossier = connection.execute(
                "SELECT content FROM dossiers WHERE id = ?", (dossier_id,)
            ).fetchone()
            if dossier is None:
                raise WorkflowError(404, "Dossier inconnu")
        content = json.loads(dossier["content"] or "{}")
        return content.get("delivery", [])

    def get_invoice_view(self, dossier_id: str) -> dict:
        with self._connection() as connection:
            dossier = connection.execute(
                "SELECT * FROM dossiers WHERE id = ?", (dossier_id,)
            ).fetchone()
            if dossier is None:
                raise WorkflowError(404, "Dossier inconnu")
            invoice = connection.execute(
                "SELECT * FROM invoices WHERE dossier_id = ?", (dossier_id,)
            ).fetchone()

        # If validated, ALWAYS read from the immutable frozen invoice snapshot (T21)!
        if invoice:
            frozen = json.loads(invoice["content"])
            calc = frozen.get("calculation")
            if calc:
                lines = _format_invoice_lines(calc)
                totals = _format_totals(calc)
            else:
                lines = [
                    {
                        "product_id": l.get("product_id"),
                        "label": l["description"],
                        "variant": l.get("variant"),
                        "qty": int(l["quantity"]),
                        "unit": int(l["unit_price_ht"]),
                        "amount": int(l["amount_ht"]),
                    }
                    for l in frozen.get("lines", [])
                ]
                totals = frozen.get("totals") or {
                    "subtotal": int(invoice["total_ttc"]),
                    "discount_label": "Remise (aucune)",
                    "discount": 0,
                    "base_after_discount": int(invoice["total_ttc"]),
                    "delivery": 0,
                    "base_ht": int(invoice["total_ttc"]),
                    "vat_rate": 18,
                    "vat": 0,
                    "total_ttc": int(invoice["total_ttc"]),
                }
            return {
                "invoice_id": invoice["id"],
                "invoice_number": invoice["number"],
                "content_hash": invoice["content_hash"],
                "config_hash": invoice["config_hash"],
                "validated_by": invoice["validated_by"],
                "validated_at": invoice["validated_at"],
                "client": frozen.get("client_snapshot") or frozen.get("client") or {},
                "vendor": frozen.get("vendor_snapshot") or frozen.get("vendor") or {},
                "lines": lines,
                "totals": totals,
                "calculation": calc,
            }

        content = json.loads(dossier["content"] or "{}")
        calc = content.get("calculation")
        if calc:
            lines = _format_invoice_lines(calc)
            totals = _format_totals(calc)
        else:
            lines = []
            totals = {
                "subtotal": 0,
                "discount_label": "Remise (aucune)",
                "discount": 0,
                "base_after_discount": 0,
                "delivery": 0,
                "base_ht": 0,
                "vat_rate": 18,
                "vat": 0,
                "total_ttc": int(content.get("total_ttc", 0)),
            }
        return {
            "invoice_id": None,
            "invoice_number": None,
            "content_hash": None,
            "config_hash": content.get("config_hash"),
            "client": content.get("client") or {},
            "vendor": content.get("vendor") or load_rules().get("vendor", {}),
            "lines": lines,
            "totals": totals,
            "calculation": calc,
        }

    def get_invoice_detail(self, invoice_id: str) -> dict:
        with self._connection() as connection:
            invoice = connection.execute(
                "SELECT * FROM invoices WHERE id = ? OR number = ?", (invoice_id, invoice_id)
            ).fetchone()
            if invoice is None:
                raise WorkflowError(404, "Facture inconnue")
            real_id = invoice["id"]
            events = [
                dict(r)
                for r in connection.execute(
                    "SELECT * FROM status_events WHERE invoice_id = ? ORDER BY created_at",
                    (real_id,),
                ).fetchall()
            ]
            payments = [
                dict(r)
                for r in connection.execute(
                    "SELECT * FROM payments WHERE invoice_id = ? ORDER BY paid_at",
                    (real_id,),
                ).fetchall()
            ]
            credits = [
                dict(r)
                for r in connection.execute(
                    "SELECT * FROM credits WHERE invoice_id = ? ORDER BY created_at",
                    (real_id,),
                ).fetchall()
            ]
            refunds = [
                dict(r)
                for r in connection.execute(
                    "SELECT * FROM refunds WHERE invoice_id = ? ORDER BY created_at",
                    (real_id,),
                ).fetchall()
            ]

        view = self.get_invoice_view(invoice["dossier_id"])
        balance = self.get_balance(real_id)
        return {
            **view,
            "dossier_id": invoice["dossier_id"],
            "events": events,
            "payments": payments,
            "credits": credits,
            "refunds": refunds,
            "balance": balance,
        }

    def get_credit_with_invoice(self, credit_id: str) -> tuple[dict, dict]:
        with self._connection() as connection:
            credit = connection.execute(
                "SELECT * FROM credits WHERE id = ? OR number = ?", (credit_id, credit_id)
            ).fetchone()
            if credit is None:
                raise WorkflowError(404, "Avoir inconnu")
            invoice = connection.execute(
                "SELECT * FROM invoices WHERE id = ?", (credit["invoice_id"],)
            ).fetchone()
        return dict(credit), dict(invoice)

    def _audit_detail(self, action: str, after: Any, obj: str) -> str:
        if isinstance(after, dict):
            if "field" in after:
                val = after.get("value")
                return f"{after['field']} = {val}" if val is not None else str(after["field"])
            if "anomaly_id" in after:
                return f"{after['anomaly_id']}: {after.get('justification', '')}"
            if "number" in after:
                return str(after["number"])
            if "amount" in after:
                ref = after.get("reference") or after.get("reason") or ""
                return f"{after['amount']} FCFA ({ref})"
            if "channel" in after:
                return f"Canal {after['channel']} (simulé)"
            if "empreinte" in after and after["empreinte"]:
                return str(after["empreinte"])[:20]
            if "reason" in after:
                return str(after["reason"])
        return obj

    def get_audit(self, dossier_id: str | None = None) -> list[dict]:
        with self._connection() as connection:
            if dossier_id:
                rows = connection.execute(
                    """SELECT * FROM audit_log
                       WHERE object = ? OR object = ?
                       ORDER BY id""",
                    (dossier_id, f"INV-{dossier_id}"),
                ).fetchall()
            else:
                rows = connection.execute("SELECT * FROM audit_log ORDER BY id").fetchall()

        entries: list[dict] = []
        for idx, r in enumerate(rows, start=1):
            before = json.loads(r["before"]) if r["before"] else None
            after = json.loads(r["after"]) if r["after"] else None
            entries.append({
                "n": idx,
                "id": r["id"],
                "timestamp": r["timestamp"],
                "action": r["action"],
                "user": r["actor"],
                "actor": r["actor"],
                "object": r["object"],
                "detail": self._audit_detail(r["action"], after, r["object"]),
                "before": before,
                "after": after,
                "previous_hash": r["previous_hash"],
                "hash": r["hash"],
            })
        return entries

    def verify_audit(self) -> dict:
        with self._connection() as connection:
            rows = connection.execute("SELECT * FROM audit_log ORDER BY id").fetchall()

        previous = "0" * 64
        for row in rows:
            if row["previous_hash"] != previous:
                return {"valid": False, "entries": len(rows), "broken_at": row["id"]}
            expected = audit_hash(
                row["previous_hash"],
                row["actor"],
                row["action"],
                row["object"],
                json.loads(row["before"]) if row["before"] else None,
                json.loads(row["after"]) if row["after"] else None,
                row["timestamp"],
            )
            if expected != row["hash"]:
                return {"valid": False, "entries": len(rows), "broken_at": row["id"]}
            previous = row["hash"]
        return {"valid": True, "entries": len(rows), "broken_at": None}

    def get_dashboard(self) -> dict:
        dossiers = self.list_dossiers()
        by_status: dict[str, int] = {}
        for d in dossiers:
            st = d["doc_status"]
            by_status[st] = by_status.get(st, 0) + 1

        with self._connection() as connection:
            invoices_count = connection.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
            total_invoiced = connection.execute(
                "SELECT COALESCE(SUM(total_ttc), 0) FROM invoices"
            ).fetchone()[0]
            total_paid = connection.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'confirme'"
            ).fetchone()[0]
            total_credits = connection.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM credits"
            ).fetchone()[0]
            open_anomalies = connection.execute(
                "SELECT COUNT(*) FROM anomalies WHERE status = 'ouverte'"
            ).fetchone()[0]
            pending_outbox = connection.execute(
                "SELECT COUNT(*) FROM outbox WHERE status = 'en_attente'"
            ).fetchone()[0]

        audit_check = self.verify_audit()
        return {
            "dossiers_total": len(dossiers),
            "dossiers_by_status": by_status,
            "invoices_count": int(invoices_count),
            "total_invoiced_ttc": int(total_invoiced),
            "total_paid": int(total_paid),
            "total_credits": int(total_credits),
            "open_anomalies": int(open_anomalies),
            "pending_outbox": int(pending_outbox),
            "audit_valid": audit_check["valid"],
            "audit_entries": audit_check["entries"],
        }

    def reset_demo(self) -> dict:
        db_path = Path(self.database)
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(db_path) + suffix)
            if p.exists():
                os.remove(p)
        with connect(self.database) as connection:
            connection.executescript("")
        return {"reset": True, "database": db_path.name}

    def simulate_concurrency(
        self,
        dossier_id: str,
        validator_id: str = "USR-GER",
        validator_role: str = "gerant",
        n_requests: int = 20,
    ) -> dict:
        dossier = self.get_dossier(dossier_id)
        version = dossier["version"]

        def _call(_: int) -> dict:
            try:
                inv = self.validate_invoice(dossier_id, validator_id, validator_role, version)
                return {"ok": True, "number": inv["number"], "invoice_id": inv["id"]}
            except WorkflowError as exc:
                return {"ok": False, "status_code": exc.status_code, "detail": exc.detail}

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(n_requests, 20)) as pool:
            results = list(pool.map(_call, range(n_requests)))

        numbers = sorted({r["number"] for r in results if r.get("ok")})
        with self._connection() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM invoices WHERE dossier_id = ?", (dossier_id,)
            ).fetchone()[0]

        return {
            "dossier_id": dossier_id,
            "requests": n_requests,
            "succeeded": sum(1 for r in results if r.get("ok")),
            "conflicts": sum(1 for r in results if r.get("status_code") == 409),
            "unique_numbers": numbers,
            "invoices_in_db": int(count),
        }
