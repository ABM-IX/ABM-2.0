"""
abm/orchestrator/task_contract.py
===================================
Task Contract & Router Result Schemas â€” Phase v0.3 Executive Orchestrator Engine
Spec Reference: ABM_SPEC.md section 5 ("The Task Contract Format")

Defines the two Pydantic models that encode the complete output of the
ClassificationRouter:

  TaskContract  â€” the immutable delegation contract handed to a worker sandbox.
                  Its JSON shape matches the spec section 5 template exactly.
  RouterResult  â€” wraps a TaskContract with routing metadata (model used,
                  latency, raw classification string, confidence hint).

Design contract:
  - TaskContract is the spec-canonical format. Its field names and types are
    fixed. Do not add fields without updating the spec.
  - RouterResult is the sole return type of ClassificationRouter.classify().
    Callers interact with this object â€” they never interact with the router
    beyond receiving this result.
  - Both models use extra="forbid" so any attempt to inject unknown fields is
    caught at construction time.
  - Both models provide a to_dict() convenience method returning a plain dict
    that matches the JSON serialisation format (not Pydantic's model_dump which
    returns enum values as their Python type).
"""

from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .departments import ALL_WORKER_TOOLS, Department, get_sandbox


# ---------------------------------------------------------------------------
# TaskContract
# ---------------------------------------------------------------------------


