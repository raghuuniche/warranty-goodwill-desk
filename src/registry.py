"""
THE CLAIMS REGISTRY. The most important new idea in the multi page version.

WHY THIS EXISTS
---------------
You already have a checkpointer. It stores every step of every run and it is
what lets a paused graph resume hours later. So why add a second table?

Because a checkpointer answers "what is the state of thread X". It cannot
answer "which claims are waiting for a human right now", "what did we decide
for dealer D-8830 last week", or "show me everything that escalated today".
Those are queries over a population, not over one thread.

THE DISTINCTION, WHICH IS THE WHOLE POINT
-----------------------------------------
The checkpointer is the AGENT'S MEMORY. It exists so a run can continue.
The registry is the SYSTEM OF RECORD. It exists so the business can be run.

They have different owners, different lifespans and different audiences.
You can delete every checkpoint and the business still knows what it decided.
Delete the registry and you have lost the company's records even though every
checkpoint survives.

Enterprise teams get this wrong constantly. They treat the agent framework's
internal state as their record of what happened, then discover at audit time
that it is unqueryable, undocumented, and tied to a framework version. In a
real deployment the registry is Jira, Salesforce, ServiceNow or a warranty
system. Here it is one sqlite table so you can see the shape of the idea.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

from .config import STATE_DIR

REGISTRY_DB = os.path.join(STATE_DIR, "registry.sqlite")

SCHEMA = """
CREATE TABLE IF NOT EXISTS claims (
    claim_id          TEXT PRIMARY KEY,
    thread_id         TEXT NOT NULL,
    dealer_id         TEXT,
    part_number       TEXT,
    submitted_at      TEXT,
    decided_at        TEXT,
    raw_text          TEXT,
    status            TEXT,          -- processing | awaiting_approval | decided | error
    outcome           TEXT,          -- approve | partial | deny
    payout            REAL,
    rationale         TEXT,
    escalation_reason TEXT,
    interrupt_json    TEXT,
    approver          TEXT,
    approver_note     TEXT,
    cost_usd          REAL DEFAULT 0,
    events_json       TEXT DEFAULT '[]'
);
"""


def _conn() -> sqlite3.Connection:
    os.makedirs(STATE_DIR, exist_ok=True)
    conn = sqlite3.connect(REGISTRY_DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def next_claim_id() -> str:
    with _conn() as c:
        n = c.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
    return f"CLM-{2000 + n + 1}"


def create(claim_id: str, thread_id: str, raw_text: str) -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO claims (claim_id, thread_id, raw_text, submitted_at, status) "
            "VALUES (?,?,?,?,'processing')",
            (claim_id, thread_id, raw_text, now()),
        )


def update(claim_id: str, **fields) -> None:
    """Small generic setter. Keys must be real column names."""
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    with _conn() as c:
        c.execute(
            f"UPDATE claims SET {sets} WHERE claim_id = ?",
            (*fields.values(), claim_id),
        )


def get(claim_id: str) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,)).fetchone()
    return dict(row) if row else None


def all_claims(status: str | None = None) -> list[dict]:
    q = "SELECT * FROM claims"
    args: tuple = ()
    if status:
        q += " WHERE status = ?"
        args = (status,)
    q += " ORDER BY submitted_at DESC"
    with _conn() as c:
        return [dict(r) for r in c.execute(q, args).fetchall()]


def pending_count() -> int:
    with _conn() as c:
        return c.execute(
            "SELECT COUNT(*) FROM claims WHERE status = 'awaiting_approval'"
        ).fetchone()[0]


# --- JSON column helpers ----------------------------------------------------


def events(claim_id: str) -> list[dict]:
    row = get(claim_id)
    return json.loads(row["events_json"]) if row else []


def set_events(claim_id: str, evs: list[dict]) -> None:
    update(
        claim_id,
        events_json=json.dumps(evs),
        cost_usd=round(sum(e.get("cost_usd", 0) for e in evs), 6),
    )


def interrupt_payload(claim_id: str) -> dict | None:
    row = get(claim_id)
    if not row or not row["interrupt_json"]:
        return None
    return json.loads(row["interrupt_json"])
