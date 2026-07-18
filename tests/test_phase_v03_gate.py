"""
tests/test_phase_v03_gate.py
=============================
Phase v0.3 Gate Tests — Executive Orchestrator Engine
Spec Reference: ABM_SPEC.md sections 4, 5, 7, and 10 (item 3)

Hard gate proofs (must be 100% green before Phase v0.4):
  1. TestRouterClassificationOnlyGate — router never generates content and
     never calls a worker; classify() returns a classification only
  2. TestWorkerSandboxScopeIsolationGate — each sandbox can only access
     streams/tools scoped to its department, never others
  3. TestDelegationAndReportSchemaGate — TaskContract / WorkerTaskHandoff /
     WorkerResultReport validate; malformed payloads are rejected

Supporting contract tests cover departments, gateway, fallback, and
v0.1/v0.2 regression. Phase v0.3 does NOT advance to v0.4 until this file
is green.
"""

from __future__ import annotations

import inspect
import json
import sys
import os
import unittest
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# ---------------------------------------------------------------------------
# v0.1 imports (must remain unchanged)
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
)

# ---------------------------------------------------------------------------
# v0.2 imports (must remain unchanged)
# ---------------------------------------------------------------------------
from abm.companion.file_watcher import CODE_EXTENSIONS

# ---------------------------------------------------------------------------
# v0.3 imports
# ---------------------------------------------------------------------------
from abm.orchestrator.departments import (
    ALL_WORKER_TOOLS,
    DEPARTMENT_REGISTRY,
    Department,
    DepartmentWorkerSandbox,
    TOOL_CHROMA_QUERY,
    TOOL_CODE_STRUCTURE_ANALYZER,
    TOOL_FILE_WATCHER,
    TOOL_GIT_PIPELINE,
    TOOL_INGESTION_COORDINATOR,
    TOOL_MODEL_GATEWAY,
    TOOL_PATCH_PROPOSAL_WRITER,
    TOOL_SECURITY_STATIC_SCAN,
    TOOL_STRATEGIC_SUMMARY_BUILDER,
    TOOL_STYLE_FINGERPRINT_EXTRACTOR,
    department_from_string,
    get_sandbox,
)
from abm.orchestrator.model_gateway import (
    DEFAULT_CLASSIFICATION_MODEL,
    GenerationResponse,
    ModelGatewayError,
    OllamaModelGateway,
)
from abm.orchestrator.router import (
    CONFIDENCE_HINTS,
    FALLBACK_DEPARTMENT,
    MAX_TASK_DESCRIPTION_CHARS,
    ClassificationRouter,
)
from abm.orchestrator.task_contract import (
    RouterResult,
    TaskContract,
    WorkerResultReport,
    WorkerTaskHandoff,
)
import abm.orchestrator.router as router_module
from pydantic import ValidationError



# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_ALL_STREAM_NAMES = {
    COLLECTION_COGNITIVE_IDENTITY,
    COLLECTION_CODE_TOPOLOGIES,
    COLLECTION_TECHNICAL_MASTERY,
    COLLECTION_AMBIENT_TELEMETRY,
}

MOCK_EMBEDDING = [0.0] * 768

GOOD_JSON_RESPONSE = json.dumps(
    {"department": "software_engineering", "confidence": "high"}
)
STRATEGIC_JSON_RESPONSE = json.dumps(
    {"department": "strategic_planning", "confidence": "medium"}
)


def _make_mock_gateway(response_text: str = GOOD_JSON_RESPONSE) -> MagicMock:
    gw = MagicMock(spec=OllamaModelGateway)
    gw.model = "phi3:mini"
    gw.base_url = "http://127.0.0.1:11434"
    gw.generate.return_value = GenerationResponse(
        text=response_text, latency_ms=120, model="phi3:mini"
    )
    gw.is_available.return_value = True
    return gw


def _make_mock_controller() -> MagicMock:
    ctrl = MagicMock()
    ctrl.query_collection.return_value = {
        "documents": [["ABM is a privacy-first Cognitive OS for FirstMinds Ltd."]]
    }
    return ctrl


def _make_mock_embedder() -> MagicMock:
    emb = MagicMock()
    emb.embed.return_value = MOCK_EMBEDDING
    return emb


# ---------------------------------------------------------------------------
# HARD GATE 1 — router classifies only; never generates; never calls workers
# ---------------------------------------------------------------------------


class TestRouterClassificationOnlyGate(unittest.TestCase):
    """
    Prove ClassificationRouter never generates content and never invokes a
    worker sandbox — classify() returns a classification (RouterResult) only.
    """

    BANNED_CONTENT_METHODS = (
        "generate",
        "write",
        "respond",
        "explain",
        "complete",
        "produce",
        "synthesize",
        "draft",
    )
    BANNED_WORKER_METHODS = (
        "execute",
        "dispatch_worker",
        "call_worker",
        "run_sandbox",
        "invoke_worker",
        "handoff_to_worker",
        "execute_contract",
        "run_department",
    )

    def setUp(self) -> None:
        self.gateway = _make_mock_gateway(GOOD_JSON_RESPONSE)
        self.router = ClassificationRouter(gateway=self.gateway)

    def test_banned_content_generation_methods_absent(self):
        for name in self.BANNED_CONTENT_METHODS:
            with self.subTest(method=name):
                self.assertFalse(
                    hasattr(self.router, name),
                    f"Router must not expose content method '{name}'",
                )

    def test_banned_worker_invocation_methods_absent(self):
        for name in self.BANNED_WORKER_METHODS:
            with self.subTest(method=name):
                self.assertFalse(
                    hasattr(self.router, name),
                    f"Router must not expose worker-call method '{name}'",
                )

    def test_public_action_surface_is_classify_and_is_available_only(self):
        public = {
            name
            for name, _ in inspect.getmembers(self.router, predicate=inspect.ismethod)
            if not name.startswith("_")
        }
        self.assertEqual(public, {"classify", "is_available"})

    def test_classify_returns_router_result_not_worker_handoff_or_report(self):
        result = self.router.classify("Build a Flutter BLoC auth module")
        self.assertIsInstance(result, RouterResult)
        self.assertNotIsInstance(result, WorkerTaskHandoff)
        self.assertNotIsInstance(result, WorkerResultReport)
        self.assertIsInstance(result.contract, TaskContract)
        self.assertIsInstance(result.contract.department, Department)

    def test_classify_does_not_construct_worker_handoff_or_report(self):
        with (
            patch(
                "abm.orchestrator.task_contract.WorkerTaskHandoff.build",
                wraps=WorkerTaskHandoff.build,
            ) as handoff_build,
            patch(
                "abm.orchestrator.task_contract.WorkerResultReport.build",
                wraps=WorkerResultReport.build,
            ) as report_build,
        ):
            # Patch where router would import them if it called workers —
            # router module must not reference these builders at all.
            result = self.router.classify("Scan for plaintext secrets")
            self.assertIsInstance(result, RouterResult)
            handoff_build.assert_not_called()
            report_build.assert_not_called()

    def test_router_module_does_not_import_worker_handoff_or_result_report(self):
        source = inspect.getsource(router_module)
        self.assertNotIn("WorkerTaskHandoff", source)
        self.assertNotIn("WorkerResultReport", source)
        # Classification output only — no worker execution vocabulary
        for token in ("dispatch_worker", "execute_contract", "run_sandbox"):
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_classify_only_calls_gateway_generate_not_worker_tools(self):
        result = self.router.classify("Refactor navigation stack")
        self.gateway.generate.assert_called_once()
        # Gateway is the classification model — no other side-effect APIs
        self.assertFalse(hasattr(self.gateway, "execute_worker"))
        self.assertIsInstance(result, RouterResult)
        self.assertEqual(result.contract.department, Department.SOFTWARE_ENGINEERING)


# ---------------------------------------------------------------------------
# HARD GATE 2 — sandbox stream/tool isolation per department
# ---------------------------------------------------------------------------


