"""Mock action tools with a JSONL audit log.

Every action the agent takes is appended to an audit log so the run is
fully reviewable after the fact.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_AUDIT_PATH = "audit.jsonl"


def _audit_path() -> Path:
    return Path(os.environ.get("RELAYG_AUDIT_PATH", DEFAULT_AUDIT_PATH))


def _record(action: str, ticket_id: str, **details: object) -> dict:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "ticket_id": ticket_id,
        **details,
    }
    path = _audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    return entry


def send_reply(ticket_id: str, message: str) -> dict:
    """Mock: send a reply to the customer."""
    return _record("send_reply", ticket_id, message=message)


def issue_refund(ticket_id: str, amount: float, approved_by: str) -> dict:
    """Mock: issue a refund. Records who approved it."""
    return _record("issue_refund", ticket_id, amount=amount, approved_by=approved_by)


def escalate(ticket_id: str, reason: str) -> dict:
    """Mock: escalate the ticket to a senior agent."""
    return _record("escalate", ticket_id, reason=reason)
