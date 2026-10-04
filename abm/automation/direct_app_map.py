"""
abm/automation/direct_app_map.py
==================================
Tier-1 Deterministic App Launcher — Phase 7 Extension

Provides a curated DIRECT_APP_MAP of safe application names to launch
commands, and a regex-based intent matcher that detects open/close requests
at zero token cost (no LLM call needed).

Design contract:
  - DIRECT_APP_MAP is the single source of truth for Tier-1-safe app names.
    It is used by BOTH the local answerQuestion() fast-path (capabilities.py)
    and the remote /api/sync/command endpoint (sync_server.py).
  - Only apps in DIRECT_APP_MAP may be launched via remote dispatch.
    This prevents arbitrary remote command execution.
  - match_tier1_intent() returns (action, canonical_name) or None.
    action is always "open" or "close".
  - Never raises to the caller.

Note (Constitution Rule 1 - local-first):
  remote_command messages over /api/sync/command require BOTH devices to be
  reachable via the existing local pairing/sync connection. This does NOT
  work over the open internet. Both nodes must be on the same LAN or VPN
  segment with the sync server port (8765) accessible from the mobile device.
"""

from __future__ import annotations

import re
from typing import Optional


# Tier-1 Safe App Registry
DIRECT_APP_MAP: dict[str, str] = {
    "spotify":     "spotify",
    "chrome":      "chrome",
    "firefox":     "firefox",
    "cursor":      "cursor",
    "vscode":      "code",
    "notepad":     "notepad",
    "calculator":  "calc",
    "explorer":    "explorer",
    "whatsapp":    "whatsapp:",
    "terminal":    "wt",
    "brave":       "brave",
    "slack":       "slack",
    "discord":     "discord",
}

_APP_ALIASES: dict[str, str] = {
    "google chrome": "chrome",
    "vs code":       "vscode",
    "visual studio code": "vscode",
    "command prompt": "terminal",
    "cmd":           "terminal",
    "powershell":    "terminal",
    "file explorer": "explorer",
    "files":         "explorer",
    "calc":          "calculator",
}

_APP_NAME_PATTERN = "|".join(
    re.escape(k) for k in sorted(
        list(DIRECT_APP_MAP.keys()) + list(_APP_ALIASES.keys()),
        key=len,
        reverse=True,
    )
)

_OPEN_PATTERN: re.Pattern[str] = re.compile(
    r"\b(open|launch|start|run|load|bring\s+up)\b[\s\w]*?\b(" + _APP_NAME_PATTERN + r")\b",
    re.IGNORECASE,
)

_CLOSE_PATTERN: re.Pattern[str] = re.compile(
    r"\b(close|quit|kill|stop|exit|shut\s+down|terminate)\b[\s\w]*?\b(" + _APP_NAME_PATTERN + r")\b",
    re.IGNORECASE,
)


def _resolve_canonical(raw_name: str) -> Optional[str]:
    name = raw_name.lower().strip()
    if name in DIRECT_APP_MAP:
        return name
    if name in _APP_ALIASES:
        return _APP_ALIASES[name]
    return None


def match_tier1_intent(text: str) -> Optional[tuple[str, str]]:
    """
    Check whether text expresses a Tier-1 open or close intent.

    Zero tokens - pure regex, no LLM call.

    Returns (action, canonical_app_name) or None.
    action is always 'open' or 'close'.
    canonical_app_name is always a key in DIRECT_APP_MAP.
    """
    if not text or not text.strip():
        return None

    m = _OPEN_PATTERN.search(text)
    if m:
        raw = m.group(2).lower()
        canonical = _resolve_canonical(raw)
        if canonical:
            return ("open", canonical)

    m = _CLOSE_PATTERN.search(text)
    if m:
        raw = m.group(2).lower()
        canonical = _resolve_canonical(raw)
        if canonical:
            return ("close", canonical)

    return None


def resolve_command(canonical_name: str) -> Optional[str]:
    """Return the launch command for a canonical app name."""
    name = canonical_name.lower().strip()
    if name in _APP_ALIASES:
        name = _APP_ALIASES[name]
    return DIRECT_APP_MAP.get(name)


__all__ = [
    "DIRECT_APP_MAP",
    "match_tier1_intent",
    "resolve_command",
]
