"""
tests/test_tray_app.py
=======================
Phase 6 gate: ABMTrayApp system tray wrapper

Proofs required:
  1. TrayDependencyError is raised when pystray/Pillow are not installed.
  2. ABMTrayApp.is_launcher_running returns False before start.
  3. ABMTrayApp._start_launcher starts a subprocess.
  4. ABMTrayApp.stop terminates the subprocess.
  5. ABMTrayApp.launcher_pid returns the PID of the managed process.
  6. _on_open_web_ui opens the correct URL.
  7. _make_icon_image returns an Image object or fallback without crashing.
  8. ABMTrayApp does not import pystray at module level (lazy load).
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Import tray_app without triggering pystray/Pillow at module import time
# ---------------------------------------------------------------------------


import importlib.util
_TRAY_PATH = Path(__file__).parent.parent / "abm" / "tray_app.py"
_spec = importlib.util.spec_from_file_location("_tray_app_direct", str(_TRAY_PATH))
_tray_mod = importlib.util.module_from_spec(_spec)
sys.modules["_tray_app_direct"] = _tray_mod
_spec.loader.exec_module(_tray_mod)

ABMTrayApp = _tray_mod.ABMTrayApp
TrayDependencyError = _tray_mod.TrayDependencyError
_make_icon_image = _tray_mod._make_icon_image
_check_tray_deps = _tray_mod._check_tray_deps


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTrayDependencyCheck:
    """Gate: TrayDependencyError raised when deps missing."""

    def test_raises_when_pystray_missing(self):
        """If pystray is not importable, TrayDependencyError must be raised."""
        import sys
        # Temporarily hide pystray from imports
        original = sys.modules.get("pystray")
        sys.modules["pystray"] = None  # type: ignore[assignment]
        try:
            with pytest.raises(TrayDependencyError, match="pystray"):
                _check_tray_deps()
        finally:
            if original is None:
                sys.modules.pop("pystray", None)
            else:
                sys.modules["pystray"] = original


class TestABMTrayAppLifecycle:
    """Gate: Tray app lifecycle — start, status, stop."""

    def test_is_launcher_running_false_before_start(self):
        """Before _start_launcher, is_launcher_running must be False."""
        app = ABMTrayApp()
        assert not app.is_launcher_running

    def test_launcher_pid_none_before_start(self):
        """launcher_pid must be None before _start_launcher is called."""
        app = ABMTrayApp()
        assert app.launcher_pid is None

    def test_start_launcher_creates_subprocess(self):
        """_start_launcher must call subprocess.Popen with python -m abm.launcher."""
        app = ABMTrayApp()
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 12345

        with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
            app._start_launcher()

        mock_popen.assert_called_once()
        call_args = mock_popen.call_args[0][0]  # first positional = cmd list
        assert sys.executable in call_args
        assert "-m" in call_args
        assert "abm.launcher" in call_args

    def test_is_launcher_running_true_after_start(self):
        """After _start_launcher, is_launcher_running must be True."""
        app = ABMTrayApp()
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # still running
        mock_proc.pid = 99999

        with patch("subprocess.Popen", return_value=mock_proc):
            app._start_launcher()

        assert app.is_launcher_running
        assert app.launcher_pid == 99999

    def test_stop_terminates_subprocess(self):
        """stop() must call terminate() and wait() on the managed subprocess."""
        app = ABMTrayApp()
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # still running
        mock_proc.pid = 55555
        app._proc = mock_proc
        app._tray = MagicMock()
        app._running = True

        app.stop()

        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called_once()
        assert not app._running

    def test_stop_does_not_crash_when_no_proc(self):
        """stop() must not raise even if _proc is None."""
        app = ABMTrayApp()
        app._tray = None
        app._proc = None
        app._running = True
        app.stop()  # should not raise

    def test_launcher_pid_returns_proc_pid(self):
        """launcher_pid returns the pid of the running subprocess."""
        app = ABMTrayApp()
        mock_proc = MagicMock()
        mock_proc.pid = 42
        app._proc = mock_proc
        assert app.launcher_pid == 42


class TestTrayMenuActions:
    """Gate: Menu actions open the correct URLs and stop correctly."""

    def test_open_web_ui_opens_correct_url(self):
        """_on_open_web_ui must open http://localhost:<port>."""
        app = ABMTrayApp(web_ui_port=8080)
        with patch("webbrowser.open") as mock_open:
            app._on_open_web_ui()
        mock_open.assert_called_once_with("http://localhost:8080")

    def test_open_web_ui_uses_configured_port(self):
        """Custom port must be reflected in the URL."""
        app = ABMTrayApp(web_ui_port=9090)
        with patch("webbrowser.open") as mock_open:
            app._on_open_web_ui()
        mock_open.assert_called_once_with("http://localhost:9090")

    def test_on_stop_calls_stop(self):
        """_on_stop() must call self.stop()."""
        app = ABMTrayApp()
        app._proc = None
        app._tray = None
        app._running = False
        with patch.object(app, "stop") as mock_stop:
            app._on_stop()
        mock_stop.assert_called_once()
