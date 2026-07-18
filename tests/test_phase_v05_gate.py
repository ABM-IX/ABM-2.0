"""
tests/test_phase_v05_gate.py
=============================
Phase v0.5 Gate Tests — FirstMinds Strategic Wing
Spec Reference: ABM_SPEC.md section 10 (item 5)

Hard gate proofs (must be 100% green before Phase v1.0):
  1. TestDecisionJournalStreamDSchemaGate — journal entries validate against
     the existing Stream D schema with no new fields
  2. TestWorkflowMonitorReadOnlyGate — monitor never calls write methods on
     the orchestrator or sandbox
  3. TestAnalyzerDecisionSeparationGate — strategic asset analyzer never
     writes a decision journal entry; analysis and decision-recording stay
     separated

Supporting contract tests cover journal embedding, monitor lifecycle, and
prior-phase regression. Phase v0.5 does NOT advance to v1.0 until this file
is green.
"""

from __future__ import annotations

import inspect
import os
import shutil
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# ---------------------------------------------------------------------------
# Past phases imports (must remain unchanged)
# ---------------------------------------------------------------------------
from abm.companion.file_watcher import CODE_EXTENSIONS
from abm.memory.chroma_controller import (
    ALL_COLLECTIONS,
    COLLECTION_AMBIENT_TELEMETRY,
    COLLECTION_CODE_TOPOLOGIES,
    COLLECTION_COGNITIVE_IDENTITY,
    COLLECTION_TECHNICAL_MASTERY,
    SCHEMA_COGNITIVE_IDENTITY,
    QueryResult,
)
from abm.memory.metadata_models import CognitiveIdentityMetadata
from abm.orchestrator.departments import Department
from abm.orchestrator.task_contract import TaskContract
from abm.sandbox.models import ExecutionResult, GateResult

# ---------------------------------------------------------------------------
# v0.5 imports
# ---------------------------------------------------------------------------
from abm.strategic_wing.decision_journal import DecisionJournal
from abm.strategic_wing.strategic_asset_analyzer import (
    StrategicAnalysisResult,
    StrategicAssetAnalyzer,
    StrategicContextItem,
    StrategicOption,
)
from abm.strategic_wing.workflow_monitor import TaskState, WorkflowMonitor
import abm.strategic_wing.decision_journal as decision_journal_module
import abm.strategic_wing.workflow_monitor as workflow_monitor_module
import abm.strategic_wing.strategic_asset_analyzer as strategic_asset_analyzer_module

_TEST_QUARANTINE_DIR = "tests/temp_quarantine_v05"

STREAM_D_KEYS = {"owner", "target_entity", "volatility"}


# ---------------------------------------------------------------------------
# HARD GATE 1 — Stream D schema validation, no new fields
# ---------------------------------------------------------------------------


