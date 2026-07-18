"""
tests/test_phase_v04_gate.py
=============================
Phase v0.4 Gate Tests — Safe Action Sandbox
Spec Reference: ABM_SPEC.md sections 6, 7, and 10 (item 4)

Hard gate proofs (must be 100% green before Phase v0.5):
  1. TestSandboxIsolationTeardownGate — containers are isolated and torn down
     after each task; no leaks; no shared state between runs
  2. TestCompilerTestCheckRejectionGate — compile/test failures produce
     non-zero exit codes that the check loop surfaces as rejection
  3. TestConfidenceFormulaExactGate — C matches the spec formula exactly,
     including 0.80 / 0.90 / 0.85 boundary edge cases
  4. TestFloorBreachQuarantinesHighCGate — floor breaches quarantine even
     when composite C is high

Supporting contract tests cover Docker lifecycle details, quarantine file
content, and prior-phase regression. Phase v0.4 does NOT advance to v0.5
until this file is green.
"""

from __future__ import annotations

import io
import os
import shutil
import sys
import tarfile
import unittest
from unittest.mock import MagicMock, call, patch

from pydantic import ValidationError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# ---------------------------------------------------------------------------
# v0.1 / v0.2 / v0.3 imports (must remain unchanged)
# ---------------------------------------------------------------------------
from abm.memory.chroma_controller import ALL_COLLECTIONS
from abm.companion.file_watcher import CODE_EXTENSIONS
from abm.orchestrator.departments import Department
from abm.orchestrator.task_contract import TaskContract

# ---------------------------------------------------------------------------
# v0.4 imports
# ---------------------------------------------------------------------------
from abm.sandbox.container import DockerSandbox
from abm.sandbox.execution_loop import SandboxCheckLoop
from abm.sandbox.models import ExecutionResult, GateResult, ValidationScores
from abm.sandbox.validation_gate import MultiFactorGate

_TEST_QUARANTINE_DIR = "tests/temp_quarantine_v04"


def _contract() -> TaskContract:
    return TaskContract.build(
        objective="v0.4 gate task",
        department=Department.SOFTWARE_ENGINEERING,
        assigned_agents=["code_specialist"],
        autonomy_permission_level=2,
        hard_success_conditions=["unit_test_compilation == success"],
        epoch=1784370192,
    )


def _expected_c(m: float, t: float, s: float, test: float, p: float) -> float:
    """Spec section 6 formula, verbatim."""
    return (0.30 * m) + (0.25 * t) + (0.20 * s) + (0.15 * test) + (0.10 * p)


def _mock_sandbox_stack(mock_from_env: MagicMock) -> tuple[MagicMock, MagicMock]:
    mock_client = MagicMock()
    mock_from_env.return_value = mock_client
    mock_container = MagicMock()
    mock_container.id = "ctr_fresh"
    mock_client.containers.run.return_value = mock_container
    return mock_client, mock_container


# ---------------------------------------------------------------------------
# HARD GATE 1 — isolation + teardown; no leaks; no shared state
# ---------------------------------------------------------------------------