class TestWorkerSandboxScopeIsolationGate(unittest.TestCase):
    """
    Prove each department sandbox can only access its scoped streams and
    tools — never another department's exclusive resources.
    """

    def test_every_allowed_stream_is_accessible_and_denied_streams_are_not(self):
        for dept, sandbox in DEPARTMENT_REGISTRY.items():
            for stream in _ALL_STREAM_NAMES:
                with self.subTest(dept=dept.value, stream=stream):
                    if stream in sandbox.allowed_streams:
                        self.assertTrue(sandbox.can_access_stream(stream))
                    else:
                        self.assertFalse(
                            sandbox.can_access_stream(stream),
                            f"{dept.value} must NOT access '{stream}'",
                        )

    def test_every_allowed_tool_is_usable_and_denied_tools_are_not(self):
        for dept, sandbox in DEPARTMENT_REGISTRY.items():
            for tool in ALL_WORKER_TOOLS:
                with self.subTest(dept=dept.value, tool=tool):
                    if tool in sandbox.allowed_tools:
                        self.assertTrue(sandbox.can_use_tool(tool))
                    else:
                        self.assertFalse(
                            sandbox.can_use_tool(tool),
                            f"{dept.value} must NOT use '{tool}'",
                        )

    def test_security_cannot_access_stream_d_or_stream_a(self):
        sandbox = get_sandbox(Department.SECURITY)
        self.assertFalse(sandbox.can_access_stream(COLLECTION_COGNITIVE_IDENTITY))
        self.assertFalse(sandbox.can_access_stream(COLLECTION_CODE_TOPOLOGIES))
        self.assertTrue(sandbox.can_access_stream(COLLECTION_TECHNICAL_MASTERY))
        self.assertTrue(sandbox.can_access_stream(COLLECTION_AMBIENT_TELEMETRY))

    def test_strategic_planning_cannot_access_code_or_telemetry_streams(self):
        sandbox = get_sandbox(Department.STRATEGIC_PLANNING)
        self.assertFalse(sandbox.can_access_stream(COLLECTION_CODE_TOPOLOGIES))
        self.assertFalse(sandbox.can_access_stream(COLLECTION_AMBIENT_TELEMETRY))
        self.assertTrue(sandbox.can_access_stream(COLLECTION_COGNITIVE_IDENTITY))
        self.assertTrue(sandbox.can_access_stream(COLLECTION_TECHNICAL_MASTERY))

    def test_software_engineering_cannot_use_security_or_strategy_tools(self):
        sandbox = get_sandbox(Department.SOFTWARE_ENGINEERING)
        self.assertFalse(sandbox.can_use_tool(TOOL_SECURITY_STATIC_SCAN))
        self.assertFalse(sandbox.can_use_tool(TOOL_STRATEGIC_SUMMARY_BUILDER))
        self.assertFalse(sandbox.can_use_tool(TOOL_INGESTION_COORDINATOR))
        self.assertTrue(sandbox.can_use_tool(TOOL_CODE_STRUCTURE_ANALYZER))

    def test_security_cannot_use_code_structure_or_style_tools(self):
        sandbox = get_sandbox(Department.SECURITY)
        self.assertFalse(sandbox.can_use_tool(TOOL_CODE_STRUCTURE_ANALYZER))
        self.assertFalse(sandbox.can_use_tool(TOOL_STYLE_FINGERPRINT_EXTRACTOR))
        self.assertFalse(sandbox.can_use_tool(TOOL_MODEL_GATEWAY))
        self.assertTrue(sandbox.can_use_tool(TOOL_SECURITY_STATIC_SCAN))

    def test_no_two_sandboxes_share_identical_stream_and_tool_scopes(self):
        scopes = [
            (frozenset(s.allowed_streams), frozenset(s.allowed_tools))
            for s in DEPARTMENT_REGISTRY.values()
        ]
        self.assertEqual(len(scopes), len(set(scopes)))

    def test_handoff_scope_matches_sandbox_and_blocks_foreign_report_access(self):
        """Worker report claiming another department's stream/tool fails scope check."""
        for dept in Department:
            with self.subTest(dept=dept.value):
                sandbox = get_sandbox(dept)
                contract = TaskContract.build(
                    objective=f"Scoped task for {dept.value}",
                    department=dept,
                    assigned_agents=list(sandbox.assigned_agents),
                    autonomy_permission_level=sandbox.autonomy_level,
                    hard_success_conditions=list(sandbox.hard_success_conditions),
                    epoch=1784370192,
                )
                handoff = WorkerTaskHandoff.build(contract)
                self.assertEqual(set(handoff.allowed_streams), set(sandbox.allowed_streams))
                self.assertEqual(set(handoff.allowed_tools), set(sandbox.allowed_tools))

                foreign_streams = _ALL_STREAM_NAMES - set(sandbox.allowed_streams)
                foreign_tools = ALL_WORKER_TOOLS - set(sandbox.allowed_tools)
                if foreign_streams:
                    bad = WorkerResultReport.build(
                        handoff,
                        status="success",
                        summary="scope escape attempt",
                        streams_accessed=[sorted(foreign_streams)[0]],
                        completed_at=1784370299,
                    )
                    self.assertFalse(bad.validate_against_handoff(handoff))
                if foreign_tools:
                    bad = WorkerResultReport.build(
                        handoff,
                        status="success",
                        summary="tool escape attempt",
                        tools_used=[sorted(foreign_tools)[0]],
                        completed_at=1784370299,
                    )
                    self.assertFalse(bad.validate_against_handoff(handoff))


# ---------------------------------------------------------------------------
# HARD GATE 3 — delegation + result-report schemas; reject malformed JSON
# ---------------------------------------------------------------------------


