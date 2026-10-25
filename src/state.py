"""
THE SINGLE MOST IMPORTANT FILE IN A LANGGRAPH PROJECT.

WHY this exists
---------------
In a chain, data flows A -> B -> C as a return value. In a graph, there is
no return value to pass along, because a node can be reached from several
places and can run more than once. So every node reads from and writes to
one shared object. That object is the state.

Get the state right and the graph writes itself. Get it wrong and you will
spend your whole session debugging why a field is empty.

THE RULE
--------
A node returns a PARTIAL dict. LangGraph merges it into the state for you.
    return {"policy": finding}        # only touches state["policy"]
You never mutate state in place. You never return the whole state.

REDUCERS
--------
By default a returned key OVERWRITES the old value. That is wrong for a log,
where every node should append. Annotated[list, operator.add] tells LangGraph
to concatenate instead of replace. This is the one piece of LangGraph that is
genuinely non-obvious, and it is why `events` accumulates while `policy` does not.
"""

from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Structured payloads produced by the agents.
#
# WHY pydantic: `llm.with_structured_output(Claim)` makes the model return a
# validated object instead of a wall of prose. The next agent then reads a
# field, not a paragraph. In enterprise work this is the difference between
# a demo and a pipeline. Typed handoffs are the contract between agents.
# ---------------------------------------------------------------------------


class Claim(BaseModel):
    """What the intake agent extracts from a messy dealer email."""

    dealer_id: str = Field(description="Dealer code, e.g. D-4471. Use UNKNOWN if absent.")
    vin: str = Field(description="Vehicle identification number. UNKNOWN if absent.")
    mileage: int = Field(description="Odometer reading in miles. Use -1 if absent.")
    part_number: str = Field(description="Part number being claimed. UNKNOWN if absent.")
    symptom: str = Field(description="One sentence describing the customer complaint.")
    requested_amount: float = Field(description="Dollar amount the dealer is asking for.")
    months_in_service: int = Field(description="Months since vehicle sale. -1 if absent.")
    customer_tone: Literal["calm", "frustrated", "threatening legal"] = Field(
        description="Tone of the customer as reported in the claim."
    )


class PolicyFinding(BaseModel):
    """What the policy agent concludes."""

    eligibility: Literal["warranty", "goodwill", "denied"]
    rule_id: str = Field(description="The policy rule id that decided this, e.g. W-02.")
    reasoning: str = Field(description="Two sentences maximum.")


class Decision(BaseModel):
    """What the adjudicator proposes."""

    outcome: Literal["approve", "partial", "deny"]
    payout: float = Field(description="Dollars to pay. 0 when denying.")
    rationale: str = Field(description="Three sentences maximum, citing the policy rule id.")


class Review(BaseModel):
    """What the reviewer agent returns."""

    verdict: Literal["approve", "reject"]
    feedback: str = Field(description="If rejecting, say exactly what the adjudicator must fix.")


# ---------------------------------------------------------------------------
# The graph state
# ---------------------------------------------------------------------------


class Event(TypedDict):
    """One row in the live activity feed the UI renders."""

    agent: str
    kind: str  # start | done | route | interrupt | error
    detail: str
    tokens_in: int
    tokens_out: int
    cost_usd: float


class DeskState(TypedDict, total=False):
    """
    total=False means every key is optional. Nodes fill in what they own.

    NOTE on ownership: exactly one node writes each field. intake writes
    `claim`, policy writes `policy`, and so on. When two nodes write the same
    field you have created a race and a debugging problem. Keep ownership
    single until you deliberately need a reducer.
    """

    # Input
    raw_claim: str

    # Produced by agents, one field per agent
    claim: dict          # from Claim
    policy: dict         # from PolicyFinding
    cost: dict           # from the deterministic cost tool
    decision: dict       # from Decision
    review: dict         # from Review

    # Loop control. This is what stops a reviewer and adjudicator arguing forever.
    revision_count: int

    # Human in the loop
    needs_human: bool
    human_verdict: str   # approve | reject | edit
    human_note: str

    # Observability. `operator.add` makes this append across every node.
    events: Annotated[list[Event], operator.add]