class TestDecisionJournalStreamDSchemaGate(unittest.TestCase):
    """
    Prove decision journal entries validate against the existing Stream D
    schema with no new fields.
    """

    def setUp(self) -> None:
        self.mock_controller = MagicMock()
        self.mock_embedder = MagicMock()
        self.mock_embedder.embed.return_value = [0.1, 0.2, 0.3]
        self.journal = DecisionJournal(
            controller=self.mock_controller, embedder=self.mock_embedder
        )

    def test_metadata_matches_schema_cognitive_identity_exactly(self):
        self.journal.log_decision("Adopt local-first CRM boundary", "Protect privacy", epoch=1784370192)
        kwargs = self.mock_controller.add_document.call_args.kwargs
        self.assertEqual(kwargs["metadata"], dict(SCHEMA_COGNITIVE_IDENTITY))
        self.assertEqual(set(kwargs["metadata"].keys()), STREAM_D_KEYS)
        self.assertEqual(len(kwargs["metadata"]), 3)

    def test_metadata_validates_via_cognitive_identity_pydantic_model(self):
        self.journal.log_decision("Defer mobile node", "Stabilize core memory first", epoch=1)
        meta = self.mock_controller.add_document.call_args.kwargs["metadata"]
        validated = CognitiveIdentityMetadata(**meta)
        self.assertEqual(validated.owner, "ABM")
        self.assertEqual(validated.target_entity, "FirstMinds")
        self.assertEqual(validated.volatility, "immutable")

    def test_metadata_contains_no_decision_specific_extra_fields(self):
        self.journal.log_decision("Ship Smart Transit MVP", "Cashflow priority", epoch=42)
        meta = self.mock_controller.add_document.call_args.kwargs["metadata"]
        forbidden = {
            "what_decided",
            "why_decided",
            "decision",
            "reasoning",
            "epoch",
            "timestamp",
            "confidence_score",
            "department",
            "contract_id",
        }
        for key in forbidden:
            with self.subTest(key=key):
                self.assertNotIn(key, meta)

    def test_decision_payload_lives_in_text_not_metadata(self):
        self.journal.log_decision(
            "Prefer Flutter BLoC for HouseConnect",
            "Matches Stream A engineering DNA",
            epoch=99,
        )
        kwargs = self.mock_controller.add_document.call_args.kwargs
        self.assertIn("DECISION: Prefer Flutter BLoC for HouseConnect", kwargs["text"])
        self.assertIn("REASONING: Matches Stream A engineering DNA", kwargs["text"])
        self.assertNotIn("Prefer Flutter BLoC", str(kwargs["metadata"]))

    def test_writes_only_to_stream_d(self):
        self.journal.log_decision("Keep ABM above consumer OS", "Corporate boundary", epoch=7)
        kwargs = self.mock_controller.add_document.call_args.kwargs
        self.assertEqual(kwargs["collection_name"], COLLECTION_COGNITIVE_IDENTITY)

    def test_journal_uses_schema_constant_not_ad_hoc_dict(self):
        source = inspect.getsource(decision_journal_module)
        self.assertIn("SCHEMA_COGNITIVE_IDENTITY", source)
        self.assertIn("COLLECTION_COGNITIVE_IDENTITY", source)


# ---------------------------------------------------------------------------
# HARD GATE 2 — workflow monitor is strictly read-only vs orchestrator/sandbox
# ---------------------------------------------------------------------------


