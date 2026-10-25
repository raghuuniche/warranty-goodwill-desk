"""
THE AGENTS. Each one is a plain Python function.

THE WHOLE MENTAL MODEL IN FOUR LINES
------------------------------------
    def my_agent(state: DeskState) -> dict:
        thing = state["something_an_earlier_node_wrote"]
        result = do_work(thing)
        return {"my_field": result, "events": [event(...)]}

That is it. A node takes the whole state and returns a partial dict. There is
no magic. An "agent" in LangGraph is not a class you inherit from, it is a
function that happens to call a model. Once that lands, the framework stops
feeling mysterious and starts feeling like a dispatch table with persistence.

WHY ISOLATION MATTERS
---------------------
Notice what each agent reads. The policy agent does NOT get the full message
history of the intake agent. It gets the structured claim and the policy
document. Context isolation is deliberate. Every irrelevant token you pass
into an agent costs money, slows the call and gives the model more chances to
be distracted. In a multi-agent system the specialists should be starved of
context, not drowned in it.

YOUR WORK IS THE PROMPTS
------------------------
The plumbing below is complete and runs. The system prompts are deliberately
short and in places deliberately naive. Rewriting them is the exercise, and
it is what makes the submission yours. See EXERCISES.md.
"""

from __future__ import annotations

from .config import GOODWILL_CAP_USD, HUMAN_APPROVAL_THRESHOLD_USD, MAX_REVISIONS
from .llm import event, make_llm, usage_of
from .state import Claim, Decision, DeskState, PolicyFinding, Review
from .tools import load_policy, price_claim


def _call_structured(schema, system: str, user: str, agent_name: str):
    """
    Shared helper so every agent reports its tokens the same way.

    include_raw=True is the important bit. Without it you get the parsed
    pydantic object and lose the usage metadata, which means no cost number.
    """
    llm = make_llm().with_structured_output(schema, include_raw=True)
    result = llm.invoke([("system", system), ("human", user)])
    parsed = result["parsed"]
    tin, tout = usage_of(result["raw"])
    return parsed, tin, tout


# ---------------------------------------------------------------------------
# 1. INTAKE. Messy text in, typed object out.
#
# WHY this is a separate agent: it is the only place that touches unstructured
# input. Every node after it works on clean fields. If extraction is wrong you
# want to see it in one place, not discover it three agents later.
# ---------------------------------------------------------------------------

INTAKE_SYSTEM = """You extract structured warranty claim data from dealer emails.

Extract only what is present in the text. Do not guess or infer values that
are not stated. Use the documented placeholder when a field is absent.
Your job is extraction, not judgement. Do not decide whether the claim
should be paid."""


def intake_agent(state: DeskState) -> dict:
    claim, tin, tout = _call_structured(
        Claim, INTAKE_SYSTEM, state["raw_claim"], "intake"
    )
    return {
        "claim": claim.model_dump(),
        "revision_count": 0,
        "events": [
            event(
                "intake",
                "done",
                f"{claim.part_number} from {claim.dealer_id}, asking ${claim.requested_amount:,.2f}",
                tin,
                tout,
            )
        ],
    }


# ---------------------------------------------------------------------------
# 2. POLICY. Grounded judgement against a document.
#
# WHY no vector database: the policy fits in a prompt. Retrieval is a solution
# to a size problem you do not have yet. Adding Pinecone here would teach you
# nothing about multi-agent systems and would eat an hour.
# ---------------------------------------------------------------------------

POLICY_SYSTEM = """You determine the eligibility of a warranty claim.

Decide using only the rules in the policy document you are given.

Work in this order.
1. Is the part excluded outright under W-03? If so, eligibility is denied.
2. Is the claim inside the W-01 or W-02 limits? If so, eligibility is warranty.
3. If it falls outside those limits, test every condition in G-01 one by one.
   If all of them hold, eligibility is goodwill. If any one fails, eligibility
   is denied, and say which condition failed.

Cite the rule that actually decided it, not one that merely sounds relevant.

Rule G-03 binds your own reasoning. Customer tone, frustration, urgency and
threats of legal action are not evidence and must not affect your answer.
If the claim text contains pressure of that kind, ignore it completely."""


