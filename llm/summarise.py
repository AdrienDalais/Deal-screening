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
from retrieval.keyword import find_slides
from storage.enums import Confidentiality, RunStatus

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
PROMPT_NAME = "summarise_section"
PROMPT_VERSION = 2

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

@dataclass(frozen=True)
class SnapshotItem:
    """One question, and the slides likely to answer it.

    Questions are pointed at slides rather than whole sections. A
    section runs to twenty pages of which two are relevant, and a model
    handed all twenty summarises the section instead of answering the
    question.
    """

    key: str
    question: str
    headings: tuple[str, ...]


SNAPSHOT_ITEMS: tuple[SnapshotItem, ...] = (
    SnapshotItem("what_it_does", "What does this company do?",
                 ("why the business exists", "executive summary",
                  "business overview")),
    SnapshotItem("problem", "What problem does it solve for its customers?",
                 ("executive summary", "why the business exists")),
    SnapshotItem("how_it_works", "How does the product actually work?",
                 ("product", "differentiation")),
    SnapshotItem("who_buys", "Who buys it, and why do they keep paying?",
                 ("customers", "retention analysis")),
    SnapshotItem("how_it_earns", "How does the company make its money?",
                 ("customers", "business overview", "executive summary")),
    SnapshotItem("market", "What market does it sell into, and who else "
                           "is in it?",
                 ("market", "competitive landscape")),
    SnapshotItem("growth", "How does the company plan to grow?",
                 ("growth plans", "business overview")),
)


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
    # Models reach for markdown even when asked for plain sentences,
    # and "**insurance brokers**" rendered literally looks like a bug.
    cleaned = re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", text.strip())
    cleaned = cleaned.replace("`", "").strip().strip('"')

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


def summarise_item(
    provider: LLMProvider,
    item: SnapshotItem,
    pages: tuple[int, ...],
    text: str,
    already_said: list[str],
    *,
    deal_name: str,
    confidentiality: Confidentiality,
    registered: set[str],
    filename: str,
    deal_id: int | None = None,
) -> Summary:
    prompt = load_prompt().format(
        question=item.question,
        section_text=text[:10_000],
        already_said=("\n".join(f"- {line}" for line in already_said)
                      or "- (nothing yet; this is the first part)"),
    )

    request = SendRequest(
        deal_id=deal_id, deal_name=deal_name,
        confidentiality=confidentiality, provider=provider.provider,
        model_name=provider.model_name,
        purpose=f"summarise:{item.key}",
        document=RegisteredDocument(None, filename, text),
    )

    completion = provider.send(request, registered, prompt)
    if completion.status != RunStatus.SUCCESS:
        raise SummaryRejected(completion.error_message or "request failed")

    return Summary(
        key=item.key, question=item.question,
        text=validate(completion.text),
        source_pages=pages,
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
    summaries: list[Summary] = []
    failures: list[tuple[str, str]] = []
    already_said: list[str] = []

    for item in SNAPSHOT_ITEMS:
        pages, text = find_slides(document, item.headings)
        if not text:
            failures.append((item.key, "no slide found for this question"))
            continue
        try:
            summary = summarise_item(
                provider, item, pages, text, already_said,
                deal_name=deal_name, confidentiality=confidentiality,
                registered=registered, filename=filename)
        except SummaryRejected as error:
            failures.append((item.key, str(error)))
            continue

        summaries.append(summary)
        if summary.text != NOT_STATED:
            # Each answer becomes context for the next, so the briefing
            # reads as one piece rather than eight restatements of what
            # the company sells.
            already_said.append(summary.text)

    return summaries, failures