class TestWorkflowMonitorReadOnlyGate(unittest.TestCase):
    """
    Prove the workflow monitor never calls any write method on the
    orchestrator or sandbox — it only aggregates state pushed by callers
    and reads the quarantine directory.
    """

    ORCHESTRATOR_WRITE_TOKENS = (
        "ClassificationRouter",
        "classify(",
        "OllamaModelGateway",
        "WorkerTaskHandoff",
        "WorkerResultReport.build",
        "TaskContract.build",
    )
    SANDBOX_WRITE_TOKENS = (
        "DockerSandbox",
        "SandboxCheckLoop",
        "MultiFactorGate",
        "evaluate_code",
        "execute_command",
        "write_file",
        "add_document",
        "containers.run",
    )

    def setUp(self) -> None:
        self.monitor = WorkflowMonitor(quarantine_dir=_TEST_QUARANTINE_DIR)
        os.makedirs(_TEST_QUARANTINE_DIR, exist_ok=True)
        self.contract = TaskContract.build(
            objective="monitor gate task",
            department=Department.STRATEGIC_PLANNING,
            assigned_agents=["planning_engine"],
            autonomy_permission_level=1,
            hard_success_conditions=["proposal_document_generated == true"],
            epoch=1784370192,
        )

    def tearDown(self) -> None:
        if os.path.exists(_TEST_QUARANTINE_DIR):
            shutil.rmtree(_TEST_QUARANTINE_DIR)

    def test_monitor_module_does_not_import_orchestrator_or_sandbox_writers(self):
        source = inspect.getsource(workflow_monitor_module)
        # Allowed: TaskContract, ExecutionResult, GateResult as data types only
        self.assertIn("TaskContract", source)
        self.assertIn("ExecutionResult", source)
        self.assertIn("GateResult", source)
        for token in self.ORCHESTRATOR_WRITE_TOKENS + self.SANDBOX_WRITE_TOKENS:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_monitor_holds_no_orchestrator_or_sandbox_references(self):
        for attr in (
            "_router",
            "_gateway",
            "_sandbox",
            "_gate",
            "_controller",
            "_embedder",
            "router",
            "sandbox",
            "gate",
        ):
            with self.subTest(attr=attr):
                self.assertFalse(hasattr(self.monitor, attr))

    def test_lifecycle_updates_never_touch_orchestrator_or_sandbox_mocks(self):
        router = MagicMock()
        sandbox = MagicMock()
        gate = MagicMock()

        self.monitor.register_routed_task(self.contract)
        self.monitor.mark_in_sandbox(self.contract.contract_id)
        self.monitor.record_execution(
            self.contract.contract_id,
            ExecutionResult(exit_code=0, stdout="ok", stderr="", execution_time_ms=5),
        )
        self.monitor.record_gate_result(
            self.contract.contract_id,
            GateResult(passed=True, confidence_score=0.91, reason="ok"),
        )
        _ = self.monitor.get_overview_report()

        router.classify.assert_not_called()
        router.assert_not_called()
        sandbox.execute_command.assert_not_called()
        sandbox.write_file.assert_not_called()
        sandbox.evaluate_code.assert_not_called()
        gate.evaluate.assert_not_called()
        gate.calculate_confidence_score.assert_not_called()

    def test_scan_quarantine_is_disk_read_only_not_sandbox_write(self):
        path = os.path.join(
            _TEST_QUARANTINE_DIR, f"quarantine_{self.contract.contract_id}_stamp.txt"
        )
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("quarantined")

        with patch("abm.strategic_wing.workflow_monitor.os.listdir", wraps=os.listdir) as listed:
            found = self.monitor.scan_quarantine_directory()
            listed.assert_called()

        self.assertIn(self.contract.contract_id, found)
        # No Docker / gate write APIs involved
        self.assertNotIn("DockerSandbox", inspect.getsource(WorkflowMonitor.scan_quarantine_directory))


# ---------------------------------------------------------------------------
# HARD GATE 3 — analyzer never writes decision journal entries
# ---------------------------------------------------------------------------


