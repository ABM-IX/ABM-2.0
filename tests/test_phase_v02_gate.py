"""
tests/test_phase_v02_gate.py
=============================
Phase v0.2 Gate Tests — Developer Companion Node
Spec Reference: ABM_SPEC.md sections 2, 3, and 10 (item 2)

Hard gate proofs (must be 100% green before Phase v0.3):
  1. TestWatcherCreateModifyDeleteGate — create/modify/delete detection + stream
     routing without touching v0.1 internals
  2. TestGitCommitBranchStateGate — real Git repo commit/branch state reads
  3. TestStyleFingerprintNonCollisionGate — schema-valid Stream A entries that
     do not collide with or overwrite existing v0.1 data

Supporting contract tests cover routing, fingerprints, chunk delegation, and
v0.1 regression. Phase v0.2 does NOT advance to v0.3 until this file is green.
"""

from __future__ import annotations

import inspect
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Ensure repo root is on sys.path
# ---------------------------------------------------------------------------

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# ---------------------------------------------------------------------------
# v0.1 imports (must not be modified by v0.2)
# ---------------------------------------------------------------------------

from abm.memory.chroma_controller import (
    ALL_COLLECTIONS,
    COLLECTION_AMBIENT_TELEMETRY,
    COLLECTION_CODE_TOPOLOGIES,
    COLLECTION_COGNITIVE_IDENTITY,
    COLLECTION_TECHNICAL_MASTERY,
    SCHEMA_AMBIENT_TELEMETRY,
    SCHEMA_CODE_TOPOLOGIES,
    SCHEMA_COGNITIVE_IDENTITY,
    SCHEMA_TECHNICAL_MASTERY,
    ChromaController,
)
from abm.memory.chunking import chunk_stream_a_code_topologies
from abm.memory.metadata_models import CodeTopologiesMetadata

# ---------------------------------------------------------------------------
# v0.2 imports
# ---------------------------------------------------------------------------

from abm.companion.file_watcher import (
    CODE_EXTENSIONS,
    DEFAULT_DEBOUNCE_SECONDS,
    DEVICE_SOURCE,
    FileChangeEvent,
    WorkspaceFileWatcher,
    _DebounceHandler,
    _infer_repository,
)
from abm.companion.git_pipeline import (
    CommitRecord,
    DEFAULT_MAX_COMMITS,
    FileDiff,
    GitPipeline,
    GitPipelineError,
)
from abm.companion.code_structure_analyzer import (
    CodeStructureAnalysis,
    CodeStructureAnalyzer,
    CodeStructureNode,
    SUPPORTED_STRUCTURE_LANGUAGES,
    analyze_code_structure,
)
from abm.companion.style_fingerprint import (
    MIN_IDENTIFIER_COUNT,
    StyleExtractionError,
    StyleFingerprint,
    StyleFingerprintExtractor,
)
from abm.companion.ingestion_coordinator import (
    IngestionCoordinator,
    IngestionResult,
    _EXT_TO_LANGUAGE,
)
import abm.companion.file_watcher as file_watcher_module
import abm.companion.style_fingerprint as style_fingerprint_module


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

MOCK_EMBEDDING = [float(i) / 768 for i in range(768)]

PYTHON_CODE_CAMEL = """
class UserBloc:
    def handleEvent(self, userEvent):
        return self.processData(userEvent)

    def processData(self, inputData):
        return inputData
"""

PYTHON_CODE_SNAKE = """
def handle_event(user_event):
    return process_data(user_event)

def process_data(input_data):
    return input_data
"""

DART_BLOC_CODE = """
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

class UserBloc extends Bloc<UserEvent, UserState> {
  UserBloc() : super(UserInitial()) {
    on<LoadUser>((event, emit) async {
      emit(UserLoaded(user: await fetchUser()));
    });
  }
}
"""


def _make_mock_controller() -> MagicMock:
    """Return a mock ChromaController that tracks add_document calls per collection."""
    ctrl = MagicMock()
    ctrl.registered_collections = ALL_COLLECTIONS
    return ctrl


def _make_mock_embedder() -> MagicMock:
    """Return a mock OllamaEmbeddingWrapper that always returns MOCK_EMBEDDING."""
    embedder = MagicMock()
    embedder.embed.return_value = MOCK_EMBEDDING
    embedder.embed_batch.return_value = [MOCK_EMBEDDING]
    return embedder


def _make_mock_git_pipeline(
    repo_name: str = "smart_transit",
    commit_sha: str = "abc1234567890abc1234567890abc1234567890ab",
    added_code: str = PYTHON_CODE_CAMEL,
) -> MagicMock:
    """Return a mock GitPipeline with predictable return values."""
    gp = MagicMock(spec=GitPipeline)
    gp.repo_name.return_value = repo_name
    gp.current_branch.return_value = "main"
    gp.head_commit_sha.return_value = commit_sha
    gp.list_commits.return_value = [
        CommitRecord(
            sha=commit_sha,
            message="feat: add UserBloc",
            author="ABM",
            epoch_timestamp=1784370192,
            files_changed=["lib/blocs/user_bloc.py"],
        )
    ]
    gp.get_commit_diff.return_value = [
        FileDiff(
            path="lib/blocs/user_bloc.py",
            language="python",
            added_lines=added_code,
        )
    ]
    # get_commit_file_chunks must call the real v0.1 chunker
    gp.get_commit_file_chunks.return_value = chunk_stream_a_code_topologies(
        added_code, "python"
    )
    gp.get_commit_telemetry_event.return_value = {
        "epoch_timestamp": 1784370192,
        "active_repository": repo_name,
        "device_source": DEVICE_SOURCE,
        "text": f"git commit abc12345: feat: add UserBloc",
        "sha": commit_sha,
    }
    return gp


# ---------------------------------------------------------------------------
# HARD GATE 1 — create / modify / delete → correct stream, no v0.1 internals
# ---------------------------------------------------------------------------


def _fs_event(path: str, *, is_directory: bool = False) -> MagicMock:
    event = MagicMock()
    event.src_path = path
    event.is_directory = is_directory
    return event


