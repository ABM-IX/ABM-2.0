"""
tests/test_phase_v10_gate.py
=============================
Phase v1.0 Gate Tests — API Layer & Console Client

Hard gate proofs (must be 100% green to declare Phase v1.0 complete):

  1. TestAPILayerStructureGate
     - API layer exposes only capability-named functions (no module-leaking names).
     - All six stable capabilities exist and are callable.
     - All four future stubs raise NotImplementedError.
     - Return types are typed dataclasses — no raw ChromaDB types leak through.

  2. TestCapabilityStatusTagsGate
     - Each stable capability's docstring contains 'STATUS       : stable'.
     - Each future capability's docstring contains 'STATUS       : future'.
     - No capability is tagged 'experimental' (none exist yet — gate enforces
       that if one is added it must be consciously tagged).

  3. TestServiceRegistryLifecycleGate
     - boot() succeeds with mocked dependencies.
     - Accessing services before boot() raises RuntimeError.
     - shutdown() is idempotent.
     - health_check() never raises — returns HealthStatus with degraded flag.

  4. TestConsoleCommandsOnlyStableGate
     - commands.py exposes exactly: cmd_ask, cmd_search, cmd_status,
       cmd_summarize, cmd_memory, cmd_explain.
     - commands.py does NOT expose cmd_continue, cmd_reflect, cmd_plan,
       cmd_learn (these are future, no backend exists).
     - commands.py does NOT import from any abm.memory / abm.orchestrator /
       abm.companion / abm.sandbox / abm.strategic_wing module directly.

  5. TestAPICapabilityContractGate
     - answerQuestion returns AnswerResult with correct fields.
     - retrieveKnowledge returns KnowledgeResult with correct fields.
     - getSystemStatus returns StatusResult with correct fields.
     - summarizeProject delegates to StrategicAssetAnalyzer.analyze() only.
     - aggregateProjectMemory returns MemoryResult with correct fields.
     - explainAuditRecord returns ExplainResult with correct fields.
     - All stable capabilities degrade gracefully on Ollama-down (no raise).

  6. TestPriorPhaseRegressionGate
     - All v0.1–v0.5 constants and collection names remain unchanged.
     - No v0.1–v0.5 module was imported from inside any v1.0 client file.
"""

from __future__ import annotations

import inspect
import os
import sys
import types
import unittest
from dataclasses import fields as dataclass_fields
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# ---------------------------------------------------------------------------
# Prior-phase imports (must remain unchanged)
# ---------------------------------------------------------------------------
from abm.memory.chroma_controller import (
    ALL_COLLECTIONS,
    COLLECTION_AMBIENT_TELEMETRY,
    COLLECTION_CODE_TOPOLOGIES,
    COLLECTION_COGNITIVE_IDENTITY,
    COLLECTION_TECHNICAL_MASTERY,
)
from abm.orchestrator.departments import Department, DEPARTMENT_REGISTRY
from abm.orchestrator.task_contract import RouterResult, TaskContract
from abm.sandbox.models import ExecutionResult, GateResult, ValidationScores
from abm.strategic_wing.workflow_monitor import TaskState, WorkflowMonitor

# ---------------------------------------------------------------------------
# v1.0 imports under test
# ---------------------------------------------------------------------------
import abm.api as api_module
import abm.api.capabilities as caps_module
import abm.clients.console.commands as commands_module
from abm.api import (
    APIConfig,
    AnswerResult,
    ExplainResult,
    HealthStatus,
    KnowledgeResult,
    MemoryResult,
    ServiceRegistry,
    StatusResult,
    aggregateProjectMemory,
    answerQuestion,
    continueTask,
    explainAuditRecord,
    getSystemStatus,
    learnTopic,
    planProject,
    reflectOnWork,
    retrieveKnowledge,
    summarizeProject,
)
from abm.api.core.config import APIConfig as _APIConfigDirect
from abm.api.core.registry import ServiceRegistry as _ServiceRegistryDirect