class TestAnalyzerDecisionSeparationGate(unittest.TestCase):
    """
    Prove the strategic asset analyzer never writes a decision journal entry
    on its own — analysis and decision-recording stay separated.
    """

    def setUp(self) -> None:
        self.mock_controller = MagicMock()
        self.mock_embedder = MagicMock()
        self.mock_embedder.embed.return_value = [0.1, 0.2, 0.3]
        self.analyzer = StrategicAssetAnalyzer(
            controller=self.mock_controller,
            embedder=self.mock_embedder,
        )
        self.mock_controller.query_collection.return_value = QueryResult(
            collection_name=COLLECTION_COGNITIVE_IDENTITY,
            ids=[["D1"]],
            documents=[["FirstMinds stays above consumer CRM."]],
            metadatas=[[{"owner": "ABM", "target_entity": "FirstMinds", "volatility": "immutable"}]],
            distances=[[0.1]],
        )

    def test_analyze_sets_decision_recorded_false(self):
        result = self.analyzer.analyze("Should FirstMinds build a consumer CRM?")
        self.assertIsInstance(result, StrategicAnalysisResult)
        self.assertFalse(result.decision_recorded)

    def test_analyzer_never_calls_add_document(self):
        self.analyzer.analyze("Map architecture options for HouseConnect")
        self.mock_controller.add_document.assert_not_called()
        self.mock_controller.query_collection.assert_called()

    def test_analyzer_module_does_not_import_or_call_decision_journal(self):
        import ast

        source = inspect.getsource(strategic_asset_analyzer_module)
        tree = ast.parse(source)

        imported_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imported_names.add(alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported_names.add(alias.name.split(".")[-1])

        self.assertNotIn("DecisionJournal", imported_names)
        self.assertNotIn("decision_journal", imported_names)

        call_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute):
                    call_names.add(func.attr)
                elif isinstance(func, ast.Name):
                    call_names.add(func.id)

        self.assertNotIn("add_document", call_names)
        self.assertNotIn("log_decision", call_names)
        self.assertNotIn("DecisionJournal", call_names)

    def test_analyzer_does_not_accept_journal_dependency(self):
        sig = inspect.signature(StrategicAssetAnalyzer.__init__)
        param_names = set(sig.parameters.keys())
        self.assertNotIn("journal", param_names)
        self.assertNotIn("decision_journal", param_names)

    def test_analysis_and_recording_remain_separate_call_sites(self):
        """
        Analyzer returns options; only an explicit DecisionJournal.log_decision
        call writes Stream D — proving separation of concerns.
        """
        journal_controller = MagicMock()
        journal_embedder = MagicMock()
        journal_embedder.embed.return_value = [0.9, 0.8, 0.7]
        journal = DecisionJournal(journal_controller, journal_embedder)

        analysis = self.analyzer.analyze("Pick a FirstMinds product boundary")
        self.assertFalse(analysis.decision_recorded)
        self.mock_controller.add_document.assert_not_called()
        journal_controller.add_document.assert_not_called()

        # Recording is a separate, deliberate step
        doc_id = journal.log_decision(
            what_decided="Keep consumer CRM out of ABM 2.0",
            why_decided=analysis.options[0].rationale,
            epoch=1784370192,
        )
        self.assertTrue(doc_id.startswith("DECISION_"))
        journal_controller.add_document.assert_called_once()
        # Analyzer's controller still never wrote
        self.mock_controller.add_document.assert_not_called()

    def test_public_api_exposes_no_log_or_write_methods(self):
        public = {
            name
            for name, _ in inspect.getmembers(self.analyzer, predicate=inspect.ismethod)
            if not name.startswith("_")
        }
        self.assertEqual(public, {"analyze", "retrieve_context", "map_options"})
        for banned in ("log_decision", "write", "persist", "record_decision", "commit"):
            with self.subTest(method=banned):
                self.assertNotIn(banned, public)


# ---------------------------------------------------------------------------
# Supporting: DecisionJournal embedding behaviour
# ---------------------------------------------------------------------------


class TestDecisionJournal(unittest.TestCase):
    """DecisionJournal embeds and writes to Stream D."""

    def setUp(self):
        self.mock_controller = MagicMock()
        self.mock_embedder = MagicMock()
        self.mock_embedder.embed.return_value = [0.1, 0.2, 0.3]
        self.journal = DecisionJournal(
            controller=self.mock_controller, embedder=self.mock_embedder
        )

    def test_log_decision_generates_id_and_embeds(self):
        doc_id = self.journal.log_decision("Migrate to Cloud", "Cheaper")
        self.assertTrue(doc_id.startswith("DECISION_"))
        self.mock_embedder.embed.assert_called_once()
        text_arg = self.mock_embedder.embed.call_args[0][0]
        self.assertIn("Migrate to Cloud", text_arg)
        self.assertIn("Cheaper", text_arg)

    def test_log_decision_writes_to_stream_d_with_exact_metadata(self):
        self.journal.log_decision("Test", "Reason", epoch=123456)
        self.mock_controller.add_document.assert_called_once()
        kwargs = self.mock_controller.add_document.call_args.kwargs
        self.assertEqual(kwargs["collection_name"], COLLECTION_COGNITIVE_IDENTITY)
        self.assertEqual(
            kwargs["metadata"],
            {"owner": "ABM", "target_entity": "FirstMinds", "volatility": "immutable"},
        )
        self.assertIn("TIMESTAMP: 123456", kwargs["text"])
        self.assertEqual(kwargs["embedding"], [0.1, 0.2, 0.3])


# ---------------------------------------------------------------------------
# Supporting: WorkflowMonitor lifecycle
# ---------------------------------------------------------------------------


