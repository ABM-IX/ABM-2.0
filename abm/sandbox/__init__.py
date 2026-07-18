"""
ABM 2.0 — abm.sandbox
Phase v0.4: Safe Action Sandbox

Exports the core v0.4 components:
  - ExecutionResult      : Result of command execution
  - ValidationScores     : The five confidence math parameters
  - GateResult           : Outcome of the validation gate evaluation
  - DockerSandbox        : Ephemeral lifecycle manager
  - SandboxCheckLoop     : Execution orchestrator for the sandbox
  - MultiFactorGate      : Governance evaluator and quarantine router
"""

from .container import DockerSandbox
from .execution_loop import SandboxCheckLoop
from .models import ExecutionResult, GateResult, ValidationScores
from .validation_gate import MultiFactorGate

__all__ = [
    "ExecutionResult",
    "ValidationScores",
    "GateResult",
    "DockerSandbox",
    "SandboxCheckLoop",
    "MultiFactorGate",
]
