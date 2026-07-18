"""
abm/memory/metadata_models.py
================================
Pydantic metadata validators for the four ABM memory streams.

The field names and allowed values mirror ABM_SPEC.md section 3 and the
canonical schema dictionaries exported by abm.memory.chroma_controller.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr, field_validator


class _StrictMetadataModel(BaseModel):
    """Base model that rejects fields outside the stream metadata schema."""

    model_config = ConfigDict(extra="forbid")


class CognitiveIdentityMetadata(_StrictMetadataModel):
    """Stream D metadata for abm_cognitive_identity."""

    owner: Literal["ABM"]
    target_entity: Literal["FirstMinds"]
    volatility: Literal["immutable"]


class CodeTopologiesMetadata(_StrictMetadataModel):
    """Stream A metadata for abm_code_topologies."""

    language: Literal["dart", "kotlin", "python"]
    framework: Literal["flutter"]
    state_pattern: Literal["bloc"]
    naming_convention: Literal["camelCase"]


class TechnicalMasteryMetadata(_StrictMetadataModel):
    """Stream B metadata for abm_technical_mastery."""

    source: Literal["duckduckgo_sandbox", "docs_fetch"]
    date_acquired: StrictStr
    confidence_score: StrictStr

    @field_validator("date_acquired")
    @classmethod
    def _validate_date_acquired(cls, value: str) -> str:
        date.fromisoformat(value)
        return value

    @field_validator("confidence_score")
    @classmethod
    def _validate_confidence_score(cls, value: str) -> str:
        try:
            score = float(value)
        except ValueError as exc:
            raise ValueError("confidence_score must be a string-encoded float") from exc
        if not 0.0 <= score <= 1.0:
            raise ValueError("confidence_score must be between 0.0 and 1.0")
        return value


class AmbientTelemetryMetadata(_StrictMetadataModel):
    """Stream C metadata for abm_ambient_telemetry."""

    epoch_timestamp: StrictInt
    active_repository: Literal["smart_transit", "houseconnect"]
    device_source: Literal["dynamic_mobile_node"]


__all__ = [
    "CognitiveIdentityMetadata",
    "CodeTopologiesMetadata",
    "TechnicalMasteryMetadata",
    "AmbientTelemetryMetadata",
]
