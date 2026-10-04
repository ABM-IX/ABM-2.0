"""
abm/orchestrator/groq_gateway.py
==================================
Groq Model Gateway — Active Sole Reasoning Provider
Spec Reference: Architectural Constitution Rule 4 (identity constrains reasoning),
                Rule 5 (every action is auditable)

The sole active ModelGatewayInterface implementation. All generation routes
through Groq's cloud API. Ollama code remains in model_gateway.py but is
not wired to any active execution path.

SENSITIVITY CLASSIFIER (constitution rules 4 and 5):
  Any request containing Stream D content (identity, FirstMinds, personal
  principles) or content clearly outside ABM client project scope is blocked
  before reaching Groq. Blocked requests raise ModelGatewayError with a
  user-readable message. Every block is logged with the matching reason.

Config:
  Set APIConfig.model_gateway_provider = "groq" (default in ABMLauncher).
  Requires GROQ_API_KEY environment variable.
  On missing key or Groq failure, raises ModelGatewayError — no silent Ollama
  fallback. The caller (answerQuestion) catches this and surfaces a clear
  degraded=True response.

Design contract:
  - generate() is the only write method.
  - SensitivityClassifier.is_sensitive() is called before every Groq call.
  - If sensitive: raise ModelGatewayError (sensitivity block).
  - If Groq fails for any reason: raise ModelGatewayError (no local fallback).
  - is_available() checks Groq API reachability. Never raises.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import TYPE_CHECKING

import requests

# Import ModelGatewayInterface via direct module path to avoid circular import
# (abm.api.__init__ imports capabilities which imports orchestrator.departments).
from abm.api.core import interfaces as _ifaces  # noqa: E402  (direct submodule, no __init__ chain)
ModelGatewayInterface = _ifaces.ModelGatewayInterface

from abm.orchestrator.model_gateway import (
    GenerationResponse,
    ModelGatewayError,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Default Groq model to use for generation.
DEFAULT_GROQ_MODEL: str = "llama-3.1-8b-instant"

#: Groq API base URL.
GROQ_API_BASE_URL: str = "https://api.groq.com"

#: Groq chat completions endpoint.
GROQ_COMPLETIONS_ENDPOINT: str = f"{GROQ_API_BASE_URL}/openai/v1/chat/completions"

#: Environment variable name for the Groq API key.
GROQ_API_KEY_ENV: str = "GROQ_API_KEY"


# ---------------------------------------------------------------------------
# SensitivityClassifier
# ---------------------------------------------------------------------------


class SensitivityClassifier:
    """
    Pre-flight classifier that blocks sensitive content from reaching Groq.

    Blocks any request that:
    1. Contains Stream D keywords (identity, personal principles, FirstMinds data).
    2. Contains clearly non-ABM-project content (personal data, private context).

    This enforces Architectural Constitution Rule 4 (identity constrains
    reasoning) and Rule 1 (local-first for sensitive data).

    All block events are logged with the matching reason for auditability
    (Rule 5: every action is auditable).
    """

    #: Stream D / identity keywords that must stay local.
    _STREAM_D_PATTERNS: list[re.Pattern] = [
        re.compile(r"\b(cognitive identity|stream d|abm_cognitive_identity)\b", re.IGNORECASE),
        re.compile(r"\b(firstminds|first minds)\b", re.IGNORECASE),
        re.compile(r"\b(arabang)\b", re.IGNORECASE),
        re.compile(r"\b(personal principle|immutable principle|identity foundation)s?\b", re.IGNORECASE),
        re.compile(r"\b(my (goals?|values?|principles?|identity|mission|vision))\b", re.IGNORECASE),
        re.compile(r"\b(volatility.*immutable|owner.*ABM)\b", re.IGNORECASE),
    ]

    #: Patterns indicating content that is clearly outside ABM client scope.
    _NON_CLIENT_PATTERNS: list[re.Pattern] = [
        re.compile(r"\b(social security|passport|national id|tax id|ID number)\b", re.IGNORECASE),
        re.compile(r"\b(bank account|credit card|financial credential)s?\b", re.IGNORECASE),
        re.compile(r"\b(medical record|health data|patient data)\b", re.IGNORECASE),
    ]

    @classmethod
    def is_sensitive(cls, prompt: str) -> tuple[bool, str]:
        """
        Check whether ``prompt`` contains sensitive content that must not
        leave the local machine.

        Parameters
        ----------
        prompt : str
            The prompt text to analyse.

        Returns
        -------
        tuple[bool, str]
            ``(True, reason)`` if sensitive — caller must use local fallback.
            ``(False, "")`` if safe to send to Groq.
        """
        for pattern in cls._STREAM_D_PATTERNS:
            if pattern.search(prompt):
                pat_preview = repr(pattern.pattern[:60])
                reason = (
                    f"Prompt matches Stream D / identity pattern "
                    f"({pat_preview}). Routing to local Ollama."
                )
                logger.warning("SensitivityClassifier: BLOCKED — %s", reason)
                return True, reason

        for pattern in cls._NON_CLIENT_PATTERNS:
            if pattern.search(prompt):
                pat_preview = repr(pattern.pattern[:60])
                reason = (
                    f"Prompt matches non-ABM-client-project pattern "
                    f"({pat_preview}). Routing to local Ollama."
                )
                logger.warning("SensitivityClassifier: BLOCKED — %s", reason)
                return True, reason

        return False, ""


# ---------------------------------------------------------------------------
# GroqModelGateway
# ---------------------------------------------------------------------------


class GroqModelGateway(ModelGatewayInterface):
    """
    ModelGatewayInterface implementation backed by Groq's cloud API.

    This is the sole active reasoning provider. Ollama is not used as a
    fallback. On sensitivity block or Groq failure, ModelGatewayError is
    raised with a clear user-readable message.

    Parameters
    ----------
    groq_model : str
        Groq model name. Defaults to ``DEFAULT_GROQ_MODEL``.
    timeout_seconds : int
        HTTP timeout for Groq API calls in seconds. Defaults to 30.
    """

    def __init__(
        self,
        groq_model: str = DEFAULT_GROQ_MODEL,
        timeout_seconds: int = 30,
        # Legacy keyword args accepted but ignored — kept for call-site compatibility
        ollama_model: str = "",
        ollama_host: str = "",
        ollama_port: int = 0,
    ) -> None:
        self._groq_model = groq_model
        self._timeout = timeout_seconds
        self._api_key: str = os.environ.get(GROQ_API_KEY_ENV, "")
        self._classifier = SensitivityClassifier()

        if not self._api_key:
            logger.warning(
                "GroqModelGateway: %s not set — generate() will raise ModelGatewayError.",
                GROQ_API_KEY_ENV,
            )
        else:
            logger.info(
                "GroqModelGateway: initialised (groq_model=%s). Groq is the sole provider.",
                groq_model,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, prompt: str, *, max_tokens: int = 0) -> GenerationResponse:
        """
        Generate text using Groq's cloud API.

        Before sending to Groq:
          1. Checks that GROQ_API_KEY is present — raises ModelGatewayError if missing.
          2. Runs SensitivityClassifier — raises ModelGatewayError if blocked.
          3. Calls Groq API — raises ModelGatewayError on any network/HTTP error.

        There is NO local Ollama fallback. Callers (e.g. answerQuestion) catch
        ModelGatewayError and set degraded=True with a user-visible message.

        Parameters
        ----------
        prompt : str
            The prompt to send.
        max_tokens : int
            Maximum tokens to generate. 0 means model default.

        Returns
        -------
        GenerationResponse
            The Groq API response.

        Raises
        ------
        ModelGatewayError
            On missing API key, sensitivity block, or any Groq API failure.
        ValueError
            If prompt is empty or whitespace-only.
        """
        if not prompt or not prompt.strip():
            raise ValueError("GroqModelGateway.generate: prompt must be non-empty.")

        # 1. API key missing → hard error
        if not self._api_key:
            raise ModelGatewayError(
                f"GroqModelGateway: {GROQ_API_KEY_ENV} is not set. "
                "Set the GROQ_API_KEY environment variable to enable generation."
            )

        # 2. Sensitivity classifier gate — hard block, no local fallback
        is_sensitive, reason = self._classifier.is_sensitive(prompt)
        if is_sensitive:
            logger.warning(
                "GroqModelGateway.generate: sensitivity block — request cannot be sent to cloud. Reason: %s",
                reason,
            )
            raise ModelGatewayError(
                f"GroqModelGateway: request blocked by sensitivity classifier. "
                f"This content cannot be sent to the cloud provider. Reason: {reason}"
            )

        # 3. Groq API call — raise on any failure
        t0 = time.monotonic()
        try:
            payload: dict = {
                "model": self._groq_model,
                "messages": [{"role": "user", "content": prompt}],
            }
            if max_tokens > 0:
                payload["max_tokens"] = max_tokens

            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }

            response = requests.post(
                GROQ_COMPLETIONS_ENDPOINT,
                json=payload,
                headers=headers,
                timeout=self._timeout,
            )
            response.raise_for_status()

        except requests.exceptions.ConnectionError as exc:
            raise ModelGatewayError(
                f"GroqModelGateway: cannot connect to Groq API. "
                f"Check your internet connection. Detail: {exc}"
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise ModelGatewayError(
                f"GroqModelGateway: request timed out after {self._timeout}s. Detail: {exc}"
            ) from exc
        except requests.exceptions.HTTPError as exc:
            raise ModelGatewayError(
                f"GroqModelGateway: HTTP error from Groq API. Detail: {exc}"
            ) from exc

        latency_ms = int((time.monotonic() - t0) * 1000)

        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"]
            model_name = data.get("model", self._groq_model)
        except (KeyError, IndexError, ValueError) as exc:
            raise ModelGatewayError(
                f"GroqModelGateway: failed to parse Groq API response — {exc}"
            ) from exc

        logger.debug(
            "GroqModelGateway.generate: OK in %dms (model=%s, response_len=%d)",
            latency_ms, model_name, len(text),
        )
        return GenerationResponse(text=text, latency_ms=latency_ms, model=model_name)

    def is_available(self) -> bool:
        """
        Check whether the Groq API is reachable and the API key is set.

        Falls back gracefully — never raises.

        Returns
        -------
        bool
            True if Groq responded with a non-error status AND a key is set.
        """
        if not self._api_key:
            return False
        try:
            # A lightweight ping to the Groq models endpoint
            response = requests.get(
                f"{GROQ_API_BASE_URL}/openai/v1/models",
                headers={"Authorization": f"Bearer {self._api_key}"},
                timeout=5,
            )
            available = response.status_code < 300
            logger.debug(
                "GroqModelGateway.is_available: %s (status=%d)", available, response.status_code
            )
            return available
        except Exception:
            logger.debug("GroqModelGateway.is_available: False (connection error).")
            return False

    @property
    def model(self) -> str:
        """The Groq model name used by this gateway."""
        return self._groq_model

    @property
    def groq_api_key_configured(self) -> bool:
        """True if the GROQ_API_KEY environment variable is set."""
        return bool(self._api_key)


__all__ = [
    "GroqModelGateway",
    "SensitivityClassifier",
    "DEFAULT_GROQ_MODEL",
    "GROQ_API_KEY_ENV",
]
