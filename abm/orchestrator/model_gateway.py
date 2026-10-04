"""
abm/orchestrator/model_gateway.py
===================================
Ollama Model Gateway â€” Phase v0.3 Executive Orchestrator Engine
Spec Reference: ABM_SPEC.md section 4 ("Model Agnostic Channels")

A thin, model-agnostic wrapper around Ollama's /api/generate endpoint.
All calls route through the local loopback (127.0.0.1:11434) â€” no network
access. This parallels OllamaEmbeddingWrapper from v0.1 but targets
text-generation models (qwen2.5-coder:3b for classification) rather than embedding.

Design contract:
  - generate() is the only write method. There is no stream(), complete(),
    or chat() method. The gateway is a single-call synchronous interface.
  - stream is always set to false so the full response arrives in one HTTP
    response body rather than a streaming chunked transfer.
  - Returns GenerationResponse â€” a plain dataclass with text and latency_ms.
  - Raises ModelGatewayError (RuntimeError subclass) on connection failure,
    timeout, or non-2xx HTTP. The router catches this and applies its fallback
    policy â€” it never propagates to the caller.
  - is_available() does a HEAD /api/tags health check. It never raises.
  - The model name is injected at construction time to keep the gateway
    model-agnostic per spec section 4 protocol wrapper mandate.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Classification model per spec section 4.
DEFAULT_CLASSIFICATION_MODEL: str = "qwen2.5-coder:3b"

#: Default Ollama loopback address.
DEFAULT_HOST: str = "127.0.0.1"
DEFAULT_PORT: int = 11434

#: Default HTTP timeout for a generation call.
DEFAULT_TIMEOUT_SECONDS: int = 30


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ModelGatewayError(RuntimeError):
    """
    Raised when the Ollama model gateway cannot complete a generation call.

    Subclasses ``RuntimeError`` so callers that catch ``RuntimeError`` also
    handle it, while tests can assert specifically on ``ModelGatewayError``.
    """


# ---------------------------------------------------------------------------
# GenerationResponse
# ---------------------------------------------------------------------------


@dataclass
class GenerationResponse:
    """
    The result of a successful ``OllamaModelGateway.generate()`` call.

    Attributes
    ----------
    text : str
        The raw text returned by the model (Ollama's ``"response"`` field).
        The router is responsible for parsing structured content from this.
    latency_ms : int
        Wall-clock round-trip time in milliseconds from the HTTP request
        to the parsed response.
    model : str
        The model name that produced this response (from Ollama's JSON).
    """

    text: str
    latency_ms: int
    model: str


# ---------------------------------------------------------------------------
# OllamaModelGateway
# ---------------------------------------------------------------------------


from abm.api.core.interfaces import ModelGatewayInterface


class OllamaModelGateway(ModelGatewayInterface):
    """
    Thin wrapper around Ollama's ``/api/generate`` endpoint.

    Follows the same design philosophy as ``OllamaEmbeddingWrapper`` from v0.1:
    all calls are local-only, no streaming, single-call synchronous interface.

    Parameters
    ----------
    model : str
        Ollama model name to use for generation. Defaults to ``"qwen2.5-coder:3b"``.
    host : str
        Ollama server host. Defaults to ``"127.0.0.1"``.
    port : int
        Ollama server port. Defaults to ``11434``.
    timeout_seconds : int
        HTTP request timeout in seconds. Defaults to ``30``.
    """

    def __init__(
        self,
        model: str = DEFAULT_CLASSIFICATION_MODEL,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._model = model
        self._base_url = f"http://{host}:{port}"
        self._timeout = timeout_seconds
        logger.info(
            "OllamaModelGateway: initialised for model '%s' at %s.",
            model, self._base_url,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, prompt: str, *, max_tokens: int = 0) -> GenerationResponse:
        """
        Send ``prompt`` to the model and return the full generated text.

        This is a single synchronous call — ``stream`` is always ``False``.
        The complete response is returned in one HTTP response body.

        Parameters
        ----------
        prompt : str
            The prompt to send to the model.
        max_tokens : int
            Maximum number of tokens to generate. 0 (default) means no cap
            (Ollama's default behaviour). Set to ~180 for ``ask``-style synthesis
            to keep responses short and prevent timeouts.

        Returns
        -------
        GenerationResponse
            Contains the raw text, latency, and model name.

        Raises
        ------
        ModelGatewayError
            On connection failure, timeout, or non-2xx HTTP response.
        ValueError
            If ``prompt`` is empty or whitespace-only.
        """
        if not prompt or not prompt.strip():
            raise ValueError("OllamaModelGateway.generate: prompt must be non-empty.")

        url = f"{self._base_url}/api/generate"
        payload: dict = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
        }
        if max_tokens > 0:
            payload["num_predict"] = max_tokens

        logger.debug(
            "OllamaModelGateway.generate: POST %s (model=%s, prompt_len=%d)",
            url, self._model, len(prompt),
        )

        t0 = time.monotonic()
        try:
            response = requests.post(url, json=payload, timeout=self._timeout)
            response.raise_for_status()
        except requests.exceptions.ConnectionError as exc:
            raise ModelGatewayError(
                f"OllamaModelGateway: cannot connect to Ollama at '{self._base_url}'. "
                f"Ensure the local Ollama server is running. Detail: {exc}"
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise ModelGatewayError(
                f"OllamaModelGateway: request timed out after {self._timeout}s. "
                f"Detail: {exc}"
            ) from exc
        except requests.exceptions.HTTPError as exc:
            raise ModelGatewayError(
                f"OllamaModelGateway: HTTP error {response.status_code}. "
                f"Detail: {exc}"
            ) from exc

        latency_ms = int((time.monotonic() - t0) * 1000)

        try:
            data = response.json()
            text = data.get("response", "")
            model_name = data.get("model", self._model)
        except Exception as exc:
            raise ModelGatewayError(
                f"OllamaModelGateway: failed to parse JSON response â€” {exc}"
            ) from exc

        logger.debug(
            "OllamaModelGateway.generate: OK in %dms (model=%s, response_len=%d)",
            latency_ms, model_name, len(text),
        )
        return GenerationResponse(text=text, latency_ms=latency_ms, model=model_name)

    def is_available(self) -> bool:
        """
        Check whether the local Ollama server is reachable.

        Performs a GET request to ``/api/tags`` (the lightest Ollama endpoint).
        Never raises â€” returns ``False`` on any error.

        Returns
        -------
        bool
            ``True`` if the server responded with a 2xx status code.
        """
        try:
            response = requests.get(
                f"{self._base_url}/api/tags",
                timeout=5,
            )
            available = response.status_code < 300
            logger.debug(
                "OllamaModelGateway.is_available: %s (status=%d)",
                available, response.status_code,
            )
            return available
        except Exception:
            logger.debug("OllamaModelGateway.is_available: False (connection error).")
            return False

    @property
    def model(self) -> str:
        """The Ollama model name used by this gateway."""
        return self._model

    @property
    def base_url(self) -> str:
        """The base URL of the Ollama server."""
        return self._base_url


__all__ = [
    "OllamaModelGateway",
    "ModelGatewayError",
    "GenerationResponse",
    "DEFAULT_CLASSIFICATION_MODEL",
]
