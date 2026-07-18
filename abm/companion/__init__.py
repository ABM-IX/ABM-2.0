"""
ABM 2.0 — abm.companion
Phase v0.2: Developer Companion Node

Exports the four v0.2 components:
  - WorkspaceFileWatcher   : watchdog-based file change monitor
  - GitPipeline            : local Git commit/diff/branch reader
  - StyleFingerprintExtractor : AST-based code style analyzer
  - IngestionCoordinator   : wires all three into the v0.1 memory controller
"""

from .file_watcher import FileChangeEvent, WorkspaceFileWatcher
from .git_pipeline import CommitRecord, FileDiff, GitPipeline, GitPipelineError
from .ingestion_coordinator import IngestionCoordinator, IngestionResult
from .code_structure_analyzer import (
    CodeStructureAnalysis,
    CodeStructureAnalyzer,
    CodeStructureNode,
    analyze_code_structure,
)
from .style_fingerprint import StyleFingerprint, StyleFingerprintExtractor, StyleExtractionError

__all__ = [
    # file_watcher
    "WorkspaceFileWatcher",
    "FileChangeEvent",
    # git_pipeline
    "GitPipeline",
    "GitPipelineError",
    "CommitRecord",
    "FileDiff",
    # code_structure_analyzer
    "CodeStructureAnalyzer",
    "CodeStructureAnalysis",
    "CodeStructureNode",
    "analyze_code_structure",
    # style_fingerprint
    "StyleFingerprintExtractor",
    "StyleFingerprint",
    "StyleExtractionError",
    # ingestion_coordinator
    "IngestionCoordinator",
    "IngestionResult",
]