class TestSandboxIsolationTeardownGate(unittest.TestCase):
    """
    Prove sandbox containers are isolated and torn down after each task —
    no leaked containers, no shared state between runs.
    """

    @patch("abm.sandbox.container.docker.from_env")
    def test_each_run_creates_a_fresh_container(self, mock_from_env):
        mock_client = MagicMock()
        mock_from_env.return_value = mock_client
        first = MagicMock(id="ctr_1")
        second = MagicMock(id="ctr_2")
        mock_client.containers.run.side_effect = [first, second]

        with DockerSandbox() as sb1:
            self.assertIs(sb1.container, first)
        with DockerSandbox() as sb2:
            self.assertIs(sb2.container, second)

        self.assertEqual(mock_client.containers.run.call_count, 2)
        self.assertIsNot(first, second)

    @patch("abm.sandbox.container.docker.from_env")
    def test_each_run_tears_down_its_own_container(self, mock_from_env):
        mock_client = MagicMock()
        mock_from_env.return_value = mock_client
        first = MagicMock(id="ctr_1")
        second = MagicMock(id="ctr_2")
        mock_client.containers.run.side_effect = [first, second]

        with DockerSandbox():
            pass
        with DockerSandbox():
            pass

        first.stop.assert_called_once_with(timeout=1)
        first.remove.assert_called_once_with(force=True)
        second.stop.assert_called_once_with(timeout=1)
        second.remove.assert_called_once_with(force=True)
        self.assertEqual(mock_client.close.call_count, 2)

    @patch("abm.sandbox.container.docker.from_env")
    def test_teardown_runs_even_when_execute_raises(self, mock_from_env):
        mock_client, mock_container = _mock_sandbox_stack(mock_from_env)
        mock_client.api.exec_create.side_effect = RuntimeError("exec boom")

        with self.assertRaises(RuntimeError):
            with DockerSandbox() as sandbox:
                sandbox.execute_command("python -m compileall /app")

        mock_container.stop.assert_called_once()
        mock_container.remove.assert_called_once_with(force=True)
        mock_client.close.assert_called_once()

    @patch("abm.sandbox.container.docker.from_env")
    def test_container_starts_with_network_none_isolation(self, mock_from_env):
        mock_client, _ = _mock_sandbox_stack(mock_from_env)
        with DockerSandbox():
            pass
        kwargs = mock_client.containers.run.call_args.kwargs
        self.assertEqual(kwargs["network_mode"], "none")
        self.assertTrue(kwargs["detach"])
        self.assertEqual(kwargs["mem_limit"], "512m")

    @patch("abm.sandbox.container.docker.from_env")
    def test_sequential_runs_do_not_share_write_state(self, mock_from_env):
        """
        Each evaluate_code call uses a fresh sandbox factory instance —
        files written in run A are never present on run B's container.
        """
        containers: list[MagicMock] = []

        def factory() -> MagicMock:
            sb = MagicMock()
            sb.__enter__.return_value = sb
            sb.__exit__.return_value = None
            sb.execute_command.return_value = ExecutionResult(
                exit_code=0, stdout="ok", stderr="", execution_time_ms=1
            )
            containers.append(sb)
            return sb

        loop = SandboxCheckLoop(sandbox_factory=factory)
        loop.evaluate_code({"/app/a.py": "A = 1"}, "python -m py_compile /app/a.py")
        loop.evaluate_code({"/app/b.py": "B = 2"}, "python -m py_compile /app/b.py")

        self.assertEqual(len(containers), 2)
        self.assertIsNot(containers[0], containers[1])
        # Run 1 never saw run 2's file; run 2 never saw run 1's file
        containers[0].write_file.assert_called_once_with("/app/a.py", "A = 1")
        containers[1].write_file.assert_called_once_with("/app/b.py", "B = 2")
        written_on_first = [c.args[0] for c in containers[0].write_file.call_args_list]
        written_on_second = [c.args[0] for c in containers[1].write_file.call_args_list]
        self.assertNotIn("/app/b.py", written_on_first)
        self.assertNotIn("/app/a.py", written_on_second)

    @patch("abm.sandbox.container.docker.from_env")
    def test_no_leaked_containers_after_check_loop(self, mock_from_env):
        """SandboxCheckLoop must enter and exit the sandbox (teardown)."""
        mock_sandbox = MagicMock()
        mock_sandbox.__enter__.return_value = mock_sandbox
        mock_sandbox.__exit__.return_value = None
        mock_sandbox.execute_command.return_value = ExecutionResult(
            exit_code=0, stdout="", stderr="", execution_time_ms=5
        )

        loop = SandboxCheckLoop(sandbox_factory=lambda: mock_sandbox)
        loop.evaluate_code({"/app/main.py": "x = 1"}, ["python", "-m", "py_compile", "/app/main.py"])

        mock_sandbox.__enter__.assert_called_once()
        mock_sandbox.__exit__.assert_called_once()


# ---------------------------------------------------------------------------
# HARD GATE 2 — compiler / test-check loop rejects failing code
# ---------------------------------------------------------------------------