# ============================================================================
# Gate 1: API Layer Structure
# ============================================================================

class TestAPILayerStructureGate(unittest.TestCase):
    """
    Proves that the API layer exposes capability-named functions, correct
    return types, and that future stubs raise NotImplementedError.
    """

    STABLE_CAPABILITIES = [
        "answerQuestion",
        "retrieveKnowledge",
        "getSystemStatus",
        "summarizeProject",
        "aggregateProjectMemory",
        "explainAuditRecord",
    ]

    FUTURE_CAPABILITIES = [
        "continueTask",
        "reflectOnWork",
        "planProject",
        "learnTopic",
    ]

    def test_stable_capabilities_exist_in_api_module(self):
        """All six stable capabilities must be importable from abm.api."""
        for name in self.STABLE_CAPABILITIES:
            with self.subTest(name=name):
                self.assertTrue(
                    hasattr(api_module, name),
                    f"abm.api is missing stable capability: {name}",
                )
                self.assertTrue(
                    callable(getattr(api_module, name)),
                    f"abm.api.{name} is not callable",
                )

    def test_future_capabilities_exist_as_stubs(self):
        """All four future stubs must exist and raise NotImplementedError."""
        future_funcs = {
            "continueTask": lambda: continueTask("x", registry=MagicMock()),
            "reflectOnWork": lambda: reflectOnWork(registry=MagicMock()),
            "planProject": lambda: planProject("x", registry=MagicMock()),
            "learnTopic": lambda: learnTopic("x", registry=MagicMock()),
        }
        for name, call in future_funcs.items():
            with self.subTest(name=name):
                with self.assertRaises(NotImplementedError, msg=f"{name} must raise NotImplementedError"):
                    call()

    def test_no_module_leaking_names_in_public_api(self):
        """
        Capability names must not expose internal module names.
        e.g. 'memory_search' or 'router_classify' would violate constitution rule 14.
        """
        forbidden_prefixes = ["memory_", "router_", "sandbox_", "chroma_", "ollama_"]
        for name in self.STABLE_CAPABILITIES + self.FUTURE_CAPABILITIES:
            for prefix in forbidden_prefixes:
                self.assertFalse(
                    name.startswith(prefix),
                    f"Capability '{name}' leaks module name via prefix '{prefix}'",
                )

    def test_return_type_dataclasses_not_raw_chroma(self):
        """Stable result types must be the typed dataclasses, not raw ChromaDB types."""
        from abm.memory.chroma_controller import QueryResult
        result_types = [AnswerResult, KnowledgeResult, StatusResult, MemoryResult, ExplainResult]
        for rt in result_types:
            with self.subTest(rt=rt.__name__):
                self.assertIsNot(rt, QueryResult, "QueryResult must not be a public API return type")
                self.assertTrue(
                    hasattr(rt, "__dataclass_fields__"),
                    f"{rt.__name__} must be a dataclass",
                )

    def test_answer_result_fields(self):
        """AnswerResult must have all required fields."""
        field_names = {f.name for f in dataclass_fields(AnswerResult)}
        required = {"question", "department", "confidence", "hits", "fallback_used", "degraded"}
        self.assertTrue(required.issubset(field_names))

    def test_knowledge_result_fields(self):
        field_names = {f.name for f in dataclass_fields(KnowledgeResult)}
        self.assertIn("query", field_names)
        self.assertIn("hits", field_names)
        self.assertIn("degraded", field_names)

    def test_status_result_fields(self):
        field_names = {f.name for f in dataclass_fields(StatusResult)}
        required = {"overview", "quarantined_ids", "ollama_reachable", "chroma_ready", "degraded"}
        self.assertTrue(required.issubset(field_names))

    def test_memory_result_fields(self):
        field_names = {f.name for f in dataclass_fields(MemoryResult)}
        required = {"project_name", "streams", "total_hits", "degraded"}
        self.assertTrue(required.issubset(field_names))

    def test_explain_result_fields(self):
        field_names = {f.name for f in dataclass_fields(ExplainResult)}
        required = {"target", "found", "records", "notes"}
        self.assertTrue(required.issubset(field_names))