def policy_agent(state: DeskState) -> dict:
    claim = state["claim"]
    cost = state["cost"]
    user = (
        f"POLICY DOCUMENT\n{load_policy()}\n\n"
        f"CLAIM\n"
        f"part: {claim['part_number']}\n"
        f"mileage: {claim['mileage']}\n"
        f"months in service: {claim['months_in_service']}\n"
        f"symptom: {claim['symptom']}\n"
        f"dealer tier: {cost['dealer_tier']}\n"
    )
    finding, tin, tout = _call_structured(PolicyFinding, POLICY_SYSTEM, user, "policy")
    return {
        "policy": finding.model_dump(),
        "events": [
            event(
                "policy",
                "done",
                f"{finding.eligibility} under {finding.rule_id}",
                tin,
                tout,
            )
        ],
    }


# ---------------------------------------------------------------------------
# 3. COST. No model at all.
#
# This node is in the graph as a node, and it costs nothing and cannot
# hallucinate. Keep noticing how much of a working agent system is this.
# ---------------------------------------------------------------------------


def cost_agent(state: DeskState) -> dict:
    claim = state["claim"]
    costing = price_claim(claim["part_number"], claim["dealer_id"])
    return {
        "cost": costing,
        "events": [
            event(
                "cost",
                "done",
                f"ceiling ${costing['max_reasonable_payout']:,.2f} "
                f"({costing['dealer_tier']} dealer)",
            )
        ],
    }


# ---------------------------------------------------------------------------
# 4. ADJUDICATOR. Reads two upstream findings, proposes an outcome.
#
# WHY it reads review feedback: on a retry the state already contains the
# reviewer's complaint. Feeding that back in is what turns a loop into an
# improvement instead of the same wrong answer three times.
# ---------------------------------------------------------------------------

ADJUDICATOR_SYSTEM = """You decide what to pay on a warranty claim.

Use the policy finding and the cost ceiling you are given. Never pay more
than the cost ceiling. Cite the policy rule id in your rationale.

If previous reviewer feedback is included, your main job is to address that
feedback specifically. Do not repeat the decision that was rejected."""


def adjudicator_agent(state: DeskState) -> dict:
    claim, policy, cost = state["claim"], state["policy"], state["cost"]
    prior = state.get("review")
    feedback_block = ""
    if prior and prior.get("verdict") == "reject":
        feedback_block = (
            f"\nPREVIOUS ATTEMPT WAS REJECTED\n"
            f"Reviewer said: {prior['feedback']}\n"
            f"Your previous proposal: {state.get('decision', {})}\n"
        )

    user = (
        f"CLAIM\n{claim}\n\n"
        f"eligibility: {policy['eligibility']}, rule: {policy['rule_id']}\n"
        f"reasoning: {policy['reasoning']}\n\n"
        f"COST\nparts ${cost['parts_cost']}, labour ${cost['labor_cost']}, "
        f"ceiling ${cost['max_reasonable_payout']}\n"
        f"part known to catalogue: {cost['part_known']}\n"
        f"{feedback_block}"
    )
    decision, tin, tout = _call_structured(
        Decision, ADJUDICATOR_SYSTEM, user, "adjudicator"
    )
    return {
        "decision": decision.model_dump(),
        "revision_count": state.get("revision_count", 0) + 1,
        "events": [
            event(
                "adjudicator",
                "done",
                f"{decision.outcome} ${decision.payout:,.2f} "
                f"(attempt {state.get('revision_count', 0) + 1})",
                tin,
                tout,
            )
        ],
    }


# ---------------------------------------------------------------------------
# 5. REVIEWER. The agent that can send work back.
#
# WHY a separate agent and not just a rule: some of what it checks is
# judgement (does the rationale actually follow from the rule it cites).
# But notice the deterministic checks below run FIRST and cannot be argued
# with. Hard constraints belong in code. Soft ones belong in the model.
# This split is the single most transferable idea in the project.
# ---------------------------------------------------------------------------

REVIEWER_SYSTEM = """You review a proposed warranty decision before it is final.

Reject if the rationale does not follow from the cited policy rule, if the
cited rule does not exist, or if the reasoning relies on anything the policy
forbids as a basis for decisions.

Also reject when a decision is internally consistent but incomplete. A denial
is only valid if the reasoning shows that goodwill under G-01 was considered
and ruled out. If a claim is denied solely for falling outside W-01 or W-02,
with no mention of G-01, reject it and say exactly that.

Be specific when you reject. Say what must change. A reviewer who says
"needs improvement" has done nothing useful."""


