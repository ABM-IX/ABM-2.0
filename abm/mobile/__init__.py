"""
abm/mobile/__init__.py
=======================
ABM Mobile — Phase v1.0 Ambient Interaction Manager

Re-exports the complete public surface of the ``abm.mobile`` package.
Consumers import from here; they never reach into sub-modules directly.

Architectural Constitution rule 13: all clients communicate through the
API layer (``abm.api``). The symbols here are for the API layer's own
imports — not for direct client use.
"""

from abm.mobile.ambient_manager import (
    AmbientInteractionManager,
    DesignDocMonitor,
    GitTreeMonitor,
    ManagerConfig,
    WorkspaceStateMonitor,
    DESIGN_DOC_EXTENSIONS,
)
from abm.mobile.event_models import AmbientEvent, PERMITTED_SOURCE_KINDS
from abm.mobile.retention_housekeeper import (
    HousekeeperResult,
    StreamCRetentionHousekeeper,
    ARCHIVE_AFTER_DAYS,
    COLLECTION_AMBIENT_ARCHIVE,
    DELETE_AFTER_DAYS,
    HOUSEKEEPING_INTERVAL_SECONDS,
    SUMMARIZE_AFTER_DAYS,
)
from abm.mobile.stream_c_writer import (
    StreamCWriter,
    WriteResult,
    COMPRESS_WINDOW_SECONDS,
)

__all__ = [
    # Manager
    "AmbientInteractionManager",
    "ManagerConfig",
    # Monitors
    "GitTreeMonitor",
    "WorkspaceStateMonitor",
    "DesignDocMonitor",
    # Event
    "AmbientEvent",
    # Results
    "WriteResult",
    "HousekeeperResult",
    # Writer / Housekeeper
    "StreamCWriter",
    "StreamCRetentionHousekeeper",
    # Constants
    "PERMITTED_SOURCE_KINDS",
    "DESIGN_DOC_EXTENSIONS",
    "COMPRESS_WINDOW_SECONDS",
    "HOUSEKEEPING_INTERVAL_SECONDS",
    "SUMMARIZE_AFTER_DAYS",
    "ARCHIVE_AFTER_DAYS",
    "DELETE_AFTER_DAYS",
    "COLLECTION_AMBIENT_ARCHIVE",
]