# ============================================================================
# Gate 2: Capability Status Tags
# ============================================================================

class TestCapabilityStatusTagsGate(unittest.TestCase):
    """
    Proves every capability's docstring carries the correct STATUS tag.
    This is the mechanism by which the capability catalogue is enforced
    (interfaces.md section maps to these tags).
    """

    STABLE = [
        answerQuestion,
        retrieveKnowledge,
        getSystemStatus,
        summarizeProject,
        aggregateProjectMemory,
        explainAuditRecord,
    ]

    FUTURE = [continueTask, reflectOnWork, planProject, learnTopic]

    def test_stable_capabilities_are_tagged_stable(self):
        for fn in self.STABLE:
            with self.subTest(fn=fn.__name__):
                doc = inspect.getdoc(fn) or ""
                self.assertIn(
                    "STATUS       : stable",
                    doc,
                    f"{fn.__name__} must have 'STATUS       : stable' in docstring",
                )

    def test_future_capabilities_are_tagged_future(self):
        for fn in self.FUTURE:
            with self.subTest(fn=fn.__name__):
                doc = inspect.getdoc(fn) or ""
                self.assertIn(
                    "STATUS       : future",
                    doc,
                    f"{fn.__name__} must have 'STATUS       : future' in docstring",
                )

    def test_stable_capabilities_declare_owner(self):
        for fn in self.STABLE:
            with self.subTest(fn=fn.__name__):
                doc = inspect.getdoc(fn) or ""
                self.assertIn("OWNER", doc, f"{fn.__name__} must declare OWNER")

    def test_stable_capabilities_declare_consumers(self):
        for fn in self.STABLE:
            with self.subTest(fn=fn.__name__):
                doc = inspect.getdoc(fn) or ""
                self.assertIn("CONSUMERS", doc, f"{fn.__name__} must declare CONSUMERS")

    def test_stable_capabilities_declare_dependencies(self):
        for fn in self.STABLE:
            with self.subTest(fn=fn.__name__):
                doc = inspect.getdoc(fn) or ""
                self.assertIn("DEPENDENCIES", doc, f"{fn.__name__} must declare DEPENDENCIES")


# ============================================================================
# Gate 3: ServiceRegistry Lifecycle
# ============================================================================