class TestCompilerTestCheckRejectionGate(unittest.TestCase):
    """
    Prove the compiler/test-check loop correctly rejects code that fails to
    compile or fails its tests (non-zero exit_code surfaced, not swallowed).
    """

    def _loop_with_exit(self, exit_code: int, stdout: str = "", stderr: str = "") -> SandboxCheckLoop:
        mock_sandbox = MagicMock()
        mock_sandbox.__enter__.return_value = mock_sandbox
        mock_sandbox.__exit__.return_value = None
        mock_sandbox.execute_command.return_value = ExecutionResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            execution_time_ms=10,
        )
        return SandboxCheckLoop(sandbox_factory=lambda: mock_sandbox)

    def test_successful_compile_returns_exit_zero(self):
        loop = self._loop_with_exit(0, stdout="ok")
        result = loop.evaluate_code(
            {"/app/ok.py": "def ok():\n    return 1\n"},
            "python -m py_compile /app/ok.py",
        )
        self.assertEqual(result.exit_code, 0)

    def test_compile_failure_returns_non_zero_exit(self):
        loop = self._loop_with_exit(1, stdout="SyntaxError: invalid syntax")
        result = loop.evaluate_code(
            {"/app/bad.py": "def broken(\n"},
            "python -m py_compile /app/bad.py",
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("SyntaxError", result.stdout)

    def test_test_failure_returns_non_zero_exit(self):
        loop = self._loop_with_exit(1, stdout="FAILED test_login")
        result = loop.evaluate_code(
            {
                "/app/app.py": "def login():\n    return False\n",
                "/app/test_app.py": "def test_login():\n    assert login() is True\n",
            },
            "pytest /app -q",
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("FAILED", result.stdout)

    def test_compile_failure_is_not_rewritten_to_success(self):
        """Rejection must not be masked — exit_code stays failed."""
        loop = self._loop_with_exit(2, stdout="error: failed to compile")
        result = loop.evaluate_code(
            {"/app/x.py": "???"},
            ["python", "-m", "py_compile", "/app/x.py"],
        )
        self.assertEqual(result.exit_code, 2)
        self.assertIsInstance(result, ExecutionResult)

    def test_failed_check_still_tears_down_sandbox(self):
        mock_sandbox = MagicMock()
        mock_sandbox.__enter__.return_value = mock_sandbox
        mock_sandbox.__exit__.return_value = None
        mock_sandbox.execute_command.return_value = ExecutionResult(
            exit_code=1, stdout="FAILED", stderr="", execution_time_ms=3
        )
        loop = SandboxCheckLoop(sandbox_factory=lambda: mock_sandbox)
        result = loop.evaluate_code({"/app/t.py": "assert False"}, "pytest /app")
        self.assertNotEqual(result.exit_code, 0)
        mock_sandbox.__exit__.assert_called_once()

    def test_files_are_injected_before_test_command(self):
        mock_sandbox = MagicMock()
        mock_sandbox.__enter__.return_value = mock_sandbox
        mock_sandbox.__exit__.return_value = None
        mock_sandbox.execute_command.return_value = ExecutionResult(
            exit_code=1, stdout="fail", stderr="", execution_time_ms=1
        )
        loop = SandboxCheckLoop(sandbox_factory=lambda: mock_sandbox)
        loop.evaluate_code(
            {"/app/main.py": "x=1", "/app/test_main.py": "assert False"},
            "pytest /app",
        )
        # write_file calls must precede execute_command
        mock_sandbox.assert_has_calls(
            [
                call.write_file("/app/main.py", "x=1"),
                call.write_file("/app/test_main.py", "assert False"),
                call.execute_command("pytest /app"),
            ],
            any_order=False,
        )


# ---------------------------------------------------------------------------
# HARD GATE 3 — C formula exact match + boundary edge cases
# ---------------------------------------------------------------------------


class TestConfidenceFormulaExactGate(unittest.TestCase):
    """
    Prove C = 0.30(M) + 0.25(T) + 0.20(S) + 0.15(Test) + 0.10(P) exactly,
    including edge cases at the 0.80 / 0.90 / 0.85 boundaries.
    """

    def setUp(self) -> None:
        self.gate = MultiFactorGate(quarantine_dir=_TEST_QUARANTINE_DIR)
        self.contract = _contract()

    def tearDown(self) -> None:
        if os.path.exists(_TEST_QUARANTINE_DIR):
            shutil.rmtree(_TEST_QUARANTINE_DIR)

    def test_weights_match_spec_constants(self):
        self.assertEqual(MultiFactorGate.W_M_ALIGN, 0.30)
        self.assertEqual(MultiFactorGate.W_T_CORRECT, 0.25)
        self.assertEqual(MultiFactorGate.W_S_VAL, 0.20)
        self.assertEqual(MultiFactorGate.W_TEST_SUCC, 0.15)
        self.assertEqual(MultiFactorGate.W_P_ALIGN, 0.10)
        self.assertEqual(MultiFactorGate.C_THRESHOLD, 0.85)
        self.assertEqual(MultiFactorGate.FLOOR_S_VAL, 0.80)
        self.assertEqual(MultiFactorGate.FLOOR_TEST_SUCC, 0.90)

    def test_formula_across_input_range(self):
        cases = [
            (1.0, 1.0, 1.0, 1.0, 1.0),
            (0.0, 0.0, 0.0, 0.0, 0.0),
            (0.9, 0.8, 0.85, 0.95, 0.7),
            (0.5, 0.5, 0.8, 0.9, 0.5),
            (0.75, 0.75, 0.80, 0.90, 0.75),
            (1.0, 0.0, 1.0, 1.0, 0.0),
        ]
        for m, t, s, test, p in cases:
            with self.subTest(m=m, t=t, s=s, test=test, p=p):
                scores = ValidationScores(
                    m_align=m, t_correct=t, s_val=s, test_succ=test, p_align=p
                )
                expected = _expected_c(m, t, s, test, p)
                actual = self.gate.calculate_confidence_score(scores)
                self.assertAlmostEqual(actual, expected, places=12)

    def test_c_exactly_0_85_passes_when_floors_met(self):
        # 0.30(1)+0.25(1)+0.20(0.80)+0.15(0.90)+0.10(0.05) = 0.85 exactly
        scores = ValidationScores(
            m_align=1.0, t_correct=1.0, s_val=0.80, test_succ=0.90, p_align=0.05
        )
        c = self.gate.calculate_confidence_score(scores)
        self.assertAlmostEqual(c, 0.85, places=12)
        self.assertEqual(self.gate.evaluate_floor_gates(scores), [])
        result = self.gate.evaluate(self.contract, scores, "payload")
        self.assertTrue(result.passed)
        self.assertFalse(result.quarantine_flag)

    def test_c_just_below_0_85_quarantines_even_with_floors_met(self):
        # Same as above but p_align=0.04 → C = 0.849
        scores = ValidationScores(
            m_align=1.0, t_correct=1.0, s_val=0.80, test_succ=0.90, p_align=0.04
        )
        c = self.gate.calculate_confidence_score(scores)
        self.assertAlmostEqual(c, 0.849, places=12)
        self.assertLess(c, MultiFactorGate.C_THRESHOLD)
        self.assertEqual(self.gate.evaluate_floor_gates(scores), [])
        result = self.gate.evaluate(self.contract, scores, "payload")
        self.assertFalse(result.passed)
        self.assertTrue(result.quarantine_flag)
        self.assertIn("Composite confidence", result.reason)

    def test_s_val_exactly_0_80_does_not_breach_floor(self):
        scores = ValidationScores(
            m_align=1.0, t_correct=1.0, s_val=0.80, test_succ=0.90, p_align=1.0
        )
        self.assertEqual(self.gate.evaluate_floor_gates(scores), [])

    def test_s_val_just_below_0_80_breaches_floor(self):
        scores = ValidationScores(
            m_align=1.0, t_correct=1.0, s_val=0.79, test_succ=1.0, p_align=1.0
        )
        breaches = self.gate.evaluate_floor_gates(scores)
        self.assertEqual(len(breaches), 1)
        self.assertIn("Security validation", breaches[0])

    def test_test_succ_exactly_0_90_does_not_breach_floor(self):
        scores = ValidationScores(
            m_align=1.0, t_correct=1.0, s_val=1.0, test_succ=0.90, p_align=1.0
        )
        self.assertEqual(self.gate.evaluate_floor_gates(scores), [])

    def test_test_succ_just_below_0_90_breaches_floor(self):
        scores = ValidationScores(
            m_align=1.0, t_correct=1.0, s_val=1.0, test_succ=0.89, p_align=1.0
        )
        breaches = self.gate.evaluate_floor_gates(scores)
        self.assertEqual(len(breaches), 1)
        self.assertIn("Test success", breaches[0])

    def test_should_quarantine_at_exact_c_threshold(self):
        # C >= 0.85 with no floor breaches → do not quarantine
        self.assertFalse(self.gate.should_quarantine(0.85, []))
        self.assertTrue(self.gate.should_quarantine(0.849999, []))


# ---------------------------------------------------------------------------
# HARD GATE 4 — floor breach quarantines even when C is high
# ---------------------------------------------------------------------------


class TestFloorBreachQuarantinesHighCGate(unittest.TestCase):
    """
    Prove a breach of either floor gate quarantines the result even when
    the composite score C is high.
    """

    def setUp(self) -> None:
        self.gate = MultiFactorGate(quarantine_dir=_TEST_QUARANTINE_DIR)
        self.contract = _contract()

    def tearDown(self) -> None:
        if os.path.exists(_TEST_QUARANTINE_DIR):
            shutil.rmtree(_TEST_QUARANTINE_DIR)

    def test_s_val_floor_breach_quarantines_despite_high_c(self):
        # C = 0.30+0.25+0.20*0.79+0.15+0.10 = 0.958  (≥ 0.85)
        scores = ValidationScores(
            m_align=1.0, t_correct=1.0, s_val=0.79, test_succ=1.0, p_align=1.0
        )
        c = self.gate.calculate_confidence_score(scores)
        self.assertGreaterEqual(c, MultiFactorGate.C_THRESHOLD)
        result = self.gate.evaluate(self.contract, scores, "insecure payload")
        self.assertFalse(result.passed)
        self.assertTrue(result.quarantine_flag)
        self.assertIn("Security validation", result.reason)
        self.assertIsNotNone(result.quarantine_path)
        self.assertTrue(os.path.exists(result.quarantine_path))

    def test_test_succ_floor_breach_quarantines_despite_high_c(self):
        # C = 0.30+0.25+0.20+0.15*0.89+0.10 = 0.9835  (≥ 0.85)
        scores = ValidationScores(
            m_align=1.0, t_correct=1.0, s_val=1.0, test_succ=0.89, p_align=1.0
        )
        c = self.gate.calculate_confidence_score(scores)
        self.assertGreaterEqual(c, MultiFactorGate.C_THRESHOLD)
        result = self.gate.evaluate(self.contract, scores, "broken tests payload")
        self.assertFalse(result.passed)
        self.assertTrue(result.quarantine_flag)
        self.assertIn("Test success", result.reason)
        self.assertIsNotNone(result.quarantine_path)

    def test_both_floor_breaches_quarantine_despite_near_perfect_c(self):
        scores = ValidationScores(
            m_align=1.0, t_correct=1.0, s_val=0.79, test_succ=0.89, p_align=1.0
        )
        c = self.gate.calculate_confidence_score(scores)
        self.assertGreaterEqual(c, MultiFactorGate.C_THRESHOLD)
        result = self.gate.evaluate(self.contract, scores, "double breach")
        self.assertTrue(result.quarantine_flag)
        self.assertIn("Security validation", result.reason)
        self.assertIn("Test success", result.reason)

    def test_should_quarantine_true_for_high_c_with_any_floor_breach(self):
        self.assertTrue(
            self.gate.should_quarantine(0.99, ["Security validation (0.79) below 0.8 floor"])
        )
        self.assertTrue(
            self.gate.should_quarantine(0.99, ["Test success (0.89) below 0.9 floor"])
        )

    def test_high_c_with_floors_met_is_accepted(self):
        scores = ValidationScores(
            m_align=1.0, t_correct=1.0, s_val=0.80, test_succ=0.90, p_align=1.0
        )
        c = self.gate.calculate_confidence_score(scores)
        self.assertGreaterEqual(c, 0.85)
        result = self.gate.evaluate(self.contract, scores, "safe payload")
        self.assertTrue(result.passed)
        self.assertFalse(result.quarantine_flag)
        self.assertIsNone(result.quarantine_path)


# ---------------------------------------------------------------------------
# Supporting: DockerSandbox details
# ---------------------------------------------------------------------------


class TestDockerSandbox(unittest.TestCase):
    """DockerSandbox ephemeral manager tests."""

    @patch("abm.sandbox.container.docker.from_env")
    def test_sandbox_context_manager_lifecycle(self, mock_from_env):
        mock_client, mock_container = _mock_sandbox_stack(mock_from_env)

        with DockerSandbox() as sandbox:
            self.assertIsNotNone(sandbox.client)
            self.assertIsNotNone(sandbox.container)
            mock_client.containers.run.assert_called_once()
            call_kwargs = mock_client.containers.run.call_args[1]
            self.assertTrue(call_kwargs["detach"])
            self.assertEqual(call_kwargs["network_mode"], "none")

        mock_container.stop.assert_called_once()
        mock_container.remove.assert_called_once_with(force=True)
        mock_client.close.assert_called_once()

    @patch("abm.sandbox.container.docker.from_env")
    def test_sandbox_write_file_injects_tar(self, mock_from_env):
        _, mock_container = _mock_sandbox_stack(mock_from_env)

        with DockerSandbox() as sandbox:
            sandbox.write_file("/app/src/main.py", "print('hello')")

        mock_container.put_archive.assert_called_once()
        args = mock_container.put_archive.call_args[0]
        self.assertEqual(args[0], "/app/src")

        tar_stream = args[1]
        tar_stream.seek(0)
        with tarfile.open(fileobj=tar_stream, mode="r") as tar:
            members = tar.getmembers()
            self.assertEqual(len(members), 1)
            self.assertEqual(members[0].name, "main.py")
            content = tar.extractfile(members[0]).read().decode("utf-8")
            self.assertEqual(content, "print('hello')")

    @patch("abm.sandbox.container.time.monotonic")
    @patch("abm.sandbox.container.docker.from_env")
    def test_sandbox_execute_command(self, mock_from_env, mock_time):
        mock_client, mock_container = _mock_sandbox_stack(mock_from_env)
        mock_container.id = "test_id"

        mock_api = MagicMock()
        mock_client.api = mock_api
        mock_api.exec_create.return_value = {"Id": "exec_123"}
        mock_api.exec_start.return_value = [b"test output"]
        mock_api.exec_inspect.side_effect = [
            {"Running": False},
            {"ExitCode": 0},
        ]
        mock_time.side_effect = [0.0, 0.1, 0.2]

        with DockerSandbox() as sandbox:
            result = sandbox.execute_command("pytest")

        mock_api.exec_create.assert_called_once_with(
            "test_id", cmd="pytest", stdout=True, stderr=True
        )
        self.assertIsInstance(result, ExecutionResult)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stdout, "test output")


# ---------------------------------------------------------------------------
# Supporting: ExecutionLoop success path
# ---------------------------------------------------------------------------


class TestExecutionLoop(unittest.TestCase):
    """SandboxCheckLoop happy-path orchestration."""

    def test_evaluate_code_flow(self):
        mock_sandbox = MagicMock()
        mock_sandbox.execute_command.return_value = ExecutionResult(
            exit_code=0, stdout="success", stderr="", execution_time_ms=100
        )
        mock_sandbox.__enter__.return_value = mock_sandbox

        loop = SandboxCheckLoop(sandbox_factory=lambda: mock_sandbox)
        files = {
            "/app/test.py": "def test_ok(): pass",
            "/app/main.py": "x = 1",
        }
        result = loop.evaluate_code(files, "pytest /app")

        self.assertEqual(mock_sandbox.write_file.call_count, 2)
        mock_sandbox.write_file.assert_any_call("/app/test.py", "def test_ok(): pass")
        mock_sandbox.execute_command.assert_called_once_with("pytest /app")
        self.assertEqual(result.exit_code, 0)


# ---------------------------------------------------------------------------
# Supporting: math / floors / quarantine (legacy coverage retained)
# ---------------------------------------------------------------------------


class TestValidationGateMath(unittest.TestCase):
    """MultiFactorGate confidence logic (Spec section 6)."""

    def setUp(self):
        self.gate = MultiFactorGate(quarantine_dir=_TEST_QUARANTINE_DIR)
        self.contract = _contract()

    def tearDown(self):
        if os.path.exists(_TEST_QUARANTINE_DIR):
            shutil.rmtree(_TEST_QUARANTINE_DIR)

    def test_perfect_score_passes(self):
        scores = ValidationScores(
            m_align=1.0, t_correct=1.0, s_val=1.0, test_succ=1.0, p_align=1.0
        )
        result = self.gate.evaluate(self.contract, scores, "payload")
        self.assertTrue(result.passed)
        self.assertAlmostEqual(result.confidence_score, 1.0)
        self.assertFalse(result.quarantine_flag)
        self.assertIsNone(result.quarantine_path)

    def test_confidence_formula_math_is_exact(self):
        scores = ValidationScores(
            m_align=0.9, t_correct=0.8, s_val=0.7, test_succ=0.6, p_align=0.5
        )
        expected = _expected_c(0.9, 0.8, 0.7, 0.6, 0.5)
        self.assertAlmostEqual(self.gate.calculate_confidence_score(scores), expected)

    def test_score_validation_rejects_out_of_range_values(self):
        with self.assertRaises(ValidationError):
            ValidationScores(
                m_align=1.01, t_correct=1.0, s_val=1.0, test_succ=1.0, p_align=1.0
            )

    def test_threshold_failure_routes_to_quarantine(self):
        scores = ValidationScores(
            m_align=0.5, t_correct=0.5, s_val=1.0, test_succ=1.0, p_align=0.5
        )
        result = self.gate.evaluate(self.contract, scores, "payload")
        self.assertFalse(result.passed)
        self.assertTrue(result.quarantine_flag)
        self.assertAlmostEqual(result.confidence_score, 0.675)
        self.assertIsNotNone(result.quarantine_path)
        self.assertTrue(os.path.exists(result.quarantine_path))


class TestValidationFloorGates(unittest.TestCase):
    """Absolute floor gates must trigger interception regardless of C score."""

    def setUp(self):
        self.gate = MultiFactorGate(quarantine_dir=_TEST_QUARANTINE_DIR)
        self.contract = _contract()

    def tearDown(self):
        if os.path.exists(_TEST_QUARANTINE_DIR):
            shutil.rmtree(_TEST_QUARANTINE_DIR)

    def test_floor_gate_evaluation_is_independent_of_composite_score(self):
        scores = ValidationScores(
            m_align=1.0, t_correct=1.0, s_val=0.79, test_succ=0.89, p_align=1.0
        )
        breaches = self.gate.evaluate_floor_gates(scores)
        self.assertEqual(len(breaches), 2)
        self.assertIn("Security validation", breaches[0])
        self.assertIn("Test success", breaches[1])

    def test_quarantine_decision_uses_floor_breaches_without_recalculating(self):
        self.assertTrue(self.gate.should_quarantine(0.99, ["Security validation below floor"]))
        self.assertTrue(self.gate.should_quarantine(0.84, []))
        self.assertFalse(self.gate.should_quarantine(0.85, []))

    def test_s_val_floor_breach_blocks(self):
        scores = ValidationScores(
            m_align=1.0, t_correct=1.0, s_val=0.7, test_succ=1.0, p_align=1.0
        )
        result = self.gate.evaluate(self.contract, scores, "payload")
        self.assertFalse(result.passed)
        self.assertTrue(result.quarantine_flag)
        self.assertIn("Security validation", result.reason)

    def test_test_succ_floor_breach_blocks(self):
        scores = ValidationScores(
            m_align=1.0, t_correct=1.0, s_val=1.0, test_succ=0.8, p_align=1.0
        )
        result = self.gate.evaluate(self.contract, scores, "payload")
        self.assertFalse(result.passed)
        self.assertTrue(result.quarantine_flag)
        self.assertIn("Test success", result.reason)


class TestValidationQuarantine(unittest.TestCase):
    """Verifies files written to ambiguity quarantine."""

    def setUp(self):
        self.gate = MultiFactorGate(quarantine_dir=_TEST_QUARANTINE_DIR)
        self.contract = _contract()

    def tearDown(self):
        if os.path.exists(_TEST_QUARANTINE_DIR):
            shutil.rmtree(_TEST_QUARANTINE_DIR)

    def test_quarantine_file_contains_payload_and_reasons(self):
        scores = ValidationScores(
            m_align=0.0, t_correct=0.0, s_val=0.0, test_succ=0.0, p_align=0.0
        )
        result = self.gate.evaluate(self.contract, scores, "DANGEROUS PAYLOAD")
        self.assertTrue(result.quarantine_flag)
        self.assertIsNotNone(result.quarantine_path)
        with open(result.quarantine_path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn(self.contract.contract_id, content)
        self.assertIn("DANGEROUS PAYLOAD", content)
        self.assertIn("Security validation", content)


class TestV01V02V03RegressionGate(unittest.TestCase):
    """Ensure no previous module configuration drifted during Phase v0.4."""

    def test_collections_unchanged(self):
        self.assertEqual(len(ALL_COLLECTIONS), 4)

    def test_file_watcher_extensions_unchanged(self):
        self.assertIn(".dart", CODE_EXTENSIONS)
        self.assertIn(".py", CODE_EXTENSIONS)

    def test_departments_enum_unchanged(self):
        self.assertEqual(len(Department), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