class TaskContract(BaseModel):
    """
    The immutable delegation contract produced by the ClassificationRouter.

    This is the exact format specified in ABM_SPEC.md section 5.
    Before any worker sandbox is allowed to initialize a task, it must
    receive a valid TaskContract from the Orchestrator.

    Fields
    ------
    contract_id : str
        Unique transaction ID in the format ``"TXN_{epoch_timestamp}"``.
    objective : str
        The incoming task description verbatim â€” never transformed or truncated.
    department : Department
        The department the router classified this task into.
    assigned_agents : list[str]
        Ordered list of agent identifiers authorised to work on this task.
        Sourced directly from ``DepartmentWorkerSandbox.assigned_agents``.
    autonomy_permission_level : int
        Execution permission level (0â€“4) per spec section 7.
    hard_success_conditions : list[str]
        Conditions that must be met for the task to be considered successful.
        Sourced from ``DepartmentWorkerSandbox.hard_success_conditions``.
    created_at : int
        Unix timestamp (integer seconds) at which the contract was issued.
    """

    model_config = ConfigDict(extra="forbid")

    contract_id: str
    objective: str
    department: Department
    assigned_agents: list[str]
    autonomy_permission_level: int
    hard_success_conditions: list[str]
    created_at: int

    @field_validator("contract_id")
    @classmethod
    def _validate_contract_id(cls, value: str) -> str:
        if not value.startswith("TXN_"):
            raise ValueError(
                f"contract_id must start with 'TXN_', got: '{value}'"
            )
        return value

    @field_validator("objective")
    @classmethod
    def _validate_objective(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("objective must be a non-empty string.")
        return value

    @field_validator("autonomy_permission_level")
    @classmethod
    def _validate_autonomy_level(cls, value: int) -> int:
        if not 0 <= value <= 4:
            raise ValueError(
                f"autonomy_permission_level must be 0â€“4, got {value}"
            )
        return value

    @field_validator("assigned_agents")
    @classmethod
    def _validate_assigned_agents(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("assigned_agents must contain at least one agent.")
        return value

    @field_validator("hard_success_conditions")
    @classmethod
    def _validate_success_conditions(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError(
                "hard_success_conditions must contain at least one condition."
            )
        return value

    def to_dict(self) -> dict[str, Any]:
        """
        Return a plain ``dict`` whose structure matches the spec section 5 JSON.

        The ``department`` field is serialised as its string value (not the
        Python enum object), matching the JSON format exactly.
        """
        return {
            "contract_id": self.contract_id,
            "objective": self.objective,
            "department": self.department.value,
            "assigned_agents": list(self.assigned_agents),
            "autonomy_permission_level": self.autonomy_permission_level,
            "hard_success_conditions": list(self.hard_success_conditions),
            "created_at": self.created_at,
        }

    @classmethod
    def build(
        cls,
        objective: str,
        department: Department,
        assigned_agents: list[str],
        autonomy_permission_level: int,
        hard_success_conditions: list[str],
        epoch: int | None = None,
    ) -> "TaskContract":
        """
        Factory method that generates a contract_id and sets created_at automatically.

        Parameters
        ----------
        objective : str
            The task description.
        department : Department
            Classification result.
        assigned_agents : list[str]
            From ``DepartmentWorkerSandbox.assigned_agents``.
        autonomy_permission_level : int
            From ``DepartmentWorkerSandbox.autonomy_level``.
        hard_success_conditions : list[str]
            From ``DepartmentWorkerSandbox.hard_success_conditions``.
        epoch : int | None
            Unix timestamp to use. If ``None``, ``int(time.time())`` is used.

        Returns
        -------
        TaskContract
        """
        ts = epoch if epoch is not None else int(time.time())
        return cls(
            contract_id=f"TXN_{ts}",
            objective=objective,
            department=department,
            assigned_agents=assigned_agents,
            autonomy_permission_level=autonomy_permission_level,
            hard_success_conditions=hard_success_conditions,
            created_at=ts,
        )


# ---------------------------------------------------------------------------
# RouterResult
# ---------------------------------------------------------------------------


class RouterResult(BaseModel):
    """
    The complete, sealed output of ``ClassificationRouter.classify()``.

    This is the only object callers receive from the router. It contains
    the ``TaskContract`` plus routing metadata for observability.

    Fields
    ------
    contract : TaskContract
        The fully-formed delegation contract.
    raw_classification : str
        The exact department string as returned by qwen2.5-coder:3b before
        normalisation. Useful for debugging model behaviour.
    confidence_hint : str
        The model's self-reported confidence: one of ``"high"``,
        ``"medium"``, or ``"low"``. This is a hint only â€” the router does
        not use it to gate routing decisions.
    model_used : str
        The Ollama model name used for classification (e.g. ``"qwen2.5-coder:3b"``).
    routing_latency_ms : int
        Wall-clock milliseconds from the start of ``classify()`` to the
        moment the ``RouterResult`` was assembled.
    fallback_used : bool
        ``True`` if the router fell back to the default department because
        the model was unavailable or returned unparseable output.
    """

    model_config = ConfigDict(extra="forbid")

    contract: TaskContract
    raw_classification: str
    confidence_hint: str
    model_used: str
    routing_latency_ms: int
    fallback_used: bool = False

    @field_validator("confidence_hint")
    @classmethod
    def _validate_confidence_hint(cls, value: str) -> str:
        allowed = {"high", "medium", "low"}
        if value not in allowed:
            raise ValueError(
                f"confidence_hint must be one of {allowed}, got '{value}'"
            )
        return value

    @field_validator("routing_latency_ms")
    @classmethod
    def _validate_latency(cls, value: int) -> int:
        if value < 0:
            raise ValueError("routing_latency_ms must be non-negative.")
        return value

    def to_dict(self) -> dict[str, Any]:
        """
        Return a plain ``dict`` representation suitable for JSON serialisation.
        The nested ``TaskContract`` is also expanded via its own ``to_dict()``.
        """
        return {
            "contract": self.contract.to_dict(),
            "raw_classification": self.raw_classification,
            "confidence_hint": self.confidence_hint,
            "model_used": self.model_used,
            "routing_latency_ms": self.routing_latency_ms,
            "fallback_used": self.fallback_used,
        }


class WorkerTaskHandoff(BaseModel):
    """
    Router -> worker JSON delegation schema.

    Wraps the spec-canonical TaskContract with the exact sandbox scope the
    worker is allowed to use while handling that contract.
    """

    model_config = ConfigDict(extra="forbid")

    contract: TaskContract
    execution_context_id: str
    allowed_streams: list[str]
    allowed_tools: list[str]

    @field_validator("execution_context_id")
    @classmethod
    def _validate_execution_context_id(cls, value: str) -> str:
        if not value.startswith("sandbox:"):
            raise ValueError("execution_context_id must start with 'sandbox:'")
        return value

    @field_validator("allowed_streams")
    @classmethod
    def _validate_allowed_streams(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("allowed_streams must contain at least one stream.")
        return value

    @field_validator("allowed_tools")
    @classmethod
    def _validate_allowed_tools(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("allowed_tools must contain at least one tool.")
        unknown = set(value) - ALL_WORKER_TOOLS
        if unknown:
            raise ValueError(f"allowed_tools contains unknown tool(s): {sorted(unknown)}")
        return value

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serialisable handoff shape."""
        return {
            "contract": self.contract.to_dict(),
            "execution_context_id": self.execution_context_id,
            "allowed_streams": list(self.allowed_streams),
            "allowed_tools": list(self.allowed_tools),
        }

    @classmethod
    def build(cls, contract: TaskContract) -> "WorkerTaskHandoff":
        """Build a handoff from a TaskContract and its department sandbox."""
        sandbox = get_sandbox(contract.department)
        return cls(
            contract=contract,
            execution_context_id=sandbox.execution_context_id,
            allowed_streams=sorted(sandbox.allowed_streams),
            allowed_tools=sorted(sandbox.allowed_tools),
        )


class WorkerResultReport(BaseModel):
    """
    Worker -> router JSON result-reporting schema.

    Validates the result of a worker sandbox execution without allowing the
    worker to invent fields or report use of tools/streams outside its handoff.
    """

    model_config = ConfigDict(extra="forbid")

    contract_id: str
    department: Department
    execution_context_id: str
    status: Literal["success", "failed", "blocked"]
    summary: str
    artifacts: list[str] = Field(default_factory=list)
    streams_accessed: list[str] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    success_conditions_met: list[str] = Field(default_factory=list)
    error_message: str = ""
    completed_at: int

    @field_validator("contract_id")
    @classmethod
    def _validate_report_contract_id(cls, value: str) -> str:
        if not value.startswith("TXN_"):
            raise ValueError("contract_id must start with 'TXN_'")
        return value

    @field_validator("execution_context_id")
    @classmethod
    def _validate_report_execution_context_id(cls, value: str) -> str:
        if not value.startswith("sandbox:"):
            raise ValueError("execution_context_id must start with 'sandbox:'")
        return value

    @field_validator("summary")
    @classmethod
    def _validate_summary(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("summary must be a non-empty string.")
        return value

    @field_validator("completed_at")
    @classmethod
    def _validate_completed_at(cls, value: int) -> int:
        if value < 0:
            raise ValueError("completed_at must be non-negative.")
        return value

    @field_validator("tools_used")
    @classmethod
    def _validate_tools_used(cls, value: list[str]) -> list[str]:
        unknown = set(value) - ALL_WORKER_TOOLS
        if unknown:
            raise ValueError(f"tools_used contains unknown tool(s): {sorted(unknown)}")
        return value

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serialisable result report shape."""
        return {
            "contract_id": self.contract_id,
            "department": self.department.value,
            "execution_context_id": self.execution_context_id,
            "status": self.status,
            "summary": self.summary,
            "artifacts": list(self.artifacts),
            "streams_accessed": list(self.streams_accessed),
            "tools_used": list(self.tools_used),
            "success_conditions_met": list(self.success_conditions_met),
            "error_message": self.error_message,
            "completed_at": self.completed_at,
        }

    def validate_against_handoff(self, handoff: WorkerTaskHandoff) -> bool:
        """
        Return True when this report stays inside the supplied handoff scope.
        """
        if self.contract_id != handoff.contract.contract_id:
            return False
        if self.department != handoff.contract.department:
            return False
        if self.execution_context_id != handoff.execution_context_id:
            return False
        if not set(self.streams_accessed).issubset(set(handoff.allowed_streams)):
            return False
        if not set(self.tools_used).issubset(set(handoff.allowed_tools)):
            return False
        if not set(self.success_conditions_met).issubset(
            set(handoff.contract.hard_success_conditions)
        ):
            return False
        return True

    @classmethod
    def build(
        cls,
        handoff: WorkerTaskHandoff,
        status: Literal["success", "failed", "blocked"],
        summary: str,
        artifacts: list[str] | None = None,
        streams_accessed: list[str] | None = None,
        tools_used: list[str] | None = None,
        success_conditions_met: list[str] | None = None,
        error_message: str = "",
        completed_at: int | None = None,
    ) -> "WorkerResultReport":
        """Build a scoped result report from a router handoff."""
        return cls(
            contract_id=handoff.contract.contract_id,
            department=handoff.contract.department,
            execution_context_id=handoff.execution_context_id,
            status=status,
            summary=summary,
            artifacts=artifacts or [],
            streams_accessed=streams_accessed or [],
            tools_used=tools_used or [],
            success_conditions_met=success_conditions_met or [],
            error_message=error_message,
            completed_at=completed_at if completed_at is not None else int(time.time()),
        )


__all__ = [
    "TaskContract",
    "RouterResult",
    "WorkerTaskHandoff",
    "WorkerResultReport",
]
