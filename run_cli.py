"""
Run the desk in the terminal. Use this while building. The UI is for the demo.

    python run_cli.py              # runs sample claim CLM-1002
    python run_cli.py CLM-1003

WHY STREAM INSTEAD OF INVOKE
----------------------------
graph.invoke() returns only the final state. You learn nothing about what
happened in between, which is exactly the thing you are trying to learn.

graph.stream(..., stream_mode="updates") yields one dict per node as it
finishes, shaped {node_name: partial_state_update}. That is the same feed the
Streamlit app renders. Build against it here first, because debugging in a
terminal is ten times faster than debugging inside Streamlit.

Other stream modes worth knowing. "values" gives the full state after each
step. "messages" streams tokens as they generate. "updates" is the right one
for watching a multi-agent system work.
"""

from __future__ import annotations

import json
import os
import sys
import uuid

from langgraph.types import Command

from src.config import CHECKPOINT_DB, DATA_DIR, RECURSION_LIMIT, STATE_DIR
from src.graph import build_graph, make_checkpointer


def load_claim(claim_id: str | None) -> dict:
    with open(os.path.join(DATA_DIR, "claims.json")) as f:
        claims = json.load(f)
    if claim_id:
        for c in claims:
            if c["id"] == claim_id:
                return c
        raise SystemExit(f"No claim {claim_id}. Available: {[c['id'] for c in claims]}")
    return claims[1]


def show(chunk: dict) -> None:
    for node, update in chunk.items():
        if node == "__interrupt__":
            continue
        for ev in (update or {}).get("events", []):
            cost = f"  ${ev['cost_usd']:.4f}" if ev["cost_usd"] else ""
            print(f"  [{ev['agent']:<12}] {ev['detail']}{cost}")


def main() -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    claim = load_claim(sys.argv[1] if len(sys.argv) > 1 else None)

    checkpointer = make_checkpointer()
    graph = build_graph(checkpointer)

    # The thread_id is the identity of this piece of work. Same id, same
    # conversation, resumable. New id, fresh start. In a real system this
    # would be the ticket number.
    config = {
        "configurable": {"thread_id": f"{claim['id']}-{uuid.uuid4().hex[:6]}"},
        "recursion_limit": RECURSION_LIMIT,
    }

    print(f"\n=== {claim['id']}  {claim['label']} ===\n")

    interrupted = None
    for chunk in graph.stream({"raw_claim": claim["text"]}, config, stream_mode="updates"):
        show(chunk)
        if "__interrupt__" in chunk:
            interrupted = chunk["__interrupt__"][0].value

    # The graph has paused. Everything is saved. We could exit the process
    # here, come back tomorrow, and resume on the same thread_id.
    while interrupted:
        print("\n--- HUMAN NEEDED ---")
        print("reason:", interrupted["reason"])
        print("proposal:", json.dumps(interrupted["decision"], indent=2))
        verdict = input("approve / reject / edit > ").strip() or "approve"
        payload = {"verdict": verdict, "note": input("note > ").strip()}
        if verdict == "edit":
            payload["payout"] = float(input("new payout > ") or 0)
            payload["outcome"] = input("new outcome (approve/partial/deny) > ") or "partial"

        interrupted = None
        for chunk in graph.stream(Command(resume=payload), config, stream_mode="updates"):
            show(chunk)
            if "__interrupt__" in chunk:
                interrupted = chunk["__interrupt__"][0].value

    final = graph.get_state(config).values
    total = sum(e["cost_usd"] for e in final.get("events", []))
    print(f"\nDecision: {json.dumps(final.get('decision'), indent=2)}")
    print(f"Run cost: ${total:.4f}")
    print(f"Checkpoints: {CHECKPOINT_DB}")


if __name__ == "__main__":
    main()
