"""
abm/strategic_wing/workflow_monitor.py
======================================
Workflow overview monitor for Phase v0.5.
Aggregates in-flight task state across v0.3 and v0.4.
"""

import os
from dataclasses import dataclass
from enum import Enum

from abm.orchestrator.task_contract import TaskContract
from abm.sandbox.models import ExecutionResult, GateResult, ValidationScores


class TaskState(Enum):
    ROUTED = "ROUTED"
    IN_SANDBOX = "IN_SANDBOX"
    EXECUTED = "EXECUTED"
    QUARANTINED = "QUARANTINED"
    PASSED = "PASSED"


@dataclass
class TaskRecord:
    contract: TaskContract
    state: TaskState
    execution_result: ExecutionResult | None = None
    gate_result: GateResult | None = None
    validation_scores: ValidationScores | None = None


class WorkflowMonitor:
    """
    Read-side aggregation registry tracking task state across the orchestrator
    and sandbox. Designed to not intrude on v0.3/v0.4 source code.
    """

    def __init__(self, quarantine_dir: str = "memory/ambiguity_quarantine") -> None:
        self.quarantine_dir = quarantine_dir
        self._registry: dict[str, TaskRecord] = {}

    def register_routed_task(self, contract: TaskContract) -> None:
        """Track a task right after it comes out of the v0.3 Classification Router."""
        self._registry[contract.contract_id] = TaskRecord(
            contract=contract, state=TaskState.ROUTED
        )

    def mark_in_sandbox(self, contract_id: str) -> None:
        """Mark a task as currently executing in the v0.4 Docker sandbox."""
        if contract_id in self._registry:
            self._registry[contract_id].state = TaskState.IN_SANDBOX

    def record_execution(self, contract_id: str, result: ExecutionResult) -> None:
        """Record the sandbox test execution results."""
        if contract_id in self._registry:
            self._registry[contract_id].execution_result = result
            self._registry[contract_id].state = TaskState.EXECUTED

    def record_gate_result(
        self, contract_id: str, gate: GateResult, scores: ValidationScores | None = None
    ) -> None:
        """Record the final Math Validation Gate evaluation."""
        if contract_id in self._registry:
            self._registry[contract_id].gate_result = gate
            if scores is not None:
                self._registry[contract_id].validation_scores = scores
            self._registry[contract_id].state = (
                TaskState.PASSED if gate.passed else TaskState.QUARANTINED
            )

    def scan_quarantine_directory(self) -> list[str]:
        """
        Scans the physical disk to find tasks that were quarantined.
        Returns a list of quarantined contract_ids found on disk.
        """
        found_ids = []
        if not os.path.exists(self.quarantine_dir):
            return found_ids

        for filename in os.listdir(self.quarantine_dir):
            if filename.startswith("quarantine_TXN_") and filename.endswith(".txt"):
                # Extract the contract ID: quarantine_TXN_12345_2026...txt
                parts = filename.split("_")
                if len(parts) >= 3:
                    # 'quarantine', 'TXN', '12345', ...
                    contract_id = f"{parts[1]}_{parts[2]}"
                    found_ids.append(contract_id)
                    # If this is known to us but not marked quarantine, fix it
                    if contract_id in self._registry:
                        if self._registry[contract_id].state != TaskState.QUARANTINED:
                            self._registry[contract_id].state = TaskState.QUARANTINED

        return found_ids

    def get_overview_report(self) -> str:
        """Generates a human-readable summary of all in-flight work."""
        self.scan_quarantine_directory()  # Auto-sync physical state before reporting

        if not self._registry:
            return "Workflow Monitor: No tasks in-flight."

        lines = ["=== FIRSTMINDS WORKFLOW OVERVIEW ==="]
        for contract_id, record in self._registry.items():
            lines.append(f"Task: {contract_id}")
            lines.append(f"  Objective : {record.contract.objective}")
            lines.append(f"  Department: {record.contract.department.value}")
            lines.append(f"  State     : {record.state.value}")
            if record.gate_result:
                lines.append(f"  Confidence: {record.gate_result.confidence_score:.3f}")
            lines.append("-" * 36)

        return "\n".join(lines)
