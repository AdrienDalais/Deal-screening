"""Generate the cached briefing for a deal.

    python -m tools.summarise_deal              # all, where missing
    python -m tools.summarise_deal thornbury    # one
    python -m tools.summarise_deal --force      # regenerate regardless

Summaries are cached because the answer does not change unless the
document, the prompt or the model changes — and the cache key is exactly
those three things, so a stale briefing announces itself.

The fixture briefings are committed. Every company here is invented, so
there is nothing to protect, and it means the app runs for anyone who
clones the repository without needing an API key of their own.
"""

from __future__ import annotations

import argparse
import os

from dotenv import load_dotenv

from ingestion.pdf import read
from llm import cache
from llm.mistral_api import MistralProvider
from llm.summarise import PROMPT_VERSION, summarise_document
from storage.enums import Confidentiality
from tests.fixtures.build_all import COMPANIES, FIXTURE_ROOT


def briefing_path(slug: str):
    return FIXTURE_ROOT / slug / "briefing.json"


def generate(truth, provider, force: bool = False) -> str:
    slug = truth.slug
    pdf = FIXTURE_ROOT / slug / f"{slug}_cim_slides.pdf"
    path = briefing_path(slug)

    key = cache.CacheKey(
        document_sha256=cache.document_hash(pdf),
        prompt_version=PROMPT_VERSION,
        model_name=provider.model_name)

    existing = cache.load(path)
    if existing and existing.is_current_for(key) and not force:
        return f"{truth.name}: current, {len(existing.summaries)} answers"

    document = read(pdf)
    summaries, failures = summarise_document(
        provider, document, deal_name=truth.name,
        confidentiality=Confidentiality.SYNTHETIC,
        registered={pdf.name}, filename=pdf.name)
    cache.save(path, key, summaries, failures)
    return (f"{truth.name}: wrote {len(summaries)} answers, "
            f"{len(failures)} rejected -> {path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("company", nargs="?",
                        choices=[c.slug for c in COMPANIES])
    parser.add_argument("--force", action="store_true",
                        help="regenerate even if the cache is current")
    args = parser.parse_args()

    load_dotenv(".env", override=True)
    if not os.getenv("MISTRAL_API_KEY"):
        raise SystemExit(
            "MISTRAL_API_KEY is not set. Put it in .env — never on a "
            "command line, where it is written to shell history.")

    provider = MistralProvider(quiet=True)
    print(f"model: {provider.model_name}, prompt v{PROMPT_VERSION}\n")

    chosen = ([c for c in COMPANIES if c.slug == args.company]
              if args.company else COMPANIES)
    for truth in chosen:
        print(" ", generate(truth, provider, force=args.force))


if __name__ == "__main__":
    main()
