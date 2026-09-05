from __future__ import annotations

import hashlib
import hmac
import json
import queue
import sqlite3
import threading
import weakref
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def recipient_key(recipient_id: str) -> str:
    """Tokenise recipient identifiers before shared reputation storage."""

    return hashlib.sha256(recipient_id.strip().lower().encode("utf-8")).hexdigest()


def agent_terminal_key(terminal_token: str) -> str:
    """Re-tokenise the gateway token so shared storage never exposes terminal identity."""

    return hashlib.sha256(terminal_token.strip().lower().encode("utf-8")).hexdigest()


def offline_entry_hash(
    journal_id: str,
    tenant_id: str,
    event_id: str,
    original_occurred_at: str,
    created_at: str,
    payload_json: str,
    previous_hash: str,
) -> str:
    material = "|".join(  # noqa: FLY002 - ordered canonical fields are easier to audit as a list
        [journal_id, tenant_id, event_id, original_occurred_at, created_at, payload_json, previous_hash]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _drain_pool(pool: queue.LifoQueue[sqlite3.Connection]) -> None:
    while True:
        try:
            pool.get_nowait().close()
        except queue.Empty:
            return
        except sqlite3.Error:  # pragma: no cover - already closed or broken handle
            continue


class Database:
    """Small SQLite repository with explicit, auditable persistence operations."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        # A scored event touches the database ~40 times. Opening a fresh connection (file
        # open + three PRAGMAs) for each call was ~30% of request latency, so idle
        # connections are pooled. Semantics are unchanged: each `connect()` block is still
        # its own connection with commit-on-success / rollback-on-error.
        self._pool: queue.LifoQueue[sqlite3.Connection] = queue.LifoQueue()
        self._pool_size = 8
        self._closed = False
        # Drain the pool on garbage collection or interpreter exit without holding a strong
        # reference to self; __del__ would run after module teardown and leak connections.
        weakref.finalize(self, _drain_pool, self._pool)

    def _open(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        try:
            connection = self._pool.get_nowait()
        except queue.Empty:
            connection = self._open()
        healthy = True
        try:
            yield connection
            connection.commit()
        except Exception:
            healthy = False
            try:
                connection.rollback()
            finally:
                connection.close()
            raise
        finally:
            if healthy:
                if self._closed or self._pool.qsize() >= self._pool_size:
                    connection.close()
                else:
                    self._pool.put(connection)

    def close(self) -> None:
        """Close pooled connections; safe to call more than once."""

        self._closed = True
        while True:
            try:
                self._pool.get_nowait().close()
            except queue.Empty:
                break


    def initialize(self) -> None:
        # Journal mode is a database property. Setting it once avoids repeated mode
        # negotiation on every short-lived connection during concurrent scoring.
        with closing(sqlite3.connect(self.path, timeout=30)) as bootstrap:
            bootstrap.execute("PRAGMA journal_mode = WAL")
            bootstrap.execute("PRAGMA synchronous = NORMAL")
        schema = """
        CREATE TABLE IF NOT EXISTS accounts (
            account_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            shared_device_allowed INTEGER NOT NULL DEFAULT 0,
            regret_limit_30d INTEGER NOT NULL DEFAULT 3,
            trusted_contact_masked TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL REFERENCES accounts(account_id),
            occurred_at TEXT NOT NULL,
            received_at TEXT NOT NULL,
            event_type TEXT NOT NULL,
            channel TEXT NOT NULL,
            amount REAL NOT NULL,
            payload_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_events_account_time
            ON events(account_id, occurred_at);

        CREATE TABLE IF NOT EXISTS profiles (
            account_id TEXT PRIMARY KEY REFERENCES accounts(account_id),
            profile_version INTEGER NOT NULL,
            profile_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS decisions (
            decision_id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL UNIQUE REFERENCES events(event_id),
            account_id TEXT NOT NULL REFERENCES accounts(account_id),
            risk_score REAL NOT NULL,
            model_score REAL,
            anomaly_score REAL NOT NULL,
            profile_confidence REAL NOT NULL,
            risk_level TEXT NOT NULL,
            action TEXT NOT NULL,
            model_version TEXT NOT NULL,
            reasons_json TEXT NOT NULL,
            customer_explanation TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            risk_window_json TEXT NOT NULL,
            decision_confidence_json TEXT NOT NULL,
            recipient_reputation_json TEXT NOT NULL,
            recourse_json TEXT NOT NULL,
            feature_snapshot_json TEXT NOT NULL,
            policy_json TEXT NOT NULL,
            uncertainty_note TEXT,
            audit_hash TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_decisions_account_time
            ON decisions(account_id, created_at);

        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            decision_id TEXT NOT NULL REFERENCES decisions(decision_id),
            label TEXT NOT NULL,
            analyst_id TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS recipient_reputation (
            recipient_key TEXT PRIMARY KEY,
            confirmed_reports INTEGER NOT NULL,
            distinct_accounts_json TEXT NOT NULL,
            first_confirmed_at TEXT NOT NULL,
            last_confirmed_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            status TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS agent_terminal_reputation (
            tenant_id TEXT NOT NULL,
            terminal_key TEXT NOT NULL,
            confirmed_reports INTEGER NOT NULL,
            distinct_accounts_json TEXT NOT NULL,
            first_confirmed_at TEXT NOT NULL,
            last_confirmed_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            status TEXT NOT NULL,
            PRIMARY KEY (tenant_id, terminal_key)
        );

        CREATE TABLE IF NOT EXISTS audit_chain (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            previous_hash TEXT NOT NULL,
            entry_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS event_trust (
            event_id TEXT PRIMARY KEY REFERENCES events(event_id),
            trust_state TEXT NOT NULL,
            eligible_after TEXT,
            updated_at TEXT NOT NULL,
            reason TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_event_trust_state ON event_trust(trust_state, eligible_after);

        CREATE TABLE IF NOT EXISTS transaction_lifecycle (
            event_id TEXT PRIMARY KEY REFERENCES events(event_id),
            state TEXT NOT NULL,
            version INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS lifecycle_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL REFERENCES events(event_id),
            from_state TEXT NOT NULL,
            to_state TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            idempotency_key TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS campaign_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id TEXT NOT NULL,
            signature TEXT NOT NULL,
            account_id TEXT NOT NULL,
            stages_json TEXT NOT NULL,
            occurred_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_campaign_signature_time
            ON campaign_memory(tenant_id, signature, occurred_at);
        CREATE TABLE IF NOT EXISTS review_cases (
            case_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            decision_id TEXT NOT NULL REFERENCES decisions(decision_id),
            status TEXT NOT NULL,
            priority REAL NOT NULL,
            random_audit INTEGER NOT NULL DEFAULT 0,
            assigned_to TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS appeals (
            appeal_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            decision_id TEXT NOT NULL REFERENCES decisions(decision_id),
            reason TEXT NOT NULL,
            contact_channel TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            status TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS consortium_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipient_token TEXT NOT NULL,
            institution_token TEXT NOT NULL,
            confidence REAL NOT NULL,
            evidence_class TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(recipient_token, institution_token)
        );
        CREATE TABLE IF NOT EXISTS fraud_sketch_reports (
            report_id TEXT PRIMARY KEY,
            indicator_type TEXT NOT NULL,
            indicator_token TEXT NOT NULL,
            epoch_id TEXT NOT NULL,
            institution_token TEXT NOT NULL,
            confidence REAL NOT NULL,
            evidence_class TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            status TEXT NOT NULL,
            signature_digest TEXT NOT NULL,
            created_at TEXT NOT NULL,
            revoked_at TEXT,
            revocation_reason TEXT,
            UNIQUE(indicator_type, indicator_token, institution_token)
        );
        CREATE INDEX IF NOT EXISTS idx_fraud_sketch_lookup
            ON fraud_sketch_reports(indicator_type, indicator_token, status, expires_at);
        CREATE INDEX IF NOT EXISTS idx_fraud_sketch_institution_time
            ON fraud_sketch_reports(institution_token, created_at);
        CREATE TABLE IF NOT EXISTS fraud_sketch_nonces (
            nonce TEXT PRIMARY KEY,
            institution_token TEXT NOT NULL,
            claimed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fraud_sketch_capsules (
            capsule_id TEXT PRIMARY KEY,
            indicator_type TEXT NOT NULL,
            indicator_token TEXT NOT NULL,
            epoch_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            signature TEXT NOT NULL,
            issued_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            UNIQUE(indicator_type, indicator_token)
        );
        CREATE INDEX IF NOT EXISTS idx_fraud_sketch_capsule_lookup
            ON fraud_sketch_capsules(indicator_type, indicator_token, active, expires_at);
        CREATE TABLE IF NOT EXISTS privacy_requests (
            request_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            account_id TEXT NOT NULL,
            request_type TEXT NOT NULL,
            requester_id TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit_anchors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            head_hash TEXT NOT NULL,
            signature TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS resilience_state (
            tenant_id TEXT PRIMARY KEY,
            mode TEXT NOT NULL,
            dependencies_json TEXT NOT NULL,
            previous_mode TEXT NOT NULL,
            source_id TEXT NOT NULL,
            last_heartbeat_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS resilience_capsules (
            capsule_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            signature TEXT NOT NULL,
            issued_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS idx_resilience_capsule_tenant
            ON resilience_capsules(tenant_id, active, expires_at);
        CREATE TABLE IF NOT EXISTS resilience_nonces (
            nonce TEXT PRIMARY KEY,
            observed_at TEXT NOT NULL,
            claimed_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS offline_journal (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            journal_id TEXT NOT NULL UNIQUE,
            tenant_id TEXT NOT NULL,
            event_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            previous_hash TEXT NOT NULL,
            entry_hash TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            original_occurred_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            reconciled_at TEXT,
            reconciliation_json TEXT NOT NULL DEFAULT '{}',
            attempt_count INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_offline_journal_pending
            ON offline_journal(tenant_id, status, sequence);
        CREATE TABLE IF NOT EXISTS reconciliation_runs (
            run_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL,
            processed INTEGER NOT NULL DEFAULT 0,
            failed INTEGER NOT NULL DEFAULT 0,
            duplicate_actions INTEGER NOT NULL DEFAULT 0,
            integrity_valid INTEGER NOT NULL DEFAULT 0
        );
        """
        with self._lock, self.connect() as connection:
            connection.executescript(schema)
            decision_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(decisions)").fetchall()
            }
            if "customer_explanation" not in decision_columns:
                connection.execute(
                    "ALTER TABLE decisions ADD COLUMN customer_explanation TEXT NOT NULL "
                    "DEFAULT 'This decision predates customer-facing explanations.'"
                )
            if "evidence_json" not in decision_columns:
                connection.execute(
                    "ALTER TABLE decisions ADD COLUMN evidence_json TEXT NOT NULL DEFAULT "
                    "'{\"mode\":\"legacy\",\"coverage\":0.0,\"available_signals\":[],"
                    "\"missing_optional_signals\":[]}'"
                )
            if "risk_window_json" not in decision_columns:
                connection.execute(
                    "ALTER TABLE decisions ADD COLUMN risk_window_json TEXT NOT NULL DEFAULT "
                    "'{\"state\":\"clear\",\"score\":0.0,\"hours_remaining\":0.0,"
                    "\"active_precursors\":[]}'"
                )
            if "recourse_json" not in decision_columns:
                connection.execute(
                    "ALTER TABLE decisions ADD COLUMN recourse_json TEXT NOT NULL DEFAULT '[]'"
                )
            if "decision_confidence_json" not in decision_columns:
                connection.execute(
                    "ALTER TABLE decisions ADD COLUMN decision_confidence_json TEXT NOT NULL DEFAULT "
                    "'{\"score\":0.0,\"level\":\"low\",\"profile_maturity\":0.0,"
                    "\"data_coverage\":0.0,\"scorer_agreement\":0.0,\"reasons\":[]} '"
                )
            if "recipient_reputation_json" not in decision_columns:
                connection.execute(
                    "ALTER TABLE decisions ADD COLUMN recipient_reputation_json TEXT NOT NULL DEFAULT "
                    "'{\"status\":\"clear\",\"score\":0.0,\"confirmed_reports\":0,"
                    "\"distinct_accounts\":0,\"expires_at\":null}'"
                )
            if "agent_terminal_json" not in decision_columns:
                connection.execute(
                    "ALTER TABLE decisions ADD COLUMN agent_terminal_json TEXT NOT NULL DEFAULT "
                    "'{\"status\":\"not_applicable\",\"score\":0.0,\"confirmed_reports\":0,"
                    "\"distinct_accounts\":0,\"quarantined\":false,\"expires_at\":null}'"
                )
            if "fraud_sketch_json" not in decision_columns:
                connection.execute(
                    "ALTER TABLE decisions ADD COLUMN fraud_sketch_json TEXT NOT NULL DEFAULT "
                    "'{\"status\":\"clear\",\"score\":0.0,\"confidence\":0.0,"
                    "\"independent_institutions\":0,\"active_reports\":0,"
                    "\"matched_indicators\":[],\"source_mode\":\"live\","
                    "\"local_corroboration\":false,\"action_ceiling\":\"monitor\","
                    "\"expires_at\":null}'"
                )
            for name, ddl in {
                "tenant_id": "TEXT NOT NULL DEFAULT 'default'",
                "campaign_json": "TEXT NOT NULL DEFAULT '{}'",
                "learning_json": "TEXT NOT NULL DEFAULT '{}'",
                "provenance_json": "TEXT NOT NULL DEFAULT '{}'",
                "transaction_state": "TEXT NOT NULL DEFAULT 'created'",
                "resilience_json": "TEXT NOT NULL DEFAULT '{\"mode\":\"online\",\"confidence_multiplier\":1.0,\"unavailable_sources\":[],\"evidence_freshness\":{},\"capsule_valid\":false,\"safety_envelope_applied\":false}'",
            }.items():
                if name not in decision_columns:
                    connection.execute(f"ALTER TABLE decisions ADD COLUMN {name} {ddl}")
            account_columns = {row["name"] for row in connection.execute("PRAGMA table_info(accounts)")}
            if "tenant_id" not in account_columns:
                connection.execute("ALTER TABLE accounts ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default'")
            event_columns = {row["name"] for row in connection.execute("PRAGMA table_info(events)")}
            if "tenant_id" not in event_columns:
                connection.execute("ALTER TABLE events ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default'")
            # get_network_events() scans a tenant-wide time window on every score; without this
            # index it is a full-table scan that grows linearly with history.
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_tenant_time ON events(tenant_id, occurred_at)"
            )
            decision_index_columns = {row["name"] for row in connection.execute("PRAGMA table_info(decisions)")}
            if "tenant_id" in decision_index_columns:
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_decisions_tenant_time ON decisions(tenant_id, created_at)"
                )

    def create_account(self, account: dict[str, Any], tenant_id: str = "default") -> dict[str, Any]:
        created_at = iso_utc(utc_now())
        with self._lock, self.connect() as connection:
            connection.execute(
                """
                INSERT INTO accounts (
                    account_id, display_name, shared_device_allowed,
                    regret_limit_30d, trusted_contact_masked, created_at, tenant_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    account["account_id"],
                    account["display_name"],
                    int(account["shared_device_allowed"]),
                    account["regret_limit_30d"],
                    account.get("trusted_contact_masked"),
                    created_at,
                    tenant_id,
                ),
            )
        return self.get_account(account["account_id"], tenant_id) or {}

    def get_account(self, account_id: str, tenant_id: str = "default") -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM accounts WHERE account_id = ? AND tenant_id = ?", (account_id, tenant_id)
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["shared_device_allowed"] = bool(result["shared_device_allowed"])
        return result

    def event_exists(self, event_id: str, tenant_id: str = "default") -> bool:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM events WHERE event_id = ? AND tenant_id = ?", (event_id, tenant_id)
            ).fetchone()
        return row is not None

    def get_event(self, event_id: str, tenant_id: str = "default") -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM events WHERE event_id = ? AND tenant_id = ?", (event_id, tenant_id)
            ).fetchone()
        return json.loads(row["payload_json"]) if row is not None else None

    def insert_event(self, payload: dict[str, Any], tenant_id: str = "default") -> None:
        received_at = iso_utc(utc_now())
        with self._lock, self.connect() as connection:
            connection.execute(
                """
                INSERT INTO events (
                    event_id, account_id, occurred_at, received_at,
                    event_type, channel, amount, payload_json, tenant_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["event_id"],
                    payload["account_id"],
                    payload["occurred_at"],
                    received_at,
                    payload["event_type"],
                    payload["channel"],
                    float(payload.get("amount", 0.0)),
                    canonical_json(payload),
                    tenant_id,
                ),
            )
            connection.execute(
                "INSERT INTO transaction_lifecycle(event_id,state,version,updated_at) VALUES(?,?,?,?)",
                (payload["event_id"], "created", 1, received_at),
            )

    def get_events(
        self,
        account_id: str,
        *,
        tenant_id: str = "default",
        before: datetime | None = None,
        since: datetime | None = None,
        limit: int = 2000,
    ) -> list[dict[str, Any]]:
        clauses = ["account_id = ?", "tenant_id = ?"]
        params: list[Any] = [account_id, tenant_id]
        if before is not None:
            clauses.append("occurred_at < ?")
            params.append(iso_utc(before))
        if since is not None:
            clauses.append("occurred_at >= ?")
            params.append(iso_utc(since))
        params.append(limit)
        sql = f"""
            SELECT payload_json FROM events
            WHERE {' AND '.join(clauses)}
            ORDER BY occurred_at DESC
            LIMIT ?
        """
        with self.connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        events = [json.loads(row["payload_json"]) for row in reversed(rows)]
        return events

    def get_network_events(
        self,
        *,
        before: datetime,
        since: datetime,
        tenant_id: str = "default",
        limit: int = 20_000,
    ) -> list[dict[str, Any]]:
        """Return recent cross-account events for bounded recipient-graph aggregation."""

        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM events
                WHERE occurred_at < ? AND occurred_at >= ? AND tenant_id = ?
                ORDER BY occurred_at DESC LIMIT ?
                """,
                (iso_utc(before), iso_utc(since), tenant_id, limit),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in reversed(rows)]

    def save_profile(self, account_id: str, profile: dict[str, Any]) -> None:
        updated_at = iso_utc(utc_now())
        version = int(profile["profile_version"])
        with self._lock, self.connect() as connection:
            connection.execute(
                """
                INSERT INTO profiles (account_id, profile_version, profile_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(account_id) DO UPDATE SET
                    profile_version = excluded.profile_version,
                    profile_json = excluded.profile_json,
                    updated_at = excluded.updated_at
                """,
                (account_id, version, canonical_json(profile), updated_at),
            )

    def get_profile(self, account_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT profile_json, updated_at FROM profiles WHERE account_id = ?",
                (account_id,),
            ).fetchone()
        if row is None:
            return None
        profile = json.loads(row["profile_json"])
        profile["updated_at"] = row["updated_at"]
        return profile

    def insert_decision(self, decision: dict[str, Any]) -> None:
        with self._lock, self.connect() as connection:
            connection.execute(
                """
                INSERT INTO decisions (
                    decision_id, event_id, account_id, risk_score, model_score,
                    anomaly_score, profile_confidence, risk_level, action,
                    model_version, reasons_json, customer_explanation, evidence_json,
                    risk_window_json, decision_confidence_json, recipient_reputation_json,
                    agent_terminal_json, fraud_sketch_json, recourse_json,
                    feature_snapshot_json,
                    policy_json, uncertainty_note, audit_hash, created_at, tenant_id,
                    campaign_json, learning_json, provenance_json, transaction_state,
                    resilience_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision["decision_id"],
                    decision["event_id"],
                    decision["account_id"],
                    decision["risk_score"],
                    decision.get("model_score"),
                    decision["anomaly_score"],
                    decision["profile_confidence"],
                    decision["risk_level"],
                    decision["action"],
                    decision["model_version"],
                    canonical_json(decision["reasons"]),
                    decision["customer_explanation"],
                    canonical_json(decision["evidence"]),
                    canonical_json(decision["risk_window"]),
                    canonical_json(decision["decision_confidence"]),
                    canonical_json(decision["recipient_reputation"]),
                    canonical_json(decision["agent_terminal"]),
                    canonical_json(decision.get("fraud_sketch_exchange", {})),
                    canonical_json(decision["recourse_options"]),
                    canonical_json(decision["feature_snapshot"]),
                    canonical_json(decision["policy"]),
                    decision.get("uncertainty_note"),
                    decision.get("audit_hash"),
                    decision["created_at"],
                    decision.get("tenant_id", "default"),
                    canonical_json(decision.get("campaign", {})),
                    canonical_json(decision.get("learning", {})),
                    canonical_json(decision.get("provenance", {})),
                    decision.get("transaction_state", "created"),
                    canonical_json(decision.get("resilience", {})),
                ),
            )

    def set_decision_audit_hash(self, decision_id: str, audit_hash: str) -> None:
        with self._lock, self.connect() as connection:
            connection.execute(
                "UPDATE decisions SET audit_hash = ? WHERE decision_id = ?",
                (audit_hash, decision_id),
            )

    def get_decision(self, decision_id: str, tenant_id: str = "default") -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM decisions WHERE decision_id = ? AND tenant_id = ?", (decision_id, tenant_id)
            ).fetchone()
        return self._decode_decision(row) if row is not None else None

    def get_decisions(self, account_id: str, limit: int = 100, tenant_id: str = "default") -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM decisions WHERE account_id = ? AND tenant_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (account_id, tenant_id, limit),
            ).fetchall()
        return [self._decode_decision(row) for row in rows]

    @staticmethod
    def _decode_decision(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["reasons"] = json.loads(result.pop("reasons_json"))
        result["evidence"] = json.loads(result.pop("evidence_json"))
        result["risk_window"] = json.loads(result.pop("risk_window_json"))
        result["decision_confidence"] = json.loads(result.pop("decision_confidence_json"))
        result["recipient_reputation"] = json.loads(result.pop("recipient_reputation_json"))
        result["agent_terminal"] = json.loads(result.pop("agent_terminal_json"))
        result["fraud_sketch_exchange"] = json.loads(result.pop("fraud_sketch_json", "{}"))
        result["recourse_options"] = json.loads(result.pop("recourse_json"))
        result["feature_snapshot"] = json.loads(result.pop("feature_snapshot_json"))
        result["policy"] = json.loads(result.pop("policy_json"))
        result["campaign"] = json.loads(result.pop("campaign_json", "{}"))
        result["learning"] = json.loads(result.pop("learning_json", "{}"))
        result["provenance"] = json.loads(result.pop("provenance_json", "{}"))
        result["resilience"] = json.loads(result.pop("resilience_json", "{}"))
        return result

    def count_intrusive_decisions(self, account_id: str, *, days: int = 30) -> int:
        cutoff = iso_utc(utc_now() - timedelta(days=days))
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total FROM decisions
                WHERE account_id = ? AND created_at >= ?
                  AND action IN (
                    'trusted_channel_confirmation',
                    'reversible_settlement_delay',
                    'reversible_hold_and_review'
                    ,'private_safety_pause'
                  )
                """,
                (account_id, cutoff),
            ).fetchone()
        return int(row["total"] if row else 0)

    def add_feedback(self, decision_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        created_at = iso_utc(utc_now())
        with self._lock, self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO feedback (decision_id, label, analyst_id, notes, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    decision_id,
                    payload["label"],
                    payload["analyst_id"],
                    payload.get("notes"),
                    created_at,
                ),
            )
            feedback_id = int(cursor.lastrowid)
        return {
            "id": feedback_id,
            "decision_id": decision_id,
            **payload,
            "created_at": created_at,
        }

    def get_recipient_reputation(
        self, recipient_id: str | None, *, at: datetime | None = None
    ) -> dict[str, Any]:
        if not recipient_id:
            return {
                "status": "not_applicable",
                "score": 0.0,
                "confirmed_reports": 0,
                "distinct_accounts": 0,
                "expires_at": None,
                "watchlist_evidence_available": 0.0,
            }
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM recipient_reputation WHERE recipient_key = ?",
                (recipient_key(recipient_id),),
            ).fetchone()
        if row is None:
            return {
                "status": "clear",
                "score": 0.0,
                "confirmed_reports": 0,
                "distinct_accounts": 0,
                "expires_at": None,
                "watchlist_evidence_available": 1.0,
            }
        reference = (at or utc_now()).astimezone(UTC)
        expires_at = datetime.fromisoformat(row["expires_at"])
        distinct_accounts = len(json.loads(row["distinct_accounts_json"]))
        if reference >= expires_at:
            score = 0.0
            status = "expired"
        else:
            last = datetime.fromisoformat(row["last_confirmed_at"])
            age_days = max(0.0, (reference - last).total_seconds() / 86_400.0)
            base = 0.35 if distinct_accounts == 1 else 0.75 if distinct_accounts == 2 else 1.0
            score = max(0.0, base * (1.0 - age_days / 90.0))
            status = str(row["status"])
        return {
            "status": status,
            "score": round(score, 6),
            "confirmed_reports": int(row["confirmed_reports"]),
            "distinct_accounts": distinct_accounts,
            "expires_at": row["expires_at"],
            "watchlist_evidence_available": 1.0,
        }

    def record_recipient_fraud(
        self, recipient_id: str, account_id: str, *, confirmed_at: datetime | None = None
    ) -> dict[str, Any]:
        confirmed = (confirmed_at or utc_now()).astimezone(UTC)
        key = recipient_key(recipient_id)
        with self._lock, self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM recipient_reputation WHERE recipient_key = ?", (key,)
            ).fetchone()
            accounts = set(json.loads(row["distinct_accounts_json"])) if row else set()
            accounts.add(account_id)
            distinct = len(accounts)
            reports = int(row["confirmed_reports"]) + 1 if row else 1
            status = "high" if distinct >= 3 else "elevated" if distinct >= 2 else "monitor"
            first = row["first_confirmed_at"] if row else iso_utc(confirmed)
            expires = iso_utc(confirmed + timedelta(days=90))
            connection.execute(
                """
                INSERT INTO recipient_reputation (
                    recipient_key, confirmed_reports, distinct_accounts_json,
                    first_confirmed_at, last_confirmed_at, expires_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(recipient_key) DO UPDATE SET
                    confirmed_reports=excluded.confirmed_reports,
                    distinct_accounts_json=excluded.distinct_accounts_json,
                    last_confirmed_at=excluded.last_confirmed_at,
                    expires_at=excluded.expires_at,
                    status=excluded.status
                """,
                (key, reports, canonical_json(sorted(accounts)), first, iso_utc(confirmed), expires, status),
            )
        return self.get_recipient_reputation(recipient_id, at=confirmed)

    def get_agent_terminal_reputation(
        self,
        terminal_token: str | None,
        *,
        tenant_id: str = "default",
        at: datetime | None = None,
    ) -> dict[str, Any]:
        if not terminal_token:
            return {
                "status": "not_applicable",
                "score": 0.0,
                "confirmed_reports": 0,
                "distinct_accounts": 0,
                "quarantined": False,
                "expires_at": None,
                "evidence_available": 0.0,
            }
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM agent_terminal_reputation WHERE tenant_id=? AND terminal_key=?",
                (tenant_id, agent_terminal_key(terminal_token)),
            ).fetchone()
        if row is None:
            return {
                "status": "clear",
                "score": 0.0,
                "confirmed_reports": 0,
                "distinct_accounts": 0,
                "quarantined": False,
                "expires_at": None,
                "evidence_available": 1.0,
            }
        reference = (at or utc_now()).astimezone(UTC)
        expires_at = datetime.fromisoformat(row["expires_at"])
        distinct_accounts = len(json.loads(row["distinct_accounts_json"]))
        if reference >= expires_at:
            score = 0.0
            status = "expired"
        else:
            last = datetime.fromisoformat(row["last_confirmed_at"])
            age_days = max(0.0, (reference - last).total_seconds() / 86_400.0)
            base = 0.35 if distinct_accounts == 1 else 0.75 if distinct_accounts == 2 else 1.0
            score = max(0.0, base * (1.0 - age_days / 60.0))
            status = str(row["status"])
        return {
            "status": status,
            "score": round(score, 6),
            "confirmed_reports": int(row["confirmed_reports"]),
            "distinct_accounts": distinct_accounts,
            "quarantined": status == "quarantined",
            "expires_at": row["expires_at"],
            "evidence_available": 1.0,
        }

    def record_agent_terminal_fraud(
        self,
        terminal_token: str,
        account_id: str,
        *,
        tenant_id: str = "default",
        confirmed_at: datetime | None = None,
    ) -> dict[str, Any]:
        confirmed = (confirmed_at or utc_now()).astimezone(UTC)
        key = agent_terminal_key(terminal_token)
        with self._lock, self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM agent_terminal_reputation WHERE tenant_id=? AND terminal_key=?",
                (tenant_id, key),
            ).fetchone()
            accounts = set(json.loads(row["distinct_accounts_json"])) if row else set()
            accounts.add(account_id)
            distinct = len(accounts)
            reports = int(row["confirmed_reports"]) + 1 if row else 1
            status = "quarantined" if distinct >= 3 else "elevated" if distinct >= 2 else "monitor"
            first = row["first_confirmed_at"] if row else iso_utc(confirmed)
            expires = iso_utc(confirmed + timedelta(days=60))
            connection.execute(
                """
                INSERT INTO agent_terminal_reputation (
                    tenant_id,terminal_key,confirmed_reports,distinct_accounts_json,
                    first_confirmed_at,last_confirmed_at,expires_at,status
                ) VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(tenant_id,terminal_key) DO UPDATE SET
                    confirmed_reports=excluded.confirmed_reports,
                    distinct_accounts_json=excluded.distinct_accounts_json,
                    last_confirmed_at=excluded.last_confirmed_at,
                    expires_at=excluded.expires_at,
                    status=excluded.status
                """,
                (
                    tenant_id,
                    key,
                    reports,
                    canonical_json(sorted(accounts)),
                    first,
                    iso_utc(confirmed),
                    expires,
                    status,
                ),
            )
        return self.get_agent_terminal_reputation(
            terminal_token, tenant_id=tenant_id, at=confirmed
        )

    def set_event_trust(
        self, event_id: str, state: str, *, eligible_after: datetime | None = None,
        reason: str | None = None,
    ) -> None:
        now = iso_utc(utc_now())
        with self._lock, self.connect() as connection:
            connection.execute(
                """INSERT INTO event_trust(event_id,trust_state,eligible_after,updated_at,reason)
                VALUES(?,?,?,?,?) ON CONFLICT(event_id) DO UPDATE SET
                trust_state=excluded.trust_state, eligible_after=excluded.eligible_after,
                updated_at=excluded.updated_at, reason=excluded.reason""",
                (event_id, state, iso_utc(eligible_after) if eligible_after else None, now, reason),
            )

    def set_event_profile_eligibility(self, event_id: str, eligible: bool) -> None:
        with self._lock, self.connect() as connection:
            row = connection.execute("SELECT payload_json FROM events WHERE event_id=?", (event_id,)).fetchone()
            if not row:
                return
            payload = json.loads(row["payload_json"])
            payload["_profile_eligible"] = eligible
            connection.execute("UPDATE events SET payload_json=? WHERE event_id=?", (canonical_json(payload), event_id))

    def get_event_trust(self, event_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM event_trust WHERE event_id=?", (event_id,)).fetchone()
        return dict(row) if row else None

    def mature_learning_events(self, *, at: datetime | None = None) -> list[str]:
        reference = iso_utc(at or utc_now())
        with self._lock, self.connect() as connection:
            rows = connection.execute(
                "SELECT event_id FROM event_trust WHERE trust_state='pending' AND eligible_after<=?",
                (reference,),
            ).fetchall()
            ids = [str(row["event_id"]) for row in rows]
            if ids:
                connection.executemany(
                    "UPDATE event_trust SET trust_state='trusted', updated_at=? WHERE event_id=?",
                    [(reference, event_id) for event_id in ids],
                )
        return ids

    def trusted_events(self, account_id: str, *, tenant_id: str = "default") -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT e.payload_json FROM events e JOIN event_trust t ON e.event_id=t.event_id
                WHERE e.account_id=? AND e.tenant_id=? AND t.trust_state='trusted'
                ORDER BY e.occurred_at""",
                (account_id, tenant_id),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def record_campaign(
        self, tenant_id: str, signature: str, account_id: str,
        stages: list[str], occurred_at: datetime,
    ) -> dict[str, Any]:
        cutoff = iso_utc(occurred_at - timedelta(hours=24))
        with self._lock, self.connect() as connection:
            connection.execute(
                "INSERT INTO campaign_memory(tenant_id,signature,account_id,stages_json,occurred_at) VALUES(?,?,?,?,?)",
                (tenant_id, signature, account_id, canonical_json(stages), iso_utc(occurred_at)),
            )
            rows = connection.execute(
                "SELECT account_id,stages_json FROM campaign_memory WHERE tenant_id=? AND signature=? AND occurred_at>=?",
                (tenant_id, signature, cutoff),
            ).fetchall()
        all_stages = sorted({stage for row in rows for stage in json.loads(row["stages_json"])})
        return {"distinct_accounts": len({row["account_id"] for row in rows}), "stages": all_stages}

    def create_case(
        self, case_id: str, tenant_id: str, decision_id: str, priority: float,
        *, random_audit: bool = False,
    ) -> dict[str, Any]:
        now = iso_utc(utc_now())
        with self._lock, self.connect() as connection:
            connection.execute(
                "INSERT INTO review_cases VALUES(?,?,?,?,?,?,?,?,?)",
                (case_id, tenant_id, decision_id, "open", priority, int(random_audit), None, now, now),
            )
        return self.get_case(case_id, tenant_id) or {}

    def get_case(self, case_id: str, tenant_id: str = "default") -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM review_cases WHERE case_id=? AND tenant_id=?", (case_id, tenant_id)
            ).fetchone()
        return dict(row) if row else None

    def list_cases(self, tenant_id: str = "default", limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM review_cases WHERE tenant_id=? ORDER BY priority DESC,created_at LIMIT ?",
                (tenant_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_appeal(self, appeal: dict[str, Any]) -> dict[str, Any]:
        with self._lock, self.connect() as connection:
            connection.execute(
                "INSERT INTO appeals VALUES(?,?,?,?,?,?,?)",
                (appeal["appeal_id"], appeal["tenant_id"], appeal["decision_id"], appeal["reason"],
                 appeal["contact_channel"], "open", appeal["created_at"]),
            )
        return {**appeal, "status": "open"}

    def enqueue(self, topic: str, payload: dict[str, Any]) -> None:
        with self._lock, self.connect() as connection:
            connection.execute(
                "INSERT INTO outbox(topic,payload_json,status,created_at) VALUES(?,?,?,?)",
                (topic, canonical_json(payload), "pending", iso_utc(utc_now())),
            )

    def lifecycle(self, event_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM transaction_lifecycle WHERE event_id=?", (event_id,)).fetchone()
        return dict(row) if row else None

    def transition_lifecycle(
        self, event_id: str, target: str, actor: str, reason: str, idempotency_key: str,
    ) -> dict[str, Any]:
        from .platform import validate_lifecycle_transition
        now = iso_utc(utc_now())
        with self._lock, self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM lifecycle_history WHERE idempotency_key=?", (idempotency_key,)
            ).fetchone()
            if existing:
                state = connection.execute("SELECT * FROM transaction_lifecycle WHERE event_id=?", (event_id,)).fetchone()
                return {**dict(state), "idempotent_replay": True}
            row = connection.execute("SELECT * FROM transaction_lifecycle WHERE event_id=?", (event_id,)).fetchone()
            if not row:
                raise ValueError("transaction lifecycle not found")
            current = str(row["state"])
            validate_lifecycle_transition(current, target)
            connection.execute(
                "UPDATE transaction_lifecycle SET state=?,version=version+1,updated_at=? WHERE event_id=?",
                (target, now, event_id),
            )
            connection.execute("UPDATE decisions SET transaction_state=? WHERE event_id=?", (target, event_id))
            connection.execute(
                "INSERT INTO lifecycle_history(event_id,from_state,to_state,actor_id,reason,idempotency_key,created_at) VALUES(?,?,?,?,?,?,?)",
                (event_id, current, target, actor, reason, idempotency_key, now),
            )
        return {**(self.lifecycle(event_id) or {}), "idempotent_replay": False}

    def record_consortium_report(
        self, recipient_token: str, institution_token: str, confidence: float, evidence_class: str,
    ) -> dict[str, Any]:
        with self._lock, self.connect() as connection:
            connection.execute(
                """INSERT INTO consortium_reports(recipient_token,institution_token,confidence,evidence_class,created_at)
                VALUES(?,?,?,?,?) ON CONFLICT(recipient_token,institution_token) DO UPDATE SET
                confidence=excluded.confidence,evidence_class=excluded.evidence_class,created_at=excluded.created_at""",
                (recipient_token, institution_token, confidence, evidence_class, iso_utc(utc_now())),
            )
            rows = connection.execute(
                "SELECT confidence FROM consortium_reports WHERE recipient_token=?", (recipient_token,)
            ).fetchall()
        institutions = len(rows)
        score = 0.0 if institutions < 2 else min(0.92, sum(float(row["confidence"]) for row in rows) / institutions)
        return {"independent_institutions": institutions, "score": round(score, 6)}

    def consortium_score(self, recipient_token: str) -> dict[str, Any]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT confidence FROM consortium_reports WHERE recipient_token=?", (recipient_token,)
            ).fetchall()
        institutions = len(rows)
        score = 0.0 if institutions < 2 else min(0.92, sum(float(row["confidence"]) for row in rows) / institutions)
        return {"independent_institutions": institutions, "score": round(score, 6)}

    def claim_fraud_sketch_nonce(self, nonce: str, institution_token: str) -> bool:
        with self._lock, self.connect() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO fraud_sketch_nonces(nonce,institution_token,claimed_at) "
                "VALUES(?,?,?)",
                (nonce, institution_token, iso_utc(utc_now())),
            )
        return cursor.rowcount == 1

    def fraud_sketch_report_count(
        self, institution_token: str, *, since: datetime
    ) -> int:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM fraud_sketch_reports "
                "WHERE institution_token=? AND created_at>=?",
                (institution_token, iso_utc(since)),
            ).fetchone()
        return int(row["total"] if row else 0)

    def record_fraud_sketch_report(self, report: dict[str, Any]) -> dict[str, Any]:
        with self._lock, self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM fraud_sketch_reports WHERE report_id=?", (report["report_id"],)
            ).fetchone()
            if existing:
                if str(existing["signature_digest"]) != str(report["signature_digest"]):
                    raise ValueError("fraud-sketch report id has conflicting content")
                result = dict(existing)
                result["idempotent_replay"] = True
                return result
            connection.execute(
                """
                INSERT INTO fraud_sketch_reports(
                    report_id,indicator_type,indicator_token,epoch_id,institution_token,
                    confidence,evidence_class,observed_at,expires_at,status,
                    signature_digest,created_at,revoked_at,revocation_reason
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)
                ON CONFLICT(indicator_type,indicator_token,institution_token) DO UPDATE SET
                    report_id=excluded.report_id,
                    confidence=excluded.confidence,
                    evidence_class=excluded.evidence_class,
                    observed_at=excluded.observed_at,
                    expires_at=excluded.expires_at,
                    status='active',
                    signature_digest=excluded.signature_digest,
                    created_at=excluded.created_at,
                    revoked_at=NULL,
                    revocation_reason=NULL
                """,
                (
                    report["report_id"],
                    report["indicator_type"],
                    report["indicator_token"],
                    report["epoch_id"],
                    report["institution_token"],
                    float(report["confidence"]),
                    report["evidence_class"],
                    report["observed_at"],
                    report["expires_at"],
                    "active",
                    report["signature_digest"],
                    report["created_at"],
                ),
            )
            row = connection.execute(
                "SELECT * FROM fraud_sketch_reports WHERE report_id=?", (report["report_id"],)
            ).fetchone()
        result = dict(row) if row else {}
        result["idempotent_replay"] = False
        return result

    def get_fraud_sketch_report(self, report_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM fraud_sketch_reports WHERE report_id=?", (report_id,)
            ).fetchone()
        return dict(row) if row else None

    def revoke_fraud_sketch_report(
        self,
        report_id: str,
        institution_token: str,
        reason: str,
        revoked_at: datetime,
    ) -> dict[str, Any]:
        with self._lock, self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM fraud_sketch_reports WHERE report_id=?", (report_id,)
            ).fetchone()
            if row is None:
                raise KeyError(report_id)
            if str(row["institution_token"]) != institution_token:
                raise PermissionError("institution does not own this fraud-sketch report")
            if str(row["status"]) == "revoked":
                result = dict(row)
                result["idempotent_replay"] = True
                return result
            connection.execute(
                "UPDATE fraud_sketch_reports SET status='revoked',revoked_at=?,"
                "revocation_reason=? WHERE report_id=?",
                (iso_utc(revoked_at), reason, report_id),
            )
            updated = connection.execute(
                "SELECT * FROM fraud_sketch_reports WHERE report_id=?", (report_id,)
            ).fetchone()
        result = dict(updated) if updated else {}
        result["idempotent_replay"] = False
        return result

    def fraud_sketch_reports(
        self,
        indicator_type: str,
        tokens: list[str],
    ) -> list[dict[str, Any]]:
        if not tokens:
            return []
        placeholders = ",".join("?" for _ in tokens)
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM fraud_sketch_reports WHERE indicator_type=? "
                f"AND indicator_token IN ({placeholders})",
                (indicator_type, *tokens),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_fraud_sketch_capsule(
        self, payload: dict[str, Any], signature: str
    ) -> dict[str, Any]:
        with self._lock, self.connect() as connection:
            connection.execute(
                """
                INSERT INTO fraud_sketch_capsules(
                    capsule_id,indicator_type,indicator_token,epoch_id,payload_json,
                    signature,issued_at,expires_at,active
                ) VALUES(?,?,?,?,?,?,?,?,1)
                ON CONFLICT(indicator_type,indicator_token) DO UPDATE SET
                    capsule_id=excluded.capsule_id,
                    epoch_id=excluded.epoch_id,
                    payload_json=excluded.payload_json,
                    signature=excluded.signature,
                    issued_at=excluded.issued_at,
                    expires_at=excluded.expires_at,
                    active=1
                """,
                (
                    payload["capsule_id"],
                    payload["indicator_type"],
                    payload["indicator_token"],
                    payload["epoch_id"],
                    canonical_json(payload),
                    signature,
                    payload["issued_at"],
                    payload["expires_at"],
                ),
            )
        return {**payload, "signature": signature}

    def fraud_sketch_capsules(
        self, indicator_type: str, tokens: list[str]
    ) -> list[dict[str, Any]]:
        if not tokens:
            return []
        placeholders = ",".join("?" for _ in tokens)
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT payload_json,signature FROM fraud_sketch_capsules "
                f"WHERE indicator_type=? AND indicator_token IN ({placeholders}) AND active=1",
                (indicator_type, *tokens),
            ).fetchall()
        return [
            {**json.loads(row["payload_json"]), "signature": row["signature"]}
            for row in rows
        ]

    def create_privacy_request(self, request: dict[str, Any]) -> dict[str, Any]:
        with self._lock, self.connect() as connection:
            connection.execute(
                "INSERT INTO privacy_requests VALUES(?,?,?,?,?,?,?)",
                (request["request_id"], request["tenant_id"], request["account_id"], request["request_type"],
                 request["requester_id"], "queued", request["created_at"]),
            )
        return {**request, "status": "queued"}

    def decision_scores(self, tenant_id: str = "default", limit: int = 10_000) -> list[dict[str, Any]]:
        """Chronological decision summaries for governance (drift, equity, simulation)."""

        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT risk_score, action, created_at, model_version, model_score, anomaly_score,
                       feature_snapshot_json
                FROM decisions WHERE tenant_id=? ORDER BY created_at LIMIT ?
                """,
                (tenant_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def anchor_audit(self, head_hash: str, secret: str) -> dict[str, Any]:
        created_at = iso_utc(utc_now())
        signature = hmac.new(secret.encode(), f"{head_hash}|{created_at}".encode(), hashlib.sha256).hexdigest()
        with self._lock, self.connect() as connection:
            connection.execute(
                "INSERT INTO audit_anchors(head_hash,signature,created_at) VALUES(?,?,?)",
                (head_hash, signature, created_at),
            )
        return {"head_hash": head_hash, "signature": signature, "created_at": created_at}

    def save_resilience_capsule(
        self,
        capsule_id: str,
        tenant_id: str,
        payload: dict[str, Any],
        signature: str,
    ) -> dict[str, Any]:
        with self._lock, self.connect() as connection:
            connection.execute(
                "UPDATE resilience_capsules SET active=0 WHERE tenant_id=?",
                (tenant_id,),
            )
            connection.execute(
                """INSERT INTO resilience_capsules(
                capsule_id,tenant_id,payload_json,signature,issued_at,expires_at,active
                ) VALUES(?,?,?,?,?,?,1)""",
                (
                    capsule_id,
                    tenant_id,
                    canonical_json(payload),
                    signature,
                    payload["issued_at"],
                    payload["expires_at"],
                ),
            )
        return {
            "capsule_id": capsule_id,
            "tenant_id": tenant_id,
            "payload": payload,
            "signature": signature,
            "issued_at": payload["issued_at"],
            "expires_at": payload["expires_at"],
            "active": True,
        }

    def get_active_resilience_capsule(self, tenant_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT * FROM resilience_capsules
                WHERE tenant_id=? AND active=1 ORDER BY issued_at DESC LIMIT 1""",
                (tenant_id,),
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["payload"] = json.loads(result.pop("payload_json"))
        result["active"] = bool(result["active"])
        return result

    def claim_resilience_nonce(self, nonce: str, observed_at: datetime) -> bool:
        try:
            with self._lock, self.connect() as connection:
                connection.execute(
                    "INSERT INTO resilience_nonces(nonce,observed_at,claimed_at) VALUES(?,?,?)",
                    (nonce, iso_utc(observed_at), iso_utc(utc_now())),
                )
        except sqlite3.IntegrityError:
            return False
        return True

    def set_resilience_state(
        self,
        tenant_id: str,
        mode: str,
        dependencies: dict[str, bool],
        observed_at: datetime,
        previous_mode: str,
        *,
        source_id: str,
    ) -> dict[str, Any]:
        updated_at = iso_utc(utc_now())
        with self._lock, self.connect() as connection:
            connection.execute(
                """INSERT INTO resilience_state(
                tenant_id,mode,dependencies_json,previous_mode,source_id,last_heartbeat_at,updated_at
                ) VALUES(?,?,?,?,?,?,?) ON CONFLICT(tenant_id) DO UPDATE SET
                mode=excluded.mode,dependencies_json=excluded.dependencies_json,
                previous_mode=excluded.previous_mode,source_id=excluded.source_id,
                last_heartbeat_at=excluded.last_heartbeat_at,updated_at=excluded.updated_at""",
                (
                    tenant_id,
                    mode,
                    canonical_json(dependencies),
                    previous_mode,
                    source_id,
                    iso_utc(observed_at),
                    updated_at,
                ),
            )
        return self.get_resilience_state(tenant_id) or {}

    def get_resilience_state(self, tenant_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM resilience_state WHERE tenant_id=?", (tenant_id,)
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["dependencies"] = json.loads(result.pop("dependencies_json"))
        return result

    def append_offline_journal(
        self,
        journal_id: str,
        tenant_id: str,
        event_id: str,
        original_occurred_at: datetime,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        payload_json = canonical_json(payload)
        created_at = iso_utc(utc_now())
        original = iso_utc(original_occurred_at)
        with self._lock, self.connect() as connection:
            previous = connection.execute(
                "SELECT entry_hash FROM offline_journal WHERE tenant_id=? ORDER BY sequence DESC LIMIT 1",
                (tenant_id,),
            ).fetchone()
            previous_hash = str(previous["entry_hash"]) if previous else "0" * 64
            digest = offline_entry_hash(
                journal_id,
                tenant_id,
                event_id,
                original,
                created_at,
                payload_json,
                previous_hash,
            )
            connection.execute(
                """INSERT INTO offline_journal(
                journal_id,tenant_id,event_id,payload_json,previous_hash,entry_hash,status,
                original_occurred_at,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    journal_id,
                    tenant_id,
                    event_id,
                    payload_json,
                    previous_hash,
                    digest,
                    "pending",
                    original,
                    created_at,
                ),
            )
        return {
            "journal_id": journal_id,
            "tenant_id": tenant_id,
            "event_id": event_id,
            "entry_hash": digest,
            "previous_hash": previous_hash,
            "status": "pending",
            "created_at": created_at,
        }

    def list_offline_journal(
        self,
        tenant_id: str,
        *,
        status: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM offline_journal WHERE tenant_id=?"
        params: list[Any] = [tenant_id]
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY sequence LIMIT ?"
        params.append(limit)
        with self.connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            item["reconciliation"] = json.loads(item.pop("reconciliation_json"))
            results.append(item)
        return results

    def verify_offline_journal(self, tenant_id: str) -> dict[str, Any]:
        rows = self.list_offline_journal(tenant_id, limit=100_000)
        previous_hash = "0" * 64
        checked = 0
        for row in rows:
            expected = offline_entry_hash(
                str(row["journal_id"]),
                str(row["tenant_id"]),
                str(row["event_id"]),
                str(row["original_occurred_at"]),
                str(row["created_at"]),
                canonical_json(row["payload"]),
                previous_hash,
            )
            if row["previous_hash"] != previous_hash or row["entry_hash"] != expected:
                return {
                    "valid": False,
                    "entries_checked": checked,
                    "first_invalid_journal_id": row["journal_id"],
                    "head_hash": previous_hash if checked else None,
                }
            previous_hash = str(row["entry_hash"])
            checked += 1
        return {
            "valid": True,
            "entries_checked": checked,
            "first_invalid_journal_id": None,
            "head_hash": previous_hash if checked else None,
        }

    def mark_offline_reconciled(self, journal_id: str, result: dict[str, Any]) -> None:
        with self._lock, self.connect() as connection:
            connection.execute(
                """UPDATE offline_journal SET status='reconciled',reconciled_at=?,
                reconciliation_json=?,attempt_count=attempt_count+1 WHERE journal_id=? AND status='pending'""",
                (iso_utc(utc_now()), canonical_json(result), journal_id),
            )

    def start_reconciliation_run(self, run_id: str, tenant_id: str) -> None:
        with self._lock, self.connect() as connection:
            connection.execute(
                """INSERT INTO reconciliation_runs(
                run_id,tenant_id,started_at,status,integrity_valid
                ) VALUES(?,?,?,?,0)""",
                (run_id, tenant_id, iso_utc(utc_now()), "running"),
            )

    def finish_reconciliation_run(
        self,
        run_id: str,
        *,
        status: str,
        processed: int,
        failed: int,
        duplicate_actions: int,
        integrity_valid: bool,
    ) -> dict[str, Any]:
        with self._lock, self.connect() as connection:
            connection.execute(
                """UPDATE reconciliation_runs SET completed_at=?,status=?,processed=?,failed=?,
                duplicate_actions=?,integrity_valid=? WHERE run_id=?""",
                (
                    iso_utc(utc_now()),
                    status,
                    processed,
                    failed,
                    duplicate_actions,
                    int(integrity_valid),
                    run_id,
                ),
            )
            row = connection.execute(
                "SELECT * FROM reconciliation_runs WHERE run_id=?", (run_id,)
            ).fetchone()
        result = dict(row) if row else {}
        if result:
            result["integrity_valid"] = bool(result["integrity_valid"])
        return result

    def complete_reconciliation(self, tenant_id: str) -> dict[str, Any]:
        state = self.get_resilience_state(tenant_id)
        dependencies = dict(state["dependencies"]) if state else {
            "core_banking": True,
            "telco_gateway": True,
            "consortium": True,
            "recipient_graph": True,
            "model_runtime": True,
        }
        return self.set_resilience_state(
            tenant_id,
            "online",
            dependencies,
            utc_now(),
            str(state["mode"]) if state else "reconciling",
            source_id="reconciliation-engine",
        )

    def metrics(self) -> dict[str, Any]:
        with self.connect() as connection:
            account_count = connection.execute("SELECT COUNT(*) AS n FROM accounts").fetchone()["n"]
            event_count = connection.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
            decision_count = connection.execute("SELECT COUNT(*) AS n FROM decisions").fetchone()["n"]
            levels = connection.execute(
                "SELECT risk_level, COUNT(*) AS n FROM decisions GROUP BY risk_level"
            ).fetchall()
            actions = connection.execute(
                "SELECT action, COUNT(*) AS n FROM decisions GROUP BY action"
            ).fetchall()
            feedback = connection.execute(
                "SELECT label, COUNT(*) AS n FROM feedback GROUP BY label"
            ).fetchall()
            pending_learning = connection.execute("SELECT COUNT(*) n FROM event_trust WHERE trust_state='pending'").fetchone()["n"]
            open_cases = connection.execute("SELECT COUNT(*) n FROM review_cases WHERE status='open'").fetchone()["n"]
            outbox_pending = connection.execute("SELECT COUNT(*) n FROM outbox WHERE status='pending'").fetchone()["n"]
            offline_pending = connection.execute(
                "SELECT COUNT(*) n FROM offline_journal WHERE status='pending'"
            ).fetchone()["n"]
            outage_modes = connection.execute(
                "SELECT mode,COUNT(*) n FROM resilience_state GROUP BY mode"
            ).fetchall()
            active_sketches = connection.execute(
                "SELECT COUNT(*) n FROM fraud_sketch_reports "
                "WHERE status='active' AND expires_at>?",
                (iso_utc(utc_now()),),
            ).fetchone()["n"]
            active_sketch_capsules = connection.execute(
                "SELECT COUNT(*) n FROM fraud_sketch_capsules "
                "WHERE active=1 AND expires_at>?",
                (iso_utc(utc_now()),),
            ).fetchone()["n"]
        return {
            "accounts": int(account_count),
            "events": int(event_count),
            "decisions": int(decision_count),
            "decisions_by_level": {row["risk_level"]: int(row["n"]) for row in levels},
            "decisions_by_action": {row["action"]: int(row["n"]) for row in actions},
            "feedback_by_label": {row["label"]: int(row["n"]) for row in feedback},
            "pending_learning_events": int(pending_learning),
            "open_cases": int(open_cases),
            "outbox_pending": int(outbox_pending),
            "offline_journal_pending": int(offline_pending),
            "resilience_modes": {row["mode"]: int(row["n"]) for row in outage_modes},
            "active_fraud_sketch_reports": int(active_sketches),
            "active_fraud_sketch_capsules": int(active_sketch_capsules),
        }