class TestWorkflowMonitor(unittest.TestCase):
    """WorkflowMonitor aggregations."""

    def setUp(self):
        self.monitor = WorkflowMonitor(quarantine_dir=_TEST_QUARANTINE_DIR)
        os.makedirs(_TEST_QUARANTINE_DIR, exist_ok=True)
        self.contract = TaskContract.build(
            objective="test task",
            department=Department.SOFTWARE_ENGINEERING,
            assigned_agents=["a"],
            autonomy_permission_level=2,
            hard_success_conditions=["success == true"],
        )

    def tearDown(self):
        if os.path.exists(_TEST_QUARANTINE_DIR):
            shutil.rmtree(_TEST_QUARANTINE_DIR)

    def test_task_lifecycle_happy_path(self):
        c_id = self.contract.contract_id
        self.monitor.register_routed_task(self.contract)
        self.assertEqual(self.monitor._registry[c_id].state, TaskState.ROUTED)
        self.monitor.mark_in_sandbox(c_id)
        self.assertEqual(self.monitor._registry[c_id].state, TaskState.IN_SANDBOX)
        exec_res = ExecutionResult(exit_code=0, stdout="", stderr="", execution_time_ms=10)
        self.monitor.record_execution(c_id, exec_res)
        self.assertEqual(self.monitor._registry[c_id].state, TaskState.EXECUTED)
        gate_res = GateResult(passed=True, confidence_score=0.9, reason="ok")
        self.monitor.record_gate_result(c_id, gate_res)
        self.assertEqual(self.monitor._registry[c_id].state, TaskState.PASSED)

    def test_task_lifecycle_quarantine_path(self):
        c_id = self.contract.contract_id
        self.monitor.register_routed_task(self.contract)
        gate_res = GateResult(passed=False, confidence_score=0.5, reason="failed")
        self.monitor.record_gate_result(c_id, gate_res)
        self.assertEqual(self.monitor._registry[c_id].state, TaskState.QUARANTINED)

    def test_scan_quarantine_directory(self):
        c_id = self.contract.contract_id
        self.monitor.register_routed_task(self.contract)
        file_path = os.path.join(_TEST_QUARANTINE_DIR, f"quarantine_{c_id}_123.txt")
        with open(file_path, "w", encoding="utf-8") as handle:
            handle.write("test")
        found = self.monitor.scan_quarantine_directory()
        self.assertIn(c_id, found)
        self.assertEqual(self.monitor._registry[c_id].state, TaskState.QUARANTINED)

    def test_get_overview_report(self):
        self.monitor.register_routed_task(self.contract)
        report = self.monitor.get_overview_report()
        self.assertIn("=== FIRSTMINDS WORKFLOW OVERVIEW ===", report)
        self.assertIn(self.contract.contract_id, report)
        self.assertIn("test task", report)
        self.assertIn("ROUTED", report)


# ---------------------------------------------------------------------------
# Supporting: StrategicAssetAnalyzer behaviour
# ---------------------------------------------------------------------------


