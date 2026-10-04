"""
ABM 2.0 â€” abm.orchestrator
Phase v0.3: Executive Orchestrator Engine

Exports the four v0.3 components:
  - ClassificationRouter  : non-generating task classification router
  - OllamaModelGateway    : qwen2.5-coder:3b caller via local Ollama loopback
  - ModelGatewayError     : raised on any gateway failure
  - GenerationResponse    : raw output from OllamaModelGateway.generate()
  - Department            : enum of all valid routing departments
  - DepartmentWorkerSandbox : frozen sandbox config per department
  - DEPARTMENT_REGISTRY   : dept â†’ sandbox lookup table
  - get_sandbox           : department â†’ DepartmentWorkerSandbox lookup
  - department_from_string: normalises raw model strings to Department
  - TaskContract          : immutable delegation contract (spec section 5)
  - RouterResult          : complete output of ClassificationRouter.classify()
"""

from .departments import (
    ALL_WORKER_TOOLS,
    Department,
    DepartmentWorkerSandbox,
    DEPARTMENT_REGISTRY,
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
from .model_gateway import (
    GenerationResponse,
    ModelGatewayError,
    OllamaModelGateway,
    DEFAULT_CLASSIFICATION_MODEL,
)
from .router import (
    ClassificationRouter,
    CONFIDENCE_HINTS,
    FALLBACK_DEPARTMENT,
    MAX_TASK_DESCRIPTION_CHARS,
)
from .task_contract import (
    RouterResult,
    TaskContract,
    WorkerResultReport,
    WorkerTaskHandoff,
)

__all__ = [
    # departments
    "Department",
    "DepartmentWorkerSandbox",
    "DEPARTMENT_REGISTRY",
    "ALL_WORKER_TOOLS",
    "TOOL_CHROMA_QUERY",
    "TOOL_CODE_STRUCTURE_ANALYZER",
    "TOOL_STYLE_FINGERPRINT_EXTRACTOR",
    "TOOL_GIT_PIPELINE",
    "TOOL_FILE_WATCHER",
    "TOOL_INGESTION_COORDINATOR",
    "TOOL_MODEL_GATEWAY",
    "TOOL_SECURITY_STATIC_SCAN",
    "TOOL_PATCH_PROPOSAL_WRITER",
    "TOOL_STRATEGIC_SUMMARY_BUILDER",
    "department_from_string",
    "get_sandbox",
    # model_gateway
    "OllamaModelGateway",
    "ModelGatewayError",
    "GenerationResponse",
    "DEFAULT_CLASSIFICATION_MODEL",
    # router
    "ClassificationRouter",
    "CONFIDENCE_HINTS",
    "FALLBACK_DEPARTMENT",
    "MAX_TASK_DESCRIPTION_CHARS",
    # task_contract
    "TaskContract",
    "RouterResult",
    "WorkerTaskHandoff",
    "WorkerResultReport",
]
