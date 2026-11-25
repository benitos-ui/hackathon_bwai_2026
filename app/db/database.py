import sqlite3
from pathlib import Path


SCHEMA = """
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
    content TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS anomalies (
    id TEXT PRIMARY KEY,
    dossier_id TEXT NOT NULL,
    code TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ouverte',
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
    amount INTEGER NOT NULL CHECK (amount >= 0),
    reason TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
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

CREATE TRIGGER IF NOT EXISTS prevent_audit_update
BEFORE UPDATE ON audit_log BEGIN
    SELECT RAISE(ABORT, 'The audit log is append-only');
END;

CREATE TRIGGER IF NOT EXISTS prevent_audit_delete
BEFORE DELETE ON audit_log BEGIN
    SELECT RAISE(ABORT, 'The audit log is append-only');
END;

INSERT OR IGNORE INTO counters(name, value) VALUES ('invoice', 0);
INSERT OR IGNORE INTO users(id, name, role, password_hash) VALUES
    ('USR-VEND', 'Vendeuse', 'vendeuse', 'demo-not-a-password'),
    ('USR-GER', 'Gérant', 'gerant', 'demo-not-a-password'),
    ('USR-AUD', 'Auditeur', 'auditeur', 'demo-not-a-password');
"""


def connect(database: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(database), timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.executescript(SCHEMA)
    return connection
