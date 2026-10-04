"""
tests/test_automation.py
==========================
Phase 7 + Phase 8 gate tests.

Phase 7 — Tier 1 Automation:
  DynamicLauncher (Proofs):
    1. launch() with a PATH-resolvable name calls Popen with the resolved path.
    2. launch() with a full path uses it directly.
    3. launch() returns LaunchResult.success=False when exe not found.
    4. launch() returns LaunchResult.success=False for empty command.
    5. launch() returns pid on success.
    6. launch() with arguments passes them through.

  SpotifyGateway (Proofs):
    7. is_configured is False when env vars are absent.
    8. is_configured is True when both env vars are set.
    9. search() returns empty list when not configured.
    10. search() returns Track list when Spotify responds correctly.
    11. play() returns False when SPOTIFY_ACCESS_TOKEN is absent.
    12. play() returns True on HTTP 204.

Phase 8 — Tier 2 Automation (WhatsApp):
  13. compose() returns ComposeResult with ready_to_send=False on empty recipient.
  14. compose() returns ComposeResult with ready_to_send=False on empty message.
  15. confirm_and_send() raises AssertionError when called without prior compose().
  16. confirm_and_send(confirmed=False) does NOT send — returns False.
  17. confirm_and_send(confirmed=True) after compose sends (mocked browser).
  18. confirm_and_send() with wrong session_id raises AssertionError.
  19. Calling confirm_and_send() twice on the same ComposeResult raises AssertionError.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Direct imports (no package __init__ chain issues for automation modules)
# ---------------------------------------------------------------------------

from abm.automation.launcher_map import DynamicLauncher, LaunchResult
from abm.automation.spotify_gateway import (
    SpotifyGateway,
    Track,
    SPOTIFY_CLIENT_ID_ENV,
    SPOTIFY_CLIENT_SECRET_ENV,
)
from abm.automation.whatsapp_gateway import WhatsAppGateway, ComposeResult


# ===========================================================================
# PHASE 7 — DynamicLauncher tests
# ===========================================================================


class TestDynamicLauncher:
    """Gate: DynamicLauncher resolves executables and launches subprocesses."""

    def _make_mock_proc(self, pid: int = 12345) -> MagicMock:
        p = MagicMock()
        p.pid = pid
        p.poll.return_value = None
        return p

    def test_launch_empty_command_returns_failure(self):
        """Empty command must return LaunchResult.success=False."""
        launcher = DynamicLauncher()
        result = launcher.launch("")
        assert not result.success
        assert result.pid is None
        assert result.error

    def test_launch_whitespace_only_returns_failure(self):
        """Whitespace-only command must return LaunchResult.success=False."""
        launcher = DynamicLauncher()
        result = launcher.launch("   ")
        assert not result.success

    def test_launch_unknown_exe_returns_failure(self):
        """An executable that can't be found must return success=False."""
        launcher = DynamicLauncher()
        with patch("shutil.which", return_value=None):
            result = launcher.launch("nonexistent_app_xyz123")
        assert not result.success
        assert "not found" in result.error.lower()
        assert result.pid is None

    def test_launch_path_resolvable_exe_succeeds(self):
        """When shutil.which resolves the exe, Popen should be called and pid returned."""
        launcher = DynamicLauncher()
        mock_proc = self._make_mock_proc(pid=9876)

        with patch("shutil.which", return_value="/usr/bin/fake_app"), \
             patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
            result = launcher.launch("fake_app")

        assert result.success
        assert result.pid == 9876
        mock_popen.assert_called_once()
        # First arg is the cmd list
        called_cmd = mock_popen.call_args[0][0]
        assert "/usr/bin/fake_app" in called_cmd

    def test_launch_with_arguments_passes_args_to_popen(self):
        """Arguments in the command string must be passed through to Popen."""
        launcher = DynamicLauncher()
        mock_proc = self._make_mock_proc()

        with patch("shutil.which", return_value="/usr/bin/code"), \
             patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
            result = launcher.launch("code /my/project")

        called_cmd = mock_popen.call_args[0][0]
        # Should have the project arg in the cmd list
        assert any("/my/project" in str(c) for c in called_cmd)
        assert result.success

    def test_launch_returns_correct_pid(self):
        """LaunchResult.pid must match the process PID."""
        launcher = DynamicLauncher()
        mock_proc = self._make_mock_proc(pid=42)

        with patch("shutil.which", return_value="/usr/bin/python3"), \
             patch("subprocess.Popen", return_value=mock_proc):
            result = launcher.launch("python3")

        assert result.pid == 42

    def test_launch_handles_popen_file_not_found(self):
        """If Popen raises FileNotFoundError, return success=False."""
        launcher = DynamicLauncher()

        with patch("shutil.which", return_value="/fake/path/app"), \
             patch("subprocess.Popen", side_effect=FileNotFoundError("not found")):
            result = launcher.launch("app")

        assert not result.success
        assert result.pid is None