class TestDelegationAndReportSchemaGate(unittest.TestCase):
    """
    Prove task delegation and result-reporting JSON validate against the
    defined schemas, and malformed payloads are rejected.
    """

    def _se_contract(self) -> TaskContract:
        sandbox = get_sandbox(Department.SOFTWARE_ENGINEERING)
        return TaskContract.build(
            objective="Build secure local token encryption module",
            department=Department.SOFTWARE_ENGINEERING,
            assigned_agents=list(sandbox.assigned_agents),
            autonomy_permission_level=sandbox.autonomy_level,
            hard_success_conditions=list(sandbox.hard_success_conditions),
            epoch=1784370192,
        )

    def _se_handoff(self) -> WorkerTaskHandoff:
        return WorkerTaskHandoff.build(self._se_contract())

    # ---- valid payloads ----

    def test_valid_task_contract_json_round_trip(self):
        contract = self._se_contract()
        payload = json.loads(json.dumps(contract.to_dict()))
        restored = TaskContract(**payload)
        self.assertEqual(restored.contract_id, contract.contract_id)
        self.assertEqual(restored.department, Department.SOFTWARE_ENGINEERING)

    def test_valid_worker_handoff_json_round_trip(self):
        handoff = self._se_handoff()
        payload = json.loads(json.dumps(handoff.to_dict()))
        restored = WorkerTaskHandoff(**payload)
        self.assertEqual(restored.execution_context_id, "sandbox:software_engineering")
        self.assertEqual(set(restored.allowed_tools), set(handoff.allowed_tools))

    def test_valid_worker_result_report_json_round_trip(self):
        handoff = self._se_handoff()
        report = WorkerResultReport.build(
            handoff,
            status="success",
            summary="Patch proposal drafted.",
            streams_accessed=[COLLECTION_CODE_TOPOLOGIES],
            tools_used=[TOOL_PATCH_PROPOSAL_WRITER],
            success_conditions_met=["syntax_tree_validity == true"],
            completed_at=1784370299,
        )
        payload = json.loads(json.dumps(report.to_dict()))
        restored = WorkerResultReport(**payload)
        self.assertTrue(restored.validate_against_handoff(handoff))

    # ---- malformed TaskContract ----

    def test_rejects_task_contract_missing_txn_prefix(self):
        with self.assertRaises(ValidationError):
            TaskContract(
                contract_id="BAD_1784370192",
                objective="x",
                department=Department.SECURITY,
                assigned_agents=["security_scanner"],
                autonomy_permission_level=1,
                hard_success_conditions=["static_analysis_clean == true"],
                created_at=1784370192,
            )

    def test_rejects_task_contract_extra_fields(self):
        with self.assertRaises(ValidationError):
            TaskContract(
                contract_id="TXN_1",
                objective="x",
                department=Department.SECURITY,
                assigned_agents=["security_scanner"],
                autonomy_permission_level=1,
                hard_success_conditions=["c"],
                created_at=1,
                worker_payload="not allowed",
            )

    def test_rejects_task_contract_empty_objective(self):
        with self.assertRaises(ValidationError):
            TaskContract.build(
                objective="   ",
                department=Department.ARCHITECTURE,
                assigned_agents=["architecture_node"],
                autonomy_permission_level=2,
                hard_success_conditions=["c"],
            )

    # ---- malformed WorkerTaskHandoff ----

    def test_rejects_handoff_without_sandbox_prefix(self):
        with self.assertRaises(ValidationError):
            WorkerTaskHandoff(
                contract=self._se_contract(),
                execution_context_id="software_engineering",
                allowed_streams=[COLLECTION_CODE_TOPOLOGIES],
                allowed_tools=[TOOL_CHROMA_QUERY],
            )

    def test_rejects_handoff_unknown_tool(self):
        with self.assertRaises(ValidationError):
            WorkerTaskHandoff(
                contract=self._se_contract(),
                execution_context_id="sandbox:software_engineering",
                allowed_streams=[COLLECTION_CODE_TOPOLOGIES],
                allowed_tools=["openai_api"],
            )

    def test_rejects_handoff_empty_streams(self):
        with self.assertRaises(ValidationError):
            WorkerTaskHandoff(
                contract=self._se_contract(),
                execution_context_id="sandbox:software_engineering",
                allowed_streams=[],
                allowed_tools=[TOOL_CHROMA_QUERY],
            )

    def test_rejects_handoff_extra_fields(self):
        with self.assertRaises(ValidationError):
            WorkerTaskHandoff(
                contract=self._se_contract(),
                execution_context_id="sandbox:software_engineering",
                allowed_streams=[COLLECTION_CODE_TOPOLOGIES],
                allowed_tools=[TOOL_CHROMA_QUERY],
                docker_image="forbidden-in-v0.3",
            )

    def test_rejects_handoff_from_malformed_json_dict(self):
        bad = {
            "contract": self._se_contract().to_dict(),
            "execution_context_id": "sandbox:software_engineering",
            "allowed_streams": [COLLECTION_CODE_TOPOLOGIES],
            "allowed_tools": [TOOL_CHROMA_QUERY],
            "extra_secret": True,
        }
        with self.assertRaises(ValidationError):
            WorkerTaskHandoff(**bad)

    # ---- malformed WorkerResultReport ----

    def test_rejects_report_invalid_status(self):
        with self.assertRaises(ValidationError):
            WorkerResultReport(
                contract_id="TXN_1784370192",
                department=Department.SOFTWARE_ENGINEERING,
                execution_context_id="sandbox:software_engineering",
                status="partial",
                summary="done",
                completed_at=1784370299,
            )

    def test_rejects_report_empty_summary(self):
        with self.assertRaises(ValidationError):
            WorkerResultReport.build(
                self._se_handoff(),
                status="failed",
                summary="",
                completed_at=1784370299,
            )

    def test_rejects_report_unknown_tool_in_tools_used(self):
        with self.assertRaises(ValidationError):
            WorkerResultReport(
                contract_id="TXN_1784370192",
                department=Department.SOFTWARE_ENGINEERING,
                execution_context_id="sandbox:software_engineering",
                status="success",
                summary="ok",
                tools_used=["shell_escape"],
                completed_at=1784370299,
            )

    def test_rejects_report_missing_sandbox_prefix(self):
        with self.assertRaises(ValidationError):
            WorkerResultReport(
                contract_id="TXN_1784370192",
                department=Department.SOFTWARE_ENGINEERING,
                execution_context_id="ctx:software_engineering",
                status="success",
                summary="ok",
                completed_at=1784370299,
            )

    def test_rejects_report_extra_fields_from_json(self):
        handoff = self._se_handoff()
        bad = WorkerResultReport.build(
            handoff,
            status="success",
            summary="ok",
            completed_at=1784370299,
        ).to_dict()
        bad["raw_model_output"] = "should be forbidden"
        with self.assertRaises(ValidationError):
            WorkerResultReport(**bad)

    def test_validate_against_handoff_rejects_contract_id_mismatch(self):
        handoff = self._se_handoff()
        report = WorkerResultReport.build(
            handoff,
            status="success",
            summary="ok",
            completed_at=1784370299,
        )
        # Bypass build() to forge a mismatched id
        forged = report.model_copy(update={"contract_id": "TXN_9999999999"})
        self.assertFalse(forged.validate_against_handoff(handoff))


# ---------------------------------------------------------------------------
# TestDepartmentEnum
# ---------------------------------------------------------------------------


class TestDepartmentEnum(unittest.TestCase):
    """All five departments exist with correct string values."""

    def test_software_engineering_value(self):
        self.assertEqual(Department.SOFTWARE_ENGINEERING.value, "software_engineering")

    def test_strategic_planning_value(self):
        self.assertEqual(Department.STRATEGIC_PLANNING.value, "strategic_planning")

    def test_architecture_value(self):
        self.assertEqual(Department.ARCHITECTURE.value, "architecture")

    def test_security_value(self):
        self.assertEqual(Department.SECURITY.value, "security")

    def test_memory_indexing_value(self):
        self.assertEqual(Department.MEMORY_INDEXING.value, "memory_indexing")

    def test_exactly_five_departments(self):
        self.assertEqual(len(Department), 5)

    def test_department_is_str_subclass(self):
        """Department members can be used directly as JSON-serialisable strings."""
        self.assertIsInstance(Department.SOFTWARE_ENGINEERING, str)


# ---------------------------------------------------------------------------
# TestDepartmentRegistry
# ---------------------------------------------------------------------------


