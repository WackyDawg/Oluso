from __future__ import annotations

from pathlib import Path

from oluso.audit import AuditChain
from oluso.storage import Database


def test_audit_chain_detects_alteration(tmp_path: Path) -> None:
    database = Database(tmp_path / "audit.db")
    database.initialize()
    chain = AuditChain(database)
    chain.append("first", "entity-1", {"score": 0.2})
    chain.append("second", "entity-2", {"score": 0.8})
    valid = chain.verify()
    assert valid["valid"] is True
    assert valid["entries_checked"] == 2

    with database.connect() as connection:
        connection.execute(
            "UPDATE audit_chain SET payload_json = ? WHERE sequence = 1",
            ('{"score":0.99}',),
        )
    invalid = chain.verify()
    assert invalid["valid"] is False
    assert invalid["first_invalid_sequence"] == 1