# ===========================================================================
# PHASE 7 — SpotifyGateway tests
# ===========================================================================


class TestSpotifyGateway:
    """Gate: SpotifyGateway handles credentials, search, and play correctly."""

    def test_is_configured_false_when_env_absent(self):
        """is_configured must be False when CLIENT_ID or CLIENT_SECRET is missing."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop(SPOTIFY_CLIENT_ID_ENV, None)
            os.environ.pop(SPOTIFY_CLIENT_SECRET_ENV, None)
            gw = SpotifyGateway()
        assert not gw.is_configured

    def test_is_configured_true_when_env_set(self):
        """is_configured must be True when both env vars are set."""
        with patch.dict(os.environ, {
            SPOTIFY_CLIENT_ID_ENV: "test-client-id",
            SPOTIFY_CLIENT_SECRET_ENV: "test-client-secret",
        }):
            gw = SpotifyGateway()
        assert gw.is_configured

    def test_search_returns_empty_when_not_configured(self):
        """search() must return [] when not configured."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop(SPOTIFY_CLIENT_ID_ENV, None)
            os.environ.pop(SPOTIFY_CLIENT_SECRET_ENV, None)
            gw = SpotifyGateway()
            result = gw.search("Kendrick Lamar")
        assert result == []

    def test_search_returns_empty_for_empty_query(self):
        """search() must return [] for empty query."""
        with patch.dict(os.environ, {
            SPOTIFY_CLIENT_ID_ENV: "id",
            SPOTIFY_CLIENT_SECRET_ENV: "secret",
        }):
            gw = SpotifyGateway()
            result = gw.search("")
        assert result == []

    def test_search_returns_tracks_on_success(self):
        """search() must return a list of Track objects when Spotify responds."""
        with patch.dict(os.environ, {
            SPOTIFY_CLIENT_ID_ENV: "test-id",
            SPOTIFY_CLIENT_SECRET_ENV: "test-secret",
        }):
            gw = SpotifyGateway()

            # Mock token call
            token_resp = MagicMock()
            token_resp.json.return_value = {
                "access_token": "mock-token",
                "expires_in": 3600,
            }
            token_resp.raise_for_status = MagicMock()

            # Mock search response
            search_resp = MagicMock()
            search_resp.raise_for_status = MagicMock()
            search_resp.json.return_value = {
                "tracks": {
                    "items": [
                        {
                            "name": "HUMBLE.",
                            "artists": [{"name": "Kendrick Lamar"}],
                            "album": {"name": "DAMN."},
                            "uri": "spotify:track:abc123",
                            "duration_ms": 177000,
                        }
                    ]
                }
            }

            with patch("requests.post", return_value=token_resp), \
                 patch("requests.get", return_value=search_resp):
                results = gw.search("Kendrick Lamar")

        assert len(results) == 1
        assert isinstance(results[0], Track)
        assert results[0].name == "HUMBLE."
        assert results[0].artist == "Kendrick Lamar"
        assert results[0].uri == "spotify:track:abc123"

    def test_play_returns_false_when_no_access_token(self):
        """play() must return False when SPOTIFY_ACCESS_TOKEN is not set."""
        with patch.dict(os.environ, {
            SPOTIFY_CLIENT_ID_ENV: "id",
            SPOTIFY_CLIENT_SECRET_ENV: "secret",
        }):
            os.environ.pop("SPOTIFY_ACCESS_TOKEN", None)
            gw = SpotifyGateway()
            result = gw.play("spotify:track:abc123")
        assert result is False

    def test_play_returns_true_on_http_204(self):
        """play() must return True when Spotify responds with 204."""
        with patch.dict(os.environ, {
            SPOTIFY_CLIENT_ID_ENV: "id",
            SPOTIFY_CLIENT_SECRET_ENV: "secret",
            "SPOTIFY_ACCESS_TOKEN": "user-token-here",
        }):
            gw = SpotifyGateway()
            mock_resp = MagicMock()
            mock_resp.status_code = 204
            with patch("requests.put", return_value=mock_resp):
                result = gw.play("spotify:track:abc123")
        assert result is True

    def test_play_returns_false_for_empty_uri(self):
        """play() must return False for an empty track URI."""
        with patch.dict(os.environ, {
            SPOTIFY_CLIENT_ID_ENV: "id",
            SPOTIFY_CLIENT_SECRET_ENV: "secret",
            "SPOTIFY_ACCESS_TOKEN": "user-token",
        }):
            gw = SpotifyGateway()
            result = gw.play("")
        assert result is False


# ===========================================================================
# PHASE 8 — WhatsAppGateway tests
# ===========================================================================