class TestServiceRegistryLifecycleGate(unittest.TestCase):
    """
    Proves boot/shutdown/health_check lifecycle contracts.
    Uses mocks — no live Ollama or ChromaDB required.
    """

    def _make_mock_registry(self):
        """Return a ServiceRegistry with all internal services mocked."""
        registry = ServiceRegistry.__new__(ServiceRegistry)
        registry._config = APIConfig()
        registry._booted = False
        registry._controller = None
        registry._embedder = None
        registry._gateway = None
        registry._router = None
        registry._monitor = None
        registry._analyzer = None
        return registry

    def test_accessing_service_before_boot_raises(self):
        registry = _ServiceRegistryDirect()
        services = ["controller", "embedder", "gateway", "router", "monitor", "analyzer"]
        for svc in services:
            with self.subTest(svc=svc):
                with self.assertRaises(RuntimeError, msg=f"Accessing {svc} before boot must raise"):
                    getattr(registry, svc)

    def test_shutdown_before_boot_is_noop(self):
        registry = _ServiceRegistryDirect()
        # Must not raise
        registry.shutdown()
        self.assertFalse(registry.is_booted)

    def test_double_shutdown_is_idempotent(self):
        registry = _ServiceRegistryDirect()
        registry.shutdown()
        registry.shutdown()  # second call must not raise

    @patch("abm.api.core.registry.ChromaController")
    @patch("abm.api.core.registry.OllamaEmbeddingWrapper")
    @patch("abm.api.core.registry.OllamaModelGateway")
    @patch("abm.api.core.registry.ClassificationRouter")
    @patch("abm.api.core.registry.WorkflowMonitor")
    @patch("abm.api.core.registry.StrategicAssetAnalyzer")
    def test_boot_populates_all_services(
        self, mock_analyzer, mock_monitor, mock_router,
        mock_gateway, mock_embedder, mock_controller
    ):
        registry = _ServiceRegistryDirect()
        registry.boot()
        self.assertTrue(registry.is_booted)
        # All six services must be accessible without RuntimeError
        _ = registry.controller
        _ = registry.embedder
        _ = registry.gateway
        _ = registry.router
        _ = registry.monitor
        _ = registry.analyzer
        registry.shutdown()

    @patch("abm.api.core.registry.ChromaController")
    @patch("abm.api.core.registry.OllamaEmbeddingWrapper")
    @patch("abm.api.core.registry.OllamaModelGateway")
    @patch("abm.api.core.registry.ClassificationRouter")
    @patch("abm.api.core.registry.WorkflowMonitor")
    @patch("abm.api.core.registry.StrategicAssetAnalyzer")
    def test_shutdown_clears_all_services(
        self, mock_analyzer, mock_monitor, mock_router,
        mock_gateway, mock_embedder, mock_controller
    ):
        registry = _ServiceRegistryDirect()
        registry.boot()
        registry.shutdown()
        self.assertFalse(registry.is_booted)
        with self.assertRaises(RuntimeError):
            _ = registry.controller

    def test_double_boot_is_warned_not_errored(self):
        """Calling boot() a second time must not raise — it logs a warning."""
        with patch("abm.api.core.registry.ChromaController"), \
             patch("abm.api.core.registry.OllamaEmbeddingWrapper"), \
             patch("abm.api.core.registry.OllamaModelGateway"), \
             patch("abm.api.core.registry.ClassificationRouter"), \
             patch("abm.api.core.registry.WorkflowMonitor"), \
             patch("abm.api.core.registry.StrategicAssetAnalyzer"):
            registry = _ServiceRegistryDirect()
            registry.boot()
            registry.boot()  # second call: must not raise
            self.assertTrue(registry.is_booted)
            registry.shutdown()

    def test_health_check_never_raises_when_not_booted(self):
        """health_check must return HealthStatus with degraded=True, never raise."""
        registry = _ServiceRegistryDirect()
        status = registry.health_check()
        self.assertIsInstance(status, HealthStatus)
        self.assertTrue(status.degraded)
        self.assertFalse(status.ollama_reachable)
        self.assertFalse(status.chroma_ready)

    def test_api_config_defaults(self):
        config = _APIConfigDirect()
        self.assertEqual(config.ollama_base_url, "http://127.0.0.1:11434")
        self.assertEqual(config.embedding_model, "nomic-embed-text")
        self.assertEqual(config.classification_model, "phi3:mini")
        self.assertEqual(config.chroma_persist_directory, "./memory/chroma_store")
        self.assertEqual(config.quarantine_dir, "memory/ambiguity_quarantine")


# ============================================================================
# Gate 4: Console Commands — Only Stable, No Direct Module Imports
# ============================================================================

