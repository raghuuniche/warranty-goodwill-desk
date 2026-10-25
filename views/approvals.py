"""
APPROVALS DASHBOARD. The human half of the workforce.

THE IDEA THIS PAGE EXISTS TO DEMONSTRATE
----------------------------------------
Nothing about a paused claim lives in this browser tab. The graph state sits
in the checkpointer keyed by thread_id, and the queue sits in the registry.
So the reviewer can be a different person, on a different machine, the next
morning. Close the laptop mid approval and reopen it. The queue is still here.

A paused run that only resumes in the session that started it is not a
workflow. It is a script with a prompt in the middle.

ON THE APPROVER NAME
--------------------
It is required. An approval with no named human is not an audit trail, it is
a button press. Every governance conversation about agent systems arrives at
this point eventually, usually late. Putting the name in the record from day
one costs nothing and is the difference between a demo and something a client
can actually run.
"""

from __future__ import annotations

import streamlit as st

from src import registry, runner
from views.common import get_graph, money

st.title("Warranty review queue")
st.caption("Claims the agents could not finalise on their own.")

graph = get_graph()
queue = registry.all_claims("awaiting_approval")

if not queue:
    st.success("Nothing waiting. The agents cleared every claim on their own.")
    st.stop()

st.write(f"**{len(queue)} claim{'s' if len(queue) > 1 else ''} waiting**")

claim_id = st.radio(
    "Select a claim",
    [r["claim_id"] for r in queue],
    format_func=lambda cid: (
        f"{cid}  ·  {registry.get(cid)['dealer_id'] or 'unknown dealer'}  ·  "
        f"{money(registry.get(cid)['payout'])}"
    ),
)

row = registry.get(claim_id)
payload = registry.interrupt_payload(claim_id) or {}

st.divider()
st.subheader(f"Claim {claim_id}")
st.warning(f"**Why this needs you.** {row['escalation_reason']}")

tab_summary, tab_evidence, tab_text = st.tabs(["Proposal", "Evidence", "Original claim"])

with tab_summary:
    a, b, c = st.columns(3)
    a.metric("Proposed outcome", (row["outcome"] or "-").title())
    b.metric("Proposed payout", money(row["payout"]))
    c.metric("Cost ceiling", money(payload.get("cost", {}).get("max_reasonable_payout")))
    st.write(row["rationale"] or "")

with tab_evidence:
    e1, e2 = st.columns(2)
    with e1:
        st.caption("Policy finding")
        st.json(payload.get("policy", {}))
        st.caption("Last review")
        st.json(payload.get("review", {}))
    with e2:
        st.caption("Costing")
        st.json(payload.get("cost", {}))
        st.caption("Extracted claim")
        st.json(payload.get("claim", {}))

with tab_text:
    st.text(row["raw_text"])

# --- Decide ----------------------------------------------------------------

st.divider()
st.subheader("Your decision")

approver = st.text_input("Your name", placeholder="Required for the audit record")
verdict = st.radio("Decision", ["approve", "reject", "edit"], horizontal=True)
note = st.text_area("Note", height=80, placeholder="Why you decided this way.")

payout = outcome = None
if verdict == "edit":
    c1, c2 = st.columns(2)
    payout = c1.number_input(
        "Revised payout", value=float(row["payout"] or 0), step=50.0, min_value=0.0
    )
    outcome = c2.selectbox("Revised outcome", ["approve", "partial", "deny"])

ready = bool(approver.strip())
if not ready:
    st.caption("Enter your name to enable the decision button.")

if st.button("Submit decision", type="primary", disabled=not ready):
    with st.spinner("Finalising..."):
        runner.resume(
            graph,
            claim_id,
            verdict=verdict,
            approver=approver.strip(),
            note=note.strip(),
            payout=payout,
            outcome=outcome,
        )
    st.success(f"{claim_id} finalised by {approver.strip()}.")
    st.rerun()
