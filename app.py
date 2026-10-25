"""
Entry point for the multi page demo.

    streamlit run app.py

THREE AUDIENCES, THREE PAGES
----------------------------
Dealer portal   what the customer of the service sees. No agents visible.
Agent console   what the operator sees. Every step, every token, every dollar.
Review queue    what the human reviewer sees. Only claims that need them.

Splitting by audience rather than by feature is why this reads as a product
rather than a demo harness. It is also the honest shape of an agent system in
an enterprise. Three groups of people care about three different things, and
the one group that should never see the agents is the end user.

The old single page version is kept as app_single_page.py.bak if you want to
compare, or to fall back to during the recording.
"""

import streamlit as st

st.set_page_config(page_title="Warranty goodwill desk", layout="wide")

from src import registry  # noqa: E402  (after set_page_config by design)

pending = registry.pending_count()

pages = [
    st.Page("views/dealer.py", title="Dealer portal", default=True),
    st.Page("views/agents_view.py", title="Agent console"),
    st.Page(
        "views/approvals.py",
        title=f"Review queue ({pending})" if pending else "Review queue",
    ),
]

with st.sidebar:
    st.subheader("Warranty goodwill desk")
    st.caption("Multi agent claim adjudication with human review.")
    if pending:
        st.warning(f"{pending} claim{'s' if pending > 1 else ''} awaiting review")

st.navigation(pages).run()
