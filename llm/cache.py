"""Stored summaries, and knowing when they are stale.

Summaries are cached because regenerating them costs a wait and an API
call every time a page is opened, and the answer does not change unless
something that produced it changes.

**The cache key is what produced the summary**, not the deal: the
document's content hash, the prompt version, and the model name. Change
the CIM, revise the prompt, or move to a different model, and the cache
no longer matches — so a stale summary announces itself rather than
being quietly served as current.

That is the same principle as the reconciliation fingerprint in decision
011: a stored conclusion must not outlive the thing it was concluded
from.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from llm.summarise import Summary


@dataclass(frozen=True)
class CacheKey:
    document_sha256: str
    prompt_version: int
    model_name: str

    @property
    def digest(self) -> str:
        return hashlib.sha256(
            f"{self.document_sha256}|{self.prompt_version}|{self.model_name}"
            .encode()).hexdigest()[:16]


@dataclass
class CachedBriefing:
    key: CacheKey
    generated_at: str
    summaries: list[Summary]
    failures: list[tuple[str, str]]

    def is_current_for(self, key: CacheKey) -> bool:
        return self.key.digest == key.digest

    def staleness(self, key: CacheKey) -> list[str]:
        """Say *what* changed, not merely that something did."""
        reasons = []
        if self.key.document_sha256 != key.document_sha256:
            reasons.append("the document has changed since this was written")
        if self.key.prompt_version != key.prompt_version:
            reasons.append(
                f"written with prompt v{self.key.prompt_version}, "
                f"current is v{key.prompt_version}")
        if self.key.model_name != key.model_name:
            reasons.append(
                f"written by {self.key.model_name}, current model is "
                f"{key.model_name}")
        return reasons


def document_hash(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path: Path, key: CacheKey, summaries: list[Summary],
         failures: list[tuple[str, str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "key": asdict(key),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "summaries": [
            {**asdict(s), "source_pages": list(s.source_pages)}
            for s in summaries
        ],
        "failures": [list(f) for f in failures],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def load(path: Path) -> CachedBriefing | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text())
    return CachedBriefing(
        key=CacheKey(**payload["key"]),
        generated_at=payload["generated_at"],
        summaries=[
            Summary(**{**s, "source_pages": tuple(s["source_pages"])})
            for s in payload["summaries"]
        ],
        failures=[tuple(f) for f in payload["failures"]],
    )