class TestWhatsAppGatewayComposeValidation:
    """Gate: compose() validates inputs and never sends."""

    def test_compose_empty_recipient_returns_error(self):
        """compose() with empty recipient must return ready_to_send=False."""
        gw = WhatsAppGateway()
        result = gw.compose("", "Hello!")
        assert not result.ready_to_send
        assert result.error
        assert result.session_id == ""

    def test_compose_empty_message_returns_error(self):
        """compose() with empty message must return ready_to_send=False."""
        gw = WhatsAppGateway()
        result = gw.compose("Alice", "")
        assert not result.ready_to_send
        assert result.error

    def test_compose_returns_staged_result_on_success(self):
        """compose() with valid args and mocked browser must stage the message."""
        gw = WhatsAppGateway()
        with patch.object(gw, "_ensure_browser"), \
             patch.object(gw, "_navigate_to_chat"), \
             patch.object(gw, "_type_message"):
            result = gw.compose("Bob", "Test message")

        assert result.ready_to_send
        assert result.message == "Test message"
        assert result.recipient == "Bob"
        assert result.session_id != ""

    def test_compose_does_not_call_submit(self):
        """compose() must NEVER call _submit_message (that would send it)."""
        gw = WhatsAppGateway()
        with patch.object(gw, "_ensure_browser"), \
             patch.object(gw, "_navigate_to_chat"), \
             patch.object(gw, "_type_message"), \
             patch.object(gw, "_submit_message") as mock_submit:
            gw.compose("Eve", "Hello")

        mock_submit.assert_not_called()


class TestWhatsAppGatewayConfirmFlow:
    """Gate: confirm_and_send() enforces the two-step safety contract."""

    def _staged_compose(self, gw: WhatsAppGateway, recipient="Bob", message="Hi") -> ComposeResult:
        """Helper: stage a message with mocked browser."""
        with patch.object(gw, "_ensure_browser"), \
             patch.object(gw, "_navigate_to_chat"), \
             patch.object(gw, "_type_message"):
            return gw.compose(recipient, message)

    def test_confirm_without_prior_compose_raises_assertion(self):
        """confirm_and_send() without prior compose() must raise AssertionError."""
        gw = WhatsAppGateway()
        fake_result = ComposeResult(
            session_id="fake", recipient="Alice", message="Test", ready_to_send=True
        )
        with pytest.raises(AssertionError, match="compose"):
            gw.confirm_and_send(fake_result, confirmed=True)

    def test_confirm_with_confirmed_false_does_not_send(self):
        """confirmed=False must NOT call _submit_message."""
        gw = WhatsAppGateway()
        result = self._staged_compose(gw)

        with patch.object(gw, "_submit_message") as mock_submit:
            sent = gw.confirm_and_send(result, confirmed=False)

        mock_submit.assert_not_called()
        assert sent is False

    def test_confirm_with_confirmed_true_calls_submit(self):
        """confirmed=True must call _submit_message exactly once."""
        gw = WhatsAppGateway()
        result = self._staged_compose(gw)

        with patch.object(gw, "_submit_message") as mock_submit, \
             patch.object(gw, "_log_to_journal"):
            sent = gw.confirm_and_send(result, confirmed=True)

        mock_submit.assert_called_once()
        assert sent is True

    def test_wrong_session_id_raises_assertion(self):
        """confirm_and_send() with wrong session_id must raise AssertionError."""
        gw = WhatsAppGateway()
        result = self._staged_compose(gw)

        # Tamper with session ID
        tampered = ComposeResult(
            session_id="wrong_session",
            recipient=result.recipient,
            message=result.message,
            ready_to_send=True,
        )
        with pytest.raises(AssertionError, match="session_id"):
            gw.confirm_and_send(tampered, confirmed=True)

    def test_second_call_after_send_raises_assertion(self):
        """After a successful send, the compose result is cleared.
        A second confirm_and_send() must raise AssertionError."""
        gw = WhatsAppGateway()
        result = self._staged_compose(gw)

        with patch.object(gw, "_submit_message"), \
             patch.object(gw, "_log_to_journal"):
            gw.confirm_and_send(result, confirmed=True)

        # Second call — compose result was cleared
        with pytest.raises(AssertionError):
            gw.confirm_and_send(result, confirmed=True)

    def test_compose_result_ready_false_is_rejected(self):
        """A ComposeResult with ready_to_send=False must not proceed to send."""
        gw = WhatsAppGateway()
        # Inject a compose result directly with ready_to_send=False
        error_result = ComposeResult(
            session_id="test_session", recipient="Alice",
            message="Hi", ready_to_send=False, error="Some error"
        )
        gw._compose_result = error_result

        with patch.object(gw, "_submit_message") as mock_submit:
            sent = gw.confirm_and_send(error_result, confirmed=True)

        mock_submit.assert_not_called()
        assert sent is False