class TestDepartmentRegistry(unittest.TestCase):
    """DEPARTMENT_REGISTRY contains exactly five entries with valid configs."""

    def test_registry_has_five_entries(self):
        self.assertEqual(len(DEPARTMENT_REGISTRY), 5)

    def test_all_departments_in_registry(self):
        for dept in Department:
            with self.subTest(dept=dept):
                self.assertIn(dept, DEPARTMENT_REGISTRY)

    def test_all_allowed_streams_are_valid_collections(self):
        for dept, sandbox in DEPARTMENT_REGISTRY.items():
            with self.subTest(dept=dept):
                self.assertTrue(
                    sandbox.allowed_streams.issubset(_ALL_STREAM_NAMES),
                    f"{dept}: allowed_streams {sandbox.allowed_streams} "
                    f"contains unknown collection name(s).",
                )

    def test_all_allowed_streams_are_non_empty(self):
        for dept, sandbox in DEPARTMENT_REGISTRY.items():
            with self.subTest(dept=dept):
                self.assertGreater(len(sandbox.allowed_streams), 0)

    def test_all_allowed_tools_are_valid(self):
        for dept, sandbox in DEPARTMENT_REGISTRY.items():
            with self.subTest(dept=dept):
                self.assertTrue(sandbox.allowed_tools.issubset(ALL_WORKER_TOOLS))

    def test_all_allowed_tools_are_non_empty(self):
        for dept, sandbox in DEPARTMENT_REGISTRY.items():
            with self.subTest(dept=dept):
                self.assertGreater(len(sandbox.allowed_tools), 0)

    def test_execution_context_ids_are_stable_sandbox_ids(self):
        for dept, sandbox in DEPARTMENT_REGISTRY.items():
            with self.subTest(dept=dept):
                self.assertEqual(sandbox.execution_context_id, f"sandbox:{dept.value}")

    def test_memory_indexing_has_all_four_streams(self):
        sandbox = DEPARTMENT_REGISTRY[Department.MEMORY_INDEXING]
        self.assertEqual(sandbox.allowed_streams, frozenset(_ALL_STREAM_NAMES))

    def test_security_does_not_have_stream_d(self):
        """Security sandbox must not have cognitive identity stream."""
        sandbox = DEPARTMENT_REGISTRY[Department.SECURITY]
        self.assertNotIn(COLLECTION_COGNITIVE_IDENTITY, sandbox.allowed_streams)

    def test_strategic_planning_does_not_have_stream_a(self):
        """Strategic planning does not need code topologies."""
        sandbox = DEPARTMENT_REGISTRY[Department.STRATEGIC_PLANNING]
        self.assertNotIn(COLLECTION_CODE_TOPOLOGIES, sandbox.allowed_streams)

    def test_software_engineering_has_stream_a(self):
        sandbox = DEPARTMENT_REGISTRY[Department.SOFTWARE_ENGINEERING]
        self.assertIn(COLLECTION_CODE_TOPOLOGIES, sandbox.allowed_streams)

    def test_software_engineering_has_code_tools(self):
        sandbox = DEPARTMENT_REGISTRY[Department.SOFTWARE_ENGINEERING]
        self.assertIn(TOOL_CODE_STRUCTURE_ANALYZER, sandbox.allowed_tools)
        self.assertIn(TOOL_STYLE_FINGERPRINT_EXTRACTOR, sandbox.allowed_tools)

    def test_security_has_static_scan_tool(self):
        sandbox = DEPARTMENT_REGISTRY[Department.SECURITY]
        self.assertIn(TOOL_SECURITY_STATIC_SCAN, sandbox.allowed_tools)

    def test_memory_indexing_has_ingestion_tool(self):
        sandbox = DEPARTMENT_REGISTRY[Department.MEMORY_INDEXING]
        self.assertIn(TOOL_INGESTION_COORDINATOR, sandbox.allowed_tools)


# ---------------------------------------------------------------------------
# TestDepartmentWorkerSandbox
# ---------------------------------------------------------------------------


class TestDepartmentWorkerSandbox(unittest.TestCase):
    """Sandbox autonomy_level, assigned_agents, and success_conditions are valid."""

    def test_all_autonomy_levels_in_valid_range(self):
        for dept, sandbox in DEPARTMENT_REGISTRY.items():
            with self.subTest(dept=dept):
                self.assertGreaterEqual(sandbox.autonomy_level, 0)
                self.assertLessEqual(sandbox.autonomy_level, 4)

    def test_all_assigned_agents_non_empty(self):
        for dept, sandbox in DEPARTMENT_REGISTRY.items():
            with self.subTest(dept=dept):
                self.assertGreater(len(sandbox.assigned_agents), 0)

    def test_all_hard_success_conditions_non_empty(self):
        for dept, sandbox in DEPARTMENT_REGISTRY.items():
            with self.subTest(dept=dept):
                self.assertGreater(len(sandbox.hard_success_conditions), 0)

    def test_sandbox_is_frozen(self):
        """DepartmentWorkerSandbox must be immutable."""
        sandbox = DEPARTMENT_REGISTRY[Department.SOFTWARE_ENGINEERING]
        with self.assertRaises((AttributeError, TypeError)):
            sandbox.autonomy_level = 99  # type: ignore[misc]

    def test_memory_indexing_is_observe_only(self):
        """Memory indexing must have autonomy_level == 0 (Observe Only)."""
        sandbox = DEPARTMENT_REGISTRY[Department.MEMORY_INDEXING]
        self.assertEqual(sandbox.autonomy_level, 0)

    def test_software_engineering_autonomy_is_sandbox_simulation(self):
        sandbox = DEPARTMENT_REGISTRY[Department.SOFTWARE_ENGINEERING]
        self.assertEqual(sandbox.autonomy_level, 2)

    def test_department_field_matches_registry_key(self):
        for dept, sandbox in DEPARTMENT_REGISTRY.items():
            with self.subTest(dept=dept):
                self.assertEqual(sandbox.department, dept)

    def test_description_is_non_empty_string(self):
        for dept, sandbox in DEPARTMENT_REGISTRY.items():
            with self.subTest(dept=dept):
                self.assertIsInstance(sandbox.description, str)
                self.assertGreater(len(sandbox.description), 0)

    def test_can_access_stream_helper(self):
        sandbox = DEPARTMENT_REGISTRY[Department.SECURITY]
        self.assertTrue(sandbox.can_access_stream(COLLECTION_TECHNICAL_MASTERY))
        self.assertFalse(sandbox.can_access_stream(COLLECTION_COGNITIVE_IDENTITY))

    def test_can_use_tool_helper(self):
        sandbox = DEPARTMENT_REGISTRY[Department.STRATEGIC_PLANNING]
        self.assertTrue(sandbox.can_use_tool(TOOL_STRATEGIC_SUMMARY_BUILDER))
        self.assertFalse(sandbox.can_use_tool(TOOL_SECURITY_STATIC_SCAN))


# ---------------------------------------------------------------------------
# TestDepartmentHelpers
# ---------------------------------------------------------------------------


class TestDepartmentHelpers(unittest.TestCase):
    """get_sandbox() and department_from_string() helper functions."""

    def test_get_sandbox_returns_correct_sandbox(self):
        sandbox = get_sandbox(Department.ARCHITECTURE)
        self.assertEqual(sandbox.department, Department.ARCHITECTURE)

    def test_department_from_string_exact_match(self):
        dept = department_from_string("software_engineering")
        self.assertEqual(dept, Department.SOFTWARE_ENGINEERING)

    def test_department_from_string_strips_whitespace(self):
        dept = department_from_string("  security  ")
        self.assertEqual(dept, Department.SECURITY)

    def test_department_from_string_normalises_case(self):
        dept = department_from_string("ARCHITECTURE")
        self.assertEqual(dept, Department.ARCHITECTURE)

    def test_department_from_string_raises_on_unknown(self):
        with self.assertRaises(ValueError):
            department_from_string("quantum_computing")

    def test_department_from_string_raises_on_empty(self):
        with self.assertRaises(ValueError):
            department_from_string("")

    def test_all_departments_round_trip_through_string(self):
        for dept in Department:
            with self.subTest(dept=dept):
                result = department_from_string(dept.value)
                self.assertEqual(result, dept)


# ---------------------------------------------------------------------------
# TestTaskContractSchema
# ---------------------------------------------------------------------------


