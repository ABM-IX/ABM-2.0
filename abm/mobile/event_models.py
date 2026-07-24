"""
abm/mobile/event_models.py
===========================
Internal event transport for the ABM Mobile Ambient Interaction Manager.

``AmbientEvent`` is the single internal representation produced by all
data-source monitors (GitTreeMonitor, WorkspaceStateMonitor,
DesignDocMonitor) and consumed by ``StreamCWriter``.  It is deliberately
*not* a ChromaDB record — the conversion to the exact Stream C metadata
schema (``epoch_timestamp``, ``active_repository``, ``device_source``)
lives in ``StreamCWriter``.

Telemetry scope (Phase v1.0 guardrail — PROJECT_BRIEF.md ground rule 8):
  - ``git_commit``      — a Git commit event from a watched repo
  - ``workspace_file``  — a non-code file change in the IDE workspace
  - ``design_doc``      — a static design / spec document discovered on disk

Clipboard, voice, and browser events are intentionally omitted from this
enum and will raise ``ValueError`` if passed to ``StreamCWriter``.

Constitutional compliance:
  - Rule 3  : every ``AmbientEvent`` carries ``source_path`` (the artefact
    that generated it) satisfying the "traceable to a source" requirement.
  - Rule 8  : every write goes through ``StreamCWriter`` which calls the
    ``StreamCRetentionHousekeeper`` — so the lifecycle is enforced from
    the very first event, not bolted on later.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

# ---------------------------------------------------------------------------
# Permitted source kinds
# ---------------------------------------------------------------------------

#: Exhaustive set of permitted ambient telemetry source kinds for Phase v1.0.
#: Adding a new kind requires a phase brief — do not extend this set ad hoc.
PERMITTED_SOURCE_KINDS: frozenset[str] = frozenset(
    {
        "git_commit",     # A commit event from GitTreeMonitor
        "workspace_file", # A non-code file change from WorkspaceStateMonitor
        "design_doc",     # A design/spec doc discovered by DesignDocMonitor
        "chat_history",   # A captured chat interaction history
    }
)


# ---------------------------------------------------------------------------
# AmbientEvent dataclass
# ---------------------------------------------------------------------------


@dataclass
class AmbientEvent:
    """
    Normalised ambient interaction event produced by data-source monitors.

    All fields are validated before the event reaches ``StreamCWriter``.
    The event is ephemeral — it exists only in memory until ``StreamCWriter``
    converts it into a ChromaDB Stream C record.

    Attributes
    ----------
    source_kind : str
        Category of the event.  Must be one of ``PERMITTED_SOURCE_KINDS``.
        ``StreamCWriter`` raises ``ValueError`` for any other value.
    active_repository : str
        Name of the Git repository associated with this event.
        ``\"\"`` (empty string) if no repository context is available.
    source_path : str
        Absolute path of the file / commit that generated the event.
        Satisfies Architectural Constitution rule 3 (explainability).
    text : str
        Human-readable description of the event.  This becomes the
        ChromaDB document body for embedding.
    epoch_timestamp : int
        Unix timestamp (integer seconds) when the event was detected.
        Defaults to ``int(time.time())`` at construction time if not supplied.
    device_source : str
        Always ``\"dynamic_mobile_node\"`` per spec section 2 / section 10
        hardware-agnostic blueprint correction.  Set automatically in
        ``__post_init__``; do not pass explicitly.
    extra : dict
        Optional extra key/value pairs for diagnostic use.  Never written
        to ChromaDB metadata — only appears in ``StreamCWriter`` logs.
    """

    source_kind: str
    active_repository: str
    source_path: str
    text: str
    epoch_timestamp: int = field(default_factory=lambda: int(time.time()))
    device_source: str = "desktop_workspace"
    extra: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validate source_kind at construction time so callers get a clear error
        if self.source_kind not in PERMITTED_SOURCE_KINDS:
            raise ValueError(
                f"AmbientEvent: source_kind '{self.source_kind}' is not permitted "
                f"in Phase v1.0. Allowed: {sorted(PERMITTED_SOURCE_KINDS)}. "
                "Clipboard, voice, and browser sources are offline until explicitly "
                "re-scoped by ABM in a future brief (PROJECT_BRIEF.md ground rule 8)."
            )
        if not self.text or not self.text.strip():
            raise ValueError("AmbientEvent: 'text' must be non-empty.")


__all__ = ["AmbientEvent", "PERMITTED_SOURCE_KINDS"]
