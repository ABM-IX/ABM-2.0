"""
abm/tray_app.py
================
ABM 2.0 Desktop Launcher — System Tray Application
Phase 6: Desktop Launcher App

Wraps the existing ABM launcher process in a system tray icon using pystray
and Pillow. This module ONLY orchestrates the existing launcher — it adds no
logic to launcher.py, api/, or any other ABM module.

Design contract:
  - Starts `python -m abm.launcher` as a managed subprocess.
  - System tray menu: Open Web UI | Status | Stop ABM.
  - Polls the subprocess every 5 seconds and updates the icon (green/red).
  - Clicking "Open Web UI" opens the default browser to http://localhost:8080.
  - Clicking "Stop ABM" terminates the subprocess and exits the tray app.
  - RAM usage is shown in the status item using psutil.
  - No writes to ChromaDB, Stream C, or any ABM memory layer.
  - pystray and Pillow are optional at import time — missing them gives a clear
    InstallationError rather than a cryptic AttributeError.

Usage:
    python -m abm.tray_app
    # or from Python:
    from abm.tray_app import ABMTrayApp
    app = ABMTrayApp(web_ui_port=8080)
    app.run()  # blocks until user clicks Stop
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional

import psutil
import requests

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dependency check
# ---------------------------------------------------------------------------


class TrayDependencyError(RuntimeError):
    """Raised when pystray or Pillow are not installed."""
    pass


def _check_tray_deps() -> tuple:
    """Return (pystray, PIL.Image) or raise TrayDependencyError."""
    try:
        import pystray
        from PIL import Image
        return pystray, Image
    except ImportError as exc:
        raise TrayDependencyError(
            "ABM tray app requires 'pystray' and 'Pillow'. "
            "Install them with: pip install pystray Pillow\n"
            f"Original error: {exc}"
        ) from exc


def _launch_native_window(url: str, title: str = "ABM 2.0", width: int = 1200, height: int = 800) -> None:
    """
    Open the ABM web UI in a native desktop window via pywebview.

    Runs in a separate thread so it does not block the tray icon event loop.
    If pywebview is not installed, falls back to opening the default browser.

    Parameters
    ----------
    url : str
        The URL to load (e.g. ``http://localhost:8080``).
    title : str
        The window title.
    width, height : int
        Initial window dimensions in pixels.
    """
    try:
        import webview  # type: ignore[import]
        logger.info("_launch_native_window: opening '%s' via pywebview.", url)
        win = webview.create_window(title, url, width=width, height=height)
        webview.start()
    except ImportError:
        logger.info(
            "_launch_native_window: pywebview not installed — falling back to system browser."
        )
        webbrowser.open(url)
    except Exception as exc:
        logger.warning("_launch_native_window: failed — %s. Falling back to browser.", exc)
        webbrowser.open(url)


# ---------------------------------------------------------------------------
# Icon generation
# ---------------------------------------------------------------------------


def _make_icon_image(Image, color: str = "#6366f1") -> object:
    """
    Generate a simple 64x64 circle icon using Pillow.

    Parameters
    ----------
    Image : PIL.Image class
        Passed in to avoid importing PIL at module level.
    color : str
        The circle fill colour. Default is ABM indigo.

    Returns
    -------
    PIL.Image.Image
        A 64x64 RGBA image with a filled circle.
    """
    try:
        from PIL import ImageDraw
        size = 64
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((4, 4, size - 4, size - 4), fill=color)
        return img
    except Exception as exc:
        logger.warning("_make_icon_image: could not draw icon — %s", exc)
        # Fallback: a tiny 1x1 transparent image
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))


# ---------------------------------------------------------------------------
# ABMTrayApp
# ---------------------------------------------------------------------------


class ABMTrayApp:
    """
    System tray wrapper for the ABM launcher process.

    Parameters
    ----------
    web_ui_port : int
        Port where the ABM web UI is served. Default 8080.
    launcher_module : str
        Python module path to run as a subprocess. Default ``abm.launcher``.
    poll_interval_s : float
        Seconds between subprocess health polls. Default 5.
    """

    _ICON_RUNNING_COLOR = "#22c55e"   # green
    _ICON_STOPPED_COLOR = "#ef4444"   # red
    _ICON_STARTING_COLOR = "#f59e0b"  # amber

    def __init__(
        self,
        web_ui_port: int = 8080,
        launcher_module: str = "abm.launcher",
        poll_interval_s: float = 5.0,
    ) -> None:
        self._port = web_ui_port
        self._launcher_module = launcher_module
        self._poll_interval = poll_interval_s

        self._proc: Optional[subprocess.Popen] = None
        self._tray = None
        self._pystray = None
        self._Image = None
        self._running = False
        self._status_text = "Starting…"
        self._log_path: Optional[Path] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> None:
        """
        Start the tray app. Blocks until the user clicks Stop or the process
        is externally terminated.

        Raises
        ------
        TrayDependencyError
            If pystray or Pillow are not installed.
        """
        self._pystray, self._Image = _check_tray_deps()

        self._start_launcher()
        self._running = True

        icon_img = _make_icon_image(self._Image, self._ICON_STARTING_COLOR)
        menu = self._pystray.Menu(
            self._pystray.MenuItem("ABM 2.0", None, enabled=False),
            self._pystray.Menu.SEPARATOR,
            self._pystray.MenuItem("Open Web UI", self._on_open_web_ui),
            self._pystray.MenuItem("Open Window (Native)", self._on_open_native_window),
            self._pystray.MenuItem("\U0001F3A4 Talk to ABM (voice)", self._on_talk_to_abm),
            self._pystray.MenuItem("Open Logs", self._on_open_logs),
            self._pystray.MenuItem(
                lambda item: self._status_text,
                action=None,
                enabled=False,
            ),
            self._pystray.Menu.SEPARATOR,
            self._pystray.MenuItem("Stop ABM", self._on_stop),
        )

        self._tray = self._pystray.Icon(
            name="abm",
            icon=icon_img,
            title="ABM 2.0",
            menu=menu,
        )

        # Background thread: poll subprocess + update icon/status
        poll_thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="abm-tray-poll"
        )
        poll_thread.start()

        # Background thread: wait for backend readiness, then auto-open the
        # native window — see _auto_open_window's docstring for why.
        autowindow_thread = threading.Thread(
            target=self._auto_open_window, daemon=True, name="abm-tray-autowindow"
        )
        autowindow_thread.start()

        logger.info("ABMTrayApp: entering tray icon event loop.")
        self._tray.run()

    def stop(self) -> None:
        """Terminate the ABM subprocess and exit the tray."""
        self._running = False
        if self._proc and self._proc.poll() is None:
            logger.info("ABMTrayApp.stop: terminating ABM launcher subprocess.")
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        if self._tray:
            self._tray.stop()

    @property
    def is_launcher_running(self) -> bool:
        """True if the managed subprocess is alive."""
        return self._proc is not None and self._proc.poll() is None

    @property
    def launcher_pid(self) -> Optional[int]:
        """PID of the managed subprocess, or None if not running."""
        return self._proc.pid if self._proc else None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _start_launcher(self) -> None:
        """
        Launch the ABM process as a subprocess.

        Root-cause fix (2026-11-02): this used to pipe stdout/stderr to
        DEVNULL, which discarded the exact tracebacks needed to diagnose a
        silent failure (e.g. the web API hanging on an unhandled exception).
        Now captured to logs/abm_launcher.log instead — visible via the new
        "Open Logs" tray menu item.
        """
        cmd = [sys.executable, "-m", self._launcher_module]
        try:
            log_dir = Path(__file__).resolve().parent.parent / "logs"
            log_dir.mkdir(exist_ok=True)
            self._log_path = log_dir / "abm_launcher.log"
            log_file = open(self._log_path, "w", encoding="utf-8")
            self._proc = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
            logger.info("ABMTrayApp: started launcher (PID=%d). Logs: %s", self._proc.pid, self._log_path)
        except Exception as exc:
            logger.error("ABMTrayApp: failed to start launcher — %s", exc)
            self._proc = None

    def _wait_for_backend(self, timeout_s: float = 25.0) -> bool:
        """Poll the web API until it answers or timeout_s elapses."""
        deadline = time.time() + timeout_s
        url = f"http://localhost:{self._port}/"
        while time.time() < deadline:
            try:
                requests.get(url, timeout=1.5)
                return True
            except Exception:
                time.sleep(0.5)
        return False

    def _auto_open_window(self) -> None:
        """
        Background thread: wait for the backend to actually be listening,
        then open the native window automatically — no second click needed.
        This replaces "launch to a hidden tray, then dig through the menu
        for Open Window" with "click once, a visible window appears."
        """
        if self._wait_for_backend():
            logger.info("ABMTrayApp: backend ready — auto-opening native window.")
            self._on_open_native_window()
        else:
            logger.warning(
                "ABMTrayApp: backend did not respond within timeout — window not "
                "auto-opened. Check Open Logs for why, or try 'Open Window (Native)' "
                "manually once it's up."
            )

    def _poll_loop(self) -> None:
        """Background thread: polls subprocess status and updates tray icon."""
        while self._running:
            if self.is_launcher_running:
                try:
                    mem = psutil.virtual_memory()
                    avail_gb = mem.available / (1024 ** 3)
                    self._status_text = (
                        f"Running (PID {self._proc.pid}) · "
                        f"{avail_gb:.1f} GB RAM free"
                    )
                except Exception:
                    self._status_text = f"Running (PID {self._proc.pid})"
                color = self._ICON_RUNNING_COLOR
            else:
                self._status_text = "Stopped"
                color = self._ICON_STOPPED_COLOR

            if self._tray and self._Image:
                try:
                    self._tray.icon = _make_icon_image(self._Image, color)
                except Exception as exc:
                    logger.debug("ABMTrayApp._poll_loop: icon update failed — %s", exc)

            time.sleep(self._poll_interval)

    def _on_open_web_ui(self, icon=None, item=None) -> None:
        """Open the ABM web UI in the default browser."""
        url = f"http://localhost:{self._port}"
        logger.info("ABMTrayApp: opening %s in browser.", url)
        webbrowser.open(url)

    def _on_open_native_window(self, icon=None, item=None) -> None:
        """Open the ABM web UI in a native pywebview desktop window."""
        url = f"http://localhost:{self._port}"
        logger.info("ABMTrayApp: opening native window at %s.", url)
        # pywebview.start() is blocking — run in a separate daemon thread
        native_thread = threading.Thread(
            target=_launch_native_window,
            args=(url,),
            daemon=True,
            name="abm-native-window",
        )
        native_thread.start()

    def _on_talk_to_abm(self, icon=None, item=None) -> None:
        """
        Launch the push-to-talk voice interface (abm/voice/voice_interface.py)
        in its own console window.

        This is a separate OS process, not a thread inside the tray app, for
        two reasons: (1) the voice interface is an interactive stdin/stdout
        CLI loop (press Enter to talk) and mixing that with pystray's own
        event loop would be fragile; (2) if the voice process crashes, it
        can't take the tray icon or the ABM launcher down with it. It talks
        to the already-running ABM web API over HTTP (/api/ask), exactly
        like this tray app's own "Open Web UI" does nothing more invasive
        than opening a URL.
        """
        logger.info("ABMTrayApp: launching voice interface.")
        try:
            creationflags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
            subprocess.Popen(
                [sys.executable, "-m", "abm.voice.voice_interface"],
                creationflags=creationflags,
            )
        except Exception as exc:
            logger.error("ABMTrayApp: failed to launch voice interface — %s", exc)

    def _on_open_logs(self, icon=None, item=None) -> None:
        """Open the launcher's captured stdout/stderr log file."""
        if not self._log_path or not self._log_path.exists():
            logger.warning("ABMTrayApp: no log file yet.")
            return
        logger.info("ABMTrayApp: opening log file %s.", self._log_path)
        try:
            if sys.platform == "win32":
                os.startfile(self._log_path)  # type: ignore[attr-defined]
            else:
                webbrowser.open(f"file://{self._log_path}")
        except Exception as exc:
            logger.error("ABMTrayApp: failed to open log file — %s", exc)

    def _on_stop(self, icon=None, item=None) -> None:
        """Handle Stop ABM menu click."""
        logger.info("ABMTrayApp: Stop clicked by user.")
        self.stop()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point when run as ``python -m abm.tray_app``."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass  # dotenv is optional, handled gracefully

    logging.basicConfig(level=logging.INFO)
    app = ABMTrayApp()
    try:
        app.run()
    except TrayDependencyError as exc:
        print(f"\n[ABM Tray] Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        app.stop()


if __name__ == "__main__":
    main()
