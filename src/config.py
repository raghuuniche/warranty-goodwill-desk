"""
Every number that governs agent behaviour lives here, not scattered in prompts.

WHY this matters beyond the course project
------------------------------------------
In an enterprise agent system the autonomy policy must be configuration, not
code. A client changes the approval threshold without a release. An auditor
reads one file to see what the boundaries were on a given date. The moment a
threshold is buried inside a prompt string you have lost both of those.

Treat this file as the tiny ancestor of a real agent charter.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# --- Model -----------------------------------------------------------------
# The course notebook uses gpt-5.5. Override with MODEL in your .env.
MODEL = os.getenv("MODEL", "gpt-5.5")

# Rough price per 1M tokens, USD. Edit to match whatever model you point at.
# WHY hardcode it: you want a cost number in the UI today. In production this
# comes from the gateway, not from a constant in your app.
PRICE_PER_MTOK_IN = float(os.getenv("PRICE_IN", "1.25"))
PRICE_PER_MTOK_OUT = float(os.getenv("PRICE_OUT", "10.00"))

# --- Autonomy policy -------------------------------------------------------

# Any proposed payout at or above this goes to a human before it is final.
HUMAN_APPROVAL_THRESHOLD_USD = 500.0
GOODWILL_CAP_USD = 1500.0

# How many times the reviewer may bounce work back to the adjudicator before
# the system gives up and escalates to a human instead of looping.
# THIS IS THE MOST IMPORTANT NUMBER IN THE PROJECT. Without it, two agents
# that disagree will burn your budget until the recursion limit kills the run.
MAX_REVISIONS = 3

# Hard ceiling on graph steps. Not a token budget. A backstop against cycles
# you did not anticipate.
RECURSION_LIMIT = 40

# --- Paths -----------------------------------------------------------------
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "state")
CHECKPOINT_DB = os.path.join(STATE_DIR, "checkpoints.sqlite")


def estimate_cost(tokens_in: int, tokens_out: int) -> float:
    return (tokens_in * PRICE_PER_MTOK_IN + tokens_out * PRICE_PER_MTOK_OUT) / 1_000_000
