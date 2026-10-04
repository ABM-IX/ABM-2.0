"""
tests/test_groq_gateway.py
===========================
Phase 5 gate: GroqModelGateway and SensitivityClassifier — Groq-only mode.

Proofs required:
  1. SensitivityClassifier blocks Stream D / identity content — returns (True, reason).
  2. SensitivityClassifier passes neutral technical prompts — returns (False, "").
  3. GroqModelGateway raises ModelGatewayError when GROQ_API_KEY is not set (no Ollama fallback).
  4. GroqModelGateway raises ModelGatewayError when prompt is sensitive (no Ollama fallback).
  5. GroqModelGateway calls Groq API when key is set and prompt is safe.
  6. GroqModelGateway raises ModelGatewayError when Groq returns an HTTP error (no fallback).
  7. APIConfig.model_gateway_provider defaults to "ollama".
  8. model property returns the groq model name.
  9. max_tokens included in Groq payload when > 0, omitted when 0.
  10. GroqModelGateway has no _ollama_fallback attribute.

NOTE: This test file uses stub injection rather than direct groq_gateway imports
to avoid a pre-existing circular import in the package __init__ chain:
  abm.orchestrator.__init__ -> departments -> chroma_controller -> abm.api.__init__
  -> capabilities -> departments (circular).
All tests run correctly when the full suite is collected (where the import order
resolves naturally), but isolated collection requires the stub approach.
"""

import os
import sys
import importlib.util
import re
import time
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Bootstrap: inject stubs so groq_gateway.py can be loaded in isolation
# ---------------------------------------------------------------------------


def _make_stub_module(name: str, **attrs: Any) -> ModuleType:
    m = ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


