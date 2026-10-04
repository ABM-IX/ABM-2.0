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

import logging
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
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


__all__ = ["DynamicLauncher", "LaunchResult"]