class TestTaskContractSchema(unittest.TestCase):
    """TaskContract serialises to the correct JSON shape (spec section 5)."""

    def _build(self, **overrides) -> TaskContract:
        defaults = dict(
            objective="Build secure local token encryption module",
            department=Department.SOFTWARE_ENGINEERING,
            assigned_agents=["architecture_node", "code_specialist"],
            autonomy_permission_level=2,
            hard_success_conditions=[
                "syntax_tree_validity == true",
                "security_vulnerability_scan == clean",
                "unit_test_compilation == success",
            ],
            epoch=1784370192,
        )
        defaults.update(overrides)
        return TaskContract.build(**defaults)

    def test_contract_id_starts_with_txn(self):
        contract = self._build()
        self.assertTrue(contract.contract_id.startswith("TXN_"))

    def test_contract_id_contains_epoch(self):
        contract = self._build(epoch=1784370192)
        self.assertIn("1784370192", contract.contract_id)

    def test_objective_preserved_verbatim(self):
        contract = self._build(objective="Refactor UserBloc to Cubit pattern")
        self.assertEqual(contract.objective, "Refactor UserBloc to Cubit pattern")

    def test_department_is_department_enum(self):
        contract = self._build()
        self.assertIsInstance(contract.department, Department)

    def test_to_dict_department_is_string(self):
        contract = self._build()
        d = contract.to_dict()
        self.assertIsInstance(d["department"], str)
        self.assertEqual(d["department"], "software_engineering")

    def test_to_dict_has_all_spec_keys(self):
        """Must have exactly the six keys from spec section 5."""
        contract = self._build()
        d = contract.to_dict()
        expected_keys = {
            "contract_id",
            "objective",
            "department",
            "assigned_agents",
            "autonomy_permission_level",
            "hard_success_conditions",
            "created_at",
        }
        self.assertEqual(set(d.keys()), expected_keys)

    def test_to_dict_is_json_serialisable(self):
        contract = self._build()
        serialised = json.dumps(contract.to_dict())
        self.assertIsInstance(serialised, str)

    def test_assigned_agents_is_list_of_strings(self):
        contract = self._build()
        d = contract.to_dict()
        self.assertIsInstance(d["assigned_agents"], list)
        for agent in d["assigned_agents"]:
            self.assertIsInstance(agent, str)

    def test_hard_success_conditions_is_list(self):
        contract = self._build()
        d = contract.to_dict()
        self.assertIsInstance(d["hard_success_conditions"], list)

    def test_created_at_is_int(self):
        contract = self._build()
        self.assertIsInstance(contract.created_at, int)


# ---------------------------------------------------------------------------
# TestTaskContractValidation
# ---------------------------------------------------------------------------