def _bootstrap_groq_gateway():
    """
    Load groq_gateway in isolation by pre-populating sys.modules with
    lightweight stubs for everything groq_gateway actually imports.
    Returns the loaded module.
    """
    # Stub GenerationResponse dataclass
    from dataclasses import dataclass

    @dataclass
    class _GenerationResponse:
        text: str
        latency_ms: int = 0
        model: str = "stub"

    class _ModelGatewayError(Exception):
        pass

    class _ModelGatewayInterface:
        pass

    # Build stub modules — no OllamaModelGateway needed since groq_gateway no longer imports it
    _mg_stub = _make_stub_module(
        "abm.orchestrator.model_gateway",
        GenerationResponse=_GenerationResponse,
        ModelGatewayError=_ModelGatewayError,
    )

    _iface_stub = _make_stub_module(
        "abm.api.core.interfaces",
        ModelGatewayInterface=_ModelGatewayInterface,
    )

    _iface_core_stub = _make_stub_module(
        "abm.api.core",
        interfaces=_iface_stub,
    )

    # Pre-populate sys.modules TRANSIENTLY so groq_gateway's imports resolve to stubs.
    # We track which keys we added so we can remove them after loading.
    _stub_keys = [
        "abm.orchestrator.model_gateway",
        "abm.api.core.interfaces",
        "abm.api.core",
    ]
    _previously_absent = [k for k in _stub_keys if k not in sys.modules]
    for mod_name, mod in [
        ("abm.orchestrator.model_gateway", _mg_stub),
        ("abm.api.core.interfaces", _iface_stub),
        ("abm.api.core", _iface_core_stub),
    ]:
        sys.modules.setdefault(mod_name, mod)

    # Load groq_gateway.py directly from file
    gw_path = Path(__file__).parent.parent / "abm" / "orchestrator" / "groq_gateway.py"
    spec = importlib.util.spec_from_file_location("_groq_gateway_isolated", str(gw_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_groq_gateway_isolated"] = mod
    spec.loader.exec_module(mod)

    # Remove transient stubs that we added — so downstream test files (test_launcher_ollama,
    # test_memory_pressure_launcher, test_phase_v10_sync_gate) can import the real packages.
    for k in _previously_absent:
        sys.modules.pop(k, None)

    return mod, _GenerationResponse


_gg, _GenerationResponse = _bootstrap_groq_gateway()
GroqModelGateway = _gg.GroqModelGateway
SensitivityClassifier = _gg.SensitivityClassifier
DEFAULT_GROQ_MODEL = _gg.DEFAULT_GROQ_MODEL
GROQ_API_KEY_ENV = _gg.GROQ_API_KEY_ENV


# ---------------------------------------------------------------------------
# SensitivityClassifier tests
# ---------------------------------------------------------------------------


class TestSensitivityClassifier:
    """Gate: SensitivityClassifier correctly identifies sensitive content."""

    def test_stream_d_keywords_are_blocked(self):
        """Prompts containing Stream D identity keywords must be blocked."""
        sensitive_prompts = [
            "What is in my cognitive identity stream?",
            "Tell me about FirstMinds philosophy.",
            "Who is Arabang?",
            "List my personal principles and identity foundations.",
        ]
        for prompt in sensitive_prompts:
            is_sensitive, reason = SensitivityClassifier.is_sensitive(prompt)
            assert is_sensitive, (
                f"Expected prompt blocked as sensitive, was not: {prompt!r}"
            )
            assert reason, f"Expected non-empty reason for: {prompt!r}"

    def test_neutral_technical_prompts_are_allowed(self):
        """Safe, neutral technical prompts must not be blocked."""
        safe_prompts = [
            "Write a Python function to sort a list.",
            "How do I implement a REST API with FastAPI?",
            "Explain the difference between async and sync in Python.",
            "What is the time complexity of quicksort?",
        ]
        for prompt in safe_prompts:
            is_sensitive, reason = SensitivityClassifier.is_sensitive(prompt)
            assert not is_sensitive, (
                f"Expected safe, but blocked: {prompt!r}, Reason: {reason}"
            )
            assert reason == ""

    def test_non_client_personal_data_is_blocked(self):
        """Non-ABM personal data (medical, financial) must be blocked."""
        sensitive_prompts = [
            "My bank account number is 1234.",
            "Can you process this medical record for me?",
        ]
        for prompt in sensitive_prompts:
            is_sensitive, reason = SensitivityClassifier.is_sensitive(prompt)
            assert is_sensitive, f"Expected blocked: {prompt!r}"


# ---------------------------------------------------------------------------
# GroqModelGateway tests — Groq-only (no Ollama fallback)
# ---------------------------------------------------------------------------


class TestGroqModelGatewayGroqOnly:
    """Gate: GroqModelGateway raises ModelGatewayError instead of falling back to Ollama."""

    def test_raises_when_no_api_key(self):
        """Without GROQ_API_KEY, generate() must raise ModelGatewayError."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop(GROQ_API_KEY_ENV, None)
            gateway = GroqModelGateway()

        with pytest.raises(_gg.ModelGatewayError, match=GROQ_API_KEY_ENV):
            gateway.generate("What is 2+2?")

    def test_raises_when_prompt_is_sensitive(self):
        """Sensitive prompts must raise ModelGatewayError (sensitivity block)."""
        with patch.dict(os.environ, {GROQ_API_KEY_ENV: "fake-key"}):
            gateway = GroqModelGateway()

        with pytest.raises(_gg.ModelGatewayError, match="sensitivity classifier"):
            gateway.generate("Tell me about FirstMinds strategy.")

    def test_raises_on_groq_connection_error(self):
        """On Groq ConnectionError, raise ModelGatewayError — no local fallback."""
        import requests as req_lib

        with patch.dict(os.environ, {GROQ_API_KEY_ENV: "fake-key"}):
            gateway = GroqModelGateway()

        with patch.object(_gg.requests, "post") as mock_post:
            mock_post.side_effect = req_lib.exceptions.ConnectionError("Groq unreachable")
            with pytest.raises(_gg.ModelGatewayError, match="cannot connect"):
                gateway.generate("Explain quicksort.")

    def test_raises_on_groq_timeout(self):
        """On Groq timeout, raise ModelGatewayError — no local fallback."""
        import requests as req_lib

        with patch.dict(os.environ, {GROQ_API_KEY_ENV: "fake-key"}):
            gateway = GroqModelGateway()

        with patch.object(_gg.requests, "post") as mock_post:
            mock_post.side_effect = req_lib.exceptions.Timeout("timed out")
            with pytest.raises(_gg.ModelGatewayError, match="timed out"):
                gateway.generate("Explain quicksort.")

    def test_raises_on_groq_http_error(self):
        """On Groq HTTP error, raise ModelGatewayError — no local fallback."""
        import requests as req_lib

        with patch.dict(os.environ, {GROQ_API_KEY_ENV: "fake-key"}):
            gateway = GroqModelGateway()

        with patch.object(_gg.requests, "post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.raise_for_status.side_effect = req_lib.exceptions.HTTPError("403")
            mock_post.return_value = mock_resp
            with pytest.raises(_gg.ModelGatewayError, match="HTTP error"):
                gateway.generate("Explain quicksort.")

    def test_no_ollama_fallback_attribute(self):
        """GroqModelGateway must NOT have an _ollama_fallback attribute."""
        with patch.dict(os.environ, {GROQ_API_KEY_ENV: "fake-key"}):
            gateway = GroqModelGateway()
        assert not hasattr(gateway, "_ollama_fallback"), (
            "_ollama_fallback must not exist — Ollama fallback has been removed"
        )

    def test_groq_called_for_safe_prompt_with_key(self):
        """With API key set and a safe prompt, Groq API must be called."""
        with patch.dict(os.environ, {GROQ_API_KEY_ENV: "fake-key"}):
            gateway = GroqModelGateway()

            mock_http = MagicMock()
            mock_http.json.return_value = {
                "model": "llama-3.1-8b-instant",
                "choices": [{"message": {"content": "Groq answered!"}}],
            }
            mock_http.raise_for_status = MagicMock()

            with patch.object(_gg.requests, "post", return_value=mock_http) as mock_post:
                result = gateway.generate("Write a Python sort function.")

        mock_post.assert_called_once()
        assert result.text == "Groq answered!"
        assert result.model == "llama-3.1-8b-instant"

    def test_max_tokens_passed_to_groq_when_positive(self):
        """max_tokens > 0 must be included in the Groq API payload."""
        with patch.dict(os.environ, {GROQ_API_KEY_ENV: "fake-key"}):
            gateway = GroqModelGateway()

            mock_http = MagicMock()
            mock_http.json.return_value = {
                "model": "llama-3.1-8b-instant",
                "choices": [{"message": {"content": "Short answer"}}],
            }
            mock_http.raise_for_status = MagicMock()

            with patch.object(_gg.requests, "post", return_value=mock_http) as mock_post:
                gateway.generate("Brief answer please.", max_tokens=180)

        sent_payload = mock_post.call_args[1]["json"]
        assert sent_payload.get("max_tokens") == 180

    def test_max_tokens_zero_omitted_from_payload(self):
        """max_tokens=0 must NOT add max_tokens to the Groq payload."""
        with patch.dict(os.environ, {GROQ_API_KEY_ENV: "fake-key"}):
            gateway = GroqModelGateway()

            mock_http = MagicMock()
            mock_http.json.return_value = {
                "model": "llama-3.1-8b-instant",
                "choices": [{"message": {"content": "Uncapped"}}],
            }
            mock_http.raise_for_status = MagicMock()

            with patch.object(_gg.requests, "post", return_value=mock_http) as mock_post:
                gateway.generate("Explain at length.", max_tokens=0)

        sent_payload = mock_post.call_args[1]["json"]
        assert "max_tokens" not in sent_payload


# ---------------------------------------------------------------------------
# Config and property tests
# ---------------------------------------------------------------------------


class TestGroqConfig:
    """Gate: Config and property handling."""

    def test_api_config_defaults_to_ollama(self):
        """APIConfig defaults: model_gateway_provider='ollama', groq_model=DEFAULT_GROQ_MODEL."""
        import importlib.util as _iu
        spec = _iu.spec_from_file_location(
            "_config_check",
            str(Path(__file__).parent.parent / "abm" / "api" / "core" / "config.py"),
        )
        # Register under a temp name so dataclass can resolve __module__
        sys.modules["_config_check"] = _m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_m)
        config = _m.APIConfig()
        assert config.model_gateway_provider == "ollama", (
            f"Expected 'ollama', got {config.model_gateway_provider!r}"
        )
        assert config.groq_model == DEFAULT_GROQ_MODEL
        del sys.modules["_config_check"]

    def test_groq_model_property(self):
        """GroqModelGateway.model must return the configured groq model name."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop(GROQ_API_KEY_ENV, None)
            gateway = GroqModelGateway(groq_model="llama-3.1-70b-versatile")
        assert gateway.model == "llama-3.1-70b-versatile"

    def test_groq_api_key_configured_false_without_key(self):
        """groq_api_key_configured must be False when env var is absent."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop(GROQ_API_KEY_ENV, None)
            gateway = GroqModelGateway()
        assert not gateway.groq_api_key_configured

    def test_groq_api_key_configured_true_with_key(self):
        """groq_api_key_configured must be True when env var is set."""
        with patch.dict(os.environ, {GROQ_API_KEY_ENV: "sk-test-key"}):
            gateway = GroqModelGateway()
        assert gateway.groq_api_key_configured
