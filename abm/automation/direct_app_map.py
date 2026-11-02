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

# Root-cause fix (2026-11-02): the old pattern required one of these names
# to appear LITERALLY in the text. "open whatsapp" matched; "open what's
# app" did not, because speech-to-text is inconsistent about spacing and
# punctuation in compound brand names ("what's app" vs "whatsapp" vs
# "whats-app") and a literal regex alternation can't absorb that variance.
# Fix: capture a bounded phrase after the verb, NORMALIZE it (strip
# everything but letters/digits), and compare against normalized known
# names instead of matching literal text. Still requires an exact
# normalized match against a KNOWN app — this is not fuzzy/substring
# matching against arbitrary text, so it doesn't introduce false positives
# for sentences that merely contain "open" followed by unrelated words.

_VERB_OPEN = r"(open|launch|start|run|load|bring\s+up)"
_VERB_CLOSE = r"(close|quit|kill|stop|exit|shut\s+down|terminate)"

# Up to 5 words after the verb — wide enough for "what's app", "visual
# studio code", "ea sports fc 26"; bounded so it can't run into the rest
# of an unrelated sentence.
_OPEN_PATTERN: re.Pattern[str] = re.compile(
    r"\b" + _VERB_OPEN + r"\b\s+((?:[\w'\u2019]+\s*){1,5})",
    re.IGNORECASE,
)
_CLOSE_PATTERN: re.Pattern[str] = re.compile(
    r"\b" + _VERB_CLOSE + r"\b\s+((?:[\w'\u2019]+\s*){1,5})",
    re.IGNORECASE,
)


def _normalize(name: str) -> str:
    """Lowercase and strip everything but letters/digits."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _build_normalized_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}
    for k in DIRECT_APP_MAP:
        lookup[_normalize(k)] = k
    for alias, canon in _APP_ALIASES.items():
        lookup.setdefault(_normalize(alias), canon)
    return lookup


_NORMALIZED_LOOKUP: dict[str, str] = _build_normalized_lookup()


def _resolve_canonical(raw_phrase: str) -> Optional[str]:
    """
    Normalize the captured phrase and look it up against every known app
    name/alias. Tries progressively shorter prefixes (dropping trailing
    words like "please" or "for me") before giving up.
    """
    if not raw_phrase:
        return None
    normalized = _normalize(raw_phrase)
    if normalized in _NORMALIZED_LOOKUP:
        return _NORMALIZED_LOOKUP[normalized]

    words = raw_phrase.split()
    for cut in range(len(words) - 1, 0, -1):
        candidate = _normalize(" ".join(words[:cut]))
        if candidate in _NORMALIZED_LOOKUP:
            return _NORMALIZED_LOOKUP[candidate]
    return None


def match_tier1_intent(text: str) -> Optional[tuple[str, str]]:
    """
    Check whether text expresses a Tier-1 open or close intent for a KNOWN
    app (one in DIRECT_APP_MAP or _APP_ALIASES).

    Zero tokens - pure regex, no LLM call.

    Returns (action, canonical_app_name) or None.
    action is always 'open' or 'close'.
    canonical_app_name is always a key in DIRECT_APP_MAP.
    """
    if not text or not text.strip():
        return None

    m = _OPEN_PATTERN.search(text)
    if m:
        canonical = _resolve_canonical(m.group(2))
        if canonical:
            return ("open", canonical)

    m = _CLOSE_PATTERN.search(text)
    if m:
        canonical = _resolve_canonical(m.group(2))
        if canonical:
            return ("close", canonical)

    return None


def extract_open_phrase(text: str) -> Optional[str]:
    """
    Detect an "open/launch/start X" structure WITHOUT requiring X to be a
    known app — returns the raw captured phrase (e.g. "fc 26") so the
    caller can try a broader, dynamic lookup (every app actually installed
    on the machine, not just the curated DIRECT_APP_MAP) for apps ABM
    doesn't have a hardcoded entry for.

    Only "open" (not "close") — closing an app ABM has no curated entry
    for is intentionally NOT auto-resolved here; killing an arbitrary
    dynamically-matched process by name is a meaningfully different risk
    than opening one, and is left out for now rather than guessed at.
    """
    if not text or not text.strip():
        return None
    m = _OPEN_PATTERN.search(text)
    if m:
        phrase = m.group(2).strip()
        return phrase or None
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
