"""
abm/automation/launcher_map.py
================================
Dynamic Application Launcher — Phase 7 Tier 1 Automation

Launches ANY application by name or full path using the system shell,
based on user's request. No static pre-configuration is required —
ABM resolves and runs any command the user specifies.

Design contract:
  - ``DynamicLauncher.launch(command)`` accepts either:
    - A short app name (e.g. ``"codex"``, ``"cursor"``, ``"chrome"``).
    - A full executable path (e.g. ``"C:\\Program Files\\cursor\\cursor.exe"``).
    - A command with arguments (e.g. ``"code C:\\myproject"``).
  - Launches via ``subprocess.Popen`` (non-blocking, returns immediately).
  - Logs every launch with the resolved command for auditability (constitution rule 5).
  - Never modifies PATH or system configuration.
  - Returns ``LaunchResult`` — never raises to the caller.
  - ``LaunchResult.success`` is False if the executable was not found or failed to start.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LaunchResult
# ---------------------------------------------------------------------------


@dataclass
class LaunchResult:
    """
    Result of a ``DynamicLauncher.launch()`` call.

    Attributes
    ----------
    success : bool
        True if the process started successfully.
    command : str
        The resolved command that was (or would have been) launched.
    pid : int | None
        PID of the launched process. None on failure.
    error : str
        Human-readable error message. Empty on success.
    """

    success: bool
    command: str
    pid: Optional[int] = None
    error: str = ""


# ---------------------------------------------------------------------------
# DynamicLauncher
# ---------------------------------------------------------------------------


class DynamicLauncher:
    """
    Dynamic launcher that can start any application by name or path.

    Per the user's requirement: ABM should be able to launch any app at command —
    no pre-configuration needed. This launcher resolves names using ``shutil.which``
    (which searches PATH) and falls back to treating the name as a direct path.

    Usage
    -----
    ::

        launcher = DynamicLauncher()
        result = launcher.launch("codex")              # resolve from PATH
        result = launcher.launch("cursor /my/project") # with argument
        result = launcher.launch("C:/Apps/cursor.exe") # full path

    """

    def __init__(self) -> None:
        pass

    def launch(self, command: str) -> LaunchResult:
        """
        Launch an application from a name, path, or full command string.

        Resolution order:
        1. Split the command string into ``[executable, *args]``.
        2. If the executable is found on PATH via ``shutil.which``, use it.
        3. Otherwise treat it as a literal path (absolute or relative).
        4. On Windows, also try appending ``.exe`` if not found.

        Parameters
        ----------
        command : str
            The application to launch. Can be a short name, a full path, or a
            command with arguments (e.g. ``"code /home/user/project"``).

        Returns
        -------
        LaunchResult
            Always returns a result — never raises.
        """
        if not command or not command.strip():
            return LaunchResult(success=False, command=command, error="Empty command.")

        # Split command into parts on Windows (handle paths with spaces via shlex)
        try:
            if sys.platform == "win32":
                parts = shlex.split(command, posix=False)
            else:
                parts = shlex.split(command)
        except ValueError as exc:
            return LaunchResult(success=False, command=command, error=f"Command parse error: {exc}")

        exe, args = parts[0], parts[1:]
        resolved_exe = self._resolve_executable(exe)

        if resolved_exe is None:
            if sys.platform == "win32" and (command.endswith(":") or command.startswith("start ")):
                try:
                    full_cmd = ["cmd.exe", "/c", "start", ""] + parts
                    proc = subprocess.Popen(
                        full_cmd,
                        shell=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    logger.info("DynamicLauncher.launch: started via Windows shell '%s' (PID=%d).", command, proc.pid)
                    return LaunchResult(success=True, command=command, pid=proc.pid)
                except Exception as exc:
                    logger.warning("DynamicLauncher.launch: Windows shell start failed — %s", exc)

            error_msg = (
                f"Executable not found: '{exe}'. "
                f"Make sure it is on your PATH or provide a full path."
            )
            logger.warning("DynamicLauncher.launch: %s", error_msg)
            return LaunchResult(success=False, command=command, error=error_msg)

        full_cmd = [resolved_exe] + args
        resolved_command = subprocess.list2cmdline(full_cmd)

        try:
            proc = subprocess.Popen(
                full_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                # On Windows, don't create a console window for GUI apps
                **({"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}),
            )
            logger.info(
                "DynamicLauncher.launch: started '%s' (PID=%d).", resolved_command, proc.pid
            )
            return LaunchResult(success=True, command=resolved_command, pid=proc.pid)
        except FileNotFoundError:
            error_msg = f"Executable not found at resolved path: '{resolved_exe}'."
            logger.warning("DynamicLauncher.launch: %s", error_msg)
            return LaunchResult(success=False, command=command, error=error_msg)
        except PermissionError as exc:
            error_msg = f"Permission denied launching '{resolved_exe}': {exc}"
            logger.warning("DynamicLauncher.launch: %s", error_msg)
            return LaunchResult(success=False, command=command, error=error_msg)
        except Exception as exc:
            error_msg = f"Unexpected error launching '{command}': {exc}"
            logger.error("DynamicLauncher.launch: %s", error_msg)
            return LaunchResult(success=False, command=command, error=error_msg)

    def _resolve_executable(self, exe: str) -> Optional[str]:
        """
        Resolve an executable name to its full path.

        Tries (in order):
        1. ``shutil.which(exe)`` — searches PATH.
        2. The literal value if it's an absolute path that exists.
        3. On Windows, ``shutil.which(exe + ".exe")`` if ``exe`` has no extension.

        Parameters
        ----------
        exe : str
            The executable name or path.

        Returns
        -------
        str | None
            Resolved path string, or None if not found.
        """
        # 1. Search PATH
        found = shutil.which(exe)
        if found:
            return found

        # 2. Treat as a direct path
        p = Path(exe)
        if p.is_absolute() and p.exists():
            return str(p)

        # 3. Windows: try adding .exe
        if sys.platform == "win32" and not exe.lower().endswith(".exe"):
            found = shutil.which(exe + ".exe")
            if found:
                return found

        return None


# ---------------------------------------------------------------------------
# Dynamic installed-app lookup (2026-11-02 addition)
# ---------------------------------------------------------------------------
#
# DIRECT_APP_MAP only knows a curated set of app names. DynamicLauncher above
# resolves a KNOWN command via PATH, which works for CLI-style tools but
# misses most GUI apps and games (installers rarely add themselves to PATH)
# and can't reach Microsoft Store/UWP apps at all (they have no .exe on PATH
# — they're launched via an AppID through explorer.exe, not a normal process
# start). This covers both gaps by asking Windows itself what's installed,
# the same way Windows Search does, instead of trying to hardcode every app
# Arabang might ever install.
#
# Local-use only: this is wired into the local chat path (capabilities.py),
# NOT the remote phone->PC sync_server path, which intentionally stays
# restricted to the curated DIRECT_APP_MAP only (see sync_server.py's own
# "Arbitrary command execution is rejected" contract) — a looser, fuzzy,
# "launch whatever's closest" match is reasonable when Arabang is directly
# at his own keyboard, not when a command arrives from another device.

_STARTAPPS_CACHE: Optional[list[dict]] = None
_STARTAPPS_CACHE_TIME: float = 0.0
_STARTAPPS_CACHE_TTL_S = 300.0  # 5 minutes — installed apps don't change often
_FUZZY_MATCH_THRESHOLD = 0.72


def _normalize_app_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _get_installed_apps(force_refresh: bool = False) -> list[dict]:
    """
    Enumerate every app registered in the Windows Start Menu — classic
    .exe-backed apps AND Microsoft Store/UWP apps — via PowerShell's
    built-in ``Get-StartApps`` cmdlet. Cached for 5 minutes.

    Returns a list of ``{"Name": ..., "AppID": ...}`` dicts. Never raises;
    returns [] (or the last good cache) on any failure, including on a
    non-Windows host.

    NOTE: written and syntax-checked but not executed against a real
    Windows machine — this bridge has no PowerShell/Windows runtime to
    verify against. First real run is the actual test.
    """
    global _STARTAPPS_CACHE, _STARTAPPS_CACHE_TIME
    now = time.time()
    if (
        not force_refresh
        and _STARTAPPS_CACHE is not None
        and (now - _STARTAPPS_CACHE_TIME) < _STARTAPPS_CACHE_TTL_S
    ):
        return _STARTAPPS_CACHE

    if sys.platform != "win32":
        return []

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-StartApps | ConvertTo-Json -Compress"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0 or not result.stdout.strip():
            logger.warning(
                "launcher_map: Get-StartApps returned no usable output (rc=%s) — %s",
                result.returncode, result.stderr.strip()[:300],
            )
            return _STARTAPPS_CACHE or []

        data = json.loads(result.stdout)
        if isinstance(data, dict):
            data = [data]  # PowerShell doesn't wrap a single result in a list
        if not isinstance(data, list):
            return _STARTAPPS_CACHE or []

        _STARTAPPS_CACHE = data
        _STARTAPPS_CACHE_TIME = now
        logger.info("launcher_map: enumerated %d installed apps via Get-StartApps.", len(data))
        return data
    except Exception as exc:
        logger.warning("launcher_map: could not enumerate installed apps — %s", exc)
        return _STARTAPPS_CACHE or []


def find_installed_app(query: str) -> Optional[dict]:
    """
    Fuzzy-match `query` (e.g. "fc 26", "what's app") against every app
    actually installed on this machine. Returns the best-matching
    ``{"Name": ..., "AppID": ...}`` dict, or None if nothing crosses the
    confidence threshold. Never raises.
    """
    target = _normalize_app_name(query)
    if not target:
        return None

    apps = _get_installed_apps()
    best: Optional[dict] = None
    best_score = 0.0

    for app in apps:
        app_name = app.get("Name") or ""
        normalized = _normalize_app_name(app_name)
        if not normalized:
            continue
        if target == normalized or target in normalized or normalized in target:
            return app  # strong/exact-ish match — stop immediately
        score = SequenceMatcher(None, target, normalized).ratio()
        if score > best_score:
            best_score = score
            best = app

    return best if best_score >= _FUZZY_MATCH_THRESHOLD else None


def launch_installed_app(query: str) -> LaunchResult:
    """
    Resolve `query` via find_installed_app() and launch it.

    ``explorer.exe shell:AppsFolder\\<AppID>`` only works when AppID is a
    genuine UWP/Microsoft Store package identity — a
    "PackageFamilyName!AppId" string (it always contains "!"). For a
    classic installed app or a Steam-created Start Menu shortcut,
    ``Get-StartApps`` reports AppID as a plain file path instead, and
    shell:AppsFolder does not accept that at all — it just fails.

    Root-cause fix (2026-11-02): this is why "open fc 26" errored out.
    FC 26 is a Steam game, so its Start Menu shortcut's AppID is a plain
    path, not a UWP package identity. We now branch on whether "!" is
    present: UWP apps still go through shell:AppsFolder; everything else
    goes through os.startfile(), which is the correct Windows-native way
    to open a plain .exe OR a .lnk shortcut (including one that itself
    points at a steam:// URI).
    """
    app = find_installed_app(query)
    if not app:
        return LaunchResult(
            success=False,
            command=query,
            error=f"No installed app matched '{query}'.",
        )

    app_id = app.get("AppID", "")
    app_name = app.get("Name", query)
    if not app_id:
        return LaunchResult(success=False, command=query, error=f"Matched '{app_name}' but it has no AppID.")

    try:
        if "!" in app_id:
            # Genuine UWP/Microsoft Store package identity.
            proc = subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app_id}"])
            pid = proc.pid
        else:
            # Classic app or Steam/other shortcut — AppID is a plain path.
            os.startfile(app_id)  # type: ignore[attr-defined]  (Windows-only API)
            pid = None
        logger.info("launcher_map.launch_installed_app: launched '%s' (AppID=%s).", app_name, app_id)
        return LaunchResult(success=True, command=app_name, pid=pid)
    except Exception as exc:
        logger.warning("launcher_map.launch_installed_app: failed to launch '%s' — %s", app_name, exc)
        return LaunchResult(success=False, command=query, error=f"Found '{app_name}' but launch failed: {exc}")


__all__ = ["DynamicLauncher", "LaunchResult", "find_installed_app", "launch_installed_app"]
