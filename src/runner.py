"""
The bridge between the graph and the registry.

WHY A SEPARATE MODULE
---------------------
Two different pages now drive the same graph. The dealer portal starts a run.
The approvals dashboard resumes one. If each page called graph.stream()
directly, the logic that writes to the registry would be duplicated in two
places and would drift apart within a week.

More importantly, nothing here imports streamlit. That is deliberate. The UI
is one client of this module. A REST endpoint, a scheduled job or a Slack bot
could be another without changing a line. Keeping orchestration free of UI
imports is what later lets you move the agents behind a service.
"""

from __future__ import annotations

import json
import uuid

from langgraph.types import Command

from . import registry
from .config import RECURSION_LIMIT


def _config(thread_id: str) -> dict:
    return {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": RECURSION_LIMIT,
    }


def _drain(graph, stream, claim_id: str) -> dict | None:
    """
    Consume the stream, append events to the registry as we go, and return
    the interrupt payload if the graph paused.
    """
    evs = registry.events(claim_id)
    interrupt = None

    for chunk in stream:
        if "__interrupt__" in chunk:
            interrupt = chunk["__interrupt__"][0].value
        for node, update in chunk.items():
            if node == "__interrupt__":
                continue
            for ev in (update or {}).get("events", []):
                evs.append(ev)
        registry.set_events(claim_id, evs)

    return interrupt


def _record_outcome(graph, claim_id: str, thread_id: str, interrupt: dict | None) -> None:
    snapshot = graph.get_state(_config(thread_id))
    values = snapshot.values
    claim = values.get("claim", {})

    registry.update(
        claim_id,
        dealer_id=claim.get("dealer_id"),
        part_number=claim.get("part_number"),
    )

    if interrupt:
        registry.update(
            claim_id,
            status="awaiting_approval",
            escalation_reason=interrupt.get("reason"),
            interrupt_json=json.dumps(interrupt),
            outcome=interrupt["decision"]["outcome"],
            payout=interrupt["decision"]["payout"],
            rationale=interrupt["decision"]["rationale"],
        )
        return

    decision = values.get("decision") or {}
    registry.update(
        claim_id,
        status="decided",
        decided_at=registry.now(),
        interrupt_json=None,
        outcome=decision.get("outcome"),
        payout=decision.get("payout"),
        rationale=decision.get("rationale"),
    )


def submit(graph, raw_text: str) -> str:
    """Start a new claim. Returns the claim id."""
    claim_id = registry.next_claim_id()
    thread_id = f"{claim_id}-{uuid.uuid4().hex[:6]}"
    registry.create(claim_id, thread_id, raw_text)

    interrupt = _drain(
        graph,
        graph.stream({"raw_claim": raw_text}, _config(thread_id), stream_mode="updates"),
        claim_id,
    )
    _record_outcome(graph, claim_id, thread_id, interrupt)
    return claim_id


def resume(graph, claim_id: str, verdict: str, approver: str, note: str,
           payout: float | None = None, outcome: str | None = None) -> None:
    """
    Resume a paused claim from the approvals dashboard.

    WHY THIS WORKS FROM A DIFFERENT PAGE AND A DIFFERENT DAY
    --------------------------------------------------------
    Nothing about the paused run lives in this process. The graph state is in
    the checkpointer keyed by thread_id. All this function needs is that id,
    which it reads back out of the registry. The approver could be a different
    person on a different machine. That is the difference between an
    interrupt and a script that waits on input().
    """
    row = registry.get(claim_id)
    if not row:
        raise ValueError(f"No claim {claim_id}")

    payload = {"verdict": verdict, "note": f"[{approver}] {note}".strip()}
    if verdict == "edit":
        payload["payout"] = float(payout or 0)
        payload["outcome"] = outcome or "partial"

    registry.update(claim_id, approver=approver, approver_note=note)

    interrupt = _drain(
        graph,
        graph.stream(Command(resume=payload), _config(row["thread_id"]), stream_mode="updates"),
        claim_id,
    )
    _record_outcome(graph, claim_id, row["thread_id"], interrupt)
