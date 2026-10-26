"""The provider interface. Nothing outside this package imports an SDK.

A provider cannot be called directly. `send()` is the only entry point,
it runs the policy check first, and a provider's own `_complete()` is
reachable only through it. A caller cannot skip the check by accident,
because there is no path that skips it.

The SDK import lives inside the concrete provider's `_complete()` rather
than at module scope, so that importing this package — or running the
test suite — never loads a network client at all.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from llm.policy import Manifest, SendRequest, assert_may_send
from storage.enums import Provider, RunStatus


@dataclass
class Completion:
    text: str
    manifest: Manifest
    status: RunStatus
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None
    error_message: str | None = None


class LLMProvider(ABC):
    """Base class. Subclasses implement `_complete` and nothing else."""

    provider: Provider
    model_name: str

    def send(self, request: SendRequest, registered: set[str],
             prompt: str) -> Completion:
        """The only way to reach a model.

        Refuses first, sends second. A ProviderRefusal propagates: it is
        never converted into a failed Completion, because a refusal is
        not a failed attempt — it is an attempt that did not happen, and
        recording it as a failure would suggest something was sent.
        """
        manifest = assert_may_send(request, registered)
        self.on_manifest(manifest)
        return self._complete(request, prompt, manifest)

    def on_manifest(self, manifest: Manifest) -> None:
        """Called once a request is permitted, before anything is sent.

        Override to record it. The default prints, so that during
        development nothing is ever sent silently.
        """
        print(f"[llm] about to send — {manifest.describe()}")

    @abstractmethod
    def _complete(self, request: SendRequest, prompt: str,
                  manifest: Manifest) -> Completion:
        """Perform the call. Only ever reached through `send`."""
