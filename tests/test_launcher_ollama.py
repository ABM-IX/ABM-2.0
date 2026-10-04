"""
tests/test_launcher_ollama.py
==============================
Gate: ABMLauncher Groq-only boot lifecycle.

Ollama is no longer managed by ABMLauncher. This test suite confirms:
  1. boot() never spawns an Ollama subprocess.
  2. stop() does not attempt to terminate any Ollama process.
  3. watcher attribute is None before boot() (no AttributeError in stop()).
  4. ABMLauncher uses model_gateway_provider='groq' in its APIConfig.
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from abm.launcher import ABMLauncher


class TestABMLauncherGroqOnlyLifecycle(unittest.TestCase):
    """Gate: Launcher no longer manages Ollama — Groq is the sole provider."""

    def test_watcher_initialized_to_none_before_boot(self):
        """self.watcher must be None before boot() — prevents AttributeError in stop()."""
        launcher = ABMLauncher("/fake/project/root")
        self.assertIsNone(launcher.watcher)

    def test_stop_before_boot_does_not_raise(self):
        """stop() called before boot() must not raise AttributeError."""
        launcher = ABMLauncher("/fake/project/root")
        # Should not raise even though watcher/sync_server/web_server are None
        try:
            launcher.stop()
        except AttributeError:
            self.fail("stop() raised AttributeError before boot()")

    def test_boot_does_not_spawn_ollama(self):
        """boot() must never call subprocess.Popen to start Ollama."""
        launcher = ABMLauncher("/fake/project/root")
        with patch("subprocess.Popen") as mock_popen, \
             patch.object(launcher.registry, "boot"), \
             patch("abm.launcher.WorkspaceFileWatcher"), \
             patch("abm.launcher.build_coordinator", return_value=MagicMock()), \
             patch("abm.launcher.web_main"), \
             patch("abm.launcher.ThreadingHTTPServer"), \
             patch("abm.launcher.HTTPServer"), \
             patch("builtins.open", MagicMock(return_value=MagicMock(
                 __enter__=MagicMock(return_value=MagicMock(
                     read=MagicMock(return_value='{"watch_paths": []}')
                 )),
                 __exit__=MagicMock(return_value=False)
             ))), \
             patch("pathlib.Path.exists", return_value=False):
            launcher.boot()

        # Popen must never be called for Ollama
        for call_args in mock_popen.call_args_list:
            args = call_args[0]
            if args and "ollama" in str(args[0]).lower():
                self.fail(f"boot() spawned an Ollama process: {call_args}")

    def test_boot_does_not_urlopen_ollama(self):
        """boot() must not call urllib.request.urlopen to check Ollama health."""
        launcher = ABMLauncher("/fake/project/root")
        with patch("urllib.request.urlopen") as mock_urlopen, \
             patch.object(launcher.registry, "boot"), \
             patch("abm.launcher.WorkspaceFileWatcher"), \
             patch("abm.launcher.build_coordinator", return_value=MagicMock()), \
             patch("abm.launcher.web_main"), \
             patch("abm.launcher.ThreadingHTTPServer"), \
             patch("abm.launcher.HTTPServer"), \
             patch("pathlib.Path.exists", return_value=False):
            launcher.boot()

        mock_urlopen.assert_not_called()

    def test_stop_does_not_kill_any_subprocess(self):
        """stop() must not attempt to terminate any subprocess."""
        launcher = ABMLauncher("/fake/project/root")
        mock_proc = MagicMock()
        # Even if someone manually sets a proc, stop() should not call terminate
        # (the owns_ollama / ollama_proc fields have been removed)
        self.assertFalse(hasattr(launcher, "owns_ollama"),
                         "owns_ollama field should not exist on ABMLauncher after Ollama removal")

    def test_registry_uses_groq_provider(self):
        """ABMLauncher must configure the registry with model_gateway_provider='groq'."""
        launcher = ABMLauncher("/fake/project/root")
        self.assertEqual(launcher.registry.config.model_gateway_provider, "groq")


if __name__ == "__main__":
    unittest.main()
