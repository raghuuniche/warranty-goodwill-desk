"""
DEALER PORTAL. What the dealer sees.

Note what is absent from this page. No agent names, no token counts, no
routing. A dealer submits a claim and gets an answer. The entire multi agent
machine is invisible to them, exactly as it should be.

That is worth saying out loud in the demo. The agent architecture is an
implementation detail of the service, not a feature of it. Teams building
their first agent system often expose the agents to the end user because the
agents are the thing they are proud of. Nobody outside the project cares.
"""

from __future__ import annotations

import json
import os

import streamlit as st

from src import registry, runner
from src.config import DATA_DIR
from views.common import get_graph, money, status_chip

st.image(os.path.join("assets", "banner.png"), use_container_width=True)
st.title("Dealer warranty portal")
st.caption("Submit a goodwill or warranty claim. Most claims are answered immediately.")

graph = get_graph()


@st.cache_data
def samples() -> list[dict]:
    with open(os.path.join(DATA_DIR, "claims.json")) as f:
        return json.load(f)


# --- Submit ----------------------------------------------------------------

st.subheader("New claim")

sample = st.selectbox(
    "Prefill from a sample claim, or leave blank and type your own",
    [None] + samples(),
    format_func=lambda c: "Type my own" if c is None else f"{c['id']} {c['label']}",
)

text = st.text_area(
    "Claim details",
    value=sample["text"] if sample else "",
    height=160,
    placeholder=(
        "Describe the claim. Include the dealer code, VIN, mileage, months in "
        "service, part number and the amount you are requesting."
    ),
)

if st.button("Submit claim", type="primary", disabled=not text.strip()):
    with st.spinner("Reviewing your claim..."):
        claim_id = runner.submit(graph, text.strip())
    st.session_state["last_claim"] = claim_id
    st.rerun()

# --- Result of the most recent submission ----------------------------------

last = st.session_state.get("last_claim")
if last:
    row = registry.get(last)
    st.divider()
    st.subheader(f"Claim {row['claim_id']}")

    if row["status"] == "awaiting_approval":
        st.info(
            "This claim needs a manual review before it can be finalised. "
            "You will be notified once a reviewer has decided."
        )
        st.write(f"**Reason for review.** {row['escalation_reason']}")
    elif row["status"] == "decided":
        a, b = st.columns(2)
        a.metric("Outcome", status_chip(row))
        b.metric("Payout", money(row["payout"]))
        st.write(row["rationale"])
        if row["approver"]:
            st.caption(f"Reviewed by {row['approver']}. {row['approver_note'] or ''}")

# --- All claims ------------------------------------------------------------

st.divider()
st.subheader("Your claims")

rows = registry.all_claims()
if not rows:
    st.caption("No claims submitted yet.")
else:
    st.dataframe(
        [
            {
                "Claim": r["claim_id"],
                "Dealer": r["dealer_id"] or "-",
                "Part": r["part_number"] or "-",
                "Status": status_chip(r),
                "Payout": money(r["payout"]) if r["payout"] is not None else "-",
                "Reviewer": r["approver"] or "-",
                "Submitted": (r["submitted_at"] or "")[:16].replace("T", " "),
            }
            for r in rows
        ],
        use_container_width=True,
        hide_index=True,
    )
