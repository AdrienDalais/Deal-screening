"""What may leave this machine.

These are the tests that matter most in the project. Everything else
protects the quality of an answer; these protect a confidentiality
obligation to someone who is not in the room.
"""

from __future__ import annotations

import pytest

from llm.policy import (
    ConfidentialityViolation, EmptyRequest, RegisteredDocument, SendRequest,
    UnregisteredDocument, assert_may_send, is_local,
)
from llm.provider import Completion, LLMProvider
from storage.enums import Confidentiality, Provider, RunStatus

DOC = RegisteredDocument(1, "cim.pdf", "Revenue was 15.4m in FY24.")


def request(confidentiality: Confidentiality, provider: Provider,
            document: RegisteredDocument = DOC) -> SendRequest:
    return SendRequest(
        deal_id=1, deal_name="Thornbury Analytics",
        confidentiality=confidentiality, provider=provider,
        model_name="mistral-large-latest", purpose="extraction",
        document=document)


# ---------------------------------------------------------------------
# Confidentiality
# ---------------------------------------------------------------------

def test_a_confidential_deal_cannot_be_sent_to_a_hosted_provider():
    with pytest.raises(ConfidentialityViolation):
        assert_may_send(
            request(Confidentiality.CONFIDENTIAL, Provider.MISTRAL_API),
            {"cim.pdf"})


def test_a_confidential_deal_may_use_the_local_provider():
    manifest = assert_may_send(
        request(Confidentiality.CONFIDENTIAL, Provider.LOCAL_OLLAMA),
        {"cim.pdf"})
    assert manifest.provider == "local_ollama"


def test_synthetic_and_public_deals_may_use_a_hosted_provider():
    for level in (Confidentiality.SYNTHETIC, Confidentiality.PUBLIC):
        manifest = assert_may_send(
            request(level, Provider.MISTRAL_API), {"cim.pdf"})
        assert manifest.confidentiality == level.value


def test_only_ollama_and_none_count_as_local():
    """A provider added later is hosted until someone says otherwise.
    The safe default is the one that requires a deliberate change."""
    assert is_local(Provider.LOCAL_OLLAMA)
    assert not is_local(Provider.MISTRAL_API)


# ---------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------

def test_an_unregistered_document_is_refused():
    """Not a path that happens to exist — a document registered against
    this deal. There is no directory walking in this project."""
    with pytest.raises(UnregisteredDocument):
        assert_may_send(
            request(Confidentiality.SYNTHETIC, Provider.MISTRAL_API,
                    RegisteredDocument(None, "notes_from_my_desktop.pdf",
                                       "something else entirely")),
            {"cim.pdf", "financials.xlsx"})


def test_registration_is_per_deal_not_global():
    """A document registered against one deal is not thereby sendable
    for another."""
    with pytest.raises(UnregisteredDocument):
        assert_may_send(request(Confidentiality.SYNTHETIC,
                                Provider.MISTRAL_API), set())


def test_an_empty_document_is_refused():
    with pytest.raises(EmptyRequest):
        assert_may_send(
            request(Confidentiality.SYNTHETIC, Provider.MISTRAL_API,
                    RegisteredDocument(1, "cim.pdf", "   \n  ")),
            {"cim.pdf"})


# ---------------------------------------------------------------------
# The manifest
# ---------------------------------------------------------------------

def test_the_manifest_states_exactly_what_would_be_sent():
    manifest = assert_may_send(
        request(Confidentiality.SYNTHETIC, Provider.MISTRAL_API),
        {"cim.pdf"})
    assert manifest.filename == "cim.pdf"
    assert manifest.characters == len(DOC.content)
    assert manifest.document_sha256 == DOC.sha256
    assert "cim.pdf" in manifest.describe()
    assert "mistral_api" in manifest.describe()


# ---------------------------------------------------------------------
# The interface cannot be used around the check
# ---------------------------------------------------------------------

class _Spy(LLMProvider):
    """Records whether a send was ever attempted."""

    provider = Provider.MISTRAL_API
    model_name = "mistral-large-latest"

    def __init__(self) -> None:
        self.attempts = 0
        self.manifests = []

    def on_manifest(self, manifest):
        self.manifests.append(manifest)

    def _complete(self, request, prompt, manifest):
        self.attempts += 1
        return Completion(text="{}", manifest=manifest,
                          status=RunStatus.SUCCESS)


def test_a_refusal_means_nothing_was_attempted():
    """THE TEST THIS MODULE EXISTS FOR.

    The database constraint rejects the *record* of a confidential call,
    which happens after the network request. This proves the request is
    never made in the first place.
    """
    spy = _Spy()
    with pytest.raises(ConfidentialityViolation):
        spy.send(request(Confidentiality.CONFIDENTIAL, Provider.MISTRAL_API),
                 {"cim.pdf"}, prompt="extract the financials")
    assert spy.attempts == 0
    assert spy.manifests == []


def test_a_permitted_request_is_manifested_before_it_is_sent():
    spy = _Spy()
    result = spy.send(
        request(Confidentiality.SYNTHETIC, Provider.MISTRAL_API),
        {"cim.pdf"}, prompt="extract the financials")
    assert spy.attempts == 1
    assert len(spy.manifests) == 1
    assert result.manifest.filename == "cim.pdf"


def test_an_unregistered_document_never_reaches_the_provider():
    spy = _Spy()
    with pytest.raises(UnregisteredDocument):
        spy.send(request(Confidentiality.SYNTHETIC, Provider.MISTRAL_API),
                 set(), prompt="extract the financials")
    assert spy.attempts == 0


def test_importing_the_llm_package_loads_no_network_client():
    """The SDK import lives inside a concrete provider's _complete, so
    that importing this package — or running these tests — never loads a
    network client."""
    import sys

    for module in ("llm", "llm.policy", "llm.provider"):
        __import__(module)
    assert "mistralai" not in sys.modules