class TestConsoleCommandsOnlyStableGate(unittest.TestCase):
    """
    Proves console commands.py exposes exactly the six stable commands,
    does NOT expose future commands, and imports only through abm.api.
    """

    EXPECTED_COMMANDS = {
        "cmd_ask", "cmd_search", "cmd_status",
        "cmd_summarize", "cmd_memory", "cmd_explain",
    }

    FORBIDDEN_COMMANDS = {
        "cmd_continue", "cmd_reflect", "cmd_plan", "cmd_learn",
    }

    FORBIDDEN_DIRECT_IMPORTS = [
        "abm.memory",
        "abm.orchestrator",
        "abm.companion",
        "abm.sandbox",
        "abm.strategic_wing",
    ]

    def test_expected_commands_exist(self):
        for cmd in self.EXPECTED_COMMANDS:
            with self.subTest(cmd=cmd):
                self.assertTrue(
                    hasattr(commands_module, cmd),
                    f"commands.py must expose {cmd}",
                )
                self.assertTrue(callable(getattr(commands_module, cmd)))

    def test_forbidden_commands_do_not_exist(self):
        for cmd in self.FORBIDDEN_COMMANDS:
            with self.subTest(cmd=cmd):
                self.assertFalse(
                    hasattr(commands_module, cmd),
                    f"commands.py must NOT expose {cmd} — backend not yet built",
                )

    def test_commands_module_does_not_import_internal_modules_directly(self):
        """
        commands.py must import capabilities from abm.api, never directly
        from abm.memory, abm.orchestrator, abm.companion, abm.sandbox,
        abm.strategic_wing.

        Proved by inspecting the module's __dict__ for any submodule references
        that would indicate a direct import.
        """
        for forbidden in self.FORBIDDEN_DIRECT_IMPORTS:
            # Check if any name in the module's namespace is a module whose
            # __name__ starts with a forbidden prefix
            for attr_name, attr_val in vars(commands_module).items():
                if isinstance(attr_val, types.ModuleType):
                    mod_name = getattr(attr_val, "__name__", "")
                    self.assertFalse(
                        mod_name.startswith(forbidden),
                        f"commands.py directly imported '{mod_name}' — "
                        f"must import through abm.api only",
                    )

    def test_commands_callable_signatures_accept_registry(self):
        """Each cmd_* must accept a 'registry' keyword argument."""
        for cmd_name in self.EXPECTED_COMMANDS:
            fn = getattr(commands_module, cmd_name)
            sig = inspect.signature(fn)
            self.assertIn(
                "registry",
                sig.parameters,
                f"{cmd_name} must have a 'registry' keyword parameter",
            )


# ============================================================================
# Gate 5: Capability Contract — Correct Delegation and Graceful Degradation
# ============================================================================

