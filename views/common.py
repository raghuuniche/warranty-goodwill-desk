"""
Shared helpers for the pages.

The graph is built once per Streamlit process and reused by every page.
@st.cache_resource is what makes that happen. Without it each page load would
open a new sqlite connection and recompile the graph.

If you edit any file under src/, clear the cache or restart Streamlit.
Otherwise you will be running the old compiled graph and chasing ghosts.
"""

from __future__ import annotations

import streamlit as st

from src.graph import build_graph, make_checkpointer

STATUS_LABEL = {
    "processing": "Processing",
    "awaiting_approval": "Awaiting approval",
    "decided": "Decided",
    "error": "Error",
}

OUTCOME_LABEL = {"approve": "Approved", "partial": "Partial", "deny": "Denied"}


@st.cache_resource
def get_graph():
    return build_graph(make_checkpointer())


def money(v) -> str:
    try:
        return f"${float(v):,.2f}"
    except (TypeError, ValueError):
        return "-"


def status_chip(row: dict) -> str:
    """Plain text status, no decoration. Keeps the demo readable on a projector."""
    status = row.get("status", "")
    if status == "decided":
        return OUTCOME_LABEL.get(row.get("outcome"), "Decided")
    return STATUS_LABEL.get(status, status)
