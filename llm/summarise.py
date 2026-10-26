"""Plain-language summaries of CIM sections.

The one thing in this project a model does that deterministic code
cannot: turn a sales document's prose into three sentences a reader with
no industry knowledge can follow.

**The model writes prose and never writes a figure.** That is enforced
here, not merely asked for in the prompt: a summary containing a digit
is rejected. Every number in the finished snapshot comes from an
extracted observation carrying its own source reference, so a plausible
invented figure is not a risk to be managed — it is a category that
cannot occur.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ingestion.pdf import Document
from llm.policy import RegisteredDocument, SendRequest
from llm.provider import LLMProvider
from retrieval.keyword import Section, find_sections
from storage.enums import Confidentiality, RunStatus

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
PROMPT_NAME = "summarise_section"
PROMPT_VERSION = 1

NOT_STATED = "NOT STATED"
MAX_SENTENCES = 3

# Checking for digits alone let "every two weeks" and "three-year
# contracts" through. A figure spelled out is still a figure the model
# supplied rather than reviewed data did.
SPELLED_NUMBERS = (
    "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "twenty", "thirty", "forty",
    "fifty", "hundred", "thousand", "million", "billion",
)

# The sections worth putting in front of a reader, and the plain
# question each one answers.
SNAPSHOT_SECTIONS: dict[str, str] = {
    "business_overview": "What the company does",
    "executive_summary": "The problem it solves",
    "product": "How the product works",
    "customers": "Who buys it",
    "market": "The market it sells into",
    "management": "Who runs it",
}


class SummaryRejected(Exception):
    """The model returned something that may not be shown."""


@dataclass(frozen=True)
class Summary:
    key: str
    question: str
    text: str
    source_pages: tuple[int, ...]
    prompt_version: int
    model_name: str
    input_tokens: int | None = None
    output_tokens: int | None = None

    @property
    def citation(self) -> str:
        pages = self.source_pages
        if not pages:
            return "no source pages"
        if len(pages) == 1:
            return f"p.{pages[0]}"
        return f"pp.{pages[0]}–{pages[-1]}"


def load_prompt() -> str:
    text = (PROMPT_DIR / f"{PROMPT_NAME}_v{PROMPT_VERSION}.md").read_text()
    # Strip the front matter: it documents the prompt, it is not part of it.
    if text.startswith("---"):
        text = text.split("---", 2)[-1]
    return text.strip()


def _sentence_count(text: str) -> int:
    return len([s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s])


def validate(text: str) -> str:
    """Accept a summary, or refuse it with a reason.

    Rejecting is the right outcome. A summary that breaks these rules is
    not a summary to be tidied up — it is evidence the prompt or the
    model is not doing what was asked, and showing it anyway would mean
    the rules exist only on paper.
    """
    cleaned = text.strip().strip('"')

    if not cleaned:
        raise SummaryRejected("empty response")

    if cleaned.upper().startswith(NOT_STATED):
        return NOT_STATED

    if re.search(r"\d", cleaned):
        raise SummaryRejected(
            f"contains a figure, which only reviewed data may supply: "
            f"{cleaned[:120]!r}")

    spelled = [word for word in SPELLED_NUMBERS
               if re.search(rf"\b{word}\b", cleaned, re.IGNORECASE)]
    if spelled:
        raise SummaryRejected(
            f"contains a quantity spelled out ({', '.join(spelled)}), "
            f"which only reviewed data may supply: {cleaned[:120]!r}")

    if _sentence_count(cleaned) > MAX_SENTENCES:
        raise SummaryRejected(
            f"{_sentence_count(cleaned)} sentences, maximum is "
            f"{MAX_SENTENCES}")

    return cleaned


def summarise_section(
    provider: LLMProvider,
    section: Section,
    question: str,
    *,
    deal_name: str,
    confidentiality: Confidentiality,
    registered: set[str],
    filename: str,
    deal_id: int | None = None,
) -> Summary:
    prompt = load_prompt().format(section_name=section.heading,
                                  section_text=section.text[:12_000])

    request = SendRequest(
        deal_id=deal_id, deal_name=deal_name,
        confidentiality=confidentiality, provider=provider.provider,
        model_name=provider.model_name,
        purpose=f"summarise:{section.name}",
        document=RegisteredDocument(None, filename, section.text),
    )

    completion = provider.send(request, registered, prompt)
    if completion.status != RunStatus.SUCCESS:
        raise SummaryRejected(completion.error_message or "request failed")

    return Summary(
        key=section.name, question=question,
        text=validate(completion.text),
        source_pages=section.pages,
        prompt_version=PROMPT_VERSION, model_name=provider.model_name,
        input_tokens=completion.input_tokens,
        output_tokens=completion.output_tokens,
    )


def summarise_document(
    provider: LLMProvider,
    document: Document,
    *,
    deal_name: str,
    confidentiality: Confidentiality,
    registered: set[str],
    filename: str,
) -> tuple[list[Summary], list[tuple[str, str]]]:
    """Summarise each snapshot section. Returns (summaries, failures).

    A failure is returned rather than raised, so that one rejected
    section does not cost the other five. What is shown is what passed.
    """
    sections = {s.name: s for s in find_sections(document)}
    summaries: list[Summary] = []
    failures: list[tuple[str, str]] = []

    for name, question in SNAPSHOT_SECTIONS.items():
        section = sections.get(name)
        if section is None:
            failures.append((name, "section not found in the document"))
            continue
        try:
            summaries.append(summarise_section(
                provider, section, question, deal_name=deal_name,
                confidentiality=confidentiality, registered=registered,
                filename=filename))
        except SummaryRejected as error:
            failures.append((name, str(error)))

    return summaries, failures
