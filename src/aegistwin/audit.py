from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from .storage import Database, canonical_json

GENESIS_HASH = "0" * 64


def _entry_hash(
    sequence: int,
    created_at: str,
    entry_type: str,
    entity_id: str,
    payload_json: str,
    previous_hash: str,
) -> str:
    material = "|".join(
        [str(sequence), created_at, entry_type, entity_id, payload_json, previous_hash]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class AuditChain:
    """Append-only SHA-256 chain for detecting local audit-log alteration."""

    def __init__(self, database: Database):
        self.database = database

    def append(self, entry_type: str, entity_id: str, payload: dict[str, Any]) -> str:
        payload_json = canonical_json(payload)
        created_at = datetime.now(UTC).isoformat()
        with self.database._lock, self.database.connect() as connection:
            previous = connection.execute(
                "SELECT sequence, entry_hash FROM audit_chain ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            previous_hash = previous["entry_hash"] if previous else GENESIS_HASH
            sequence = int(previous["sequence"] + 1) if previous else 1
            digest = _entry_hash(
                sequence,
                created_at,
                entry_type,
                entity_id,
                payload_json,
                previous_hash,
            )
            connection.execute(
                """
                INSERT INTO audit_chain (
                    sequence, entry_type, entity_id, payload_json,
                    previous_hash, entry_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sequence,
                    entry_type,
                    entity_id,
                    payload_json,
                    previous_hash,
                    digest,
                    created_at,
                ),
            )
        return digest

    def verify(self) -> dict[str, Any]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM audit_chain ORDER BY sequence ASC"
            ).fetchall()
        previous_hash = GENESIS_HASH
        for expected_sequence, row in enumerate(rows, start=1):
            sequence = int(row["sequence"])
            expected_hash = _entry_hash(
                sequence,
                row["created_at"],
                row["entry_type"],
                row["entity_id"],
                row["payload_json"],
                previous_hash,
            )
            if (
                sequence != expected_sequence
                or row["previous_hash"] != previous_hash
                or row["entry_hash"] != expected_hash
            ):
                return {
                    "valid": False,
                    "entries_checked": expected_sequence - 1,
                    "first_invalid_sequence": sequence,
                    "head_hash": previous_hash if previous_hash != GENESIS_HASH else None,
                }
            previous_hash = row["entry_hash"]
        return {
            "valid": True,
            "entries_checked": len(rows),
            "first_invalid_sequence": None,
            "head_hash": previous_hash if rows else None,
        }

