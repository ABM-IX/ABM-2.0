"""
abm/sandbox/validation_gate.py
==============================
Implements the Phase v0.4 Multi-Factor Validation Gate formula and quarantine logic.
"""

import os
from datetime import datetime

from abm.orchestrator.task_contract import TaskContract
from abm.sandbox.models import GateResult, ValidationScores


class MultiFactorGate:
    """
    Enforces the mathematical governance rule from ABM_SPEC section 6.
    Calculates the confidence score C and evaluates absolute floor gates.
    """

    # Spec-defined weights
    W_M_ALIGN = 0.30
    W_T_CORRECT = 0.25
    W_S_VAL = 0.20
    W_TEST_SUCC = 0.15
    W_P_ALIGN = 0.10

    # Spec-defined thresholds
    C_THRESHOLD = 0.85
    FLOOR_S_VAL = 0.80
    FLOOR_TEST_SUCC = 0.90

    def __init__(self, quarantine_dir: str = "memory/ambiguity_quarantine") -> None:
        self.quarantine_dir = quarantine_dir
        if not os.path.exists(self.quarantine_dir):
            os.makedirs(self.quarantine_dir, exist_ok=True)

    def calculate_confidence_score(self, scores: ValidationScores) -> float:
        """Return the spec-defined weighted confidence score C."""
        return (
            (scores.m_align * self.W_M_ALIGN)
            + (scores.t_correct * self.W_T_CORRECT)
            + (scores.s_val * self.W_S_VAL)
            + (scores.test_succ * self.W_TEST_SUCC)
            + (scores.p_align * self.W_P_ALIGN)
        )

    def evaluate_floor_gates(self, scores: ValidationScores) -> list[str]:
        """Return floor-gate breach reasons without evaluating composite C."""
        breaches = []

        if scores.s_val < self.FLOOR_S_VAL:
            breaches.append(
                f"Security validation ({scores.s_val}) below {self.FLOOR_S_VAL} floor"
            )

        if scores.test_succ < self.FLOOR_TEST_SUCC:
            breaches.append(
                f"Test success ({scores.test_succ}) below {self.FLOOR_TEST_SUCC} floor"
            )

        return breaches

    def should_quarantine(
        self, confidence_score: float, floor_gate_breaches: list[str]
    ) -> bool:
        """Return True when the asset must be routed to ambiguity quarantine."""
        return confidence_score < self.C_THRESHOLD or bool(floor_gate_breaches)

    def evaluate(
        self, contract: TaskContract, scores: ValidationScores, payload: str
    ) -> GateResult:
        """
        Evaluate the confidence formula and route to quarantine if failed.
        """
        c_score = self.calculate_confidence_score(scores)
        reasons = self.evaluate_floor_gates(scores)

        # Enforce composite threshold
        if c_score < self.C_THRESHOLD:
            reasons.append(f"Composite confidence ({c_score:.3f}) below {self.C_THRESHOLD} threshold")

        quarantine_flag = self.should_quarantine(c_score, reasons)

        if not quarantine_flag:
            return GateResult(
                passed=True,
                confidence_score=c_score,
                reason="All governance parameters satisfied.",
                quarantine_flag=False,
                quarantine_path=None,
            )

        # Handle failure: route to Ambiguity Quarantine
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"quarantine_{contract.contract_id}_{timestamp}.txt"
        quarantine_path = os.path.join(self.quarantine_dir, filename)

        reason_text = "; ".join(reasons)
        
        with open(quarantine_path, "w", encoding="utf-8") as f:
            f.write(f"CONTRACT: {contract.contract_id}\n")
            f.write(f"OBJECTIVE: {contract.objective}\n")
            f.write(f"FAIL REASONS: {reason_text}\n")
            f.write(f"CONFIDENCE: {c_score:.3f}\n")
            f.write("-" * 40 + "\n")
            f.write("SCORES:\n")
            f.write(f"M_align: {scores.m_align}\n")
            f.write(f"T_correct: {scores.t_correct}\n")
            f.write(f"S_val: {scores.s_val}\n")
            f.write(f"Test_succ: {scores.test_succ}\n")
            f.write(f"P_align: {scores.p_align}\n")
            f.write("-" * 40 + "\n")
            f.write("PAYLOAD:\n")
            f.write(payload)

        return GateResult(
            passed=False,
            confidence_score=c_score,
            reason=reason_text,
            quarantine_flag=True,
            quarantine_path=quarantine_path,
        )
