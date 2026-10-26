"""The hosted Mistral provider.

The SDK is imported inside `_complete`, not at module scope, so that
importing this module — or running the test suite — never loads a
network client. A test asserts it.

This class cannot be called around the policy check: `_complete` is
reachable only through `LLMProvider.send()`, which refuses first.
"""

from __future__ import annotations

import os
import time

from llm.policy import Manifest, SendRequest
from llm.provider import Completion, LLMProvider
from storage.enums import Provider, RunStatus

DEFAULT_MODEL = "mistral-medium-latest"


class MistralProvider(LLMProvider):
    provider = Provider.MISTRAL_API

    def __init__(self, model_name: str | None = None,
                 api_key: str | None = None, quiet: bool = False) -> None:
        self.model_name = (model_name or os.getenv("MISTRAL_MODEL")
                           or DEFAULT_MODEL)
        self._api_key = api_key or os.getenv("MISTRAL_API_KEY") or ""
        self._quiet = quiet
        if not self._api_key:
            raise RuntimeError(
                "MISTRAL_API_KEY is not set. Put it in .env — never on a "
                "command line, where it is written to shell history.")

    def on_manifest(self, manifest: Manifest) -> None:
        if not self._quiet:
            print(f"[llm] sending — {manifest.describe()}")

    def _complete(self, request: SendRequest, prompt: str,
                  manifest: Manifest) -> Completion:
        # Imported here, not at module scope. Nothing that merely reads
        # this file loads a network client.
        from mistralai.client import Mistral

        client = Mistral(api_key=self._api_key)
        started = time.time()
        try:
            response = client.chat.complete(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,     # deterministic: the same section
                                     # should summarise the same way twice
                max_tokens=400,
            )
        except Exception as error:
            message = str(error)
            status = (RunStatus.FAILED if "429" not in message
                      else RunStatus.FAILED)
            return Completion(
                text="", manifest=manifest, status=status,
                latency_ms=int((time.time() - started) * 1000),
                error_message=message[:500])

        return Completion(
            text=(response.choices[0].message.content or "").strip(),
            manifest=manifest,
            status=RunStatus.SUCCESS,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            latency_ms=int((time.time() - started) * 1000),
        )
