import time
import subprocess
import urllib.request
import urllib.error
from unittest.mock import patch, MagicMock, ANY

import pytest

from abm.launcher import ABMLauncher

class TestABMLauncherOllamaLifecycle:
    @patch("urllib.request.urlopen")
    @patch("subprocess.Popen")
    def test_ollama_already_running(self, mock_popen, mock_urlopen):
        # Setup mock to simulate Ollama already running (tags responds successfully)
        # We need two successful responses: one for the check, one for the pre-warm
        mock_response = MagicMock()
        mock_response.read.return_value = b"{}"
        mock_urlopen.return_value = mock_response

        launcher = ABMLauncher("/fake/project/root")
        
        with patch.object(launcher.registry, "boot") as mock_registry_boot:
            launcher.boot()

        # Popen should not have been called since it's already running
        mock_popen.assert_not_called()
        assert not launcher.owns_ollama

        # The pre-warm should still have been called
        assert mock_urlopen.call_count == 2
        mock_registry_boot.assert_called_once()

    @patch("time.sleep", return_value=None)
    @patch("urllib.request.urlopen")
    @patch("subprocess.Popen")
    def test_starts_ollama_if_not_reachable(self, mock_popen, mock_urlopen, mock_sleep):
        # Simulate Ollama is unreachable at first, then becomes reachable
        # 1st call: check -> Exception
        # 2nd call: poll -> Exception
        # 3rd call: poll -> Success
        # 4th call: pre-warm -> Success
        
        def urlopen_side_effect(*args, **kwargs):
            if mock_urlopen.call_count <= 2:
                raise urllib.error.URLError("Connection refused")
            return MagicMock()
            
        mock_urlopen.side_effect = urlopen_side_effect

        launcher = ABMLauncher("/fake/project/root")
        
        with patch.object(launcher.registry, "boot"):
            launcher.boot()

        # Should have started Ollama
        mock_popen.assert_called_once_with(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        assert launcher.owns_ollama
        assert launcher.ollama_proc == mock_popen.return_value

    @patch("urllib.request.urlopen")
    def test_stop_kills_owned_ollama(self, mock_urlopen):
        launcher = ABMLauncher("/fake/project/root")
        launcher.owns_ollama = True
        launcher.ollama_proc = MagicMock()

        launcher.stop()

        launcher.ollama_proc.terminate.assert_called_once()
        launcher.ollama_proc.wait.assert_called_once_with(timeout=2.0)

    @patch("urllib.request.urlopen")
    def test_stop_does_not_kill_unowned_ollama(self, mock_urlopen):
        launcher = ABMLauncher("/fake/project/root")
        launcher.owns_ollama = False
        launcher.ollama_proc = MagicMock()

        launcher.stop()

        launcher.ollama_proc.terminate.assert_not_called()
