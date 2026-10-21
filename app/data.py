"""Loading for the Streamlit app. No business logic — CLAUDE.md section 4.

Everything here is a thin cache around core.pipeline. The app must not
be able to compute a figure of its own: if a number appears on screen it
came from the same code the tests cover.
"""

from __future__ import annotations

import streamlit as st

from core.pipeline import DealReport
from tests.fixtures.build_all import COMPANIES, FIXTURE_ROOT
from tools.run_deal import report_for

# The synthetic companies are the only deals that exist. When real deals
# are loaded from the database this is the one function that changes.
DEALS = {c.slug: c for c in COMPANIES}


@st.cache_data(show_spinner=False)
def load(slug: str) -> DealReport:
    return report_for(DEALS[slug])


def truth(slug: str):
    return DEALS[slug]


def fixture_dir(slug: str):
    return FIXTURE_ROOT / slug