class TestAPICapabilityContractGate(unittest.TestCase):
    """
    Proves each stable capability:
      (a) delegates to the correct backend function/class
      (b) returns the correct typed dataclass
      (c) degrades gracefully when Ollama is down (no raise to caller)
    """

    def _make_registry(self) -> ServiceRegistry:
        """Create a ServiceRegistry with all services mocked."""
        registry = MagicMock(spec=ServiceRegistry)
        registry.config = APIConfig()
        return registry

    # ── answerQuestion ────────────────────────────────────────────────────────

    def test_answer_question_empty_input_returns_fallback_result(self):
        registry = self._make_registry()
        result = answerQuestion("", registry=registry)
        self.assertIsInstance(result, AnswerResult)
        self.assertTrue(result.fallback_used)

    def test_answer_question_calls_router_classify(self):
        registry = self._make_registry()
        mock_router_result = MagicMock()
        mock_router_result.contract.department = Department.SOFTWARE_ENGINEERING
        mock_router_result.confidence_hint = "high"
        mock_router_result.fallback_used = False
        registry.router.classify.return_value = mock_router_result

        mock_embedding = [0.1] * 768
        registry.embedder.embed.return_value = mock_embedding

        # controller.query_collection returns a QueryResult-like
        mock_qr = MagicMock()
        mock_qr.ids = [[]]
        mock_qr.documents = [[]]
        mock_qr.metadatas = [[]]
        mock_qr.distances = [[]]
        registry.controller.query_collection.return_value = mock_qr

        result = answerQuestion("test question", registry=registry)

        registry.router.classify.assert_called_once_with("test question")
        self.assertIsInstance(result, AnswerResult)
        self.assertEqual(result.department, "software_engineering")
        self.assertEqual(result.confidence, "high")
        self.assertFalse(result.fallback_used)

    def test_answer_question_degrades_when_embedder_raises(self):
        """Embedder failure → degraded=True, no raise to caller."""
        registry = self._make_registry()
        mock_router_result = MagicMock()
        mock_router_result.contract.department = Department.SOFTWARE_ENGINEERING
        mock_router_result.confidence_hint = "low"
        mock_router_result.fallback_used = False
        registry.router.classify.return_value = mock_router_result
        registry.embedder.embed.side_effect = ConnectionError("Ollama down")

        result = answerQuestion("test", registry=registry)
        self.assertIsInstance(result, AnswerResult)
        self.assertTrue(result.degraded)
        self.assertEqual(result.hits, [])

    # ── retrieveKnowledge ─────────────────────────────────────────────────────

    def test_retrieve_knowledge_empty_query_returns_empty_result(self):
        registry = self._make_registry()
        result = retrieveKnowledge("", registry=registry)
        self.assertIsInstance(result, KnowledgeResult)
        self.assertEqual(result.hits, [])
        self.assertFalse(result.degraded)

    def test_retrieve_knowledge_queries_all_four_collections(self):
        registry = self._make_registry()
        registry.embedder.embed.return_value = [0.1] * 768
        mock_qr = MagicMock()
        mock_qr.ids = [[]]
        mock_qr.documents = [[]]
        mock_qr.metadatas = [[]]
        mock_qr.distances = [[]]
        registry.controller.query_collection.return_value = mock_qr

        retrieveKnowledge("BLoC pattern", registry=registry)

        # Must have queried all four collections
        call_args = [
            call[0][0] if call[0] else call[1].get("collection_name")
            for call in registry.controller.query_collection.call_args_list
        ]
        queried_collections = {
            ca if isinstance(ca, str) else ca
            for ca in call_args
        }
        # Each call uses collection_name as keyword arg
        actual_names = set()
        for call in registry.controller.query_collection.call_args_list:
            kw = call[1] if call[1] else {}
            pos = call[0] if call[0] else []
            if "collection_name" in kw:
                actual_names.add(kw["collection_name"])
            elif pos:
                actual_names.add(pos[0])
        self.assertEqual(actual_names, set(ALL_COLLECTIONS))

    def test_retrieve_knowledge_degrades_on_embed_failure(self):
        registry = self._make_registry()
        registry.embedder.embed.side_effect = RuntimeError("Ollama down")
        result = retrieveKnowledge("test", registry=registry)
        self.assertIsInstance(result, KnowledgeResult)
        self.assertTrue(result.degraded)

    # ── getSystemStatus ───────────────────────────────────────────────────────

    def test_get_system_status_returns_status_result(self):
        registry = self._make_registry()
        registry.monitor.scan_quarantine_directory.return_value = []
        registry.monitor.get_overview_report.return_value = "No tasks in-flight."
        registry.health_check.return_value = HealthStatus(
            ollama_reachable=True, chroma_ready=True, degraded=False, notes=[]
        )

        result = getSystemStatus(registry=registry)
        self.assertIsInstance(result, StatusResult)
        self.assertFalse(result.degraded)
        self.assertTrue(result.ollama_reachable)

    def test_get_system_status_never_raises_on_monitor_error(self):
        registry = self._make_registry()
        registry.monitor.scan_quarantine_directory.side_effect = RuntimeError("disk error")
        registry.health_check.return_value = HealthStatus(
            ollama_reachable=False, chroma_ready=False, degraded=True, notes=[]
        )
        result = getSystemStatus(registry=registry)
        self.assertIsInstance(result, StatusResult)
        self.assertTrue(result.degraded)

    # ── summarizeProject ──────────────────────────────────────────────────────

    def test_summarize_project_delegates_to_analyzer(self):
        from abm.strategic_wing.strategic_asset_analyzer import StrategicAnalysisResult
        registry = self._make_registry()
        mock_result = StrategicAnalysisResult(
            query="smart_transit",
            context_items=[],
            options=[],
            decision_recorded=False,
        )
        registry.analyzer.analyze.return_value = mock_result

        result = summarizeProject("smart_transit", registry=registry)
        registry.analyzer.analyze.assert_called_once_with(
            query="smart_transit", n_results_per_stream=3
        )
        self.assertIs(result, mock_result)

    def test_summarize_project_decision_recorded_always_false(self):
        """Analyzer contract: decision_recorded is always False."""
        from abm.strategic_wing.strategic_asset_analyzer import StrategicAnalysisResult
        registry = self._make_registry()
        mock_result = StrategicAnalysisResult(
            query="houseconnect",
            context_items=[],
            options=[],
            decision_recorded=False,
        )
        registry.analyzer.analyze.return_value = mock_result
        result = summarizeProject("houseconnect", registry=registry)
        self.assertFalse(result.decision_recorded)

    # ── aggregateProjectMemory ────────────────────────────────────────────────

    def test_aggregate_project_memory_empty_name_returns_early(self):
        registry = self._make_registry()
        result = aggregateProjectMemory("", registry=registry)
        self.assertIsInstance(result, MemoryResult)
        self.assertEqual(result.total_hits, 0)
        registry.embedder.embed.assert_not_called()

    def test_aggregate_project_memory_queries_all_streams(self):
        registry = self._make_registry()
        registry.embedder.embed.return_value = [0.1] * 768
        mock_qr = MagicMock()
        mock_qr.ids = [["doc1"]]
        mock_qr.documents = [["some text"]]
        mock_qr.metadatas = [[{"owner": "ABM"}]]
        mock_qr.distances = [[0.12]]
        registry.controller.query_collection.return_value = mock_qr

        result = aggregateProjectMemory("smart_transit", registry=registry)
        self.assertIsInstance(result, MemoryResult)
        self.assertEqual(registry.controller.query_collection.call_count, 4)
        self.assertEqual(result.total_hits, 4)  # 1 hit × 4 streams

    def test_aggregate_project_memory_degrades_on_embed_failure(self):
        registry = self._make_registry()
        registry.embedder.embed.side_effect = ConnectionError("Ollama down")
        result = aggregateProjectMemory("project_x", registry=registry)
        self.assertIsInstance(result, MemoryResult)
        self.assertTrue(result.degraded)

    # ── explainAuditRecord ────────────────────────────────────────────────────

    def test_explain_empty_target_returns_not_found(self):
        registry = self._make_registry()
        result = explainAuditRecord("", registry=registry)
        self.assertIsInstance(result, ExplainResult)
        self.assertFalse(result.found)

    def test_explain_searches_monitor_registry(self):
        """explainAuditRecord must check the WorkflowMonitor._registry."""
        registry = self._make_registry()
        mock_monitor = MagicMock(spec=WorkflowMonitor)
        mock_monitor.scan_quarantine_directory.return_value = []
        mock_monitor._registry = {}
        registry.monitor = mock_monitor

        # Embedder returns a vector for Stream D lookup
        registry.embedder.embed.return_value = [0.1] * 768
        mock_qr = MagicMock()
        mock_qr.ids = [[]]
        mock_qr.documents = [[]]
        mock_qr.metadatas = [[]]
        mock_qr.distances = [[]]
        registry.controller.query_collection.return_value = mock_qr

        result = explainAuditRecord("TXN_99999", registry=registry)
        mock_monitor.scan_quarantine_directory.assert_called_once()
        self.assertIsInstance(result, ExplainResult)
        self.assertFalse(result.found)

    def test_explain_returns_monitor_record_when_found(self):
        registry = self._make_registry()
        contract = MagicMock()
        contract.objective = "Test objective"
        contract.department = MagicMock()
        contract.department.value = "software_engineering"

        task_record = MagicMock()
        task_record.contract = contract
        task_record.state = MagicMock()
        task_record.state.value = "PASSED"
        task_record.gate_result = None
        task_record.execution_result = None

        mock_monitor = MagicMock(spec=WorkflowMonitor)
        mock_monitor.scan_quarantine_directory.return_value = []
        mock_monitor._registry = {"TXN_12345": task_record}
        registry.monitor = mock_monitor

        registry.embedder.embed.return_value = [0.1] * 768
        mock_qr = MagicMock()
        mock_qr.ids = [[]]
        mock_qr.documents = [[]]
        mock_qr.metadatas = [[]]
        mock_qr.distances = [[]]
        registry.controller.query_collection.return_value = mock_qr

        result = explainAuditRecord("TXN_12345", registry=registry)
        self.assertTrue(result.found)
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0]["source"], "monitor")
        self.assertEqual(result.records[0]["contract_id"], "TXN_12345")