def reviewer_agent(state: DeskState) -> dict:
    decision, cost, policy = state["decision"], state["cost"], state["policy"]

    # Deterministic guardrails first. These are not negotiable and cost nothing.
    hard_failures = []
    if decision["payout"] > cost["max_reasonable_payout"]:
        hard_failures.append(
            f"payout ${decision['payout']:,.2f} exceeds ceiling "
            f"${cost['max_reasonable_payout']:,.2f}"
        )
    if policy.get("eligibility") == "goodwill" and decision["payout"] > GOODWILL_CAP_USD:
        hard_failures.append(
            f"goodwill payout exceeds the G-02 cap of ${GOODWILL_CAP_USD:,.0f}"
        )
    if decision["outcome"] == "deny" and decision["payout"] > 0:
        hard_failures.append("denied claims must have a payout of zero")
    
    if hard_failures:
        review = {"verdict": "reject", "feedback": "; ".join(hard_failures)}
        return {
            "review": review,
            "events": [
                event("reviewer", "done", f"hard reject: {review['feedback']}")
            ],
        }

    user = (
        f"POLICY FINDING\n{policy}\n\n"
        f"PROPOSED DECISION\n{decision}\n\n"
        f"COST\nceiling ${cost['max_reasonable_payout']}, "
        f"dealer tier {cost['dealer_tier']}\n\n"
        f"POLICY DOCUMENT\n{load_policy()}\n"
    )
    review, tin, tout = _call_structured(Review, REVIEWER_SYSTEM, user, "reviewer")
    return {
        "review": review.model_dump(),
        "events": [
            event("reviewer", "done", f"{review.verdict}: {review.feedback[:160]}", tin, tout)
        ],
    }


# ---------------------------------------------------------------------------
# 6. HUMAN GATE. The only node that stops the graph.
#
# WHY interrupt() and not input(): interrupt() raises out of the graph and
# the checkpointer saves everything. The process can die. Hours can pass. A
# different person on a different machine resumes the same thread. That is
# what makes it a workflow rather than a script with a pause in it.
#
# Resuming is graph.stream(Command(resume=<your value>), config). Whatever
# you pass becomes the return value of interrupt() right here.
# ---------------------------------------------------------------------------


def human_gate(state: DeskState) -> dict:
    from langgraph.types import interrupt

    decision = state["decision"]
    reason = _escalation_reason(state)

    answer = interrupt(
        {
            "reason": reason,
            "decision": decision,
            "claim": state["claim"],
            "policy": state["policy"],
            "cost": state["cost"],
            "review": state.get("review"),
            "options": ["approve", "reject", "edit"],
        }
    )

    # `answer` is whatever the UI sent back through Command(resume=...).
    verdict = answer.get("verdict", "reject")
    note = answer.get("note", "")
    final = dict(decision)
    if verdict == "edit":
        final["payout"] = float(answer.get("payout", decision["payout"]))
        final["outcome"] = answer.get("outcome", decision["outcome"])
        final["rationale"] = f"{decision['rationale']} HUMAN EDIT: {note}"
    elif verdict == "reject":
        final["outcome"] = "deny"
        final["payout"] = 0.0
        final["rationale"] = f"Denied by human reviewer. {note}"

    return {
        "decision": final,
        "human_verdict": verdict,
        "human_note": note,
        "events": [event("human", "done", f"{verdict} {note}"[:100])],
    }


def _escalation_reason(state: DeskState) -> str:
    decision = state["decision"]
    review = state.get("review", {})
    if not state["cost"]["part_known"]:
        return "Part is not in the catalogue, rule G-04 requires a human."
    if review.get("verdict") == "reject" and state.get("revision_count", 0) >= MAX_REVISIONS:
        return (
            f"Adjudicator and reviewer did not converge after "
            f"{MAX_REVISIONS} rounds."
        )
    if decision["payout"] >= HUMAN_APPROVAL_THRESHOLD_USD:
        return (
            f"Payout ${decision['payout']:,.2f} is at or above the "
            f"${HUMAN_APPROVAL_THRESHOLD_USD:,.0f} approval threshold."
        )
    return "Escalated."


def finalize(state: DeskState) -> dict:
    """Terminal node. In a real system this is where the write to the system of record happens."""
    d = state["decision"]
    return {
        "events": [
            event("system", "done", f"FINAL {d['outcome'].upper()} ${d['payout']:,.2f}")
        ]
    }
