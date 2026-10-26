"""Loading for the Streamlit app. No business logic — CLAUDE.md section 4.

Everything here is a thin cache around core.pipeline. The app must not
be able to compute a figure of its own: if a number appears on screen it
came from the same code the tests cover.
"""

from __future__ import annotations

import streamlit as st

from core.pipeline import DealReport
from ingestion.pdf import Document, read
from llm import cache
from llm.summarise import PROMPT_VERSION
from retrieval.keyword import best_kpis
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


def cim_path(slug: str):
    return fixture_dir(slug) / f"{slug}_cim_slides.pdf"


@st.cache_data(show_spinner=False)
def load_document(slug: str) -> Document:
    return read(cim_path(slug))


@st.cache_data(show_spinner=False)
def load_kpis(slug: str) -> dict:
    """The best-evidenced statement of each metric stated in the CIM's
    prose, with the sentence and page it came from. Candidates for
    review, not facts."""
    return best_kpis(load_document(slug))


@st.cache_data(show_spinner=False)
def load_briefing(slug: str):
    """The cached plain-language briefing, and whether it is current.

    Returns (briefing, staleness_reasons). A briefing written against a
    different document, prompt or model is still shown — withholding it
    helps nobody — but it says so.
    """
    path = fixture_dir(slug) / "briefing.json"
    briefing = cache.load(path)
    if briefing is None:
        return None, ["no briefing has been generated for this deal"]

    key = cache.CacheKey(
        document_sha256=cache.document_hash(cim_path(slug)),
        prompt_version=PROMPT_VERSION,
        model_name=briefing.key.model_name)
    return briefing, briefing.staleness(key)
