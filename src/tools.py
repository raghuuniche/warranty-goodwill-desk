"""
Deterministic lookups. No model involved.

WHY this file is important to the architecture, not just the demo
------------------------------------------------------------------
The instinct when building agents is to make everything an agent. Resist it.
A part price is a lookup. A labour rate is a lookup. Dealer claim history is
a query. Asking a language model to do any of those gives you three bad
things: a wrong number sometimes, a cost every time, and no audit trail.

The rule worth carrying into client work: an LLM should decide, interpret and
write. Code should fetch, calculate and validate. When you find yourself
prompting a model to add two numbers, you have put the boundary in the wrong
place.

In the architecture diagram these are the gray boxes. Count them. In a mature
enterprise agent system most of the boxes are gray.
"""

from __future__ import annotations

import json
import os

from .config import DATA_DIR

LABOR_RATE_PER_HOUR = 142.0


def _load(name: str) -> dict:
    with open(os.path.join(DATA_DIR, name)) as f:
        return json.load(f)


def lookup_part(part_number: str) -> dict:
    parts = _load("parts.json")
    return parts.get(
        part_number,
        {"description": "unknown part", "price": 0.0, "labor_hours": 0.0, "known": False},
    )


def lookup_dealer(dealer_id: str) -> dict:
    dealers = _load("dealers.json")
    return dealers.get(
        dealer_id,
        {"name": "unknown dealer", "tier": "standard", "claims_ytd": 0, "approval_rate": 0.0},
    )


def price_claim(part_number: str, dealer_id: str) -> dict:
    """
    Combine both lookups into the cost picture the adjudicator needs.

    Note that this returns a ceiling, not a decision. Keeping calculation and
    judgement in separate nodes is what lets you unit test half the system.
    """
    part = lookup_part(part_number)
    dealer = lookup_dealer(dealer_id)
    labor_cost = round(part.get("labor_hours", 0.0) * LABOR_RATE_PER_HOUR, 2)
    parts_cost = round(part.get("price", 0.0), 2)
    return {
        "part_description": part.get("description"),
        "part_known": part.get("known", True),
        "parts_cost": parts_cost,
        "labor_hours": part.get("labor_hours", 0.0),
        "labor_cost": labor_cost,
        "max_reasonable_payout": round(parts_cost + labor_cost, 2),
        "dealer_name": dealer.get("name"),
        "dealer_tier": dealer.get("tier"),
        "dealer_claims_ytd": dealer.get("claims_ytd"),
    }


def load_policy() -> str:
    with open(os.path.join(DATA_DIR, "policy.md")) as f:
        return f.read()
