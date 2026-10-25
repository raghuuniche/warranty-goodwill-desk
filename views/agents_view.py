"""
AGENT CONSOLE. The operator view, not the dealer view.

This reads the events list the registry stored, which is the same list the
graph appended to during the run. Nothing is recomputed and nothing is
re-run. The console is a reader, not a driver.

That property is what lets you open this page tomorrow and still see exactly
what happened on a claim from today. Observability that only exists while the
process is alive is not observability.
"""

from __future__ import annotations

import streamlit as st

from src import registry
from src.config import HUMAN_APPROVAL_THRESHOLD_USD, MAX_REVISIONS
from views.common import money, status_chip

AGENTS = ["intake", "supervisor", "cost", "policy", "adjudicator", "reviewer", "human"]

st.title("Agent console")
st.caption("How the agent team handled each claim, and what it cost.")

rows = registry.all_claims()
if not rows:
    st.info("No claims yet. Submit one from the dealer portal.")
    st.stop()

claim_id = st.selectbox(
    "Claim",
    [r["claim_id"] for r in rows],
    format_func=lambda cid: f"{cid}  ({status_chip(registry.get(cid))})",
)
row = registry.get(claim_id)
events = registry.events(claim_id)

st.caption(f"thread {row['thread_id']}")

# --- Headline numbers ------------------------------------------------------

attempts = sum(1 for e in events if e["agent"] == "adjudicator")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Run cost", f"${row['cost_usd'] or 0:.4f}")
c2.metric("Agent steps", len(events))
c3.metric("Adjudication rounds", f"{attempts} of {MAX_REVISIONS}")
c4.metric("Outcome", status_chip(row))

left, right = st.columns([1, 2])

# --- Roster ----------------------------------------------------------------

with left:
    st.subheader("Agents")
    seen = {e["agent"] for e in events}
    for a in AGENTS:
        spend = sum(e["cost_usd"] for e in events if e["agent"] == a)
        calls = sum(1 for e in events if e["agent"] == a)
        if a == "human" and row["status"] == "awaiting_approval":
            st.write("**human** · waiting for a reviewer")
        elif a in seen:
            detail = f"{calls} step{'s' if calls > 1 else ''}"
            if spend:
                detail += f" · ${spend:.4f}"
            else:
                detail += " · no model"
            st.write(f"**{a}** · {detail}")
        else:
            st.write(f"{a} · idle")

    st.caption(
        f"Human review triggers above {money(HUMAN_APPROVAL_THRESHOLD_USD)}, "
        f"on an unknown part, or after {MAX_REVISIONS} failed review rounds."
    )

# --- Timeline --------------------------------------------------------------

with right:
    st.subheader("Interaction timeline")
    for i, e in enumerate(events, 1):
        cost = f"  ·  ${e['cost_usd']:.4f}" if e["cost_usd"] else ""
        st.write(f"{i}. `{e['agent']}`  {e['detail']}{cost}")

    if attempts > 1:
        st.warning(
            f"The reviewer sent this claim back {attempts - 1} time"
            f"{'s' if attempts > 2 else ''}. Each round costs tokens, which is "
            f"why MAX_REVISIONS exists."
        )

# --- Decision --------------------------------------------------------------

st.divider()
if row["status"] == "awaiting_approval":
    st.subheader("Paused")
    st.warning(row["escalation_reason"])
    st.caption("Open the approvals page to release it.")
elif row["rationale"]:
    st.subheader("Decision")
    a, b = st.columns(2)
    a.metric("Outcome", status_chip(row))
    b.metric("Payout", money(row["payout"]))
    st.write(row["rationale"])
    if row["approver"]:
        st.caption(f"Approved by {row['approver']}. {row['approver_note'] or ''}")
