"""
One place that creates models, and one place that counts what they cost.

WHY a wrapper instead of calling ChatOpenAI everywhere
------------------------------------------------------
Two reasons, and the second is the real one.

1. You will want to swap models per agent. A classifier does not need your
   most expensive model. Routing by task tier is the single biggest cost lever
   in any agent system, far bigger than prompt trimming.

2. Every call has to be attributed to an agent. If five agents share one
   client, your bill is one undifferentiated number and you can never answer
   "which agent is expensive". Attribution has to happen at call time. You
   cannot reconstruct it afterwards.

In production this job belongs to an LLM gateway with a virtual key per agent,
which can also HARD BLOCK a call that would breach a budget. Observability
tells you that you overspent. Only a gateway stops you. This file is the
ten line version of that idea so you can see the shape of it.
"""

from __future__ import annotations

from typing import Any

from langchain_openai import ChatOpenAI

from .config import MODEL, estimate_cost
from .state import Event


def make_llm(temperature: float | None = None, model: str | None = None) -> ChatOpenAI:
    kwargs: dict[str, Any] = {"model": model or MODEL}
    if temperature is not None:
        kwargs["temperature"] = temperature
    return ChatOpenAI(**kwargs)


def usage_of(response: Any) -> tuple[int, int]:
    """
    Pull token counts off whatever the call returned.

    with_structured_output() hands you a pydantic object, not an AIMessage, so
    the usage metadata is not on the thing you get back. Using
    include_raw=True gives you a dict with both. That is why the agents below
    unpack {"raw": ..., "parsed": ...}.
    """
    meta = getattr(response, "usage_metadata", None) or {}
    return int(meta.get("input_tokens", 0)), int(meta.get("output_tokens", 0))


def event(
    agent: str,
    kind: str,
    detail: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
) -> Event:
    """Build one row for the activity feed, with its cost already computed."""
    return Event(
        agent=agent,
        kind=kind,
        detail=detail,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=estimate_cost(tokens_in, tokens_out),
    )
