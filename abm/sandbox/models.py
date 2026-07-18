"""
abm/sandbox/models.py
=====================
Data models for the Safe Action Sandbox (Phase v0.4).
"""

from pydantic import BaseModel, ConfigDict, field_validator


class ExecutionResult(BaseModel):
    """Result of running a command inside the ephemeral Docker sandbox."""

    exit_code: int
    stdout: str
    stderr: str
    execution_time_ms: int


class ValidationScores(BaseModel):
    """
    The five validation scores used in the Phase v0.4 Confidence Math.
    Each score should be between 0.0 and 1.0.
    """

    model_config = ConfigDict(extra="forbid")

    m_align: float  # Memory Alignment (Stream A cosine match)
    t_correct: float  # Technical Syntax Validation (AST validity)
    s_val: float  # Security Verification (Zero secrets/insecure deps)
    test_succ: float  # Isolated Test Success (Sandbox build metrics)
    p_align: float  # Preference Alignment (Stream D constraints)

    @field_validator("m_align", "t_correct", "s_val", "test_succ", "p_align")
    @classmethod
    def _validate_score_range(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("validation scores must be between 0.0 and 1.0")
        return value


class GateResult(BaseModel):
    """Outcome of the multi-factor validation gate."""

    model_config = ConfigDict(extra="forbid")

    passed: bool
    confidence_score: float
    reason: str
    quarantine_flag: bool = False
    quarantine_path: str | None = None