class TestTaskContractValidation(unittest.TestCase):
    """Pydantic field validators reject invalid contracts."""

    def test_rejects_missing_txn_prefix(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            TaskContract(
                contract_id="INVALID_784370192",
                objective="Do something",
                department=Department.SECURITY,
                assigned_agents=["security_scanner"],
                autonomy_permission_level=1,
                hard_success_conditions=["static_analysis_clean == true"],
                created_at=1784370192,
            )

    def test_rejects_empty_objective(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            TaskContract.build(
                objective="",
                department=Department.SECURITY,
                assigned_agents=["security_scanner"],
                autonomy_permission_level=1,
                hard_success_conditions=["cond"],
            )

    def test_rejects_autonomy_level_above_4(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            TaskContract.build(
                objective="Task",
                department=Department.SOFTWARE_ENGINEERING,
                assigned_agents=["agent"],
                autonomy_permission_level=5,
                hard_success_conditions=["cond"],
            )

    def test_rejects_negative_autonomy_level(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            TaskContract.build(
                objective="Task",
                department=Department.SOFTWARE_ENGINEERING,
                assigned_agents=["agent"],
                autonomy_permission_level=-1,
                hard_success_conditions=["cond"],
            )

    def test_rejects_empty_assigned_agents(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            TaskContract.build(
                objective="Task",
                department=Department.SOFTWARE_ENGINEERING,
                assigned_agents=[],
                autonomy_permission_level=2,
                hard_success_conditions=["cond"],
            )

    def test_rejects_extra_fields(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            TaskContract(
                contract_id="TXN_123",
                objective="Task",
                department=Department.SOFTWARE_ENGINEERING,
                assigned_agents=["agent"],
                autonomy_permission_level=2,
                hard_success_conditions=["cond"],
                created_at=12345,
                unknown_extra_field="should be rejected",
            )


# ---------------------------------------------------------------------------
# TestTaskContractBuildFactory
# ---------------------------------------------------------------------------


class TestTaskContractBuildFactory(unittest.TestCase):
    """TaskContract.build() auto-generates contract_id and created_at."""

    def test_build_generates_contract_id(self):
        contract = TaskContract.build(
            objective="Test task",
            department=Department.ARCHITECTURE,
            assigned_agents=["architecture_node"],
            autonomy_permission_level=2,
            hard_success_conditions=["done == true"],
        )
        self.assertTrue(contract.contract_id.startswith("TXN_"))

    def test_build_with_explicit_epoch(self):
        contract = TaskContract.build(
            objective="Test task",
            department=Department.ARCHITECTURE,
            assigned_agents=["architecture_node"],
            autonomy_permission_level=2,
            hard_success_conditions=["done == true"],
            epoch=1784370000,
        )
        self.assertEqual(contract.contract_id, "TXN_1784370000")
        self.assertEqual(contract.created_at, 1784370000)


# ---------------------------------------------------------------------------
# TestRouterResultSchema
# ---------------------------------------------------------------------------


class TestRouterResultSchema(unittest.TestCase):
    """RouterResult wraps TaskContract with metadata fields."""

    def _make_result(self, **overrides) -> RouterResult:
        contract = TaskContract.build(
            objective="Test",
            department=Department.SOFTWARE_ENGINEERING,
            assigned_agents=["code_specialist"],
            autonomy_permission_level=2,
            hard_success_conditions=["cond"],
            epoch=1784370192,
        )
        defaults = dict(
            contract=contract,
            raw_classification="software_engineering",
            confidence_hint="high",
            model_used="phi3:mini",
            routing_latency_ms=150,
            fallback_used=False,
        )
        defaults.update(overrides)
        return RouterResult(**defaults)

    def test_result_contains_task_contract(self):
        result = self._make_result()
        self.assertIsInstance(result.contract, TaskContract)

    def test_confidence_hint_high_valid(self):
        result = self._make_result(confidence_hint="high")
        self.assertEqual(result.confidence_hint, "high")

    def test_confidence_hint_medium_valid(self):
        result = self._make_result(confidence_hint="medium")
        self.assertEqual(result.confidence_hint, "medium")

    def test_confidence_hint_low_valid(self):
        result = self._make_result(confidence_hint="low")
        self.assertEqual(result.confidence_hint, "low")

    def test_fallback_used_false_by_default(self):
        result = self._make_result()
        self.assertFalse(result.fallback_used)

    def test_fallback_used_true(self):
        result = self._make_result(fallback_used=True)
        self.assertTrue(result.fallback_used)

    def test_to_dict_has_contract_key(self):
        result = self._make_result()
        d = result.to_dict()
        self.assertIn("contract", d)
        self.assertIsInstance(d["contract"], dict)

    def test_to_dict_is_json_serialisable(self):
        result = self._make_result()
        serialised = json.dumps(result.to_dict())
        self.assertIsInstance(serialised, str)

    def test_routing_latency_ms_non_negative(self):
        result = self._make_result(routing_latency_ms=0)
        self.assertGreaterEqual(result.routing_latency_ms, 0)


# ---------------------------------------------------------------------------
# TestRouterResultValidation
# ---------------------------------------------------------------------------


class TestRouterResultValidation(unittest.TestCase):
    """Invalid RouterResult fields are rejected by Pydantic."""

    def _base_contract(self) -> TaskContract:
        return TaskContract.build(
            objective="Test",
            department=Department.SOFTWARE_ENGINEERING,
            assigned_agents=["agent"],
            autonomy_permission_level=2,
            hard_success_conditions=["cond"],
        )

    def test_rejects_invalid_confidence_hint(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            RouterResult(
                contract=self._base_contract(),
                raw_classification="software_engineering",
                confidence_hint="very_sure",  # invalid
                model_used="phi3:mini",
                routing_latency_ms=100,
            )

    def test_rejects_negative_latency(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            RouterResult(
                contract=self._base_contract(),
                raw_classification="software_engineering",
                confidence_hint="high",
                model_used="phi3:mini",
                routing_latency_ms=-1,
            )

    def test_rejects_extra_fields(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            RouterResult(
                contract=self._base_contract(),
                raw_classification="x",
                confidence_hint="low",
                model_used="phi3:mini",
                routing_latency_ms=0,
                illegal_extra="oops",
            )


# ---------------------------------------------------------------------------
# TestWorkerTaskHandoffSchema
# ---------------------------------------------------------------------------


class TestWorkerTaskHandoffSchema(unittest.TestCase):
    """Router -> worker task handoff JSON schema."""

    def _contract(self) -> TaskContract:
        sandbox = get_sandbox(Department.SOFTWARE_ENGINEERING)
        return TaskContract.build(
            objective="Build secure local token encryption module",
            department=Department.SOFTWARE_ENGINEERING,
            assigned_agents=list(sandbox.assigned_agents),
            autonomy_permission_level=sandbox.autonomy_level,
            hard_success_conditions=list(sandbox.hard_success_conditions),
            epoch=1784370192,
        )

    def test_build_uses_department_sandbox_scope(self):
        handoff = WorkerTaskHandoff.build(self._contract())
        sandbox = get_sandbox(Department.SOFTWARE_ENGINEERING)
        self.assertEqual(set(handoff.allowed_streams), set(sandbox.allowed_streams))
        self.assertEqual(set(handoff.allowed_tools), set(sandbox.allowed_tools))

    def test_execution_context_id_matches_department(self):
        handoff = WorkerTaskHandoff.build(self._contract())
        self.assertEqual(handoff.execution_context_id, "sandbox:software_engineering")

    def test_to_dict_is_json_serialisable(self):
        handoff = WorkerTaskHandoff.build(self._contract())
        json.dumps(handoff.to_dict())

    def test_to_dict_has_exact_keys(self):
        handoff = WorkerTaskHandoff.build(self._contract())
        self.assertEqual(
            set(handoff.to_dict().keys()),
            {"contract", "execution_context_id", "allowed_streams", "allowed_tools"},
        )

    def test_rejects_unknown_allowed_tool(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            WorkerTaskHandoff(
                contract=self._contract(),
                execution_context_id="sandbox:software_engineering",
                allowed_streams=[COLLECTION_CODE_TOPOLOGIES],
                allowed_tools=["cloud_api_tool"],
            )


# ---------------------------------------------------------------------------
# TestWorkerResultReportSchema
# ---------------------------------------------------------------------------


class TestWorkerResultReportSchema(unittest.TestCase):
    """Worker -> router result report JSON schema."""

    def _handoff(self) -> WorkerTaskHandoff:
        sandbox = get_sandbox(Department.SECURITY)
        contract = TaskContract.build(
            objective="Scan local storage for plaintext secrets",
            department=Department.SECURITY,
            assigned_agents=list(sandbox.assigned_agents),
            autonomy_permission_level=sandbox.autonomy_level,
            hard_success_conditions=list(sandbox.hard_success_conditions),
            epoch=1784370192,
        )
        return WorkerTaskHandoff.build(contract)

    def test_build_from_handoff_sets_contract_and_context(self):
        handoff = self._handoff()
        report = WorkerResultReport.build(
            handoff,
            status="success",
            summary="Static scan completed.",
            streams_accessed=[COLLECTION_TECHNICAL_MASTERY],
            tools_used=[TOOL_SECURITY_STATIC_SCAN],
            success_conditions_met=["static_analysis_clean == true"],
            completed_at=1784370299,
        )
        self.assertEqual(report.contract_id, handoff.contract.contract_id)
        self.assertEqual(report.execution_context_id, handoff.execution_context_id)

    def test_to_dict_has_exact_keys(self):
        report = WorkerResultReport.build(
            self._handoff(),
            status="blocked",
            summary="Waiting for local scan input.",
            completed_at=1784370299,
        )
        self.assertEqual(
            set(report.to_dict().keys()),
            {
                "contract_id",
                "department",
                "execution_context_id",
                "status",
                "summary",
                "artifacts",
                "streams_accessed",
                "tools_used",
                "success_conditions_met",
                "error_message",
                "completed_at",
            },
        )

    def test_validate_against_handoff_accepts_scoped_report(self):
        handoff = self._handoff()
        report = WorkerResultReport.build(
            handoff,
            status="success",
            summary="Done.",
            streams_accessed=[COLLECTION_TECHNICAL_MASTERY],
            tools_used=[TOOL_SECURITY_STATIC_SCAN],
            success_conditions_met=["static_analysis_clean == true"],
            completed_at=1784370299,
        )
        self.assertTrue(report.validate_against_handoff(handoff))

    def test_validate_against_handoff_rejects_stream_escape(self):
        handoff = self._handoff()
        report = WorkerResultReport.build(
            handoff,
            status="success",
            summary="Done.",
            streams_accessed=[COLLECTION_COGNITIVE_IDENTITY],
            completed_at=1784370299,
        )
        self.assertFalse(report.validate_against_handoff(handoff))

    def test_validate_against_handoff_rejects_tool_escape(self):
        handoff = self._handoff()
        report = WorkerResultReport.build(
            handoff,
            status="success",
            summary="Done.",
            tools_used=[TOOL_STRATEGIC_SUMMARY_BUILDER],
            completed_at=1784370299,
        )
        self.assertFalse(report.validate_against_handoff(handoff))

    def test_rejects_empty_summary(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            WorkerResultReport.build(
                self._handoff(),
                status="failed",
                summary="",
                completed_at=1784370299,
            )

    def test_rejects_invalid_status(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            WorkerResultReport(
                contract_id="TXN_1784370192",
                department=Department.SECURITY,
                execution_context_id="sandbox:security",
                status="maybe",
                summary="Done.",
                completed_at=1784370299,
            )


# ---------------------------------------------------------------------------
# TestModelGatewayGenerate
# ---------------------------------------------------------------------------


class TestModelGatewayGenerate(unittest.TestCase):
    """OllamaModelGateway.generate() calls /api/generate and returns GenerationResponse."""

    def test_generate_posts_to_correct_endpoint(self):
        with patch("abm.orchestrator.model_gateway.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "response": '{"department": "security", "confidence": "high"}',
                "model": "phi3:mini",
            }
            mock_post.return_value = mock_resp

            gw = OllamaModelGateway(model="phi3:mini", host="127.0.0.1", port=11434)
            result = gw.generate("classify this")

        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        self.assertIn("/api/generate", call_url)
        self.assertIn("127.0.0.1", call_url)

    def test_generate_returns_generation_response(self):
        with patch("abm.orchestrator.model_gateway.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"response": "hello", "model": "phi3:mini"}
            mock_post.return_value = mock_resp

            gw = OllamaModelGateway()
            result = gw.generate("test prompt")

        self.assertIsInstance(result, GenerationResponse)
        self.assertEqual(result.text, "hello")
        self.assertGreaterEqual(result.latency_ms, 0)

    def test_generate_sends_stream_false(self):
        with patch("abm.orchestrator.model_gateway.requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"response": "x", "model": "phi3:mini"}
            mock_post.return_value = mock_resp

            gw = OllamaModelGateway()
            gw.generate("test")

        payload = mock_post.call_args[1]["json"]
        self.assertFalse(payload["stream"])

    def test_generate_raises_value_error_on_empty_prompt(self):
        gw = OllamaModelGateway()
        with self.assertRaises(ValueError):
            gw.generate("")

    def test_generate_raises_value_error_on_whitespace_prompt(self):
        gw = OllamaModelGateway()
        with self.assertRaises(ValueError):
            gw.generate("   ")


# ---------------------------------------------------------------------------
# TestModelGatewayErrors
# ---------------------------------------------------------------------------


class TestModelGatewayErrors(unittest.TestCase):
    """ModelGatewayError is raised on connection failure and timeout."""

    def test_raises_model_gateway_error_on_connection_error(self):
        import requests as req_lib
        with patch(
            "abm.orchestrator.model_gateway.requests.post",
            side_effect=req_lib.exceptions.ConnectionError("refused"),
        ):
            gw = OllamaModelGateway()
            with self.assertRaises(ModelGatewayError):
                gw.generate("test")

    def test_raises_model_gateway_error_on_timeout(self):
        import requests as req_lib
        with patch(
            "abm.orchestrator.model_gateway.requests.post",
            side_effect=req_lib.exceptions.Timeout("timed out"),
        ):
            gw = OllamaModelGateway()
            with self.assertRaises(ModelGatewayError):
                gw.generate("test")

    def test_model_gateway_error_is_runtime_error_subclass(self):
        self.assertTrue(issubclass(ModelGatewayError, RuntimeError))


# ---------------------------------------------------------------------------
# TestModelGatewayAvailability
# ---------------------------------------------------------------------------


class TestModelGatewayAvailability(unittest.TestCase):
    """is_available() returns bool and never raises."""

    def test_is_available_true_on_2xx(self):
        with patch("abm.orchestrator.model_gateway.requests.get") as mock_get:
            mock_get.return_value = MagicMock(status_code=200)
            gw = OllamaModelGateway()
            self.assertTrue(gw.is_available())

    def test_is_available_false_on_connection_error(self):
        import requests as req_lib
        with patch(
            "abm.orchestrator.model_gateway.requests.get",
            side_effect=req_lib.exceptions.ConnectionError(),
        ):
            gw = OllamaModelGateway()
            self.assertFalse(gw.is_available())

    def test_is_available_never_raises(self):
        with patch(
            "abm.orchestrator.model_gateway.requests.get",
            side_effect=Exception("unexpected"),
        ):
            gw = OllamaModelGateway()
            try:
                result = gw.is_available()
            except Exception as exc:
                self.fail(f"is_available() raised unexpectedly: {exc}")

    def test_default_model_is_phi3_mini(self):
        self.assertEqual(DEFAULT_CLASSIFICATION_MODEL, "phi3:mini")


# ---------------------------------------------------------------------------
# TestClassificationRouterNeverGenerates
# ---------------------------------------------------------------------------


class TestClassificationRouterNeverGenerates(unittest.TestCase):
    """
    ClassificationRouter is programmatically banned from generating content.
    It must not expose generate(), write(), respond(), explain(), or complete().
    """

    BANNED_METHODS = ("generate", "write", "respond", "explain", "complete", "produce")

    def setUp(self):
        self.router = ClassificationRouter(gateway=_make_mock_gateway())

    def test_no_generate_method(self):
        self.assertFalse(hasattr(self.router, "generate"))

    def test_no_write_method(self):
        self.assertFalse(hasattr(self.router, "write"))

    def test_no_respond_method(self):
        self.assertFalse(hasattr(self.router, "respond"))

    def test_no_explain_method(self):
        self.assertFalse(hasattr(self.router, "explain"))

    def test_no_complete_method(self):
        self.assertFalse(hasattr(self.router, "complete"))

    def test_no_produce_method(self):
        self.assertFalse(hasattr(self.router, "produce"))

    def test_only_two_public_action_methods(self):
        """
        ClassificationRouter exposes exactly two public methods:
        classify() and is_available().
        """
        public_methods = [
            name for name, _ in inspect.getmembers(self.router, predicate=inspect.ismethod)
            if not name.startswith("_")
        ]
        self.assertIn("classify", public_methods)
        self.assertIn("is_available", public_methods)
        # Verify no banned generation methods snuck in
        for banned in self.BANNED_METHODS:
            with self.subTest(method=banned):
                self.assertNotIn(banned, public_methods)


# ---------------------------------------------------------------------------
# TestClassificationRouterClassify
# ---------------------------------------------------------------------------


class TestClassificationRouterClassify(unittest.TestCase):
    """classify() returns a RouterResult and never raises."""

    def setUp(self):
        self.gateway = _make_mock_gateway(GOOD_JSON_RESPONSE)
        self.router = ClassificationRouter(gateway=self.gateway)

    def test_classify_returns_router_result(self):
        result = self.router.classify("Build a Flutter BLoC authentication module")
        self.assertIsInstance(result, RouterResult)

    def test_classify_result_contains_task_contract(self):
        result = self.router.classify("Build a Flutter BLoC authentication module")
        self.assertIsInstance(result.contract, TaskContract)

    def test_classify_contract_id_starts_with_txn(self):
        result = self.router.classify("Fix navigation bug in home screen")
        self.assertTrue(result.contract.contract_id.startswith("TXN_"))

    def test_classify_department_is_valid_enum(self):
        result = self.router.classify("Fix navigation bug")
        self.assertIsInstance(result.contract.department, Department)

    def test_classify_model_used_is_gateway_model(self):
        result = self.router.classify("Some task")
        self.assertEqual(result.model_used, "phi3:mini")

    def test_classify_routing_latency_ms_non_negative(self):
        result = self.router.classify("Some task")
        self.assertGreaterEqual(result.routing_latency_ms, 0)

    def test_classify_calls_gateway_generate_once(self):
        self.router.classify("Analyse security of local storage")
        self.gateway.generate.assert_called_once()

    def test_classify_objective_is_original_task_description(self):
        task = "Build a secure encryption wrapper for local tokens"
        result = self.router.classify(task)
        self.assertEqual(result.contract.objective, task)

    def test_classify_assigns_agents_from_registry(self):
        result = self.router.classify("Code review")
        expected_sandbox = get_sandbox(result.contract.department)
        self.assertEqual(
            result.contract.assigned_agents,
            list(expected_sandbox.assigned_agents),
        )

    def test_classify_autonomy_level_matches_registry(self):
        result = self.router.classify("Code review")
        expected_sandbox = get_sandbox(result.contract.department)
        self.assertEqual(
            result.contract.autonomy_permission_level,
            expected_sandbox.autonomy_level,
        )

    def test_classify_strategic_task_routed_correctly(self):
        gateway = _make_mock_gateway(STRATEGIC_JSON_RESPONSE)
        router = ClassificationRouter(gateway=gateway)
        result = router.classify("Define Q3 OKRs for FirstMinds")
        self.assertEqual(result.contract.department, Department.STRATEGIC_PLANNING)


# ---------------------------------------------------------------------------
# TestClassificationRouterFallback
# ---------------------------------------------------------------------------


class TestClassificationRouterFallback(unittest.TestCase):
    """Gateway failure → fallback result, fallback_used=True, never raises."""

    def test_fallback_on_model_gateway_error(self):
        gw = _make_mock_gateway()
        gw.generate.side_effect = ModelGatewayError("Ollama unavailable")
        router = ClassificationRouter(gateway=gw)
        result = router.classify("Build something")
        self.assertTrue(result.fallback_used)
        self.assertEqual(result.confidence_hint, "low")
        self.assertEqual(result.contract.department, FALLBACK_DEPARTMENT)

    def test_fallback_never_raises_on_gateway_error(self):
        gw = _make_mock_gateway()
        gw.generate.side_effect = ModelGatewayError("down")
        router = ClassificationRouter(gateway=gw)
        try:
            router.classify("Task")
        except Exception as exc:
            self.fail(f"classify() raised unexpectedly on gateway error: {exc}")

    def test_fallback_department_is_software_engineering(self):
        self.assertEqual(FALLBACK_DEPARTMENT, Department.SOFTWARE_ENGINEERING)


# ---------------------------------------------------------------------------
# TestClassificationRouterBadJSON
# ---------------------------------------------------------------------------


class TestClassificationRouterBadJSON(unittest.TestCase):
    """Non-JSON or malformed model output → fallback result."""

    def _router_with_response(self, text: str) -> ClassificationRouter:
        gw = _make_mock_gateway(text)
        return ClassificationRouter(gateway=gw)

    def test_plain_text_response_uses_fallback(self):
        router = self._router_with_response("I think this is a software task.")
        result = router.classify("Build something")
        self.assertTrue(result.fallback_used)

    def test_empty_response_uses_fallback(self):
        router = self._router_with_response("")
        result = router.classify("Build something")
        self.assertTrue(result.fallback_used)

    def test_broken_json_uses_fallback(self):
        router = self._router_with_response('{"department": "software_eng')
        result = router.classify("Build something")
        self.assertTrue(result.fallback_used)

    def test_bad_json_never_raises(self):
        router = self._router_with_response("not json at all!!!")
        try:
            router.classify("Build something")
        except Exception as exc:
            self.fail(f"classify() raised on bad JSON: {exc}")


# ---------------------------------------------------------------------------
# TestClassificationRouterUnknownDept
# ---------------------------------------------------------------------------


class TestClassificationRouterUnknownDept(unittest.TestCase):
    """Unknown department string from model → fallback, no raise."""

    def test_unknown_department_uses_fallback(self):
        bad_response = json.dumps({"department": "quantum_computing", "confidence": "high"})
        gw = _make_mock_gateway(bad_response)
        router = ClassificationRouter(gateway=gw)
        result = router.classify("Something odd")
        self.assertTrue(result.fallback_used)
        self.assertEqual(result.contract.department, FALLBACK_DEPARTMENT)

    def test_unknown_department_never_raises(self):
        bad_response = json.dumps({"department": "nonexistent", "confidence": "high"})
        gw = _make_mock_gateway(bad_response)
        router = ClassificationRouter(gateway=gw)
        try:
            router.classify("Something")
        except Exception as exc:
            self.fail(f"classify() raised on unknown department: {exc}")


# ---------------------------------------------------------------------------
# TestClassificationRouterEmptyInput
# ---------------------------------------------------------------------------


class TestClassificationRouterEmptyInput(unittest.TestCase):
    """Empty or whitespace-only task descriptions → fallback, never raises."""

    def setUp(self):
        self.router = ClassificationRouter(gateway=_make_mock_gateway())

    def test_empty_string_returns_fallback(self):
        result = self.router.classify("")
        self.assertTrue(result.fallback_used)

    def test_whitespace_only_returns_fallback(self):
        result = self.router.classify("   \n  \t  ")
        self.assertTrue(result.fallback_used)

    def test_empty_input_never_raises(self):
        try:
            self.router.classify("")
        except Exception as exc:
            self.fail(f"classify('') raised: {exc}")

    def test_empty_input_fallback_has_valid_contract(self):
        result = self.router.classify("")
        self.assertIsInstance(result.contract, TaskContract)
        self.assertTrue(result.contract.contract_id.startswith("TXN_"))


# ---------------------------------------------------------------------------
# TestClassificationRouterContractShape
# ---------------------------------------------------------------------------


class TestClassificationRouterContractShape(unittest.TestCase):
    """The contract returned by classify() matches spec section 5 JSON shape."""

    def test_contract_to_dict_matches_spec_keys(self):
        gw = _make_mock_gateway(GOOD_JSON_RESPONSE)
        router = ClassificationRouter(gateway=gw)
        result = router.classify("Implement OAuth2 token refresh")
        d = result.contract.to_dict()
        expected_keys = {
            "contract_id", "objective", "department",
            "assigned_agents", "autonomy_permission_level",
            "hard_success_conditions", "created_at",
        }
        self.assertEqual(set(d.keys()), expected_keys)

    def test_hard_success_conditions_is_non_empty_list(self):
        gw = _make_mock_gateway(GOOD_JSON_RESPONSE)
        router = ClassificationRouter(gateway=gw)
        result = router.classify("Fix login flow")
        self.assertIsInstance(result.contract.hard_success_conditions, list)
        self.assertGreater(len(result.contract.hard_success_conditions), 0)


# ---------------------------------------------------------------------------
# TestRouterStreamDContextInjection
# ---------------------------------------------------------------------------


class TestRouterStreamDContextInjection(unittest.TestCase):
    """Optional Stream D context queried read-only; gracefully skipped on error."""

    def test_context_injection_queries_stream_d(self):
        gw = _make_mock_gateway(GOOD_JSON_RESPONSE)
        ctrl = _make_mock_controller()
        emb = _make_mock_embedder()
        router = ClassificationRouter(gateway=gw, controller=ctrl, embedder=emb)
        router.classify("Build encryption module")
        ctrl.query_collection.assert_called_once()
        call_args = ctrl.query_collection.call_args
        collection_arg = call_args[0][0] if call_args[0] else call_args[1].get("collection_name", "")
        # Should query Stream D
        self.assertEqual(collection_arg, COLLECTION_COGNITIVE_IDENTITY)

    def test_context_injection_never_calls_add_document(self):
        """Router must never write to ChromaDB — read-only during classification."""
        gw = _make_mock_gateway(GOOD_JSON_RESPONSE)
        ctrl = _make_mock_controller()
        emb = _make_mock_embedder()
        router = ClassificationRouter(gateway=gw, controller=ctrl, embedder=emb)
        router.classify("Build something")
        ctrl.add_document.assert_not_called()

    def test_context_injection_skipped_when_no_controller(self):
        gw = _make_mock_gateway(GOOD_JSON_RESPONSE)
        router = ClassificationRouter(gateway=gw, controller=None, embedder=None)
        # Should complete without error
        result = router.classify("Design new module")
        self.assertIsInstance(result, RouterResult)

    def test_context_injection_skipped_gracefully_on_query_error(self):
        gw = _make_mock_gateway(GOOD_JSON_RESPONSE)
        ctrl = _make_mock_controller()
        ctrl.query_collection.side_effect = RuntimeError("ChromaDB down")
        emb = _make_mock_embedder()
        router = ClassificationRouter(gateway=gw, controller=ctrl, embedder=emb)
        try:
            result = router.classify("Build something")
        except Exception as exc:
            self.fail(f"classify() raised on context error: {exc}")


# ---------------------------------------------------------------------------
# TestRouterV01V02Boundary
# ---------------------------------------------------------------------------


class TestRouterV01V02Boundary(unittest.TestCase):
    """
    ClassificationRouter never accesses private v0.1/v0.2 internals.
    It only uses the public API (query_collection, embed).
    """

    def test_router_does_not_access_internal_collections_dict(self):
        gw = _make_mock_gateway(GOOD_JSON_RESPONSE)
        ctrl = _make_mock_controller()
        emb = _make_mock_embedder()
        router = ClassificationRouter(gateway=gw, controller=ctrl, embedder=emb)
        router.classify("Test task")

        accessed = [str(c) for c in ctrl.method_calls]
        private_accesses = [a for a in accessed if "_collections" in a]
        self.assertEqual(
            private_accesses, [],
            "ClassificationRouter must not access _collections directly.",
        )

    def test_router_only_calls_query_collection_not_add_document(self):
        gw = _make_mock_gateway(GOOD_JSON_RESPONSE)
        ctrl = _make_mock_controller()
        emb = _make_mock_embedder()
        router = ClassificationRouter(gateway=gw, controller=ctrl, embedder=emb)
        router.classify("Test task")
        ctrl.add_document.assert_not_called()


# ---------------------------------------------------------------------------
# TestV01V02V03RegressionGate
# ---------------------------------------------------------------------------


class TestV01V02V03RegressionGate(unittest.TestCase):
    """
    Regression gate: all v0.1, v0.2, and v0.3 constants must be unchanged.
    No previous phase's interface is allowed to drift.
    """

    # v0.1 regressions
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

    # v0.2 regressions
    def test_v02_code_extensions_unchanged(self):
        expected = {".py", ".dart", ".kt", ".java", ".js", ".css", ".html"}
        self.assertEqual(CODE_EXTENSIONS, expected)

    # v0.3 constants
    def test_fallback_department_is_software_engineering(self):
        self.assertEqual(FALLBACK_DEPARTMENT, Department.SOFTWARE_ENGINEERING)

    def test_confidence_hints_set_is_correct(self):
        self.assertEqual(CONFIDENCE_HINTS, {"high", "medium", "low"})

    def test_default_classification_model_is_phi3_mini(self):
        self.assertEqual(DEFAULT_CLASSIFICATION_MODEL, "phi3:mini")

    def test_max_task_description_chars_is_2000(self):
        self.assertEqual(MAX_TASK_DESCRIPTION_CHARS, 2000)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
