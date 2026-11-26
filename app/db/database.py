import hashlib
import hmac
import sqlite3
from pathlib import Path


_PASSWORD_SALT = "boutique-x-bwai-2026-demo"


def hash_password(password: str, salt: str = _PASSWORD_SALT) -> str:
    """Derive a salted PBKDF2-SHA256 hash so no plaintext password is stored."""
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000
    )
    return f"pbkdf2_sha256${salt}${derived.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    if not stored_hash or "$" not in stored_hash:
        return False
    parts = stored_hash.split("$", 2)
    if len(parts) != 3 or parts[0] != "pbkdf2_sha256":
        return False
    _, salt, _ = parts
    expected = hash_password(password, salt)
    return hmac.compare_digest(expected, stored_hash)


_DEMO_PASSWORD_HASH = hash_password("demo")


SCHEMA = f"""
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE,
    role TEXT NOT NULL CHECK (role IN ('vendeuse', 'gerant', 'auditeur')),
    password_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    fingerprint TEXT UNIQUE,
    raw_text TEXT NOT NULL DEFAULT '',
    imported_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dossiers (
    id TEXT PRIMARY KEY,
    conversation_id TEXT,
    idempotency_key TEXT UNIQUE,
    status TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '{{}}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS processing_steps (
    dossier_id TEXT NOT NULL,
    step TEXT NOT NULL,
    status TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    PRIMARY KEY (dossier_id, step),
    FOREIGN KEY (dossier_id) REFERENCES dossiers(id)
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id TEXT PRIMARY KEY,
    dossier_id TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    timestamp TEXT,
    author TEXT NOT NULL,
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    type_message TEXT NOT NULL DEFAULT 'INFORMATION',
    UNIQUE (dossier_id, message_id),
    FOREIGN KEY (dossier_id) REFERENCES dossiers(id)
);

CREATE TABLE IF NOT EXISTS extracted_fields (
    id TEXT PRIMARY KEY,
    dossier_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    raw_value TEXT,
    normalized_value TEXT,
    ref TEXT,
    message_id TEXT,
    source_text TEXT,
    start_pos INTEGER,
    end_pos INTEGER,
    confidence REAL NOT NULL DEFAULT 0.0,
    couleur TEXT NOT NULL DEFAULT 'rouge',
    origin TEXT NOT NULL DEFAULT 'conversation',
    status TEXT NOT NULL DEFAULT 'extracted',
    model_version TEXT NOT NULL DEFAULT 'baseline-1.0',
    corrected_value TEXT,
    confirmed INTEGER NOT NULL DEFAULT 0,
    confirmed_by TEXT,
    confirmed_at TEXT,
    position INTEGER NOT NULL DEFAULT 0,
    UNIQUE (dossier_id, field_name),
    FOREIGN KEY (dossier_id) REFERENCES dossiers(id)
);

CREATE TABLE IF NOT EXISTS anomalies (
    id TEXT PRIMARY KEY,
    dossier_id TEXT NOT NULL,
    code TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'bloquante',
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ouverte',
    concerned_value TEXT,
    justification TEXT,
    resolved_by TEXT,
    resolved_at TEXT,
    FOREIGN KEY (dossier_id) REFERENCES dossiers(id)
);

CREATE TABLE IF NOT EXISTS invoices (
    id TEXT PRIMARY KEY,
    dossier_id TEXT UNIQUE NOT NULL,
    number TEXT UNIQUE NOT NULL,
    total_ttc INTEGER NOT NULL,
    content TEXT NOT NULL,
    content_hash TEXT UNIQUE NOT NULL,
    config_hash TEXT,
    validated_by TEXT NOT NULL,
    validated_at TEXT NOT NULL,
    FOREIGN KEY (dossier_id) REFERENCES dossiers(id)
);

CREATE TABLE IF NOT EXISTS invoice_lines (
    id TEXT PRIMARY KEY,
    invoice_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    product_id TEXT,
    description TEXT NOT NULL,
    variant TEXT,
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    unit_price_ht INTEGER NOT NULL,
    amount_ht INTEGER NOT NULL,
    UNIQUE (invoice_id, position),
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
);

CREATE TABLE IF NOT EXISTS status_events (
    id TEXT PRIMARY KEY,
    invoice_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    channel TEXT,
    detail TEXT,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    idempotency_key TEXT UNIQUE,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
);

CREATE TABLE IF NOT EXISTS outbox (
    id TEXT PRIMARY KEY,
    invoice_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('en_attente', 'envoye')),
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    sent_at TEXT,
    idempotency_key TEXT UNIQUE,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
);

CREATE TABLE IF NOT EXISTS payments (
    id TEXT PRIMARY KEY,
    invoice_id TEXT NOT NULL,
    amount INTEGER NOT NULL CHECK (amount >= 0),
    mode TEXT NOT NULL,
    reference TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('confirme', 'rejete', 'annule')),
    paid_at TEXT NOT NULL,
    entered_by TEXT NOT NULL,
    idempotency_key TEXT UNIQUE,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
);

CREATE TABLE IF NOT EXISTS credits (
    id TEXT PRIMARY KEY,
    invoice_id TEXT NOT NULL,
    number TEXT UNIQUE,
    amount INTEGER NOT NULL CHECK (amount >= 0),
    reason TEXT NOT NULL,
    lines_json TEXT NOT NULL DEFAULT '[]',
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    idempotency_key TEXT UNIQUE,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
);

CREATE TABLE IF NOT EXISTS refunds (
    id TEXT PRIMARY KEY,
    invoice_id TEXT NOT NULL,
    payment_id TEXT,
    credit_id TEXT,
    amount INTEGER NOT NULL CHECK (amount >= 0),
    reason TEXT NOT NULL,
    reference TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('confirme', 'en_cours', 'annule')),
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    idempotency_key TEXT UNIQUE,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id)
);

CREATE TABLE IF NOT EXISTS counters (
    name TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    object TEXT NOT NULL,
    before TEXT,
    after TEXT,
    previous_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS prevent_invoice_update
BEFORE UPDATE ON invoices BEGIN
    SELECT RAISE(ABORT, 'A validated invoice is immutable');
END;

CREATE TRIGGER IF NOT EXISTS prevent_invoice_delete
BEFORE DELETE ON invoices BEGIN
    SELECT RAISE(ABORT, 'A validated invoice is immutable');
END;

CREATE TRIGGER IF NOT EXISTS prevent_invoice_line_update
BEFORE UPDATE ON invoice_lines BEGIN
    SELECT RAISE(ABORT, 'Validated invoice lines are immutable');
END;

CREATE TRIGGER IF NOT EXISTS prevent_invoice_line_delete
BEFORE DELETE ON invoice_lines BEGIN
    SELECT RAISE(ABORT, 'Validated invoice lines are immutable');
END;

CREATE TRIGGER IF NOT EXISTS prevent_credit_update
BEFORE UPDATE ON credits BEGIN
    SELECT RAISE(ABORT, 'A validated credit note is immutable');
END;

CREATE TRIGGER IF NOT EXISTS prevent_credit_delete
BEFORE DELETE ON credits BEGIN
    SELECT RAISE(ABORT, 'A validated credit note is immutable');
END;

CREATE TRIGGER IF NOT EXISTS prevent_audit_update
BEFORE UPDATE ON audit_log BEGIN
    SELECT RAISE(ABORT, 'The audit log is append-only');
END;

CREATE TRIGGER IF NOT EXISTS prevent_audit_delete
BEFORE DELETE ON audit_log BEGIN
    SELECT RAISE(ABORT, 'The audit log is append-only');
END;

INSERT OR IGNORE INTO counters(name, value) VALUES ('invoice', 0);
INSERT OR IGNORE INTO counters(name, value) VALUES ('dossier', 0);
INSERT OR IGNORE INTO counters(name, value) VALUES ('credit', 0);
INSERT OR IGNORE INTO users(id, name, role, password_hash) VALUES
    ('USR-VEND', 'Vendeuse', 'vendeuse', '{_DEMO_PASSWORD_HASH}'),
    ('USR-GER', 'Gérant', 'gerant', '{_DEMO_PASSWORD_HASH}'),
    ('USR-AUD', 'Auditeur', 'auditeur', '{_DEMO_PASSWORD_HASH}');
"""


def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    cols = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _migrate(connection: sqlite3.Connection) -> None:
    _ensure_column(connection, "conversations", "raw_text", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "anomalies", "severity", "TEXT NOT NULL DEFAULT 'bloquante'")
    _ensure_column(connection, "anomalies", "concerned_value", "TEXT")
    _ensure_column(connection, "invoices", "config_hash", "TEXT")
    _ensure_column(connection, "credits", "number", "TEXT")
    _ensure_column(connection, "credits", "lines_json", "TEXT NOT NULL DEFAULT '[]'")
    _ensure_column(connection, "credits", "idempotency_key", "TEXT")
    # Upgrade legacy non-hashed demo password rows cleanly
    connection.execute(
        "UPDATE users SET password_hash = ? WHERE password_hash = 'demo-not-a-password'",
        (_DEMO_PASSWORD_HASH,),
    )


def connect(database: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(database), timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.executescript(SCHEMA)
    _migrate(connection)
    connection.commit()
    return connection
