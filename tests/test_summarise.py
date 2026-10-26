"""Summarisation rules, tested without a network call.

A fake provider returns whatever a test tells it to, so the rules can be
exercised exhaustively and deterministically. What the real model
actually writes is a separate question, and not one a test suite can
answer.
"""

from __future__ import annotations

import pytest

from ingestion.pdf import read
from llm.policy import Manifest, SendRequest
from llm.provider import Completion, LLMProvider
from llm.summarise import (
    NOT_STATED, SNAPSHOT_ITEMS, SummaryRejected, summarise_document, validate,
)
from storage.enums import Confidentiality, Provider, RunStatus
from tests.fixtures.build_all import FIXTURE_ROOT


class FakeProvider(LLMProvider):
    provider = Provider.MISTRAL_API
    model_name = "fake-model"

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []

    def on_manifest(self, manifest: Manifest) -> None:
        pass

    def _complete(self, request: SendRequest, prompt: str,
                  manifest: Manifest) -> Completion:
        self.prompts.append(prompt)
        reply = self.replies.pop(0) if self.replies else "A plain sentence."
        return Completion(text=reply, manifest=manifest,
                          status=RunStatus.SUCCESS)


# ---------------------------------------------------------------------
# The no-figures rule
# ---------------------------------------------------------------------

def test_plain_prose_is_accepted():
    assert validate("It sells software to insurance brokers.") == \
        "It sells software to insurance brokers."


@pytest.mark.parametrize("text", [
    "Founded in 2016, it sells software.",
    "Revenue grew 32% last year.",
    "It has 214 customers.",
])
def test_a_summary_containing_a_digit_is_rejected(text):
    with pytest.raises(SummaryRejected):
        validate(text)


@pytest.mark.parametrize("text", [
    "It deploys updates every two weeks.",
    "Contracts run for three years.",
    "The two co-founders still run it.",
])
def test_a_quantity_spelled_out_is_rejected(text):
    """Checking digits alone let these through. A figure spelled out is
    still a figure the model supplied rather than reviewed data."""
    with pytest.raises(SummaryRejected):
        validate(text)


def test_more_than_three_sentences_is_rejected():
    with pytest.raises(SummaryRejected):
        validate("One thing. Another thing. A third thing. A fourth.")


def test_markdown_is_stripped_rather_than_rejected():
    """Models reach for emphasis even when asked for plain sentences,
    and it renders literally. Formatting is not a rule violation."""
    assert validate("It sells to **insurance brokers** widely.") == \
        "It sells to insurance brokers widely."


def test_not_stated_passes_through():
    assert validate("NOT STATED") == NOT_STATED


def test_an_empty_response_is_rejected():
    with pytest.raises(SummaryRejected):
        validate("   ")


# ---------------------------------------------------------------------
# The briefing as a whole
# ---------------------------------------------------------------------

@pytest.fixture(scope="module")
def document():
    path = FIXTURE_ROOT / "thornbury" / "thornbury_cim_slides.pdf"
    if not path.exists():
        pytest.skip("fixtures not built")
    return read(path)


def _run(document, replies):
    return summarise_document(
        FakeProvider(replies), document, deal_name="Thornbury Analytics",
        confidentiality=Confidentiality.SYNTHETIC,
        registered={"thornbury_cim_slides.pdf"},
        filename="thornbury_cim_slides.pdf")


def test_every_question_is_asked_and_cites_its_pages(document):
    summaries, failures = _run(document, [])
    assert len(summaries) == len(SNAPSHOT_ITEMS), failures
    for summary in summaries:
        assert summary.source_pages
        assert summary.citation.startswith("p")


def test_one_rejected_answer_does_not_cost_the_others(document):
    """A rejected section is a failure of that section, not of the
    briefing."""
    replies = ["It has 214 customers."] + ["A plain sentence."] * 10
    summaries, failures = _run(document, replies)
    assert len(failures) == 1
    assert len(summaries) == len(SNAPSHOT_ITEMS) - 1


def test_earlier_answers_are_given_to_later_questions(document):
    """Each answer becomes context for the next, so the briefing reads
    as one piece rather than seven restatements of what the company
    sells."""
    replies = ["Thornbury sells software to brokers."] + \
              ["A plain sentence."] * 10
    provider = FakeProvider(replies)
    summarise_document(
        provider, document, deal_name="Thornbury Analytics",
        confidentiality=Confidentiality.SYNTHETIC,
        registered={"thornbury_cim_slides.pdf"},
        filename="thornbury_cim_slides.pdf")

    assert "nothing yet" in provider.prompts[0]
    assert "Thornbury sells software to brokers." in provider.prompts[1]


def test_the_prompt_version_is_recorded_on_every_summary(document):
    """A summary that looks wrong in three months must be traceable to
    the instructions that produced it."""
    summaries, _ = _run(document, [])
    for summary in summaries:
        assert summary.prompt_version >= 2
        assert summary.model_name == "fake-model"


def test_a_confidential_deal_cannot_be_summarised_by_a_hosted_provider(
        document):
    from llm.policy import ConfidentialityViolation

    with pytest.raises(ConfidentialityViolation):
        summarise_document(
            FakeProvider([]), document, deal_name="Project Redacted",
            confidentiality=Confidentiality.CONFIDENTIAL,
            registered={"thornbury_cim_slides.pdf"},
            filename="thornbury_cim_slides.pdf")