class TestStrategicAssetAnalyzer(unittest.TestCase):
    """StrategicAssetAnalyzer is read-only and returns option maps."""

    def setUp(self):
        self.mock_controller = MagicMock()
        self.mock_embedder = MagicMock()
        self.mock_embedder.embed.return_value = [0.1, 0.2, 0.3]
        self.analyzer = StrategicAssetAnalyzer(
            controller=self.mock_controller,
            embedder=self.mock_embedder,
        )

    def _query_result(self, collection_name, doc_id, document, metadata, distance):
        return QueryResult(
            collection_name=collection_name,
            ids=[[doc_id]],
            documents=[[document]],
            metadatas=[[metadata]],
            distances=[[distance]],
        )

    def test_analyze_retrieves_all_memory_streams(self):
        results = {
            COLLECTION_COGNITIVE_IDENTITY: self._query_result(
                COLLECTION_COGNITIVE_IDENTITY,
                "D1",
                "FirstMinds prioritizes lean MVPs",
                {"owner": "ABM", "target_entity": "FirstMinds", "volatility": "immutable"},
                0.1,
            ),
            COLLECTION_CODE_TOPOLOGIES: self._query_result(
                COLLECTION_CODE_TOPOLOGIES,
                "A1",
                "Flutter BLoC architecture preference",
                {
                    "language": "dart",
                    "framework": "flutter",
                    "state_pattern": "bloc",
                    "naming_convention": "camelCase",
                },
                0.2,
            ),
            COLLECTION_TECHNICAL_MASTERY: self._query_result(
                COLLECTION_TECHNICAL_MASTERY,
                "B1",
                "Validated API reference",
                {
                    "source": "docs_fetch",
                    "date_acquired": "2026-07-18",
                    "confidence_score": "0.92",
                },
                0.3,
            ),
            COLLECTION_AMBIENT_TELEMETRY: self._query_result(
                COLLECTION_AMBIENT_TELEMETRY,
                "C1",
                "Current task load",
                {
                    "epoch_timestamp": 1784370192,
                    "active_repository": "smart_transit",
                    "device_source": "dynamic_mobile_node",
                },
                0.4,
            ),
        }
        self.mock_controller.query_collection.side_effect = (
            lambda collection_name, query_embedding, n_results: results[collection_name]
        )

        result = self.analyzer.analyze(
            "Where should FirstMinds take product architecture next?"
        )

        self.assertIsInstance(result, StrategicAnalysisResult)
        self.assertFalse(result.decision_recorded)
        self.assertEqual(self.mock_embedder.embed.call_args[0][0], result.query)
        self.assertEqual(self.mock_controller.query_collection.call_count, 4)
        queried_collections = {
            call_args.kwargs["collection_name"]
            for call_args in self.mock_controller.query_collection.call_args_list
        }
        self.assertEqual(queried_collections, set(ALL_COLLECTIONS))
        self.assertEqual(len(result.context_items), 4)
        self.assertGreaterEqual(len(result.options), 4)

    def test_analyzer_never_writes_or_logs_decisions(self):
        self.mock_controller.query_collection.return_value = QueryResult(
            collection_name=COLLECTION_COGNITIVE_IDENTITY
        )
        result = self.analyzer.analyze("Should we build internal CRM now?")
        self.assertFalse(result.decision_recorded)
        self.mock_controller.add_document.assert_not_called()
        self.assertEqual(result.options[0].title, "Evidence-gathering path")

    def test_map_options_returns_dataclasses_not_decisions(self):
        item = StrategicContextItem(
            collection_name=COLLECTION_COGNITIVE_IDENTITY,
            document_id="D1",
            text="FirstMinds stays decoupled from consumer CRM.",
            metadata={"owner": "ABM"},
            distance=0.1,
        )
        options = self.analyzer.map_options("CRM direction", [item])
        self.assertEqual(len(options), 1)
        self.assertIsInstance(options[0], StrategicOption)
        self.assertIn("Mission-aligned", options[0].title)
        self.assertTrue(options[0].next_questions)

    def test_empty_query_is_rejected(self):
        with self.assertRaises(ValueError):
            self.analyzer.analyze("   ")


# ---------------------------------------------------------------------------
# Supporting: prior-phase regression
# ---------------------------------------------------------------------------


class TestV01V02V03V04RegressionGate(unittest.TestCase):
    """Ensure no previous module configuration drifted during Phase v0.5."""

    def test_collections_unchanged(self):
        self.assertEqual(len(ALL_COLLECTIONS), 4)

    def test_file_watcher_extensions_unchanged(self):
        self.assertIn(".dart", CODE_EXTENSIONS)
        self.assertIn(".py", CODE_EXTENSIONS)

    def test_departments_enum_unchanged(self):
        self.assertEqual(len(Department), 5)

    def test_stream_d_schema_unchanged(self):
        self.assertEqual(
            set(SCHEMA_COGNITIVE_IDENTITY.keys()),
            {"owner", "target_entity", "volatility"},
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
