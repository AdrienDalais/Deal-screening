"""What may be sent, to whom. Checked before anything can leave the machine.

This module contains no network code and imports no SDK. That is the
point: the decision about whether a request is permitted is made in a
place that is incapable of making the request.

Two rules, in order.

**A confidential deal may only use a local provider.** The database
already rejects an analysis_runs row recording a confidential deal
against a hosted provider — but a database constraint rejects the
*record* after the network call has already happened. This runs first.

**Only an explicitly registered document may be sent.** Not a path that
happens to exist, not whatever is in a folder: a document registered
against this deal, named by the caller. There is no directory walking
anywhere in this project, and a request naming anything else is refused.

Every permitted request produces a Manifest saying exactly what would
leave the machine, which is recorded whether or not the call succeeds.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from storage.enums import Confidentiality, Provider

# Providers that run on this machine. Everything else is hosted, and a
# confidential deal may not use it.
LOCAL_PROVIDERS = frozenset({Provider.LOCAL_OLLAMA, Provider.NONE})


class ProviderRefusal(Exception):
    """A request that will not be sent. Never caught and retried."""


class ConfidentialityViolation(ProviderRefusal):
    """A confidential deal, directed at a hosted provider."""


class UnregisteredDocument(ProviderRefusal):
    """Content that is not a document registered against this deal."""


class EmptyRequest(ProviderRefusal):
    """Nothing to send. Refused so that an empty call cannot be logged
    as a successful extraction."""


@dataclass(frozen=True)
class RegisteredDocument:
    """A document the analyst has registered against a deal.

    `content` is held rather than read on demand, deliberately: the
    policy layer never touches the filesystem, so it cannot be persuaded
    to read a file nobody registered.
    """

    document_id: int | None
    filename: str
    content: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content.encode()).hexdigest()


@dataclass(frozen=True)
class SendRequest:
    deal_id: int | None
    deal_name: str
    confidentiality: Confidentiality
    provider: Provider
    model_name: str
    purpose: str
    document: RegisteredDocument


@dataclass(frozen=True)
class Manifest:
    """What would leave this machine, recorded before it does.

    Written whether or not the call then succeeds, so that a failed or
    interrupted request still leaves a record that it was attempted.
    """

    deal_name: str
    confidentiality: str
    provider: str
    model_name: str
    purpose: str
    filename: str
    document_sha256: str
    characters: int
    approximate_tokens: int
    prepared_at: datetime

    def describe(self) -> str:
        return (
            f"{self.provider} / {self.model_name}: {self.characters:,} "
            f"characters (~{self.approximate_tokens:,} tokens) from "
            f"{self.filename} for deal {self.deal_name!r} "
            f"[{self.confidentiality}], purpose {self.purpose!r}."
        )


def is_local(provider: Provider) -> bool:
    return provider in LOCAL_PROVIDERS


def assert_may_send(
    request: SendRequest,
    registered: frozenset[str] | set[str],
) -> Manifest:
    """Permit or refuse. Returns the manifest; raises otherwise.

    `registered` is the set of filenames registered against this deal.
    The caller supplies it from the database; this function does not go
    looking, because a check that can discover its own inputs is not a
    check.
    """
    if (request.confidentiality == Confidentiality.CONFIDENTIAL
            and not is_local(request.provider)):
        raise ConfidentialityViolation(
            f"Deal {request.deal_name!r} is marked confidential and "
            f"{request.provider.value} is a hosted provider. Nothing from "
            f"this deal may leave this machine. Use "
            f"{Provider.LOCAL_OLLAMA.value}."
        )

    if request.document.filename not in registered:
        raise UnregisteredDocument(
            f"{request.document.filename!r} is not registered against deal "
            f"{request.deal_name!r}. Only documents registered against a "
            f"deal may be sent. Registered: "
            f"{', '.join(sorted(registered)) or 'none'}."
        )

    if not request.document.content.strip():
        raise EmptyRequest(
            f"{request.document.filename!r} has no text content. Refused, "
            f"so that an empty request cannot be recorded as a successful "
            f"extraction."
        )

    return Manifest(
        deal_name=request.deal_name,
        confidentiality=request.confidentiality.value,
        provider=request.provider.value,
        model_name=request.model_name,
        purpose=request.purpose,
        filename=request.document.filename,
        document_sha256=request.document.sha256,
        characters=len(request.document.content),
        approximate_tokens=len(request.document.content) // 4,
        prepared_at=datetime.now(timezone.utc),
    )