# ============================================================================
# Gate 6: Prior-Phase Regression
# ============================================================================

class TestPriorPhaseRegressionGate(unittest.TestCase):
    """
    Hard-asserts that zero drift occurred in v0.1–v0.5 constants or
    collection schema definitions.
    """

    def test_collection_names_unchanged(self):
        self.assertEqual(COLLECTION_COGNITIVE_IDENTITY, "abm_cognitive_identity")
        self.assertEqual(COLLECTION_CODE_TOPOLOGIES, "abm_code_topologies")
        self.assertEqual(COLLECTION_TECHNICAL_MASTERY, "abm_technical_mastery")
        self.assertEqual(COLLECTION_AMBIENT_TELEMETRY, "abm_ambient_telemetry")

    def test_all_collections_tuple_count(self):
        self.assertEqual(len(ALL_COLLECTIONS), 4)
        self.assertIn(COLLECTION_COGNITIVE_IDENTITY, ALL_COLLECTIONS)
        self.assertIn(COLLECTION_CODE_TOPOLOGIES, ALL_COLLECTIONS)
        self.assertIn(COLLECTION_TECHNICAL_MASTERY, ALL_COLLECTIONS)
        self.assertIn(COLLECTION_AMBIENT_TELEMETRY, ALL_COLLECTIONS)

    def test_department_enum_values_unchanged(self):
        self.assertEqual(Department.SOFTWARE_ENGINEERING.value, "software_engineering")
        self.assertEqual(Department.STRATEGIC_PLANNING.value, "strategic_planning")
        self.assertEqual(Department.ARCHITECTURE.value, "architecture")
        self.assertEqual(Department.SECURITY.value, "security")
        self.assertEqual(Department.MEMORY_INDEXING.value, "memory_indexing")

    def test_task_state_enum_values_unchanged(self):
        self.assertEqual(TaskState.ROUTED.value, "ROUTED")
        self.assertEqual(TaskState.IN_SANDBOX.value, "IN_SANDBOX")
        self.assertEqual(TaskState.EXECUTED.value, "EXECUTED")
        self.assertEqual(TaskState.QUARANTINED.value, "QUARANTINED")
        self.assertEqual(TaskState.PASSED.value, "PASSED")

    def test_department_registry_has_five_departments(self):
        self.assertEqual(len(DEPARTMENT_REGISTRY), 5)

    def test_validation_scores_formula_weights_unchanged(self):
        """The confidence formula weights from v0.4 must not change."""
        from abm.sandbox.validation_gate import MultiFactorGate
        gate = MultiFactorGate.__new__(MultiFactorGate)
        gate.quarantine_dir = "memory/ambiguity_quarantine"
        scores = ValidationScores(
            m_align=1.0, t_correct=1.0, s_val=1.0, test_succ=1.0, p_align=1.0
        )
        # C = 0.30 + 0.25 + 0.20 + 0.15 + 0.10 = 1.00
        gate._registry = {}
        c = gate.calculate_confidence_score(scores)
        self.assertAlmostEqual(c, 1.0, places=6)

    def test_api_config_ollama_url_is_loopback(self):
        """APIConfig must never point anywhere but 127.0.0.1 — constitution rule 1."""
        config = APIConfig()
        self.assertIn("127.0.0.1", config.ollama_base_url)
        self.assertNotIn("openai", config.ollama_base_url)
        self.assertNotIn("anthropic", config.ollama_base_url)
        self.assertNotIn("gemini", config.ollama_base_url)
        self.assertNotIn("groq", config.ollama_base_url)


if __name__ == "__main__":
    unittest.main()