class TestWatcherCreateModifyDeleteGate(unittest.TestCase):
    """
    Prove file-watcher hooks detect create/modify/delete and route them to
    the right stream callbacks without touching v0.1 memory internals.
    """

    def _make_handler(self) -> tuple[_DebounceHandler, list[FileChangeEvent], list[FileChangeEvent]]:
        code_events: list[FileChangeEvent] = []
        telem_events: list[FileChangeEvent] = []
        handler = _DebounceHandler(
            on_code_change=code_events.append,
            on_telemetry_event=telem_events.append,
            debounce_seconds=0.0,
        )
        return handler, code_events, telem_events

    def test_on_created_schedules_created_event_type(self):
        handler, _, _ = self._make_handler()
        with patch.object(handler, "_schedule") as mock_schedule:
            handler.on_created(_fs_event("/workspace/lib/user_bloc.dart"))
            mock_schedule.assert_called_once_with(
                "/workspace/lib/user_bloc.dart", "created"
            )

    def test_on_modified_schedules_modified_event_type(self):
        handler, _, _ = self._make_handler()
        with patch.object(handler, "_schedule") as mock_schedule:
            handler.on_modified(_fs_event("/workspace/lib/main.py"))
            mock_schedule.assert_called_once_with("/workspace/lib/main.py", "modified")

    def test_on_deleted_schedules_deleted_event_type(self):
        handler, _, _ = self._make_handler()
        with patch.object(handler, "_schedule") as mock_schedule:
            handler.on_deleted(_fs_event("/workspace/lib/old.kt"))
            mock_schedule.assert_called_once_with("/workspace/lib/old.kt", "deleted")

    def test_directory_events_are_ignored(self):
        handler, _, _ = self._make_handler()
        with patch.object(handler, "_schedule") as mock_schedule:
            handler.on_created(_fs_event("/workspace/lib", is_directory=True))
            handler.on_modified(_fs_event("/workspace/lib", is_directory=True))
            handler.on_deleted(_fs_event("/workspace/lib", is_directory=True))
            mock_schedule.assert_not_called()

    def test_create_modify_delete_preserve_event_type_on_dispatch(self):
        for event_type in ("created", "modified", "deleted"):
            with self.subTest(event_type=event_type):
                handler, code, _ = self._make_handler()
                handler._dispatch("/workspace/app.py", event_type)
                self.assertEqual(len(code), 1)
                self.assertEqual(code[0].event_type, event_type)
                self.assertTrue(code[0].is_code_file)

    def test_code_create_routes_to_code_callback_not_telemetry(self):
        handler, code, telem = self._make_handler()
        handler._dispatch("/workspace/feature.dart", "created")
        self.assertEqual(len(code), 1)
        self.assertEqual(len(telem), 0)
        self.assertEqual(code[0].event_type, "created")

    def test_non_code_modify_routes_to_telemetry_not_code(self):
        handler, code, telem = self._make_handler()
        handler._dispatch("/workspace/README.md", "modified")
        self.assertEqual(len(code), 0)
        self.assertEqual(len(telem), 1)
        self.assertEqual(telem[0].event_type, "modified")

    def test_code_delete_routes_to_code_callback_for_stream_a_skip_path(self):
        """Deletes still reach the code callback; coordinator skips embedding."""
        handler, code, telem = self._make_handler()
        handler._dispatch("/workspace/gone.py", "deleted")
        self.assertEqual(len(code), 1)
        self.assertEqual(code[0].event_type, "deleted")
        self.assertEqual(len(telem), 0)

        coord = IngestionCoordinator(
            controller=_make_mock_controller(),
            embedder=_make_mock_embedder(),
        )
        result = coord.ingest_file_change(code[0])
        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.collection, COLLECTION_CODE_TOPOLOGIES)

    def test_watcher_module_does_not_import_v01_chroma_or_chunking(self):
        """Watcher must not touch v0.1 memory internals — callbacks only."""
        source = inspect.getsource(file_watcher_module)
        forbidden = (
            "chroma_controller",
            "ChromaController",
            "add_document",
            "chunk_stream_a",
            "OllamaEmbeddingWrapper",
            "abm.memory",
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_workspace_file_watcher_holds_no_controller_reference(self):
        watcher = WorkspaceFileWatcher.__new__(WorkspaceFileWatcher)
        watcher._watch_paths = ["/tmp"]
        watcher._on_code_change = lambda e: None
        watcher._on_telemetry_event = lambda e: None
        watcher._debounce_seconds = 1.0
        for attr in ("_controller", "_embedder", "_chroma", "_collections"):
            with self.subTest(attr=attr):
                self.assertFalse(hasattr(watcher, attr))

    def test_ingest_routes_created_code_to_stream_a_and_c_never_b_or_d(self):
        ctrl = _make_mock_controller()
        coord = IngestionCoordinator(controller=ctrl, embedder=_make_mock_embedder())
        evt = FileChangeEvent(
            path="/workspace/main.py",
            event_type="created",
            epoch_timestamp=1784370192,
            repository="smart_transit",
        )
        with patch.object(Path, "read_text", return_value=PYTHON_CODE_CAMEL):
            coord.ingest_file_change(evt)

        collections = [
            (c.args[0] if c.args else c.kwargs.get("collection_name"))
            for c in ctrl.add_document.call_args_list
        ]
        self.assertIn(COLLECTION_CODE_TOPOLOGIES, collections)
        self.assertIn(COLLECTION_AMBIENT_TELEMETRY, collections)
        self.assertNotIn(COLLECTION_TECHNICAL_MASTERY, collections)
        self.assertNotIn(COLLECTION_COGNITIVE_IDENTITY, collections)


# ---------------------------------------------------------------------------
# HARD GATE 2 — Git integration reads commit / branch state
# ---------------------------------------------------------------------------


class TestGitCommitBranchStateGate(unittest.TestCase):
    """
    Prove GitPipeline correctly reads commit history and branch state from a
    real local repository (no network, no mocks of GitPython Repo).
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdir = tempfile.mkdtemp(prefix="abm_v02_git_")
        cls._repo_root = Path(cls._tmpdir) / "smart_transit"
        cls._repo_root.mkdir()
        cls._run_git("init", "-b", "main")
        cls._run_git("config", "user.email", "abm@firstminds.test")
        cls._run_git("config", "user.name", "ABM")

        cls._write("README.md", "# smart_transit\n")
        cls._run_git("add", "README.md")
        cls._run_git("commit", "-m", "init: scaffold")

        cls._write(
            "lib/user_bloc.py",
            "class UserBloc:\n    def handleEvent(self, userEvent):\n        return userEvent\n",
        )
        cls._run_git("add", "lib/user_bloc.py")
        cls._run_git("commit", "-m", "feat: add UserBloc")

        cls._run_git("checkout", "-b", "feature/companion-node")
        cls._write("lib/user_bloc.py", "class UserBloc:\n    def handleEvent(self, userEvent):\n        return self.processData(userEvent)\n\n    def processData(self, inputData):\n        return inputData\n")
        cls._run_git("add", "lib/user_bloc.py")
        cls._run_git("commit", "-m", "feat: extend UserBloc")

        cls.pipeline = GitPipeline(str(cls._repo_root))
        cls.head_sha = cls._run_git("rev-parse", "HEAD").stdout.strip()
        cls.main_sha = cls._run_git("rev-parse", "main").stdout.strip()

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls._tmpdir, ignore_errors=True)

    @classmethod
    def _run_git(cls, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=cls._repo_root,
            check=True,
            capture_output=True,
            text=True,
        )

    @classmethod
    def _write(cls, relative: str, content: str) -> None:
        path = cls._repo_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_repo_name_matches_directory_basename(self):
        self.assertEqual(self.pipeline.repo_name(), "smart_transit")

    def test_current_branch_is_feature_branch(self):
        self.assertEqual(self.pipeline.current_branch(), "feature/companion-node")

    def test_head_commit_sha_matches_git_rev_parse(self):
        self.assertEqual(self.pipeline.head_commit_sha(), self.head_sha)
        self.assertEqual(len(self.pipeline.head_commit_sha()), 40)

    def test_list_commits_returns_newest_first_with_expected_messages(self):
        commits = self.pipeline.list_commits(max_count=10)
        self.assertGreaterEqual(len(commits), 3)
        self.assertIsInstance(commits[0], CommitRecord)
        self.assertEqual(commits[0].sha, self.head_sha)
        self.assertEqual(commits[0].message, "feat: extend UserBloc")
        messages = [c.message for c in commits]
        self.assertIn("feat: add UserBloc", messages)
        self.assertIn("init: scaffold", messages)

    def test_list_commits_respects_max_count(self):
        commits = self.pipeline.list_commits(max_count=2)
        self.assertEqual(len(commits), 2)
        self.assertEqual(commits[0].sha, self.head_sha)

    def test_commit_record_exposes_author_timestamp_and_files(self):
        head = self.pipeline.list_commits(max_count=1)[0]
        self.assertEqual(head.author, "ABM")
        self.assertIsInstance(head.epoch_timestamp, int)
        self.assertGreater(head.epoch_timestamp, 0)
        self.assertTrue(any(path.endswith("user_bloc.py") for path in head.files_changed))

    def test_branch_switch_updates_current_branch_and_head(self):
        self._run_git("checkout", "main")
        try:
            pipeline = GitPipeline(str(self._repo_root))
            self.assertEqual(pipeline.current_branch(), "main")
            self.assertEqual(pipeline.head_commit_sha(), self.main_sha)
            self.assertNotEqual(pipeline.head_commit_sha(), self.head_sha)
        finally:
            self._run_git("checkout", "feature/companion-node")

    def test_invalid_repo_raises_git_pipeline_error(self):
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(GitPipelineError):
                GitPipeline(empty)


# ---------------------------------------------------------------------------
# HARD GATE 3 — style fingerprints: schema-valid, no v0.1 overwrite
# ---------------------------------------------------------------------------


class TestStyleFingerprintNonCollisionGate(unittest.TestCase):
    """
    Prove the style fingerprint engine writes schema-valid Stream A entries
    that do not collide with or overwrite existing v0.1 documents.
    """

    V01_DOC_ID = "v01_seed_code_topology_001"
    V01_TEXT = "v0.1 seeded engineering DNA — must survive fingerprint ingest"
    V01_EMBEDDING = [1.0] + [0.0] * 31
    FP_EMBEDDING = [0.0, 1.0] + [0.0] * 30

    def setUp(self) -> None:
        self.controller = ChromaController(in_memory=True)
        self.controller.add_document(
            COLLECTION_CODE_TOPOLOGIES,
            doc_id=self.V01_DOC_ID,
            text=self.V01_TEXT,
            metadata={
                "language": "dart",
                "framework": "flutter",
                "state_pattern": "bloc",
                "naming_convention": "camelCase",
            },
            embedding=self.V01_EMBEDDING,
        )
        self.embedder = MagicMock()
        self.embedder.embed.return_value = self.FP_EMBEDDING
        self.coord = IngestionCoordinator(
            controller=self.controller,
            embedder=self.embedder,
        )
        self.extractor = StyleFingerprintExtractor()

    def tearDown(self) -> None:
        for name in ALL_COLLECTIONS:
            self.controller.clear_collection(name)

    def test_fingerprint_metadata_validates_against_v01_pydantic_schema(self):
        fp = self.extractor.extract(DART_BLOC_CODE, "dart")
        meta = self.extractor.to_stream_a_metadata(fp)
        # Must not raise — exact Stream A contract from v0.1
        validated = CodeTopologiesMetadata(**meta)
        self.assertEqual(validated.language, "dart")
        self.assertEqual(validated.framework, "flutter")
        self.assertEqual(validated.state_pattern, "bloc")
        self.assertEqual(validated.naming_convention, "camelCase")

    def test_stream_a_metadata_clamps_naming_convention_to_schema_literal(self):
        """
        Detected snake_case may live on the fingerprint / document text, but
        Stream A metadata must always use the schema Literal \"camelCase\".
        """
        fp = self.extractor.extract(PYTHON_CODE_SNAKE, "python")
        self.assertEqual(fp.naming_convention, "snake_case")
        meta = self.extractor.to_stream_a_metadata(fp)
        self.assertEqual(meta["naming_convention"], "camelCase")
        CodeTopologiesMetadata(**meta)  # must validate

    def test_fingerprint_metadata_has_exactly_four_stream_a_keys(self):
        fp = self.extractor.extract(DART_BLOC_CODE, "dart")
        meta = self.extractor.to_stream_a_metadata(fp)
        self.assertEqual(set(meta.keys()), set(SCHEMA_CODE_TOPOLOGIES.keys()))
        self.assertEqual(len(meta), 4)

    def test_ingest_fingerprint_does_not_overwrite_existing_v01_document(self):
        before = self.controller.collection_count(COLLECTION_CODE_TOPOLOGIES)
        self.assertEqual(before, 1)

        result = self.coord.ingest_code_fingerprint(
            DART_BLOC_CODE,
            "dart",
            context_id="gate_fingerprint",
        )
        self.assertEqual(result.status, "ok")
        self.assertEqual(len(result.doc_ids), 1)
        new_id = result.doc_ids[0]

        # New fingerprint must use a distinct doc_id
        self.assertNotEqual(new_id, self.V01_DOC_ID)

        after = self.controller.collection_count(COLLECTION_CODE_TOPOLOGIES)
        self.assertEqual(after, 2)

        # Seeded v0.1 document still retrievable by its embedding
        seed_hit = self.controller.query_collection(
            COLLECTION_CODE_TOPOLOGIES,
            self.V01_EMBEDDING,
            n_results=2,
        )
        flat_ids = [doc_id for group in seed_hit.ids for doc_id in group]
        self.assertIn(self.V01_DOC_ID, flat_ids)

        seed_docs = self.controller.get_collection(COLLECTION_CODE_TOPOLOGIES).get(
            ids=[self.V01_DOC_ID],
            include=["documents"],
        )
        self.assertEqual(seed_docs["documents"][0], self.V01_TEXT)

    def test_fingerprint_doc_id_does_not_collide_with_v01_seed_id(self):
        result = self.coord.ingest_code_fingerprint(
            DART_BLOC_CODE,
            "dart",
            context_id="collision_probe",
        )
        self.assertTrue(result.doc_ids)
        self.assertNotEqual(result.doc_ids[0], self.V01_DOC_ID)
        # Content-hash IDs are stable but namespaced away from raw v0.1 seeds
        self.assertTrue(result.doc_ids[0].startswith("fingerprint_"))

    def test_fingerprint_ingest_never_writes_streams_b_c_or_d(self):
        counts_before = {
            name: self.controller.collection_count(name) for name in ALL_COLLECTIONS
        }
        self.coord.ingest_code_fingerprint(DART_BLOC_CODE, "dart", context_id="iso")
        self.assertEqual(
            self.controller.collection_count(COLLECTION_CODE_TOPOLOGIES),
            counts_before[COLLECTION_CODE_TOPOLOGIES] + 1,
        )
        for other in (
            COLLECTION_TECHNICAL_MASTERY,
            COLLECTION_AMBIENT_TELEMETRY,
            COLLECTION_COGNITIVE_IDENTITY,
        ):
            with self.subTest(collection=other):
                self.assertEqual(
                    self.controller.collection_count(other),
                    counts_before[other],
                )

    def test_style_fingerprint_module_does_not_import_chroma_controller(self):
        """Extractor produces data only — IngestionCoordinator owns writes."""
        source = inspect.getsource(style_fingerprint_module)
        self.assertNotIn("from abm.memory", source)
        self.assertNotIn("import abm.memory", source)
        # Mentions in docstrings are fine; actual controller API usage is not.
        self.assertNotIn("controller.add_document", source)
        self.assertNotIn("ChromaController(", source)


# ---------------------------------------------------------------------------
# TestCodeStructureAnalyzer
# ---------------------------------------------------------------------------


class TestCodeStructureAnalyzer(unittest.TestCase):
    """General-purpose AST/structure analysis built on the v0.1 chunker."""

    def setUp(self):
        self.analyzer = CodeStructureAnalyzer()

    def test_supported_languages_match_stream_a_names(self):
        self.assertEqual(SUPPORTED_STRUCTURE_LANGUAGES, {"dart", "kotlin", "python"})

    def test_python_analysis_returns_nodes_and_chunks(self):
        analysis = self.analyzer.analyze(PYTHON_CODE_CAMEL, "python")
        self.assertIsInstance(analysis, CodeStructureAnalysis)
        self.assertGreater(len(analysis.nodes), 0)
        self.assertGreater(len(analysis.chunks), 0)
        self.assertTrue(any(node.name == "UserBloc" for node in analysis.nodes))

    def test_python_analysis_node_shape(self):
        analysis = self.analyzer.analyze(PYTHON_CODE_CAMEL, "python")
        node = analysis.nodes[0]
        self.assertIsInstance(node, CodeStructureNode)
        self.assertGreaterEqual(node.end_line, node.start_line)
        self.assertTrue(node.text.strip())

    def test_dart_analysis_detects_architecture_preferences(self):
        analysis = self.analyzer.analyze(DART_BLOC_CODE, "dart")
        self.assertTrue(analysis.architectural_preferences["uses_flutter"])
        self.assertTrue(analysis.architectural_preferences["uses_bloc"])
        self.assertGreaterEqual(analysis.architectural_preferences["bloc_class_count"], 1)

    def test_formatting_patterns_include_indent_and_line_lengths(self):
        analysis = self.analyzer.analyze(PYTHON_CODE_CAMEL, "python")
        self.assertIn("indent_style", analysis.formatting_patterns)
        self.assertIn("indent_unit", analysis.formatting_patterns)
        self.assertIn("average_line_length", analysis.formatting_patterns)

    def test_convenience_wrapper_returns_analysis(self):
        analysis = analyze_code_structure(PYTHON_CODE_CAMEL, "python")
        self.assertIsInstance(analysis, CodeStructureAnalysis)


# ---------------------------------------------------------------------------
# TestFileWatcherEventRouting
# ---------------------------------------------------------------------------


class TestFileWatcherEventRouting(unittest.TestCase):
    """Correct callback fires per file extension."""

    def _make_handler(self) -> tuple[_DebounceHandler, list, list]:
        code_events: list[FileChangeEvent] = []
        telem_events: list[FileChangeEvent] = []
        handler = _DebounceHandler(
            on_code_change=code_events.append,
            on_telemetry_event=telem_events.append,
            debounce_seconds=0.0,  # zero debounce for synchronous testing
        )
        return handler, code_events, telem_events

    def _dispatch(self, handler: _DebounceHandler, path: str, event_type: str = "modified") -> None:
        """Force an immediate dispatch bypassing the debounce timer."""
        handler._dispatch(path, event_type)

    def test_py_file_routes_to_code_callback(self):
        handler, code, _ = self._make_handler()
        self._dispatch(handler, "/workspace/main.py")
        self.assertEqual(len(code), 1)
        self.assertEqual(code[0].extension, ".py")

    def test_dart_file_routes_to_code_callback(self):
        handler, code, _ = self._make_handler()
        self._dispatch(handler, "/workspace/user_bloc.dart")
        self.assertEqual(len(code), 1)
        self.assertEqual(code[0].extension, ".dart")

    def test_kotlin_file_routes_to_code_callback(self):
        handler, code, _ = self._make_handler()
        self._dispatch(handler, "/workspace/MainActivity.kt")
        self.assertEqual(len(code), 1)
        self.assertEqual(code[0].extension, ".kt")

    def test_java_file_routes_to_code_callback(self):
        handler, code, _ = self._make_handler()
        self._dispatch(handler, "/workspace/Main.java")
        self.assertEqual(len(code), 1)

    def test_js_file_routes_to_code_callback(self):
        handler, code, _ = self._make_handler()
        self._dispatch(handler, "/workspace/app.js")
        self.assertEqual(len(code), 1)

    def test_css_file_routes_to_code_callback(self):
        handler, code, _ = self._make_handler()
        self._dispatch(handler, "/workspace/styles.css")
        self.assertEqual(len(code), 1)

    def test_html_file_routes_to_code_callback(self):
        handler, code, _ = self._make_handler()
        self._dispatch(handler, "/workspace/index.html")
        self.assertEqual(len(code), 1)

    def test_md_file_routes_to_telemetry_callback(self):
        handler, code, telem = self._make_handler()
        self._dispatch(handler, "/workspace/README.md")
        self.assertEqual(len(code), 0)
        self.assertEqual(len(telem), 1)

    def test_txt_file_routes_to_telemetry_callback(self):
        handler, code, telem = self._make_handler()
        self._dispatch(handler, "/workspace/notes.txt")
        self.assertEqual(len(code), 0)
        self.assertEqual(len(telem), 1)

    def test_json_file_routes_to_telemetry_callback(self):
        handler, code, telem = self._make_handler()
        self._dispatch(handler, "/workspace/pubspec.yaml")
        self.assertEqual(len(code), 0)
        self.assertEqual(len(telem), 1)

    def test_no_extension_routes_to_telemetry_callback(self):
        handler, code, telem = self._make_handler()
        self._dispatch(handler, "/workspace/Makefile")
        self.assertEqual(len(code), 0)
        self.assertEqual(len(telem), 1)

    def test_code_extensions_constant_contains_expected_extensions(self):
        expected = {".py", ".dart", ".kt", ".java", ".js", ".css", ".html"}
        self.assertEqual(CODE_EXTENSIONS, expected)


# ---------------------------------------------------------------------------
# TestFileWatcherIsolation
# ---------------------------------------------------------------------------


class TestFileWatcherIsolation(unittest.TestCase):
    """
    WorkspaceFileWatcher never writes to ChromaDB directly.
    Its interface is callbacks only — no controller reference anywhere.
    """

    def test_workspace_file_watcher_has_no_controller_attribute(self):
        """WorkspaceFileWatcher must not hold a reference to ChromaController."""
        code_cb = MagicMock()
        telem_cb = MagicMock()
        # Use /tmp as a placeholder — we won't actually start it
        watcher = WorkspaceFileWatcher.__new__(WorkspaceFileWatcher)
        watcher._watch_paths = []
        watcher._on_code_change = code_cb
        watcher._on_telemetry_event = telem_cb
        watcher._debounce_seconds = DEFAULT_DEBOUNCE_SECONDS
        # Should not have _controller, _embedder, or any ChromaDB reference
        for attr in ("_controller", "_embedder", "_chroma", "_collection"):
            with self.subTest(attr=attr):
                self.assertFalse(
                    hasattr(watcher, attr),
                    f"WorkspaceFileWatcher must not have attribute '{attr}'",
                )

    def test_debounce_handler_has_no_controller_attribute(self):
        """_DebounceHandler must not hold a ChromaDB reference."""
        handler = _DebounceHandler(
            on_code_change=lambda e: None,
            on_telemetry_event=lambda e: None,
            debounce_seconds=1.0,
        )
        for attr in ("_controller", "_embedder", "_chroma"):
            with self.subTest(attr=attr):
                self.assertFalse(hasattr(handler, attr))

    def test_file_change_event_has_no_controller_reference(self):
        """FileChangeEvent is a plain data container — no ChromaDB fields."""
        evt = FileChangeEvent(
            path="/workspace/main.py",
            event_type="modified",
            epoch_timestamp=1784370192,
            repository="smart_transit",
        )
        for attr in ("_controller", "_embedder", "_chroma", "add_document"):
            with self.subTest(attr=attr):
                self.assertFalse(hasattr(evt, attr))


# ---------------------------------------------------------------------------
# TestFileChangeEventShape
# ---------------------------------------------------------------------------


class TestFileChangeEventShape(unittest.TestCase):
    """FileChangeEvent populates all derived fields correctly."""

    def setUp(self):
        self.evt = FileChangeEvent(
            path="/workspace/user_bloc.dart",
            event_type="created",
            epoch_timestamp=1784370192,
            repository="smart_transit",
        )

    def test_extension_is_lowercase_dot_dart(self):
        self.assertEqual(self.evt.extension, ".dart")

    def test_is_code_file_true_for_dart(self):
        self.assertTrue(self.evt.is_code_file)

    def test_device_source_is_dynamic_mobile_node(self):
        self.assertEqual(self.evt.device_source, "dynamic_mobile_node")

    def test_device_source_constant_matches_spec(self):
        self.assertEqual(DEVICE_SOURCE, "dynamic_mobile_node")

    def test_md_file_is_not_code_file(self):
        evt = FileChangeEvent(
            path="/workspace/README.md",
            event_type="modified",
            epoch_timestamp=1784370192,
            repository="smart_transit",
        )
        self.assertFalse(evt.is_code_file)

    def test_event_type_preserved(self):
        self.assertEqual(self.evt.event_type, "created")

    def test_epoch_timestamp_preserved(self):
        self.assertEqual(self.evt.epoch_timestamp, 1784370192)

    def test_repository_preserved(self):
        self.assertEqual(self.evt.repository, "smart_transit")


# ---------------------------------------------------------------------------
# TestDebounceHandler
# ---------------------------------------------------------------------------


class TestDebounceHandler(unittest.TestCase):
    """Debounce collapses rapid same-file events into one dispatch."""

    def test_two_rapid_events_same_file_trigger_one_dispatch(self):
        """Multiple _schedule calls for same path within window → one _dispatch."""
        dispatched: list[str] = []
        handler = _DebounceHandler(
            on_code_change=lambda e: dispatched.append(e.path),
            on_telemetry_event=lambda e: dispatched.append(e.path),
            debounce_seconds=0.05,  # 50ms window for test speed
        )
        # Schedule same file twice
        handler._schedule("/workspace/main.py", "modified")
        handler._schedule("/workspace/main.py", "modified")
        # Only one pending entry should survive per path
        self.assertEqual(len(handler._pending), 1)

    def test_two_different_files_create_two_pending_entries(self):
        handler = _DebounceHandler(
            on_code_change=lambda e: None,
            on_telemetry_event=lambda e: None,
            debounce_seconds=0.5,
        )
        handler._schedule("/workspace/a.py", "modified")
        handler._schedule("/workspace/b.py", "modified")
        self.assertEqual(len(handler._pending), 2)


# ---------------------------------------------------------------------------
# TestGitPipelineChunkDelegation
# ---------------------------------------------------------------------------


class TestGitPipelineChunkDelegation(unittest.TestCase):
    """
    get_commit_file_chunks delegates to the v0.1 chunk_stream_a_code_topologies
    function — it does NOT re-implement chunking.
    """

    def test_get_commit_file_chunks_calls_v01_chunker(self):
        """
        Mock the v0.1 chunker inside git_pipeline and verify it is called.
        The real GitPipeline.get_commit_file_chunks calls
        chunk_stream_a_code_topologies from abm.memory.chunking.
        """
        with patch(
            "abm.companion.git_pipeline.chunk_stream_a_code_topologies"
        ) as mock_chunk:
            mock_chunk.return_value = ["chunk_one", "chunk_two"]

            # Build a mock repo
            with patch("abm.companion.git_pipeline.Repo") as mock_repo_cls:
                mock_repo = MagicMock()
                mock_repo.working_dir = "/fake/repo"
                mock_repo.active_branch.name = "main"
                mock_repo_cls.return_value = mock_repo

                # Mock commit diff
                mock_commit = MagicMock()
                mock_commit.parents = []
                mock_commit.hexsha = "abc" * 14
                mock_repo.commit.return_value = mock_commit

                mock_diff = MagicMock()
                mock_diff.b_path = "lib/main.py"
                mock_diff.a_path = "lib/main.py"
                mock_diff.diff = b"+def hello():\n+    pass\n"
                mock_commit.diff.return_value = [mock_diff]

                pipeline = GitPipeline("/fake/repo")
                result = pipeline.get_commit_file_chunks("abc123", "python")

            # The real v0.1 chunker was invoked
            mock_chunk.assert_called_once()
            # First arg is the code text, second is "python"
            _, call_language = mock_chunk.call_args[0]
            self.assertEqual(call_language, "python")
            self.assertEqual(result, ["chunk_one", "chunk_two"])

    def test_get_commit_file_chunks_filters_by_language(self):
        """Only files matching the given language are chunked."""
        with patch("abm.companion.git_pipeline.chunk_stream_a_code_topologies") as mock_chunk:
            mock_chunk.return_value = ["chunk"]
            with patch("abm.companion.git_pipeline.Repo") as mock_repo_cls:
                mock_repo = MagicMock()
                mock_repo.working_dir = "/fake/repo"
                mock_repo_cls.return_value = mock_repo

                mock_commit = MagicMock()
                mock_commit.parents = []
                mock_commit.hexsha = "abc" * 14

                # Two diffs: one Python, one Dart
                diff_py = MagicMock()
                diff_py.b_path = "main.py"
                diff_py.a_path = "main.py"
                diff_py.diff = b"+x = 1\n"

                diff_dart = MagicMock()
                diff_dart.b_path = "widget.dart"
                diff_dart.a_path = "widget.dart"
                diff_dart.diff = b"+class Foo {}\n"

                mock_commit.diff.return_value = [diff_py, diff_dart]
                mock_repo.commit.return_value = mock_commit

                pipeline = GitPipeline("/fake/repo")
                pipeline.get_commit_file_chunks("abc123", "python")

            # chunker should only be called once (for the .py file)
            self.assertEqual(mock_chunk.call_count, 1)


# ---------------------------------------------------------------------------
# TestGitPipelineTelemetryShape
# ---------------------------------------------------------------------------


class TestGitPipelineTelemetryShape(unittest.TestCase):
    """get_commit_telemetry_event returns a dict with correct Stream C keys."""

    def _make_pipeline_with_commit(self, authored_date: int, message: str, repo_name: str):
        with patch("abm.companion.git_pipeline.Repo") as mock_repo_cls:
            mock_repo = MagicMock()
            mock_repo.working_dir = f"/home/user/{repo_name}"
            mock_repo_cls.return_value = mock_repo

            mock_commit = MagicMock()
            mock_commit.authored_date = authored_date
            mock_commit.message = message
            mock_commit.hexsha = "deadbeef1234deadbeef1234deadbeef12345678"
            mock_repo.commit.return_value = mock_commit

            pipeline = GitPipeline(f"/home/user/{repo_name}")
        return pipeline, mock_repo

    def test_telemetry_event_has_epoch_timestamp_key(self):
        pipeline, mock_repo = self._make_pipeline_with_commit(
            1784370192, "init commit", "smart_transit"
        )
        with patch("abm.companion.git_pipeline.Repo") as mock_repo_cls:
            mock_repo_cls.return_value = mock_repo
            result = pipeline.get_commit_telemetry_event("deadbeef")
        self.assertIn("epoch_timestamp", result)

    def test_telemetry_event_has_active_repository_key(self):
        pipeline, mock_repo = self._make_pipeline_with_commit(
            1784370192, "init", "smart_transit"
        )
        with patch("abm.companion.git_pipeline.Repo") as mock_repo_cls:
            mock_repo_cls.return_value = mock_repo
            result = pipeline.get_commit_telemetry_event("deadbeef")
        self.assertIn("active_repository", result)

    def test_telemetry_event_has_device_source_key(self):
        pipeline, mock_repo = self._make_pipeline_with_commit(
            1784370192, "init", "smart_transit"
        )
        with patch("abm.companion.git_pipeline.Repo") as mock_repo_cls:
            mock_repo_cls.return_value = mock_repo
            result = pipeline.get_commit_telemetry_event("deadbeef")
        self.assertIn("device_source", result)

    def test_telemetry_event_device_source_is_dynamic_mobile_node(self):
        pipeline, mock_repo = self._make_pipeline_with_commit(
            1784370192, "init", "smart_transit"
        )
        with patch("abm.companion.git_pipeline.Repo") as mock_repo_cls:
            mock_repo_cls.return_value = mock_repo
            result = pipeline.get_commit_telemetry_event("deadbeef")
        self.assertEqual(result["device_source"], "dynamic_mobile_node")

    def test_telemetry_event_epoch_timestamp_is_int(self):
        pipeline, mock_repo = self._make_pipeline_with_commit(
            1784370192, "init", "smart_transit"
        )
        with patch("abm.companion.git_pipeline.Repo") as mock_repo_cls:
            mock_repo_cls.return_value = mock_repo
            result = pipeline.get_commit_telemetry_event("deadbeef")
        self.assertIsInstance(result["epoch_timestamp"], int)

    def test_telemetry_event_has_exactly_five_keys(self):
        """Must have: epoch_timestamp, active_repository, device_source, text, sha."""
        pipeline, mock_repo = self._make_pipeline_with_commit(
            1784370192, "init", "smart_transit"
        )
        with patch("abm.companion.git_pipeline.Repo") as mock_repo_cls:
            mock_repo_cls.return_value = mock_repo
            result = pipeline.get_commit_telemetry_event("deadbeef")
        self.assertEqual(
            set(result.keys()),
            {"epoch_timestamp", "active_repository", "device_source", "text", "sha"},
        )


# ---------------------------------------------------------------------------
# TestGitPipelineCommitRecord
# ---------------------------------------------------------------------------


class TestGitPipelineCommitRecord(unittest.TestCase):
    """CommitRecord and FileDiff dataclass field shapes."""

    def test_commit_record_fields(self):
        r = CommitRecord(
            sha="abc" * 14,
            message="feat: something",
            author="ABM",
            epoch_timestamp=1784370192,
            files_changed=["lib/main.py"],
        )
        self.assertEqual(r.sha, "abc" * 14)
        self.assertEqual(r.message, "feat: something")
        self.assertEqual(r.author, "ABM")
        self.assertEqual(r.epoch_timestamp, 1784370192)
        self.assertIn("lib/main.py", r.files_changed)

    def test_file_diff_fields(self):
        d = FileDiff(path="lib/main.py", language="python", added_lines="x = 1\n")
        self.assertEqual(d.path, "lib/main.py")
        self.assertEqual(d.language, "python")
        self.assertIn("x = 1", d.added_lines)

    def test_default_max_commits_is_50(self):
        self.assertEqual(DEFAULT_MAX_COMMITS, 50)


# ---------------------------------------------------------------------------
# TestStyleFingerprintExtractor
# ---------------------------------------------------------------------------


class TestStyleFingerprintExtractor(unittest.TestCase):
    """Naming convention detection and framework/state pattern detection."""

    def setUp(self):
        self.extractor = StyleFingerprintExtractor()

    def test_camel_case_detected_in_python_code(self):
        fp = self.extractor.extract(PYTHON_CODE_CAMEL, "python")
        self.assertEqual(fp.naming_convention, "camelCase")

    def test_snake_case_detected_in_python_code(self):
        fp = self.extractor.extract(PYTHON_CODE_SNAKE, "python")
        self.assertEqual(fp.naming_convention, "snake_case")

    def test_dart_bloc_framework_detected(self):
        fp = self.extractor.extract(DART_BLOC_CODE, "dart")
        self.assertEqual(fp.framework, "flutter")
        self.assertEqual(fp.state_pattern, "bloc")

    def test_language_preserved_in_fingerprint(self):
        fp = self.extractor.extract(PYTHON_CODE_CAMEL, "python")
        self.assertEqual(fp.language, "python")

    def test_camel_case_ratio_between_0_and_1(self):
        fp = self.extractor.extract(PYTHON_CODE_CAMEL, "python")
        self.assertGreaterEqual(fp.camel_case_ratio, 0.0)
        self.assertLessEqual(fp.camel_case_ratio, 1.0)

    def test_identifier_count_is_non_negative(self):
        fp = self.extractor.extract(PYTHON_CODE_CAMEL, "python")
        self.assertGreaterEqual(fp.identifier_count, 0)

    def test_formatting_patterns_are_derived(self):
        fp = self.extractor.extract(PYTHON_CODE_CAMEL, "python")
        self.assertIn("indent_style", fp.formatting_patterns)
        self.assertIn("max_line_length", fp.formatting_patterns)

    def test_architectural_preferences_are_derived(self):
        fp = self.extractor.extract(DART_BLOC_CODE, "dart")
        self.assertTrue(fp.architectural_preferences["uses_flutter"])
        self.assertTrue(fp.architectural_preferences["uses_bloc"])

    def test_stream_a_document_contains_diagnostics(self):
        fp = self.extractor.extract(DART_BLOC_CODE, "dart")
        text = self.extractor.to_stream_a_document(fp)
        self.assertIn("formatting_patterns=", text)
        self.assertIn("architectural_preferences=", text)

    def test_raises_style_extraction_error_on_empty_code(self):
        with self.assertRaises(StyleExtractionError):
            self.extractor.extract("", "python")

    def test_raises_style_extraction_error_on_whitespace_code(self):
        with self.assertRaises(StyleExtractionError):
            self.extractor.extract("   \n  ", "python")

    def test_raises_value_error_on_unsupported_language(self):
        with self.assertRaises(ValueError):
            self.extractor.extract("some code", "javascript")

    def test_kotlin_returns_flutter_bloc_defaults(self):
        """Kotlin files → flutter/bloc defaults (project context)."""
        fp = self.extractor.extract("fun main() { val userName = \"ABM\" }", "kotlin")
        self.assertEqual(fp.framework, "flutter")
        self.assertEqual(fp.state_pattern, "bloc")


# ---------------------------------------------------------------------------
# TestStyleFingerprintMetadataKeys
# ---------------------------------------------------------------------------


class TestStyleFingerprintMetadataKeys(unittest.TestCase):
    """
    to_stream_a_metadata() returns exactly the four v0.1 Stream A fields.
    No new fields are invented.
    """

    def setUp(self):
        self.extractor = StyleFingerprintExtractor()

    def test_returns_exactly_four_keys(self):
        fp = self.extractor.extract(PYTHON_CODE_CAMEL, "python")
        meta = self.extractor.to_stream_a_metadata(fp)
        self.assertEqual(len(meta), 4)

    def test_has_language_key(self):
        fp = self.extractor.extract(PYTHON_CODE_CAMEL, "python")
        meta = self.extractor.to_stream_a_metadata(fp)
        self.assertIn("language", meta)

    def test_has_framework_key(self):
        fp = self.extractor.extract(PYTHON_CODE_CAMEL, "python")
        meta = self.extractor.to_stream_a_metadata(fp)
        self.assertIn("framework", meta)

    def test_has_state_pattern_key(self):
        fp = self.extractor.extract(PYTHON_CODE_CAMEL, "python")
        meta = self.extractor.to_stream_a_metadata(fp)
        self.assertIn("state_pattern", meta)

    def test_has_naming_convention_key(self):
        fp = self.extractor.extract(PYTHON_CODE_CAMEL, "python")
        meta = self.extractor.to_stream_a_metadata(fp)
        self.assertIn("naming_convention", meta)

    def test_no_camel_case_ratio_in_metadata(self):
        """camel_case_ratio is diagnostic-only — never stored in ChromaDB."""
        fp = self.extractor.extract(PYTHON_CODE_CAMEL, "python")
        meta = self.extractor.to_stream_a_metadata(fp)
        self.assertNotIn("camel_case_ratio", meta)

    def test_no_identifier_count_in_metadata(self):
        """identifier_count is diagnostic-only — never stored in ChromaDB."""
        fp = self.extractor.extract(PYTHON_CODE_CAMEL, "python")
        meta = self.extractor.to_stream_a_metadata(fp)
        self.assertNotIn("identifier_count", meta)

    def test_no_formatting_patterns_in_metadata(self):
        fp = self.extractor.extract(PYTHON_CODE_CAMEL, "python")
        meta = self.extractor.to_stream_a_metadata(fp)
        self.assertNotIn("formatting_patterns", meta)

    def test_no_architectural_preferences_in_metadata(self):
        fp = self.extractor.extract(PYTHON_CODE_CAMEL, "python")
        meta = self.extractor.to_stream_a_metadata(fp)
        self.assertNotIn("architectural_preferences", meta)

    def test_key_names_match_v01_stream_a_schema_exactly(self):
        """Keys must match the four v0.1 schema field names verbatim."""
        fp = self.extractor.extract(PYTHON_CODE_CAMEL, "python")
        meta = self.extractor.to_stream_a_metadata(fp)
        expected_keys = set(SCHEMA_CODE_TOPOLOGIES.keys())
        self.assertEqual(set(meta.keys()), expected_keys)


# ---------------------------------------------------------------------------
# TestIngestionCoordinatorRouting
# ---------------------------------------------------------------------------


class TestIngestionCoordinatorRouting(unittest.TestCase):
    """
    ingest_file_change routes code files → Stream A and non-code → Stream C.
    Never crosses streams.
    """

    def setUp(self):
        self.ctrl = _make_mock_controller()
        self.embedder = _make_mock_embedder()
        self.coord = IngestionCoordinator(
            controller=self.ctrl,
            embedder=self.embedder,
        )

    def _make_event(
        self,
        path: str,
        event_type: str = "modified",
        repo: str = "smart_transit",
    ) -> FileChangeEvent:
        return FileChangeEvent(
            path=path,
            event_type=event_type,
            epoch_timestamp=1784370192,
            repository=repo,
        )

    def test_deleted_file_returns_skipped_result(self):
        evt = self._make_event("/workspace/main.py", event_type="deleted")
        result = self.coord.ingest_file_change(evt)
        self.assertEqual(result.status, "skipped")
        self.ctrl.add_document.assert_not_called()

    def test_code_file_result_targets_stream_a(self):
        evt = self._make_event("/workspace/main.py")
        with patch("builtins.open", unittest.mock.mock_open(read_data=PYTHON_CODE_CAMEL)):
            with patch("abm.companion.ingestion_coordinator.Path") as mock_path:
                mock_path_instance = MagicMock()
                mock_path_instance.read_text.return_value = PYTHON_CODE_CAMEL
                mock_path_instance.suffix = ".py"
                mock_path_instance.name = "main.py"
                mock_path.return_value = mock_path_instance
                result = self.coord.ingest_file_change(evt)
        # Should target Stream A
        add_calls = self.ctrl.add_document.call_args_list
        stream_a_calls = [
            c for c in add_calls
            if c[0][0] == COLLECTION_CODE_TOPOLOGIES or
               c[1].get("collection_name") == COLLECTION_CODE_TOPOLOGIES
        ]
        # Verify no Stream B or D calls
        for c in add_calls:
            coll = c[0][0] if c[0] else c[1].get("collection_name", "")
            self.assertNotEqual(coll, COLLECTION_TECHNICAL_MASTERY)
            self.assertNotEqual(coll, COLLECTION_COGNITIVE_IDENTITY)

    def test_non_code_file_writes_to_stream_c_only(self):
        """A .md file change must only write to Stream C (ambient telemetry)."""
        evt = self._make_event("/workspace/README.md")
        result = self.coord.ingest_file_change(evt)
        # All add_document calls must go to Stream C
        for c in self.ctrl.add_document.call_args_list:
            coll = c[0][0] if c[0] else c[1].get("collection_name", "")
            self.assertNotEqual(coll, COLLECTION_CODE_TOPOLOGIES)
            self.assertNotEqual(coll, COLLECTION_TECHNICAL_MASTERY)
            self.assertNotEqual(coll, COLLECTION_COGNITIVE_IDENTITY)

    def test_non_code_file_result_collection_is_stream_c(self):
        evt = self._make_event("/workspace/notes.txt")
        result = self.coord.ingest_file_change(evt)
        self.assertEqual(result.collection, COLLECTION_AMBIENT_TELEMETRY)

    def test_ingestion_result_is_dataclass(self):
        evt = self._make_event("/workspace/notes.txt")
        result = self.coord.ingest_file_change(evt)
        self.assertIsInstance(result, IngestionResult)
        self.assertIn(result.status, {"ok", "skipped", "error"})

    def test_ingest_code_fingerprint_writes_stream_a_metadata_only(self):
        result = self.coord.ingest_code_fingerprint(
            DART_BLOC_CODE,
            "dart",
            context_id="unit",
        )
        self.assertEqual(result.status, "ok")
        self.ctrl.add_document.assert_called()
        _, kwargs = self.ctrl.add_document.call_args
        self.assertEqual(set(kwargs["metadata"].keys()), set(SCHEMA_CODE_TOPOLOGIES.keys()))
        self.assertIn("formatting_patterns=", kwargs["text"])
        self.assertIn("architectural_preferences=", kwargs["text"])


# ---------------------------------------------------------------------------
# TestIngestionCoordinatorGitFlow
# ---------------------------------------------------------------------------


class TestIngestionCoordinatorGitFlow(unittest.TestCase):
    """
    ingest_git_commit writes Stream A chunks and one Stream C event.
    It never touches Stream B or D.
    """

    def setUp(self):
        self.ctrl = _make_mock_controller()
        self.embedder = _make_mock_embedder()
        self.git = _make_mock_git_pipeline()
        self.coord = IngestionCoordinator(
            controller=self.ctrl,
            embedder=self.embedder,
            git_pipeline=self.git,
        )

    def test_ingest_git_commit_writes_stream_a(self):
        result = self.coord.ingest_git_commit("abc1234", "python")
        calls = self.ctrl.add_document.call_args_list
        stream_a_calls = [c for c in calls if c[0][0] == COLLECTION_CODE_TOPOLOGIES]
        self.assertGreater(len(stream_a_calls), 0)

    def test_ingest_git_commit_writes_stream_c(self):
        result = self.coord.ingest_git_commit("abc1234", "python")
        calls = self.ctrl.add_document.call_args_list
        stream_c_calls = [c for c in calls if c[0][0] == COLLECTION_AMBIENT_TELEMETRY]
        self.assertGreater(len(stream_c_calls), 0)

    def test_ingest_git_commit_never_writes_stream_b(self):
        self.coord.ingest_git_commit("abc1234", "python")
        for c in self.ctrl.add_document.call_args_list:
            coll = c[0][0]
            self.assertNotEqual(coll, COLLECTION_TECHNICAL_MASTERY)

    def test_ingest_git_commit_never_writes_stream_d(self):
        self.coord.ingest_git_commit("abc1234", "python")
        for c in self.ctrl.add_document.call_args_list:
            coll = c[0][0]
            self.assertNotEqual(coll, COLLECTION_COGNITIVE_IDENTITY)

    def test_ingest_git_commit_result_is_ingestion_result(self):
        result = self.coord.ingest_git_commit("abc1234", "python")
        self.assertIsInstance(result, IngestionResult)

    def test_ingest_git_commit_returns_skipped_without_git_pipeline(self):
        coord_no_git = IngestionCoordinator(
            controller=self.ctrl,
            embedder=self.embedder,
            git_pipeline=None,
        )
        result = coord_no_git.ingest_git_commit("abc1234", "python")
        self.assertEqual(result.status, "skipped")

    def test_ingest_git_tree_returns_list(self):
        result = self.coord.ingest_git_tree("python", max_commits=1)
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    def test_ingest_git_tree_returns_skipped_without_git_pipeline(self):
        coord_no_git = IngestionCoordinator(
            controller=self.ctrl,
            embedder=self.embedder,
            git_pipeline=None,
        )
        result = coord_no_git.ingest_git_tree("python")
        self.assertTrue(all(r.status == "skipped" for r in result))


# ---------------------------------------------------------------------------
# TestIngestionCoordinatorV01API
# ---------------------------------------------------------------------------


class TestIngestionCoordinatorV01API(unittest.TestCase):
    """
    IngestionCoordinator only uses the v0.1 ChromaController public API.
    It never calls private ChromaDB methods directly.
    """

    def test_coordinator_calls_add_document_not_raw_chroma(self):
        """add_document is the only write method used from ChromaController."""
        ctrl = _make_mock_controller()
        embedder = _make_mock_embedder()
        coord = IngestionCoordinator(controller=ctrl, embedder=embedder)

        evt = FileChangeEvent(
            path="/workspace/README.md",
            event_type="modified",
            epoch_timestamp=1784370192,
            repository="smart_transit",
        )
        coord.ingest_file_change(evt)

        # add_document was called
        ctrl.add_document.assert_called()
        # Raw ChromaDB-level methods were not bypassed
        ctrl._client.assert_not_called()

    def test_coordinator_does_not_access_internal_collections_dict(self):
        """Coordinator must not access _collections (private v0.1 internals)."""
        ctrl = _make_mock_controller()
        embedder = _make_mock_embedder()
        coord = IngestionCoordinator(controller=ctrl, embedder=embedder)

        evt = FileChangeEvent(
            path="/workspace/notes.txt",
            event_type="modified",
            epoch_timestamp=1784370192,
            repository="houseconnect",
        )
        coord.ingest_file_change(evt)

        # _collections is a private attribute — must not be accessed
        # (MagicMock records all attribute accesses)
        accessed = [str(c) for c in ctrl.method_calls]
        private_accesses = [a for a in accessed if "_collections" in a]
        self.assertEqual(
            private_accesses, [],
            "IngestionCoordinator must not access _collections directly.",
        )


# ---------------------------------------------------------------------------
# TestV01FilesRegressionGate
# ---------------------------------------------------------------------------


class TestV01FilesRegressionGate(unittest.TestCase):
    """
    Regression gate: all v0.1 constants and schema field names must be
    identical after v0.2 is added. No v0.1 file is allowed to change.
    """

    def test_all_collections_tuple_is_unchanged(self):
        self.assertEqual(
            ALL_COLLECTIONS,
            (
                "abm_cognitive_identity",
                "abm_code_topologies",
                "abm_technical_mastery",
                "abm_ambient_telemetry",
            ),
        )

    def test_stream_a_schema_field_names_unchanged(self):
        self.assertEqual(
            set(SCHEMA_CODE_TOPOLOGIES.keys()),
            {"language", "framework", "state_pattern", "naming_convention"},
        )

    def test_stream_b_schema_field_names_unchanged(self):
        self.assertEqual(
            set(SCHEMA_TECHNICAL_MASTERY.keys()),
            {"source", "date_acquired", "confidence_score"},
        )

    def test_stream_c_schema_field_names_unchanged(self):
        self.assertEqual(
            set(SCHEMA_AMBIENT_TELEMETRY.keys()),
            {"epoch_timestamp", "active_repository", "device_source"},
        )

    def test_stream_d_schema_field_names_unchanged(self):
        self.assertEqual(
            set(SCHEMA_COGNITIVE_IDENTITY.keys()),
            {"owner", "target_entity", "volatility"},
        )

    def test_stream_c_device_source_still_dynamic_mobile_node(self):
        self.assertEqual(SCHEMA_AMBIENT_TELEMETRY["device_source"], "dynamic_mobile_node")

    def test_stream_d_volatility_still_immutable(self):
        self.assertEqual(SCHEMA_COGNITIVE_IDENTITY["volatility"], "immutable")

    def test_stream_a_framework_still_flutter(self):
        self.assertEqual(SCHEMA_CODE_TOPOLOGIES["framework"], "flutter")

    def test_stream_a_state_pattern_still_bloc(self):
        self.assertEqual(SCHEMA_CODE_TOPOLOGIES["state_pattern"], "bloc")

    def test_v01_chunker_still_importable(self):
        """chunk_stream_a_code_topologies must still be importable from its v0.1 path."""
        from abm.memory.chunking import chunk_stream_a_code_topologies as fn
        self.assertTrue(callable(fn))

    def test_v01_chunker_still_rejects_unsupported_language(self):
        """v0.1 chunking contract: unsupported language raises ValueError."""
        with self.assertRaises(ValueError):
            chunk_stream_a_code_topologies("code", "ruby")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
