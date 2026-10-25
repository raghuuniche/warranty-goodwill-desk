"""
THE WIRING. This file is where LangGraph earns its keep.

THREE CONCEPTS, AND THEY ARE THE WHOLE FRAMEWORK
------------------------------------------------
NODES are functions. You met them in agents.py.

EDGES are the fixed arrows. add_edge("policy", "supervisor") means policy
always goes to supervisor. No thinking involved.

CONDITIONAL EDGES are the interesting ones. You give LangGraph a plain Python
function that looks at state and returns the NAME of the next node. That
function is your router. Notice that it is ordinary code, not a model call.

WHY THE SUPERVISOR IS NOT AN LLM HERE
-------------------------------------
Most tutorials make the supervisor a model that is asked "who should go
next". That is expensive, slow, and occasionally it picks wrong and you
cannot explain why to an auditor. Use a model to route only when the routing
decision genuinely needs judgement. Here it does not. "Have I got a policy
finding yet" is an if statement.

This is a real architectural position and it is worth defending in your
write-up. Deterministic routing wherever the rule is knowable, model routing
only where it is not.
"""

from __future__ import annotations

import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from .agents import (
    adjudicator_agent,
    cost_agent,
    finalize,
    human_gate,
    intake_agent,
    policy_agent,
    reviewer_agent,
)
from .config import CHECKPOINT_DB, HUMAN_APPROVAL_THRESHOLD_USD, MAX_REVISIONS
from .llm import event
from .state import DeskState


def supervisor(state: DeskState) -> dict:
    """
    A node that does no work. It exists so the router has somewhere to live
    and so the UI has a visible coordination step. Its only output is an event.
    """
    return {"events": [event("supervisor", "route", "deciding next step")]}


def route_from_supervisor(state: DeskState) -> str:
    """
    Gather findings first, then adjudicate. Returns a node name.

    EXERCISE: policy and cost do not depend on each other, so running them one
    after the other wastes wall clock time. LangGraph can fan out to both at
    once by adding two edges from the same node. Try it once this works end to
    end, and watch what happens to the events list ordering. That ordering
    surprise is why the reducer on `events` matters.
    """
    if "cost" not in state:
        return "cost"
    if "policy" not in state:
        return "policy"
    return "adjudicator"


def route_from_reviewer(state: DeskState) -> str:
    """
    THE MOST IMPORTANT FUNCTION IN THE PROJECT.

    Three outcomes, and the order of the checks is deliberate.

    1. Out of patience. If the adjudicator and reviewer have gone MAX_REVISIONS
       rounds without agreeing, stop. Do not try a fourth time. Hand it to a
       human. An unbounded disagreement loop is how agent systems generate
       surprise invoices.

    2. Rejected with rounds left. Go back and try again, carrying the feedback.

    3. Approved. Then ask the separate question of whether a human must sign
       off anyway, based on amount or on the unknown-part rule.

    Note that "the reviewer approved" and "a human must approve" are
    independent. Conflating agent approval with human approval is a common
    design error and it quietly removes your control.
    """
    review = state.get("review", {})
    revisions = state.get("revision_count", 0)

    if review.get("verdict") == "reject":
        if revisions >= MAX_REVISIONS:
            return "human_gate"
        return "adjudicator"

    if not state["cost"]["part_known"]:
        return "human_gate"
    if state["decision"]["payout"] >= HUMAN_APPROVAL_THRESHOLD_USD:
        return "human_gate"
    return "finalize"


def build_graph(checkpointer=None):
    g = StateGraph(DeskState)

    g.add_node("intake", intake_agent)
    g.add_node("supervisor", supervisor)
    g.add_node("policy", policy_agent)
    g.add_node("cost", cost_agent)
    g.add_node("adjudicator", adjudicator_agent)
    g.add_node("reviewer", reviewer_agent)
    g.add_node("human_gate", human_gate)
    g.add_node("finalize", finalize)

    g.add_edge(START, "intake")
    g.add_edge("intake", "supervisor")

    g.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {"policy": "policy", "cost": "cost", "adjudicator": "adjudicator"},
    )
    # Specialists report back to the supervisor. This is the "star" topology.
    g.add_edge("policy", "supervisor")
    g.add_edge("cost", "supervisor")

    g.add_edge("adjudicator", "reviewer")

    g.add_conditional_edges(
        "reviewer",
        route_from_reviewer,
        {
            "adjudicator": "adjudicator",   # the retry loop
            "human_gate": "human_gate",
            "finalize": "finalize",
        },
    )

    g.add_edge("human_gate", "finalize")
    g.add_edge("finalize", END)

    return g.compile(checkpointer=checkpointer)


def make_checkpointer() -> SqliteSaver:
    """
    WHY SQLITE AND NOT MEMORY
    -------------------------
    An in-memory checkpointer dies with the process. That is fine for a
    notebook and useless the moment a human has to walk away and come back,
    which is exactly what your human gate requires.

    check_same_thread=False is needed because Streamlit touches the connection
    from more than one thread. Fine for a local project, not for production.
    """
    conn = sqlite3.connect(CHECKPOINT_DB, check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver
