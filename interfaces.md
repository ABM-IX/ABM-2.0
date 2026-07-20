# interfaces.md
# ABM 2.0 — Phases v0.1 & v0.2
# Complete API Reference: Every Function Signature, File Path, and Metadata Shape

> This document is the single source of truth for every public interface
> created in Phases v0.1 and v0.2. Any tool or agent building on this
> codebase must consult this file before writing integration code.

---

## Table of Contents

1. [File Map](#file-map)
2. [Collection Names](#collection-names)
3. [Metadata Schemas](#metadata-schemas)
4. [Module: `abm.memory.chroma_controller`](#module-abmmemory-chroma_controller)
5. [Module: `abm.memory.embedding_wrapper`](#module-abmmemory-embedding_wrapper)
6. [Module: `abm.memory.metadata_models`](#module-abmmemory-metadata_models)
7. [Module: `abm.memory.chunking`](#module-abmmemory-chunking)
8. [Module: `abm.memory` (package)](#module-abmmemory-package)
9. [Constants Reference (v0.1)](#constants-reference)
10. [Phase v0.2 — Developer Companion Node](#phase-v02--developer-companion-node)
    - [Module: `abm.companion.file_watcher`](#module-abmcompanion-file_watcher)
    - [Module: `abm.companion.git_pipeline`](#module-abmcompanion-git_pipeline)
    - [Module: `abm.companion.code_structure_analyzer`](#module-abmcompanion-code_structure_analyzer)
    - [Module: `abm.companion.style_fingerprint`](#module-abmcompanion-style_fingerprint)
    - [Module: `abm.companion.ingestion_coordinator`](#module-abmcompanion-ingestion_coordinator)
    - [Module: `abm.companion.watch_daemon`](#module-abmcompanion-watch_daemon)
    - [Module: `abm.companion` (package)](#module-abmcompanion-package)
    - [Constants Reference (v0.2)](#constants-reference-v02)
11. [Phase v0.3 — Executive Orchestrator Engine](#phase-v03--executive-orchestrator-engine)
    - [Module: `abm.orchestrator.departments`](#module-abmorchestrator-departments)
    - [Module: `abm.orchestrator.task_contract`](#module-abmorchestrator-task_contract)
    - [Module: `abm.orchestrator.model_gateway`](#module-abmorchestrator-model_gateway)
    - [Module: `abm.orchestrator.router`](#module-abmorchestrator-router)
    - [Module: `abm.orchestrator` (package)](#module-abmorchestrator-package)
12. [Phase v0.4 — Safe Action Sandbox](#phase-v04--safe-action-sandbox)
    - [Module: `abm.sandbox.models`](#module-abmsandbox-models)
    - [Module: `abm.sandbox.container`](#module-abmsandbox-container)
    - [Module: `abm.sandbox.execution_loop`](#module-abmsandbox-execution_loop)
    - [Module: `abm.sandbox.validation_gate`](#module-abmsandbox-validation_gate)
    - [Module: `abm.sandbox` (package)](#module-abmsandbox-package)
13. [Phase v0.5 — FirstMinds Strategic Wing](#phase-v05--firstminds-strategic-wing)
    - [Module: `abm.strategic_wing.decision_journal`](#module-abmstrategic_wing-decision_journal)
    - [Module: `abm.strategic_wing.workflow_monitor`](#module-abmstrategic_wing-workflow_monitor)
    - [Module: `abm.strategic_wing.strategic_asset_analyzer`](#module-abmstrategic_wing-strategic_asset_analyzer)
    - [Module: `abm.strategic_wing` (package)](#module-abmstrategic_wing-package)
14. [Test Suite](#test-suite)

---

## File Map

```
ABM-2.0/
├── abm/
│   ├── __init__.py                    # Package root — version and phase metadata
│   ├── memory/                        # v0.1 — sealed, do not modify
│   │   ├── __init__.py                # Re-exports all v0.1 public symbols
│   │   ├── chroma_controller.py       # ChromaDB collection manager
│   │   ├── embedding_wrapper.py       # Ollama nomic-embed-text connector
│   │   ├── chunking.py                # Stream A/B/C chunking helpers
│   │   └── metadata_models.py         # Pydantic metadata validators
│   └── companion/                     # v0.2 — Developer Companion Node
│       ├── __init__.py                # Re-exports all v0.2 public symbols
│       ├── file_watcher.py            # watchdog-based file change monitor
│       ├── git_pipeline.py            # GitPython commit/diff/branch reader
│       ├── code_structure_analyzer.py # General-purpose AST/structure analyzer
│       ├── style_fingerprint.py       # AST-based style analyzer
│       ├── ingestion_coordinator.py   # Pipeline coordinator → calls v0.1 API
│       └── watch_daemon.py            # Runnable entry point — watcher → coordinator
│   └── orchestrator/                  # v0.3 — Executive Orchestrator Engine
│       ├── __init__.py                # Re-exports all v0.3 public symbols
│       ├── departments.py             # Department enum + sandbox configs
│       ├── task_contract.py           # Pydantic TaskContract + RouterResult
│       ├── model_gateway.py           # Ollama phi3:mini caller
│       └── router.py                  # Non-generating ClassificationRouter
│   └── sandbox/                       # v0.4 — Safe Action Sandbox
│       ├── __init__.py                # Re-exports all v0.4 public symbols
│       ├── models.py                  # ExecutionResult and ValidationScores
│       ├── container.py               # Ephemeral Docker Sandbox controller
│       ├── execution_loop.py          # SandboxCheckLoop compiler test injector
│       └── validation_gate.py         # Multi-factor governance math & quarantine
│   └── strategic_wing/                # v0.5 — FirstMinds Strategic Wing
│       ├── __init__.py                # Re-exports all v0.5 public symbols
│       ├── decision_journal.py        # Writes strategic decisions to Stream D
│       └── workflow_monitor.py        # In-flight task state aggregation
├── tests/
│   ├── __init__.py
│   ├── test_phase_v01_gate.py         # Hard gate: v0.1 isolation + chunking + embed
│   ├── test_memory_isolation.py       # Mock-assertion isolation / embed contract tests
│   ├── test_metadata_and_chunking.py  # Metadata + chunking contract tests
│   ├── test_phase_v02_gate.py         # Hard gate: v0.2 watcher + git + style + ingestion
│   ├── test_phase_v03_gate.py         # Hard gate: v0.3 router + schema boundaries
│   ├── test_phase_v04_gate.py         # Hard gate: v0.4 math governance + docker isolation
│   └── test_phase_v05_gate.py         # Hard gate: v0.5 strategic wing tools
├── memory/
│   └── ambiguity_quarantine/          # Spec-defined quarantine dir (Phase v0.4 feature)
│       └── .gitkeep
├── project_context/
│   ├── PROJECT_BRIEF.md
│   └── ABM_SPEC.md
├── interfaces.md                      # This file
├── requirements.txt
└── README.md
```

---

**Additional Phase v0.1 files added after initial reference generation:**
- [`abm/memory/metadata_models.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/memory/metadata_models.py) - Pydantic metadata validators for all four streams.
- [`abm/memory/chunking.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/memory/chunking.py) - Stream A/B/C chunking helpers.
- [`tests/test_metadata_and_chunking.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/tests/test_metadata_and_chunking.py) - Contract tests for metadata validation and chunking.
- [`tests/test_phase_v01_gate.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/tests/test_phase_v01_gate.py) - Hard phase gate: retrieval isolation, chunking boundaries, embedding consistency.

---

## Collection Names

These string constants are exported from `abm.memory.chroma_controller`.
**Do not rename or abbreviate these.** (Spec section 3 mandate)

| Constant | Value | Stream | Purpose |
|----------|-------|--------|---------|
| `COLLECTION_COGNITIVE_IDENTITY` | `"abm_cognitive_identity"` | D | Identity foundations, personal/professional goals, FirstMinds philosophies |
| `COLLECTION_CODE_TOPOLOGIES` | `"abm_code_topologies"` | A | Engineering DNA, formatting signatures, pattern designs |
| `COLLECTION_TECHNICAL_MASTERY` | `"abm_technical_mastery"` | B | Validated docs, API references, external package schemas |
| `COLLECTION_AMBIENT_TELEMETRY` | `"abm_ambient_telemetry"` | C | Chronological interaction history, terminal I/O, clipboard deltas |

```python
from abm.memory.chroma_controller import (
    COLLECTION_COGNITIVE_IDENTITY,   # "abm_cognitive_identity"
    COLLECTION_CODE_TOPOLOGIES,      # "abm_code_topologies"
    COLLECTION_TECHNICAL_MASTERY,    # "abm_technical_mastery"
    COLLECTION_AMBIENT_TELEMETRY,    # "abm_ambient_telemetry"
    ALL_COLLECTIONS,                 # tuple of all four, in declaration order
)
```

---

## Metadata Schemas

Verbatim from ABM_SPEC.md section 3. Field names are NOT renamed.

### Stream D — `abm_cognitive_identity`

```python
SCHEMA_COGNITIVE_IDENTITY: dict[str, str] = {
    "owner": "ABM",
    "target_entity": "FirstMinds",
    "volatility": "immutable",
}
```

**Field descriptions:**
- `owner` — Always `"ABM"`. Identifies the cognitive identity owner.
- `target_entity` — Always `"FirstMinds"`. The corporate entity this stream serves.
- `volatility` — Always `"immutable"`. Identity foundations do not change frequently.

---

### Stream A — `abm_code_topologies`

```python
SCHEMA_CODE_TOPOLOGIES: dict[str, str] = {
    "language": "dart|kotlin|python",
    "framework": "flutter",
    "state_pattern": "bloc",
    "naming_convention": "camelCase",
}
```

**Field descriptions:**
- `language` — Target language of the code chunk. Enum: `dart`, `kotlin`, `python` (plus `javascript`, `css`, `html`, `java` per spec section 3).
- `framework` — Always `"flutter"` for cross-platform architecture targets.
- `state_pattern` — Always `"bloc"` (Business Logic Component pattern).
- `naming_convention` — Always `"camelCase"` per the spec.

**Chunking strategy:** AST node clusters, class boundaries, or closing bracket parameters. Code is never split mid-line.

---

### Stream B — `abm_technical_mastery`

```python
SCHEMA_TECHNICAL_MASTERY: dict[str, str] = {
    "source": "duckduckgo_sandbox|docs_fetch",
    "date_acquired": "2026-07-18",
    "confidence_score": "0.92",
}
```

**Field descriptions:**
- `source` — Origin of the technical asset. Enum: `duckduckgo_sandbox`, `docs_fetch`.
- `date_acquired` — ISO 8601 date string when the asset was acquired.
- `confidence_score` — String-encoded float `[0.0, 1.0]` representing validation confidence.

**Chunking strategy:** Recursive token chunking — 500-token window, 50-token overlap.

---

### Stream C — `abm_ambient_telemetry`

```python
SCHEMA_AMBIENT_TELEMETRY: dict[str, Any] = {
    "epoch_timestamp": 1784370192,    # int
    "active_repository": "smart_transit|houseconnect",
    "device_source": "dynamic_mobile_node",
}
```

**Field descriptions:**
- `epoch_timestamp` — Unix timestamp (integer) of the interaction event.
- `active_repository` — Name of the Git repository active at event time.
- `device_source` — Hardware source identifier. Uses `"dynamic_mobile_node"` per the spec's hardware-agnostic blueprint update (spec section 10 addendum). Not hardcoded to any specific device.

**Chunking strategy:** Chronological windowing. Events grouped; blocks split on 120-second interaction pauses.

**Rollout guardrail:** Ingestion starts with Git trees, IDE workspaces, and static design docs only. Clipboard tracking, voice logs, and browser tracking are offline until core memory is stable.

---

### Pydantic Validators

The following strict Pydantic models validate the exact metadata field names and constrained values above.
All models reject extra fields.

```python
from abm.memory.metadata_models import (
    CognitiveIdentityMetadata,
    CodeTopologiesMetadata,
    TechnicalMasteryMetadata,
    AmbientTelemetryMetadata,
)
```

| Model | Collection | Fields |
|-------|------------|--------|
| `CognitiveIdentityMetadata` | `abm_cognitive_identity` | `owner`, `target_entity`, `volatility` |
| `CodeTopologiesMetadata` | `abm_code_topologies` | `language`, `framework`, `state_pattern`, `naming_convention` |
| `TechnicalMasteryMetadata` | `abm_technical_mastery` | `source`, `date_acquired`, `confidence_score` |
| `AmbientTelemetryMetadata` | `abm_ambient_telemetry` | `epoch_timestamp`, `active_repository`, `device_source` |

---

## Module: `abm.memory.chroma_controller`

**File:** [`abm/memory/chroma_controller.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/memory/chroma_controller.py)

### Class `ChromaController`

```python
class ChromaController:
    def __init__(
        self,
        persist_directory: str = "./memory/chroma_store",
        *,
        in_memory: bool = False,
    ) -> None: ...
```

**Parameters:**
- `persist_directory` — Filesystem path for ChromaDB persistence. Default: `"./memory/chroma_store"`.
- `in_memory` — If `True`, uses ephemeral EphemeralClient (for testing). Overrides `persist_directory`.

---

#### `initialize_collections() -> None`

```python
def initialize_collections(self) -> None
```

Creates or retrieves all four spec-defined ChromaDB collections.
Idempotent — safe to call multiple times. Called automatically by `__init__`.

**Raises:** `RuntimeError` if ChromaDB fails to create any collection.

---

#### `get_collection(collection_name: str) -> chromadb.Collection`

```python
def get_collection(self, collection_name: str) -> chromadb.Collection
```

Returns the ChromaDB `Collection` handle for the given name.

**Parameters:**
- `collection_name` — Must be one of the four `COLLECTION_*` constants.

**Returns:** `chromadb.Collection`

**Raises:** `ValueError` for any name not in `ALL_COLLECTIONS`.

---

#### `add_document(...) -> None`

```python
def add_document(
    self,
    collection_name: str,
    doc_id: str,
    text: str,
    metadata: dict[str, Any],
    embedding: list[float],
) -> None
```

Adds a single document with a pre-computed embedding to the named collection.
Collection is resolved by name **before** the write — zero crossover is guaranteed at the API boundary.

**Parameters:**
- `collection_name` — Target collection. Must be one of the four canonical names.
- `doc_id` — Unique document identifier (ChromaDB `id`).
- `text` — Raw document text.
- `metadata` — Document metadata conforming to the collection's canonical schema.
- `embedding` — Pre-computed vector from `OllamaEmbeddingWrapper.embed()`.

**Raises:** `ValueError` for invalid collection name; `RuntimeError` on ChromaDB failure.

---

#### `query_collection(...) -> QueryResult`

```python
def query_collection(
    self,
    collection_name: str,
    query_embedding: list[float],
    n_results: int = 5,
) -> QueryResult
```

Performs nearest-neighbour vector query against the named collection only.

**Parameters:**
- `collection_name` — Target collection. Must be one of the four canonical names.
- `query_embedding` — Query vector from `OllamaEmbeddingWrapper.embed()`.
- `n_results` — Max results to return. Automatically clamped to collection size.

**Returns:** `QueryResult` dataclass (empty if collection has no data).

**Raises:** `ValueError` for invalid collection name.

---

#### `clear_collection(collection_name: str) -> None`

```python
def clear_collection(self, collection_name: str) -> None
```

Deletes all documents from the named collection. Collection structure is preserved.
**For test teardown only.**

**Raises:** `ValueError` for invalid collection name.

---

#### `collection_count(collection_name: str) -> int`

```python
def collection_count(self, collection_name: str) -> int
```

Returns the number of documents currently in the named collection.

**Raises:** `ValueError` for invalid collection name.

---

#### Property `registered_collections -> tuple[str, ...]`

```python
@property
def registered_collections(self) -> tuple[str, ...]
```

Returns all registered collection names in declaration order (matches `ALL_COLLECTIONS`).

---

### Dataclass `QueryResult`

```python
@dataclass
class QueryResult:
    collection_name: str
    ids: list[list[str]] = field(default_factory=list)
    documents: list[list[str]] = field(default_factory=list)
    metadatas: list[list[dict[str, Any]]] = field(default_factory=list)
    distances: list[list[float]] = field(default_factory=list)
```

Typed container for ChromaDB query responses. All fields are nested lists
(outer list = one entry per query, inner list = results for that query).

---

## Module: `abm.memory.embedding_wrapper`

**File:** [`abm/memory/embedding_wrapper.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/memory/embedding_wrapper.py)

### Class `OllamaEmbeddingWrapper`

```python
class OllamaEmbeddingWrapper:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "nomic-embed-text",
        connect_timeout: float = 5.0,
        read_timeout: float = 30.0,
    ) -> None: ...
```

**Parameters:**
- `base_url` — Ollama server URL. **Never change in production.** Always `127.0.0.1:11434`.
- `model` — Ollama model name. Default: `"nomic-embed-text"`.
- `connect_timeout` — TCP connect timeout (seconds).
- `read_timeout` — HTTP response read timeout (seconds).

---

#### `health_check() -> bool`

```python
def health_check(self) -> bool
```

GETs `http://127.0.0.1:11434/api/tags`. Returns `True` if Ollama responds HTTP 200, `False` otherwise (connection error or non-200 status). Use before batch embedding operations.

---

#### `embed(text: str) -> list[float]`

```python
def embed(self, text: str) -> list[float]
```

Generates a single embedding vector for `text` via `nomic-embed-text`.

POSTs to `http://127.0.0.1:11434/api/embeddings` with body:
```json
{ "model": "nomic-embed-text", "prompt": "<text>" }
```

**Returns:** `list[float]` — the embedding vector (768 dims for nomic-embed-text).

**Raises:**
- `ValueError` — if `text` is empty or whitespace-only.
- `ConnectionError` — if Ollama is not reachable at `127.0.0.1:11434`.
- `RuntimeError` — if Ollama returns non-200 or malformed response.

---

#### `embed_batch(texts: list[str]) -> list[list[float]]`

```python
def embed_batch(self, texts: list[str]) -> list[list[float]]
```

Generates embeddings for a list of texts. Calls `embed()` once per text (Ollama API does not natively batch embeddings). Results are returned in the same order as input.

**Returns:** `list[list[float]]` — one vector per input text.

**Raises:** `ValueError` if `texts` is empty; propagates all `embed()` errors.

---

#### Properties

```python
@property
def model(self) -> str         # "nomic-embed-text"

@property
def base_url(self) -> str      # "http://127.0.0.1:11434"

@property
def embed_endpoint(self) -> str  # "http://127.0.0.1:11434/api/embeddings"
```

---

## Module: `abm.memory.metadata_models`

**File:** [`abm/memory/metadata_models.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/memory/metadata_models.py)

Strict Pydantic validators for the four metadata schemas from ABM_SPEC.md section 3.
All models use `extra="forbid"` and keep the spec field names unchanged.

### Class `CognitiveIdentityMetadata`

```python
class CognitiveIdentityMetadata(BaseModel):
    owner: Literal["ABM"]
    target_entity: Literal["FirstMinds"]
    volatility: Literal["immutable"]
```

Validates Stream D metadata for `abm_cognitive_identity`.

---

### Class `CodeTopologiesMetadata`

```python
class CodeTopologiesMetadata(BaseModel):
    language: Literal["dart", "kotlin", "python"]
    framework: Literal["flutter"]
    state_pattern: Literal["bloc"]
    naming_convention: Literal["camelCase"]
```

Validates Stream A metadata for `abm_code_topologies`.

---

### Class `TechnicalMasteryMetadata`

```python
class TechnicalMasteryMetadata(BaseModel):
    source: Literal["duckduckgo_sandbox", "docs_fetch"]
    date_acquired: StrictStr
    confidence_score: StrictStr
```

Validates Stream B metadata for `abm_technical_mastery`.
`date_acquired` must be an ISO 8601 date string.
`confidence_score` must be a string-encoded float in `[0.0, 1.0]`.

---

### Class `AmbientTelemetryMetadata`

```python
class AmbientTelemetryMetadata(BaseModel):
    epoch_timestamp: StrictInt
    active_repository: Literal["smart_transit", "houseconnect"]
    device_source: Literal["dynamic_mobile_node"]
```

Validates Stream C metadata for `abm_ambient_telemetry`.

---

## Module: `abm.memory.chunking`

**File:** [`abm/memory/chunking.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/memory/chunking.py)

Chunking helpers for Streams A, B, and C. Stream D has no chunking helper in this phase.

### `chunk_stream_a_code_topologies(code: str, language: str) -> list[str]`

```python
def chunk_stream_a_code_topologies(code: str, language: str) -> list[str]
```

Chunks Stream A code on AST or structural boundaries.
Python uses top-level AST node boundaries.
Dart and Kotlin use brace-depth structural boundaries.
The function only splits on line boundaries and never splits code mid-line.

**Parameters:**
- `code` - Source code text.
- `language` - Must be one of `dart`, `kotlin`, `python`.

**Returns:** `list[str]` - code chunks.

**Raises:** `ValueError` for unsupported `language`.

---

### `chunk_stream_b_technical_mastery(...) -> list[str]`

```python
def chunk_stream_b_technical_mastery(
    text: str,
    *,
    token_window: int = STREAM_B_TOKEN_WINDOW,
    token_overlap: int = STREAM_B_TOKEN_OVERLAP,
) -> list[str]
```

Chunks Stream B text using recursive token chunking.
Default window size is `500` tokens with `50` tokens of overlap.

**Parameters:**
- `text` - Technical text/documentation to chunk.
- `token_window` - Token window size. Default: `500`.
- `token_overlap` - Overlap between adjacent windows. Default: `50`.

**Returns:** `list[str]` - token-window text chunks.

**Raises:** `ValueError` if window/overlap values are invalid.

---

### `chunk_stream_c_ambient_telemetry(...) -> list[list[dict[str, Any]]]`

```python
def chunk_stream_c_ambient_telemetry(
    events: Sequence[Mapping[str, Any]],
    *,
    gap_seconds: int = STREAM_C_INTERACTION_GAP_SECONDS,
) -> list[list[dict[str, Any]]]
```

Chunks Stream C telemetry into chronological event windows.
Events are sorted by `epoch_timestamp`.
A new window starts when the gap between adjacent events is greater than `120` seconds by default.

**Parameters:**
- `events` - Event dictionaries containing `epoch_timestamp`.
- `gap_seconds` - Interaction pause threshold. Default: `120`.

**Returns:** `list[list[dict[str, Any]]]` - chronological event windows.

**Raises:** `ValueError` if `gap_seconds` is negative or any event lacks an integer `epoch_timestamp`.

---

## Module: `abm.memory` (package)

**File:** [`abm/memory/__init__.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/memory/__init__.py)

```python
from abm.memory import ChromaController, OllamaEmbeddingWrapper
```

Primary classes, metadata models, and chunking helpers are re-exported at the package level for clean top-level imports.

```python
from abm.memory import (
    ChromaController,
    OllamaEmbeddingWrapper,
    CognitiveIdentityMetadata,
    CodeTopologiesMetadata,
    TechnicalMasteryMetadata,
    AmbientTelemetryMetadata,
    chunk_stream_a_code_topologies,
    chunk_stream_b_technical_mastery,
    chunk_stream_c_ambient_telemetry,
)
```

---

## Constants Reference

All constants are module-level and importable for use in integration code and tests.

### From `abm.memory.chroma_controller`

| Constant | Type | Value |
|----------|------|-------|
| `COLLECTION_COGNITIVE_IDENTITY` | `str` | `"abm_cognitive_identity"` |
| `COLLECTION_CODE_TOPOLOGIES` | `str` | `"abm_code_topologies"` |
| `COLLECTION_TECHNICAL_MASTERY` | `str` | `"abm_technical_mastery"` |
| `COLLECTION_AMBIENT_TELEMETRY` | `str` | `"abm_ambient_telemetry"` |
| `ALL_COLLECTIONS` | `tuple[str, ...]` | All four names in declaration order |
| `SCHEMA_COGNITIVE_IDENTITY` | `dict[str, str]` | Stream D metadata schema |
| `SCHEMA_CODE_TOPOLOGIES` | `dict[str, str]` | Stream A metadata schema |
| `SCHEMA_TECHNICAL_MASTERY` | `dict[str, str]` | Stream B metadata schema |
| `SCHEMA_AMBIENT_TELEMETRY` | `dict[str, Any]` | Stream C metadata schema |
| `COLLECTION_SCHEMAS` | `dict[str, dict]` | Maps each collection name → its schema |

### From `abm.memory.embedding_wrapper`

| Constant | Type | Value |
|----------|------|-------|
| `OLLAMA_BASE_URL` | `str` | `"http://127.0.0.1:11434"` |
| `OLLAMA_EMBED_ENDPOINT` | `str` | `"http://127.0.0.1:11434/api/embeddings"` |
| `OLLAMA_TAGS_ENDPOINT` | `str` | `"http://127.0.0.1:11434/api/tags"` |
| `EMBEDDING_MODEL` | `str` | `"nomic-embed-text"` |
| `CONNECT_TIMEOUT` | `float` | `5.0` |
| `READ_TIMEOUT` | `float` | `30.0` |

### From `abm.memory.chunking`

| Constant | Type | Value |
|----------|------|-------|
| `STREAM_B_TOKEN_WINDOW` | `int` | `500` |
| `STREAM_B_TOKEN_OVERLAP` | `int` | `50` |
| `STREAM_C_INTERACTION_GAP_SECONDS` | `int` | `120` |

---

## Test Suite

**Files:**
- [`tests/test_phase_v01_gate.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/tests/test_phase_v01_gate.py) — **Phase v0.1 hard gate**
- [`tests/test_memory_isolation.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/tests/test_memory_isolation.py)
- [`tests/test_metadata_and_chunking.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/tests/test_metadata_and_chunking.py)

**Gate run command (must be 100% green before v0.2):**
```bash
python -m pytest tests/test_phase_v01_gate.py -v
```

**Full suite:**
```bash
python -m pytest tests/ -v
```

**Phase v0.1 gate:** All tests in `test_phase_v01_gate.py` must pass 100% before advancing to Phase v0.2.

### Gate proofs (`test_phase_v01_gate.py`)

| Class | Proof |
|-------|-------|
| `TestCollectionIsolationGate` | Real in-memory ChromaDB: doc written to one collection is retrievable there and **never** from the other three (pairwise cross-query) |
| `TestChunkingBoundaryGate` | Stream A never mid-line + AST/brace boundaries; Stream B 500/50 window/overlap; Stream C split only when gap > 120s |
| `TestEmbeddingConsistencyGate` | `embed()` / `embed_batch()` return identical vectors for repeated identical inputs |

### Supporting contract tests

| Class | Coverage |
|-------|----------|
| `TestCollectionNames` | Exact name string values, `ALL_COLLECTIONS` completeness |
| `TestMetadataSchemas` | Field-by-field schema validation, field counts, no extra keys |
| `TestChromeControllerIsolation` | Per-collection write routing, wrong-collection rejection |
| `TestQueryIsolation` | Query never invokes `.query()` on non-target collection |
| `TestEmbeddingWrapper` | Endpoint URL, model name, HTTP method, payload shape |
| `TestEmbeddingWrapperErrors` | Empty input, server down, non-200, malformed response |
| `TestCrossCollectionBleed` | Four simultaneous writes, doc_id crossover check, empty bleed check |
| `TestMetadataModels` | Strict Pydantic validation for all four stream metadata schemas |
| `TestStreamChunking` | Stream A AST/structural chunking, Stream B 500/50 token overlap, Stream C 120-second gap windows |

Isolation gate uses real `ChromaController(in_memory=True)` (EphemeralClient). Embedding consistency mocks HTTP — **no live Ollama required.**

---

*Generated by Antigravity for ABM 2.0 Phase v0.1. Update this file whenever new functions or schemas are added.*

---

## Phase v0.2 — Developer Companion Node

> [!IMPORTANT]
> All v0.2 modules call into v0.1 through its **public API only**. No v0.1 file was modified.
> The only class permitted to call `ChromaController.add_document()` is `IngestionCoordinator`.

---

## Module: `abm.companion.file_watcher`

**File:** [`abm/companion/file_watcher.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/companion/file_watcher.py)

### Constants

| Constant | Type | Value |
|----------|------|-------|
| `CODE_EXTENSIONS` | `frozenset[str]` | `{".py", ".dart", ".kt", ".java", ".js", ".css", ".html"}` |
| `DEVICE_SOURCE` | `str` | `"dynamic_mobile_node"` |
| `DEFAULT_DEBOUNCE_SECONDS` | `float` | `1.0` |
| `EXCLUDED_DIRS` | `frozenset[str]` | See table below |
| `EXCLUDED_EXTENSIONS` | `frozenset[str]` | See table below |

#### `EXCLUDED_DIRS` — directory segments always ignored

Matched against **every component** of an incoming path (using `Path.parts`),
so a segment anywhere in the tree (e.g. `deep/__pycache__/foo.pyc`) is
correctly excluded.

| Segment | Reason |
|---------|--------|
| `__pycache__` | Python bytecode cache |
| `.git` | Git internal objects/refs |
| `.hg` | Mercurial metadata |
| `.svn` | Subversion metadata |
| `.tox` | tox virtual-environment artefacts |
| `.venv` / `venv` / `.env` / `env` | Virtual-environment directories |
| `node_modules` | JavaScript package tree |
| `.pytest_cache` | pytest internal cache |
| `.mypy_cache` | mypy type-check cache |
| `.ruff_cache` | ruff linter cache |
| `dist` / `build` | Python / JS build output |
| `.eggs` | setuptools egg directory |
| `__pypackages__` | PEP 582 local packages |
| `.DS_Store` | macOS Finder metadata (dir form) |
| `Thumbs.db` | Windows thumbnail cache (dir form) |

#### `EXCLUDED_EXTENSIONS` — file suffixes always ignored

Matched against `Path(path).suffix.lower()`.

| Extension | Reason |
|-----------|--------|
| `.pyc` / `.pyo` | Compiled Python bytecode |
| `.pyd` | Windows Python extension module (compiled) |
| `.pyi` | Type-stub files (not runnable source) |
| `.egg` / `.whl` | Python distribution archives |
| `.so` / `.dll` / `.exe` | Compiled native binaries |
| `.o` | C/C++ object file |
| `.class` | JVM bytecode |
| `.log` | Log files (generated output) |
| `.lock` | Lock files (e.g. `poetry.lock` — metadata, not source) |
| `.DS_Store` | macOS Finder metadata (file form) |
| `.swp` / `.swo` | Vim swap files |
| `.tmp` / `.bak` / `.orig` | Temporary / backup / merge artefacts |

### Dataclass `FileChangeEvent`

```python
@dataclass
class FileChangeEvent:
    path: str              # Absolute file path
    event_type: str        # "created" | "modified" | "deleted"
    epoch_timestamp: int   # Unix timestamp (integer seconds) of detection
    repository: str        # Git repo name inferred from nearest .git parent ("" if none)
    device_source: str     # Always "dynamic_mobile_node" — post_init set, do not pass
    extension: str         # Lowercase file extension incl. leading dot — post_init derived
    is_code_file: bool     # True if extension in CODE_EXTENSIONS — post_init derived
```

`device_source`, `extension`, and `is_code_file` are set automatically in `__post_init__`.
Only `path`, `event_type`, `epoch_timestamp`, `repository` are constructor parameters.

> [!NOTE]
> `FileChangeEvent` is only ever constructed **after** `_is_excluded()` has
> returned `False`. Excluded paths are dropped before event construction.

### Class `WorkspaceFileWatcher`

```python
class WorkspaceFileWatcher:
    def __init__(
        self,
        watch_paths: list[str],
        on_code_change: Callable[[FileChangeEvent], None],
        on_telemetry_event: Callable[[FileChangeEvent], None],
        debounce_seconds: float = 1.0,
    ) -> None: ...
```

**Parameters:**
- `watch_paths` — List of absolute directory paths to monitor recursively. Must not be empty.
- `on_code_change` — Callback fired when a code file changes (→ Stream A ingestion).
- `on_telemetry_event` — Callback fired when a non-code file changes (→ Stream C ingestion).
- `debounce_seconds` — Collapses rapid save storms into one event per file. Default `1.0`.

#### `start() -> None`
Starts the watchdog Observer in a background daemon thread. Idempotent.
**Raises:** `FileNotFoundError` if any `watch_paths` entry does not exist.

#### `stop() -> None`
Stops the observer and joins its thread. Idempotent.

#### `is_running() -> bool`
Returns `True` if the background observer is active.

#### Properties

```python
@property
def watch_paths(self) -> list[str]       # Paths being monitored (copy)
@property
def debounce_seconds(self) -> float      # Debounce window in seconds
```

### Internal: `_is_excluded(path: str) -> bool`

```python
def _is_excluded(path: str) -> bool
```

**Single authoritative exclusion gate.** Returns `True` if the path must be
silently ignored. Called inside `_DebounceHandler._schedule()` — the earliest
possible intercept point — so excluded paths:

- never enter the debounce pending queue,
- never trigger a debounce timer,
- never reach `on_code_change` or `on_telemetry_event`,
- and are **never ingested into any stream** (A, B, C, or D).

**Exclusion triggers (either is sufficient):**
1. `Path(path).suffix.lower()` is in `EXCLUDED_EXTENSIONS`.
2. Any segment in `Path(path).parts` is in `EXCLUDED_DIRS`.

Dropped events are logged at `DEBUG` level:
```
FileWatcher excluded (not ingested): <path>
```

**Returns:** `True` → drop; `False` → proceed normally.

### Internal: `_infer_repository(file_path: str) -> str`

```python
def _infer_repository(file_path: str) -> str
```

Walks up the directory tree from `file_path` to find a `.git` directory.
Returns the directory basename containing `.git`, or `""` if not found.

---

## Module: `abm.companion.git_pipeline`

**File:** [`abm/companion/git_pipeline.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/companion/git_pipeline.py)

### Exceptions

```python
class GitPipelineError(RuntimeError): ...
```
Raised for any Git operation failure. Subclasses `RuntimeError`.

### Constants

| Constant | Type | Value |
|----------|------|-------|
| `DEFAULT_MAX_COMMITS` | `int` | `50` |
| `DEVICE_SOURCE` | `str` | `"dynamic_mobile_node"` |

### Dataclass `CommitRecord`

```python
@dataclass
class CommitRecord:
    sha: str                    # Full 40-char commit SHA
    message: str                # First line of commit message (≤200 chars)
    author: str                 # Commit author name
    epoch_timestamp: int        # Unix timestamp (authored time)
    files_changed: list[str]    # Relative paths of all files touched
```

### Dataclass `FileDiff`

```python
@dataclass
class FileDiff:
    path: str          # Relative file path within repository
    language: str      # Language detected from extension ("python"|"dart"|"kotlin")
    added_lines: str   # All added lines joined — deletions excluded
```

### Class `GitPipeline`

```python
class GitPipeline:
    def __init__(self, repo_path: str) -> None: ...
```

**Raises:** `GitPipelineError` if `repo_path` is not a valid Git repository.

#### `repo_name() -> str`
Returns the basename of the repository root directory.

#### `current_branch() -> str`
Returns the active branch name, or `"HEAD"` in detached HEAD state.

#### `head_commit_sha() -> str`
Returns the full SHA of the HEAD commit.
**Raises:** `GitPipelineError` if the repository has no commits.

#### `list_commits(max_count: int = 50) -> list[CommitRecord]`

```python
def list_commits(self, max_count: int = DEFAULT_MAX_COMMITS) -> list[CommitRecord]
```

Returns the `max_count` most recent commits from HEAD, newest first.
**Raises:** `GitPipelineError` on Git failure; `ValueError` if `max_count < 1`.

#### `get_commit_diff(commit_sha: str) -> list[FileDiff]`

```python
def get_commit_diff(self, commit_sha: str) -> list[FileDiff]
```

Returns added/modified lines per file in a commit. Files with only deletions are excluded.
**Raises:** `GitPipelineError` for unknown SHA or diff failure.

#### `get_commit_file_chunks(commit_sha: str, language: str) -> list[str]`

```python
def get_commit_file_chunks(self, commit_sha: str, language: str) -> list[str]
```

Returns AST/structural code chunks for files matching `language` in a commit.
**Calls `abm.memory.chunking.chunk_stream_a_code_topologies()` directly — not reimplemented.**

**Parameters:**
- `commit_sha` — Full or abbreviated commit SHA.
- `language` — One of `"dart"`, `"kotlin"`, `"python"`.

**Returns:** Flat `list[str]` of code chunks across all matching files.
**Raises:** `GitPipelineError`; `ValueError` for unsupported language.

#### `get_commit_telemetry_event(commit_sha: str) -> dict[str, Any]`

```python
def get_commit_telemetry_event(self, commit_sha: str) -> dict[str, Any]
```

Returns a dict for Stream C ingestion with exactly these keys:

```python
{
    "epoch_timestamp": int,           # authored_date as Unix int
    "active_repository": str,         # repo_name()
    "device_source": "dynamic_mobile_node",
    "text": str,                      # "git commit <sha8>: <message>"
    "sha": str,                       # full hexsha
}
```

**Raises:** `GitPipelineError` for unknown SHA.

---

## Module: `abm.companion.code_structure_analyzer`

**File:** [`abm/companion/code_structure_analyzer.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/companion/code_structure_analyzer.py)

General-purpose code structure analyzer built on the v0.1 Stream A chunking contract.
It does not modify `abm.memory.chunking.chunk_stream_a_code_topologies()`.

### Constants

| Constant | Type | Value |
|----------|------|-------|
| `SUPPORTED_STRUCTURE_LANGUAGES` | `frozenset[str]` | `{"dart", "kotlin", "python"}` |

### Dataclass `CodeStructureNode`

```python
@dataclass
class CodeStructureNode:
    kind: str
    name: str
    start_line: int
    end_line: int
    text: str
    identifiers: list[str]
```

Represents one parsed class/function/structural unit.

### Dataclass `CodeStructureAnalysis`

```python
@dataclass
class CodeStructureAnalysis:
    language: str
    chunks: list[str]
    nodes: list[CodeStructureNode]
    identifiers: list[str]
    imports: list[str]
    formatting_patterns: dict[str, Any]
    architectural_preferences: dict[str, Any]
```

`identifiers` preserves frequency so naming-convention extraction can detect repeated habits.

### Class `CodeStructureAnalyzer`

#### `analyze(code: str, language: str) -> CodeStructureAnalysis`

```python
def analyze(self, code: str, language: str) -> CodeStructureAnalysis
```

Parses code into chunks, structure nodes, identifiers, imports, formatting patterns, and architectural preferences.

**Raises:** `ValueError` for empty code or unsupported `language`.

### Function `analyze_code_structure(code: str, language: str) -> CodeStructureAnalysis`

```python
def analyze_code_structure(code: str, language: str) -> CodeStructureAnalysis
```

Convenience wrapper around `CodeStructureAnalyzer().analyze(...)`.

---

## Module: `abm.companion.style_fingerprint`

**File:** [`abm/companion/style_fingerprint.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/companion/style_fingerprint.py)

### Exceptions

```python
class StyleExtractionError(ValueError): ...
```
Raised when `extract()` cannot produce a valid fingerprint. Subclasses `ValueError`.

### Constants

| Constant | Type | Value |
|----------|------|-------|
| `MIN_IDENTIFIER_COUNT` | `int` | `5` |

### Dataclass `StyleFingerprint`

```python
@dataclass
class StyleFingerprint:
    language: str
    framework: str
    state_pattern: str
    naming_convention: str
    camel_case_ratio: float
    identifier_count: int
    formatting_patterns: dict[str, Any]
    architectural_preferences: dict[str, Any]
```

> [!NOTE]
> `camel_case_ratio`, `identifier_count`, `formatting_patterns`, and
> `architectural_preferences` are **never stored in ChromaDB metadata**.
> They are diagnostic fields for observability and Stream A document text only.

### Class `StyleFingerprintExtractor`

#### `extract(code: str, language: str) -> StyleFingerprint`

```python
def extract(self, code: str, language: str) -> StyleFingerprint
```

Analyses `code` and returns a `StyleFingerprint`.

Uses `CodeStructureAnalyzer` for structural parsing, identifier frequency,
formatting patterns, imports, and architecture signals.

**Parameters:**
- `code` — Non-empty source code to analyse.
- `language` — One of `"dart"`, `"kotlin"`, `"python"`.

**Raises:**
- `StyleExtractionError` — if `code` is empty or whitespace-only.
- `ValueError` — if `language` is not one of the three supported values.

**Detection logic:**
- **Python** — uses `ast.parse()` for identifier extraction; falls back to regex on `SyntaxError`.
- **Dart** — regex identifier extraction; BLoC/Flutter import patterns detected (`flutter_bloc`, `extends Bloc<`).
- **Kotlin** — regex identifier extraction; returns `("flutter", "bloc")` defaults (project context).
- **Naming convention** — counts camelCase (`[a-z]...[A-Z]...`) vs snake_case (`word_word`) identifiers. If `< MIN_IDENTIFIER_COUNT` multi-word identifiers found, defaults to `"camelCase"`.

#### `to_stream_a_metadata(fingerprint: StyleFingerprint) -> dict[str, str]`

```python
def to_stream_a_metadata(self, fingerprint: StyleFingerprint) -> dict[str, str]
```

Converts a `StyleFingerprint` into the **exact four-field Stream A metadata dict** from spec section 3.
Ready to pass directly to `ChromaController.add_document()`.

**Returns:**
```python
{
    "language": str,            # fingerprint.language
    "framework": str,           # fingerprint.framework
    "state_pattern": str,       # fingerprint.state_pattern
    "naming_convention": "camelCase",  # always — Stream A schema Literal
}
```

> [!IMPORTANT]
> This dict contains **only** the four fields. No extra keys are ever added.
> `naming_convention` is always `"camelCase"` (the only value accepted by
> `CodeTopologiesMetadata`). Detected snake_case stays on the fingerprint
> object and in `to_stream_a_document()` text — never in ChromaDB metadata.
> Validated against `SCHEMA_CODE_TOPOLOGIES` key set in the v0.2 regression gate.

#### `to_stream_a_document(fingerprint: StyleFingerprint) -> str`

```python
def to_stream_a_document(self, fingerprint: StyleFingerprint) -> str
```

Renders the full style fingerprint into text for Stream A embedding.
Formatting and architectural diagnostics are included in this text, not in metadata.

---

## Module: `abm.companion.ingestion_coordinator`

**File:** [`abm/companion/ingestion_coordinator.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/companion/ingestion_coordinator.py)

> [!IMPORTANT]
> `IngestionCoordinator` is the **only** class in v0.2 that calls `ChromaController.add_document()`.
> No other v0.2 module writes to ChromaDB.

### Constants

| Constant | Type | Description |
|----------|------|-------------|
| `_EXT_TO_LANGUAGE` | `dict[str, str]` | Maps file extension → language string for ingestion routing |

### Dataclass `IngestionResult`

```python
@dataclass
class IngestionResult:
    status: str            # "ok" | "skipped" | "error"
    collection: str        # Collection name that was written to / attempted
    doc_ids: list[str]     # IDs of documents written. Empty on "skipped"/"error".
    reason: str            # Human-readable explanation. Empty on "ok".
```

### Class `IngestionCoordinator`

```python
class IngestionCoordinator:
    def __init__(
        self,
        controller: ChromaController,
        embedder: OllamaEmbeddingWrapper,
        git_pipeline: GitPipeline | None = None,
    ) -> None: ...
```

**Parameters:**
- `controller` — The v0.1 `ChromaController`. **All ChromaDB writes go through this object.**
- `embedder` — The v0.1 `OllamaEmbeddingWrapper`. All embeddings route to `127.0.0.1:11434`.
- `git_pipeline` — Optional `GitPipeline`. If `None`, Git-based ingestion methods return skipped results.

#### `ingest_file_change(event: FileChangeEvent) -> IngestionResult`

```python
def ingest_file_change(self, event: FileChangeEvent) -> IngestionResult
```

Processes a `FileChangeEvent` from the file watcher.

| Event condition | Action |
|-----------------|--------|
| `event_type == "deleted"` | Returns `status="skipped"` — nothing to embed |
| `event.is_code_file == True` | Reads file, chunks via v0.1 `chunk_stream_a_code_topologies()`, fingerprints, embeds, writes to **Stream A**. Also writes file-change event to **Stream C**. |
| `event.is_code_file == False` | Writes a single telemetry event to **Stream C** only. |

**Never raises.** All errors are captured into `IngestionResult.status = "error"`.

#### `ingest_code_fingerprint(code: str, language: str, context_id: str = "manual") -> IngestionResult`

```python
def ingest_code_fingerprint(
    self,
    code: str,
    language: str,
    context_id: str = "manual",
) -> IngestionResult
```

Derives a style fingerprint from source code and writes one document to **Stream A**.
The document text includes naming, formatting, and architectural diagnostics.
The metadata dict contains exactly the existing Stream A fields:
`language`, `framework`, `state_pattern`, `naming_convention`.

**Never writes to Stream B, C, or D. Never adds metadata fields.**

#### `ingest_git_commit(commit_sha: str, language: str) -> IngestionResult`

```python
def ingest_git_commit(self, commit_sha: str, language: str) -> IngestionResult
```

Ingests code from a single Git commit into Stream A and logs one telemetry event to Stream C.

- Calls `GitPipeline.get_commit_file_chunks()` → which calls v0.1 `chunk_stream_a_code_topologies`.
- Each chunk is fingerprinted via `StyleFingerprintExtractor`, embedded, and written to **Stream A**.
- One commit event is written to **Stream C** via `GitPipeline.get_commit_telemetry_event()`.
- **Never writes to Stream B or D.**

Returns `status="skipped"` if `git_pipeline` is `None` or no chunks are produced.
**Never raises.**

#### `ingest_git_tree(language: str, max_commits: int = 50) -> list[IngestionResult]`

```python
def ingest_git_tree(
    self,
    language: str,
    max_commits: int = DEFAULT_MAX_COMMITS,
) -> list[IngestionResult]
```

Ingests the last `max_commits` commits from HEAD. Calls `ingest_git_commit()` per commit.
Returns one `IngestionResult` per commit in reverse-chronological order.
**Never raises.**

### Internal: `_doc_id(prefix: str, content: str) -> str` *(static)*

```python
@staticmethod
def _doc_id(prefix: str, content: str) -> str
```

Generates a stable, unique document ID from a sanitised prefix and the first 12 hex characters
of a SHA-256 hash of `content`. Identical content always produces the same ID — makes
`add_document` calls **idempotent** (upsert behaviour).

---

## Module: `abm.companion.watch_daemon`

**File:** [`abm/companion/watch_daemon.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/companion/watch_daemon.py)

Runnable entry point that wires `WorkspaceFileWatcher` directly to `IngestionCoordinator`.
This is the only module in v0.2 that owns a daemon lifecycle — everything else is a library.

> [!IMPORTANT]
> `watch_daemon` is **not** imported by `abm.companion.__init__`. It is an executable
> entry point only. Import the component classes directly from `abm.companion` instead.

### Run command

```bash
python -m abm.companion.watch_daemon --path <directory> [options]
```

### CLI flags

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--path DIR` | `str` (repeatable) | *(required)* | Directory to watch recursively. Repeat for multiple paths. |
| `--debounce SECONDS` | `float` | `1.0` | Debounce window forwarded to `WorkspaceFileWatcher`. |
| `--chroma-dir DIR` | `str` | `./memory/chroma_store` | ChromaDB persistence directory. |
| `--ollama-url URL` | `str` | `http://127.0.0.1:11434` | Ollama base URL. |
| `--git-path DIR` | `str` | `None` | Optional Git repo path for `GitPipeline`. Omit to run without Git support. |
| `--log-level LEVEL` | `str` | `INFO` | `DEBUG`\|`INFO`\|`WARNING`\|`ERROR`. |

### Public functions

#### `build_coordinator(chroma_dir, ollama_url, git_path) -> IngestionCoordinator`

```python
def build_coordinator(
    chroma_dir: str,
    ollama_url: str,
    git_path: str | None,
) -> IngestionCoordinator
```

Constructs the full v0.1+v0.2 object graph:
`ChromaController` → `OllamaEmbeddingWrapper` → `GitPipeline` (optional) → `IngestionCoordinator`.

If `git_path` is provided but fails `GitPipeline` init, the warning is logged and the
coordinator runs without Git support. File-change ingestion is unaffected.

**Never raises.**

---

#### `run_daemon(watch_paths, coordinator, debounce_seconds) -> NoReturn`

```python
def run_daemon(
    watch_paths: list[str],
    coordinator: IngestionCoordinator,
    debounce_seconds: float,
) -> NoReturn
```

Wires `WorkspaceFileWatcher` to `IngestionCoordinator` and blocks until SIGINT or SIGTERM.

Constructor call (verbatim from spec):

```python
WorkspaceFileWatcher(
    watch_paths=watch_paths,                      # list[str]
    on_code_change=Callable[[FileChangeEvent], None],     # -> Stream A
    on_telemetry_event=Callable[[FileChangeEvent], None], # -> Stream C
    debounce_seconds=debounce_seconds,            # float
)
```

Both callbacks call `coordinator.ingest_file_change(event)` and print one confirmation
line to stdout per event (see output format below).

---

#### `main(argv=None) -> None`

```python
def main(argv: list[str] | None = None) -> None
```

CLI entry point. Resolves paths, calls `build_coordinator()`, then `run_daemon()`.
Registered as `__main__` so `python -m abm.companion.watch_daemon` works directly.

---

### Stdout confirmation format

A single line is printed to stdout (or stderr on error) for every event processed:

```
[ok     ] Stream A [code]       modified   abm/companion/file_watcher.py  (3 chunk(s))
[skipped] Stream C [telemetry]  deleted    some/file.txt  -- Deleted file -- nothing to embed
[error  ] Stream A [code]       created    broken.py  -- Cannot read file: ...
```

| Column | Values |
|--------|--------|
| Status tag | `[ok     ]` \| `[skipped]` \| `[error  ]` |
| Stream label | `Stream A [code]` \| `Stream C [telemetry]` \| `Stream B [docs]` \| `Stream D [identity]` |
| Event type | `created` \| `modified` \| `deleted` |
| Path | Path relative to cwd where possible |
| Detail | Chunk count on ok; reason on skipped/error |

---

## Module: `abm.companion` (package)

**File:** [`abm/companion/__init__.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/companion/__init__.py)

```python
from abm.companion import (
    WorkspaceFileWatcher,
    FileChangeEvent,
    GitPipeline,
    GitPipelineError,
    CommitRecord,
    FileDiff,
    CodeStructureAnalyzer,
    CodeStructureAnalysis,
    CodeStructureNode,
    analyze_code_structure,
    StyleFingerprintExtractor,
    StyleFingerprint,
    StyleExtractionError,
    IngestionCoordinator,
    IngestionResult,
)
```

All public v0.2 classes and dataclasses are re-exported at the package level.

---

## Constants Reference (v0.2)

### From `abm.companion.file_watcher`

| Constant | Type | Value |
|----------|------|-------|
| `CODE_EXTENSIONS` | `frozenset[str]` | `{".py", ".dart", ".kt", ".java", ".js", ".css", ".html"}` |
| `DEVICE_SOURCE` | `str` | `"dynamic_mobile_node"` |
| `DEFAULT_DEBOUNCE_SECONDS` | `float` | `1.0` |

### From `abm.companion.git_pipeline`

| Constant | Type | Value |
|----------|------|-------|
| `DEFAULT_MAX_COMMITS` | `int` | `50` |
| `DEVICE_SOURCE` | `str` | `"dynamic_mobile_node"` |

### From `abm.companion.code_structure_analyzer`

| Constant | Type | Value |
|----------|------|-------|
| `SUPPORTED_STRUCTURE_LANGUAGES` | `frozenset[str]` | `{"dart", "kotlin", "python"}` |

### From `abm.companion.style_fingerprint`

| Constant | Type | Value |
|----------|------|-------|
| `MIN_IDENTIFIER_COUNT` | `int` | `5` |

---

## Test Suite

**Files:**
- [`tests/test_phase_v01_gate.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/tests/test_phase_v01_gate.py) — **Phase v0.1 hard gate**
- [`tests/test_memory_isolation.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/tests/test_memory_isolation.py)
- [`tests/test_metadata_and_chunking.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/tests/test_metadata_and_chunking.py)
- [`tests/test_phase_v02_gate.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/tests/test_phase_v02_gate.py) — **Phase v0.2 hard gate**

**v0.2 gate only (must be 100% green before v0.3):**
```bash
python -m pytest tests/test_phase_v02_gate.py -v
```

**Full suite:**
```bash
python -m pytest tests/ -v
```
### v0.2 Gate: `test_phase_v02_gate.py`

*Updated by Antigravity for ABM 2.0 Phase v0.2. Update this file whenever new functions or schemas are added.*

---

## Phase v0.3 - Executive Orchestrator Engine

Phase v0.3 defines routing, department worker sandbox scope, and JSON delegation schemas only.
It does not build Phase v0.4 Docker sandboxes, compiler loops, or confidence-gate math.

---

## Module: `abm.orchestrator.departments`

**File:** [`abm/orchestrator/departments.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/orchestrator/departments.py)

### Enum `Department`

```python
class Department(str, Enum):
    SOFTWARE_ENGINEERING = "software_engineering"
    STRATEGIC_PLANNING = "strategic_planning"
    ARCHITECTURE = "architecture"
    SECURITY = "security"
    MEMORY_INDEXING = "memory_indexing"
```

### Tool Constants

```python
TOOL_CHROMA_QUERY = "chroma_query"
TOOL_CODE_STRUCTURE_ANALYZER = "code_structure_analyzer"
TOOL_STYLE_FINGERPRINT_EXTRACTOR = "style_fingerprint_extractor"
TOOL_GIT_PIPELINE = "git_pipeline"
TOOL_FILE_WATCHER = "file_watcher"
TOOL_INGESTION_COORDINATOR = "ingestion_coordinator"
TOOL_MODEL_GATEWAY = "model_gateway"
TOOL_SECURITY_STATIC_SCAN = "security_static_scan"
TOOL_PATCH_PROPOSAL_WRITER = "patch_proposal_writer"
TOOL_STRATEGIC_SUMMARY_BUILDER = "strategic_summary_builder"
ALL_WORKER_TOOLS: frozenset[str]
```

### Dataclass `DepartmentWorkerSandbox`

```python
@dataclass(frozen=True)
class DepartmentWorkerSandbox:
    department: Department
    allowed_streams: frozenset[str]
    allowed_tools: frozenset[str]
    execution_context_id: str
    autonomy_level: int
    assigned_agents: tuple[str, ...]
    hard_success_conditions: tuple[str, ...]
    description: str
```

Represents an isolated department execution context. `allowed_streams` must be a subset of the four v0.1 collection constants. `allowed_tools` must be a subset of `ALL_WORKER_TOOLS`. `execution_context_id` is stable and formatted as `sandbox:<department>`.

```python
def can_access_stream(self, collection_name: str) -> bool
def can_use_tool(self, tool_name: str) -> bool
```

### Registry `DEPARTMENT_REGISTRY`

```python
DEPARTMENT_REGISTRY: dict[Department, DepartmentWorkerSandbox]
```

| Department | Streams | Tools | Autonomy |
|------------|---------|-------|----------|
| `software_engineering` | Stream A, B, C | `chroma_query`, `code_structure_analyzer`, `style_fingerprint_extractor`, `git_pipeline`, `patch_proposal_writer` | `2` |
| `strategic_planning` | Stream D, B | `chroma_query`, `model_gateway`, `strategic_summary_builder` | `1` |
| `architecture` | Stream A, D, B | `chroma_query`, `code_structure_analyzer`, `model_gateway`, `patch_proposal_writer` | `2` |
| `security` | Stream B, C | `chroma_query`, `security_static_scan`, `git_pipeline` | `1` |
| `memory_indexing` | Stream D, A, B, C | `chroma_query`, `file_watcher`, `git_pipeline`, `ingestion_coordinator` | `0` |

```python
def get_sandbox(department: Department) -> DepartmentWorkerSandbox
def department_from_string(value: str) -> Department
```

---

## Module: `abm.orchestrator.task_contract`

**File:** [`abm/orchestrator/task_contract.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/orchestrator/task_contract.py)

### Class `TaskContract`

```python
class TaskContract(BaseModel):
    contract_id: str
    objective: str
    department: Department
    assigned_agents: list[str]
    autonomy_permission_level: int
    hard_success_conditions: list[str]
    created_at: int
```

Spec section 5 delegation contract. `extra="forbid"`.

```python
def to_dict(self) -> dict[str, Any]

@classmethod
def build(
    cls,
    objective: str,
    department: Department,
    assigned_agents: list[str],
    autonomy_permission_level: int,
    hard_success_conditions: list[str],
    epoch: int | None = None,
) -> TaskContract
```

### Class `RouterResult`

```python
class RouterResult(BaseModel):
    contract: TaskContract
    raw_classification: str
    confidence_hint: str
    model_used: str
    routing_latency_ms: int
    fallback_used: bool = False
```

Complete output of `ClassificationRouter.classify()`. `extra="forbid"`.

```python
def to_dict(self) -> dict[str, Any]
```

### Class `WorkerTaskHandoff`

Router -> worker task handoff JSON schema.

```python
class WorkerTaskHandoff(BaseModel):
    contract: TaskContract
    execution_context_id: str
    allowed_streams: list[str]
    allowed_tools: list[str]
```

`extra="forbid"`. `execution_context_id` must start with `sandbox:`. `allowed_tools` must be known tool constants.

```python
def to_dict(self) -> dict[str, Any]

@classmethod
def build(cls, contract: TaskContract) -> WorkerTaskHandoff
```

`build()` copies `allowed_streams`, `allowed_tools`, and `execution_context_id` from the contract department's `DepartmentWorkerSandbox`.

### Class `WorkerResultReport`

Worker -> router result-reporting JSON schema.

```python
class WorkerResultReport(BaseModel):
    contract_id: str
    department: Department
    execution_context_id: str
    status: Literal["success", "failed", "blocked"]
    summary: str
    artifacts: list[str]
    streams_accessed: list[str]
    tools_used: list[str]
    success_conditions_met: list[str]
    error_message: str
    completed_at: int
```

`extra="forbid"`. `contract_id` must start with `TXN_`; `execution_context_id` must start with `sandbox:`; `summary` must be non-empty; `tools_used` must be known tool constants.

```python
def to_dict(self) -> dict[str, Any]
def validate_against_handoff(self, handoff: WorkerTaskHandoff) -> bool

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
) -> WorkerResultReport
```

`validate_against_handoff()` returns `False` if the report escapes the handoff's contract id, department, execution context, allowed streams, allowed tools, or hard success conditions.

---

## Module: `abm.orchestrator` (package)

**File:** [`abm/orchestrator/__init__.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/orchestrator/__init__.py)

```python
from abm.orchestrator import (
    Department,
    DepartmentWorkerSandbox,
    DEPARTMENT_REGISTRY,
    ALL_WORKER_TOOLS,
    get_sandbox,
    department_from_string,
    TaskContract,
    RouterResult,
    WorkerTaskHandoff,
    WorkerResultReport,
)
```

---

## Phase v0.3 Test Gate

**Gate run command (must be 100% green before v0.4):**
```bash
python -m pytest tests/test_phase_v03_gate.py -v
```

### Hard gate proofs

| Class | Proves |
|-------|--------|
| `TestRouterClassificationOnlyGate` | Router has no content-generation or worker-invocation methods; `classify()` returns `RouterResult` only; module never imports `WorkerTaskHandoff` / `WorkerResultReport` |
| `TestWorkerSandboxScopeIsolationGate` | Exhaustive per-department stream/tool allow+deny via `can_access_stream` / `can_use_tool`; handoff scope matches sandbox; foreign stream/tool reports fail `validate_against_handoff` |
| `TestDelegationAndReportSchemaGate` | Valid `TaskContract` / `WorkerTaskHandoff` / `WorkerResultReport` JSON round-trips; malformed payloads (extra fields, bad prefixes, unknown tools, empty summary, invalid status) raise `ValidationError` |

### Supporting contract coverage

| Class | Proves |
|-------|--------|
| `TestDepartmentRegistry` | Stream/tool scope and stable `sandbox:<dept>` execution context IDs |
| `TestDepartmentWorkerSandbox` | Autonomy bounds, frozen sandboxes, helper methods |
| `TestWorkerTaskHandoffSchema` / `TestWorkerResultReportSchema` | Handoff and report field shapes |
| `TestClassificationRouterNeverGenerates` | Banned generate/write/respond/explain/complete methods |
| `TestClassificationRouterClassify` / Fallback / BadJSON | Routing behaviour and never-raise contract |
| `TestV01V02V03RegressionGate` | All previous phase constants and schemas unchanged |

---

## Phase v0.4 — Safe Action Sandbox

> [!IMPORTANT]
> The sandbox modules manage isolated code execution in ephemeral Docker containers, enforcing the mathematical Validation Gate defined in spec section 6.

---

## Module: `abm.sandbox.models`

**File:** [`abm/sandbox/models.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/sandbox/models.py)

### Pydantic Model `ExecutionResult`

Represents the result of a command run inside the sandbox.

```python
class ExecutionResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
    execution_time_ms: int
```

### Pydantic Model `ValidationScores`

The five math parameters used in the Confidence Gate.

```python
class ValidationScores(BaseModel):
    m_align: float      # Memory Alignment
    t_correct: float    # Technical Syntax Validation
    s_val: float        # Security Verification
    test_succ: float    # Isolated Test Success
    p_align: float      # Preference Alignment
```

### Pydantic Model `GateResult`

The outcome of the Multi-Factor Validation Gate.

```python
class GateResult(BaseModel):
    passed: bool
    confidence_score: float
    reason: str
    quarantine_flag: bool = False
    quarantine_path: str | None = None
```

---

## Module: `abm.sandbox.container`

**File:** [`abm/sandbox/container.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/sandbox/container.py)

### Class `DockerSandbox`

Context manager for ephemeral Docker container lifecycles.

```python
class DockerSandbox:
    def __init__(self, image: str = "python:3.11-slim", timeout_seconds: int = 60) -> None: ...
    def __enter__(self) -> "DockerSandbox": ...
    def __exit__(self, exc_type, exc_val, exc_tb) -> None: ...

    def write_file(self, container_path: str, content: str) -> None
    def execute_command(self, command: str | list[str]) -> ExecutionResult
```

---

## Module: `abm.sandbox.execution_loop`

**File:** [`abm/sandbox/execution_loop.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/sandbox/execution_loop.py)

### Class `SandboxCheckLoop`

Injects code files and executes tests or compilers inside a sandbox.

```python
class SandboxCheckLoop:
    def __init__(self, sandbox_factory: Callable[[], DockerSandbox]) -> None: ...
    def evaluate_code(self, code_files: dict[str, str], test_command: str | list[str]) -> ExecutionResult
```

---

## Module: `abm.sandbox.validation_gate`

**File:** [`abm/sandbox/validation_gate.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/sandbox/validation_gate.py)

### Class `MultiFactorGate`

Enforces the absolute governance formula from ABM_SPEC section 6.

```python
class MultiFactorGate:
    def __init__(self, quarantine_dir: str = "memory/ambiguity_quarantine") -> None: ...

    def calculate_confidence_score(self, scores: ValidationScores) -> float
    def evaluate_floor_gates(self, scores: ValidationScores) -> list[str]
    def should_quarantine(
        self, confidence_score: float, floor_gate_breaches: list[str]
    ) -> bool
    
    def evaluate(
        self, contract: TaskContract, scores: ValidationScores, payload: str
    ) -> GateResult
```

- **Formula**: `C = 0.3(m_align) + 0.25(t_correct) + 0.2(s_val) + 0.15(test_succ) + 0.1(p_align)`
- **Threshold**: `C >= 0.85`
- **Floor Gates**: `s_val >= 0.80`, `test_succ >= 0.90`
- **Quarantine**: If `C < 0.85` or any floor gate is breached, `evaluate()` returns `GateResult(quarantine_flag=True)` and writes `quarantine_TXN_...txt` to the `memory/ambiguity_quarantine/` directory.

---

## Module: `abm.sandbox` (package)

**File:** [`abm/sandbox/__init__.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/sandbox/__init__.py)

Re-exports `ExecutionResult`, `ValidationScores`, `GateResult`, `DockerSandbox`, `SandboxCheckLoop`, `MultiFactorGate`.

---

### v0.4 Gate: `test_phase_v04_gate.py`

**Gate run command (must be 100% green before v0.5):**
```bash
python -m pytest tests/test_phase_v04_gate.py -v
```

### Hard gate proofs

| Class | Proves |
|-------|--------|
| `TestSandboxIsolationTeardownGate` | Fresh container per run; stop+remove+close on exit; teardown on execute errors; `network_mode=none`; no shared write state across sequential `SandboxCheckLoop` runs |
| `TestCompilerTestCheckRejectionGate` | Compile/test failures return non-zero `exit_code` (not rewritten to success); failed checks still tear down the sandbox |
| `TestConfidenceFormulaExactGate` | `C = 0.30M+0.25T+0.20S+0.15Test+0.10P` exact across inputs; boundaries at `S=0.80`, `Test=0.90`, `C=0.85` (pass) and just-below (quarantine) |
| `TestFloorBreachQuarantinesHighCGate` | `S_val < 0.80` or `Test_succ < 0.90` quarantines even when `C ≥ 0.85`; high-C with floors met is accepted |

### Supporting contract coverage

| Class | Proves |
|-------|--------|
| `TestDockerSandbox` | Context manager lifecycle, tar file injection, execute_command |
| `TestExecutionLoop` | Code injection then test command happy path |
| `TestValidationGateMath` / `TestValidationFloorGates` / `TestValidationQuarantine` | Formula, floors, quarantine file content |
| `TestV01V02V03RegressionGate` | Hard-asserts zero state or constraint drift from `v0.1`, `v0.2`, `v0.3` |

---

## Phase v0.5 — FirstMinds Strategic Wing

> [!IMPORTANT]
> The Strategic Wing modules track corporate decisions and aggregate workflow states. They strictly adhere to the rule of not modifying core v0.1–v0.4 functionality, relying purely on existing interfaces and data shapes.

---

## Module: `abm.strategic_wing.decision_journal`

**File:** [`abm/strategic_wing/decision_journal.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/strategic_wing/decision_journal.py)

### Class `DecisionJournal`

Writes durable records of strategic decisions to Stream D (`abm_cognitive_identity`).

```python
class DecisionJournal:
    def __init__(self, controller: ChromaController, embedder: OllamaEmbeddingWrapper) -> None: ...
    
    def log_decision(
        self, what_decided: str, why_decided: str, epoch: int | None = None
    ) -> str
```

- Embeds the reasoning directly into the document `text` matrix to comply with the strict, immutable `SCHEMA_COGNITIVE_IDENTITY`.
- Generates a custom `doc_id` with format `DECISION_{epoch}_{uuid}`.

---

## Module: `abm.strategic_wing.workflow_monitor`

**File:** [`abm/strategic_wing/workflow_monitor.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/strategic_wing/workflow_monitor.py)

### Enum `TaskState`

```python
class TaskState(Enum):
    ROUTED = "ROUTED"
    IN_SANDBOX = "IN_SANDBOX"
    EXECUTED = "EXECUTED"
    QUARANTINED = "QUARANTINED"
    PASSED = "PASSED"
```

### Dataclass `TaskRecord`

```python
@dataclass
class TaskRecord:
    contract: TaskContract
    state: TaskState
    execution_result: ExecutionResult | None = None
    gate_result: GateResult | None = None
```

### Class `WorkflowMonitor`

Read-side aggregation registry tracking task state across the orchestrator and sandbox. Does not run active threads; depends on push registration from callers and lazy-evaluation of the quarantine disk layer.

```python
class WorkflowMonitor:
    def __init__(self, quarantine_dir: str = "memory/ambiguity_quarantine") -> None: ...
    
    def register_routed_task(self, contract: TaskContract) -> None
    def mark_in_sandbox(self, contract_id: str) -> None
    def record_execution(self, contract_id: str, result: ExecutionResult) -> None
    def record_gate_result(self, contract_id: str, gate: GateResult) -> None
    def scan_quarantine_directory(self) -> list[str]
    def get_overview_report(self) -> str
```

- **`get_overview_report()`**: Emits a human-readable summary of all registered tasks.
- **`scan_quarantine_directory()`**: Physically scans the disk for `quarantine_TXN_*.txt` to automatically sync the state of offline or previously quarantined tasks into the registry.

---

## Module: `abm.strategic_wing.strategic_asset_analyzer`

**File:** [`abm/strategic_wing/strategic_asset_analyzer.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/strategic_wing/strategic_asset_analyzer.py)

Read-only strategic analyzer that maps company-direction queries into options using the existing memory streams. It performs analysis only and never calls `ChromaController.add_document()` or `DecisionJournal.log_decision()`.

### Constants

```python
STREAM_LABELS: dict[str, str]
```

Maps each canonical collection name to its stream label.

### Dataclass `StrategicContextItem`

```python
@dataclass(frozen=True)
class StrategicContextItem:
    collection_name: str
    document_id: str
    text: str
    metadata: dict[str, Any]
    distance: float | None = None
```

### Dataclass `StrategicOption`

```python
@dataclass(frozen=True)
class StrategicOption:
    title: str
    rationale: str
    supporting_streams: list[str]
    evidence: list[StrategicContextItem]
    tradeoffs: list[str]
    next_questions: list[str]
```

### Dataclass `StrategicAnalysisResult`

```python
@dataclass(frozen=True)
class StrategicAnalysisResult:
    query: str
    context_items: list[StrategicContextItem]
    options: list[StrategicOption]
    decision_recorded: bool = False
```

`decision_recorded` is always `False`; decision persistence belongs to `DecisionJournal`.

### Class `StrategicAssetAnalyzer`

```python
class StrategicAssetAnalyzer:
    def __init__(
        self,
        controller: ChromaController,
        embedder: OllamaEmbeddingWrapper,
        collections: tuple[str, ...] = ALL_COLLECTIONS,
    ) -> None: ...

    def analyze(
        self, query: str, n_results_per_stream: int = 3
    ) -> StrategicAnalysisResult

    def retrieve_context(
        self, query: str, n_results_per_stream: int = 3
    ) -> list[StrategicContextItem]

    def map_options(
        self, query: str, context_items: list[StrategicContextItem]
    ) -> list[StrategicOption]
```

- **`retrieve_context()`**: Embeds `query` through `OllamaEmbeddingWrapper.embed()` and calls `ChromaController.query_collection()` for each configured collection.
- **`map_options()`**: Produces analysis-only option paths from Stream D, A, B, and C evidence.
- **`analyze()`**: Returns `StrategicAnalysisResult` with mapped options. It never records or chooses a decision.

---

## Module: `abm.strategic_wing` (package)

**File:** [`abm/strategic_wing/__init__.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/strategic_wing/__init__.py)

Re-exports `DecisionJournal`, `WorkflowMonitor`, `TaskState`, `TaskRecord`, `StrategicAssetAnalyzer`, `StrategicContextItem`, `StrategicOption`, and `StrategicAnalysisResult`.

---

### v0.5 Gate: `test_phase_v05_gate.py`

**Gate run command (must be 100% green before v1.0):**
```bash
python -m pytest tests/test_phase_v05_gate.py -v
```

### Hard gate proofs

| Class | Proves |
|-------|--------|
| `TestDecisionJournalStreamDSchemaGate` | Journal metadata is exactly `SCHEMA_COGNITIVE_IDENTITY` (3 fields); validates via `CognitiveIdentityMetadata`; decision payload lives in text, not metadata |
| `TestWorkflowMonitorReadOnlyGate` | Monitor never imports/calls orchestrator or sandbox write APIs; holds no router/sandbox/gate refs; lifecycle updates are local registry only |
| `TestAnalyzerDecisionSeparationGate` | Analyzer never calls `add_document` / `DecisionJournal.log_decision`; `decision_recorded` stays `False`; recording requires a separate explicit journal call |

### Supporting contract coverage

| Class | Proves |
|-------|--------|
| `TestDecisionJournal` | Embeds decision text and writes Stream D |
| `TestWorkflowMonitor` | Task lifecycle, quarantine scan, overview report |
| `TestStrategicAssetAnalyzer` | Multi-stream retrieval and option mapping |
| `TestV01V02V03V04RegressionGate` | Prior-phase constants unchanged |

*Updated for ABM 2.0 Phase v0.5 hard gate. Update this file whenever new functions or schemas are added.*

---

## Phase v1.0 — API Layer & Capability Catalogue

> [!IMPORTANT]
> This section IS the capability catalogue. No separate deliverable exists.
> Every capability the ABM engine exposes to any client is documented here with
> its `STATUS`, `OWNER`, `DEPENDENCIES`, and `CONSUMERS` — the four fields that
> make this a living contract (Architectural Constitution rules 13 and 14).

---

### Updated File Map (v1.0 additions)

```
ABM-2.0/
├── abm/
│   ├── api/                                  # v1.0 — API Layer
│   │   ├── __init__.py                       # Re-exports full public surface
│   │   ├── capabilities.py                   # All capabilities, status-tagged
│   │   └── core/
│   │       ├── __init__.py                   # Re-exports APIConfig, ServiceRegistry, HealthStatus
│   │       ├── config.py                     # APIConfig dataclass
│   │       └── registry.py                   # ServiceRegistry (boot/shutdown/health_check)
│   └── clients/
│       └── console/                          # v1.0 — Client #1: Console
│           ├── __init__.py
│           ├── commands.py                   # cmd_* handlers → API
│           ├── formatter.py                  # Terminal output formatters
│           └── main.py                       # CLI entry point (argparse)
├── tests/
│   └── test_phase_v10_gate.py               # Hard gate: API + console (49 tests)
```

---

## Module: `abm.api.core.config`

**File:** [`abm/api/core/config.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/api/core/config.py)

### Dataclass `APIConfig`

```python
@dataclass
class APIConfig:
    chroma_persist_directory: str = "./memory/chroma_store"
    ollama_base_url: str = "http://127.0.0.1:11434"
    embedding_model: str = "nomic-embed-text"
    classification_model: str = "phi3:mini"
    quarantine_dir: str = "memory/ambiguity_quarantine"
    connect_timeout: float = 5.0
    read_timeout: float = 30.0
    n_retrieval_results: int = 5
```

All defaults match the v0.1–v0.5 module constants. Create one instance at startup
and pass it to `ServiceRegistry`. Do not mutate after boot.

---

## Module: `abm.api.core.registry`

**File:** [`abm/api/core/registry.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/api/core/registry.py)

### Dataclass `HealthStatus`

```python
@dataclass
class HealthStatus:
    ollama_reachable: bool
    chroma_ready: bool
    degraded: bool
    notes: list[str]
```

### Class `ServiceRegistry`

Boot / service-registration / shutdown lifecycle manager. Holds lazily-initialised
singletons for every service the capability functions depend on.

```python
class ServiceRegistry:
    def __init__(self, config: APIConfig | None = None) -> None: ...

    def boot(self) -> None
    def shutdown(self) -> None
    def health_check(self) -> HealthStatus

    # Read-only service accessors (raise RuntimeError before boot())
    @property def config(self) -> APIConfig
    @property def controller(self) -> ChromaController
    @property def embedder(self) -> OllamaEmbeddingWrapper
    @property def gateway(self) -> OllamaModelGateway
    @property def router(self) -> ClassificationRouter
    @property def monitor(self) -> WorkflowMonitor
    @property def analyzer(self) -> StrategicAssetAnalyzer
    @property def is_booted(self) -> bool
```

**Boot order (dependency-first):**
1. `ChromaController` (v0.1)
2. `OllamaEmbeddingWrapper` (v0.1)
3. `OllamaModelGateway` (v0.3)
4. `ClassificationRouter` (v0.3 — depends on gateway + controller + embedder)
5. `WorkflowMonitor` (v0.5)
6. `StrategicAssetAnalyzer` (v0.5)

**Design note:** This is NOT a formal DI/IoC container — that is an
ARCHITECTURE_BACKLOG candidate. This is plain shared-instance management with
lifecycle discipline sufficient for the current single-client scope.

**`health_check()` contract:** Never raises. Returns `HealthStatus(degraded=True)`
if Ollama is unreachable or ChromaDB is not ready. (Constitution rule 9.)

**Usage:**
```python
config = APIConfig()
registry = ServiceRegistry(config)
registry.boot()
# … use registry.router, registry.embedder, etc. …
registry.shutdown()
```

---

## Module: `abm.api.capabilities`

**File:** [`abm/api/capabilities.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/api/capabilities.py)

> This module IS the capability catalogue. Each function is tagged with
> `STATUS`, `OWNER`, `DEPENDENCIES`, and `CONSUMERS`.

### Status taxonomy

| Tag | Meaning |
|-----|---------|
| `stable` | Tested, gated v0.1–v0.5 backend exists; wired to a console command now. |
| `experimental` | Built but not yet wired to any client. (None today.) |
| `future` | Documented stub only. `NotImplementedError`. Backend has no phase brief yet. |

---

### Return types

```python
@dataclass
class AnswerResult:
    question: str
    department: str          # Department enum value string
    confidence: str          # "high" | "medium" | "low"
    hits: list[dict]         # {id, text, collection, distance, metadata}
    fallback_used: bool
    degraded: bool

@dataclass
class KnowledgeResult:
    query: str
    hits: list[dict]         # {id, text, collection, distance, metadata}
    degraded: bool

@dataclass
class StatusResult:
    overview: str
    quarantined_ids: list[str]
    ollama_reachable: bool
    chroma_ready: bool
    degraded: bool

@dataclass
class MemoryResult:
    project_name: str
    streams: dict[str, list[dict]]   # collection_name → hits
    total_hits: int
    degraded: bool

@dataclass
class ExplainResult:
    target: str
    found: bool
    records: list[dict]     # {source: "monitor"|"decision_journal", ...}
    notes: str
```

---

### ── STABLE Capabilities ────────────────────────────────────────────────────

#### `answerQuestion(question, *, registry, n_results=None) → AnswerResult`

```python
def answerQuestion(
    question: str,
    *,
    registry: ServiceRegistry,
    n_results: int | None = None,
) -> AnswerResult
```

- **STATUS:** `stable`
- **OWNER:** `abm.orchestrator.router.ClassificationRouter`
- **DEPENDENCIES:** `ServiceRegistry.router`, `ServiceRegistry.embedder`, `ServiceRegistry.controller`
- **CONSUMERS:** console `ask` command

Classifies the question to a `Department` (v0.3 router), then queries only
that department's `allowed_streams` for relevant memory hits. Degrades
gracefully when Ollama is unreachable (`fallback_used=True`, empty hits,
`degraded=True`). Never raises to caller.

---

#### `retrieveKnowledge(query, *, registry, n_results=None) → KnowledgeResult`

```python
def retrieveKnowledge(
    query: str,
    *,
    registry: ServiceRegistry,
    n_results: int | None = None,
) -> KnowledgeResult
```

- **STATUS:** `stable`
- **OWNER:** `abm.memory.chroma_controller.ChromaController`
- **DEPENDENCIES:** `ServiceRegistry.embedder`, `ServiceRegistry.controller`
- **CONSUMERS:** console `search` command

Direct semantic search across all four memory streams without classification
routing. Returns hits sorted by distance. Degrades gracefully on embed failure.

---

#### `getSystemStatus(*, registry) → StatusResult`

```python
def getSystemStatus(*, registry: ServiceRegistry) -> StatusResult
```

- **STATUS:** `stable`
- **OWNER:** `abm.strategic_wing.workflow_monitor.WorkflowMonitor`
- **DEPENDENCIES:** `ServiceRegistry.monitor`, `ServiceRegistry.health_check()`
- **CONSUMERS:** console `status` command

Aggregates `WorkflowMonitor.get_overview_report()`, `scan_quarantine_directory()`,
and `ServiceRegistry.health_check()`. Read-only. Never raises.

---

#### `summarizeProject(project_name, *, registry, n_results_per_stream=3) → StrategicAnalysisResult`

```python
def summarizeProject(
    project_name: str,
    *,
    registry: ServiceRegistry,
    n_results_per_stream: int = 3,
) -> StrategicAnalysisResult
```

- **STATUS:** `stable`
- **OWNER:** `abm.strategic_wing.strategic_asset_analyzer.StrategicAssetAnalyzer`
- **DEPENDENCIES:** `ServiceRegistry.analyzer` (→ embedder + controller)
- **CONSUMERS:** console `summarize` command

Thin delegation to `StrategicAssetAnalyzer.analyze()`. Returns a
`StrategicAnalysisResult` with `decision_recorded=False` always.
**Raises** `ValueError` for empty project_name; `RuntimeError` if Ollama
is unreachable (propagated from analyzer).

---

#### `aggregateProjectMemory(project_name, *, registry, n_results=None) → MemoryResult`

```python
def aggregateProjectMemory(
    project_name: str,
    *,
    registry: ServiceRegistry,
    n_results: int | None = None,
) -> MemoryResult
```

- **STATUS:** `stable`
- **OWNER:** `abm.memory.chroma_controller.ChromaController`
- **DEPENDENCIES:** `ServiceRegistry.embedder`, `ServiceRegistry.controller`
- **CONSUMERS:** console `memory` command

Embeds the project name, queries all four streams independently, returns
results grouped by collection name. A composed retrieval view — no new engine.
Degrades gracefully on embed failure.

---

#### `explainAuditRecord(target, *, registry) → ExplainResult`

```python
def explainAuditRecord(
    target: str,
    *,
    registry: ServiceRegistry,
) -> ExplainResult
```

- **STATUS:** `stable`
- **OWNER:** `abm.strategic_wing.workflow_monitor.WorkflowMonitor` (source A),
  `abm.memory.chroma_controller.ChromaController` (source B — Stream D)
- **DEPENDENCIES:** `ServiceRegistry.monitor`, `ServiceRegistry.embedder`,
  `ServiceRegistry.controller`
- **CONSUMERS:** console `explain` command

Two audit sources consulted (constitution rule 5 — every action is auditable):

**Source A — WorkflowMonitor (in-memory, live-session scope):**
Looks up `target` as a contract_id substring. Each found `TaskRecord` exposes:
routing department, confidence_hint, task state, v0.4 gate scores
(confidence_score, quarantine_flag), and execution result.

**Source B — ChromaDB Stream D (persisted, cross-session):**
Embeds `target` and queries `abm_cognitive_identity` for
`STRATEGIC DECISION RECORD` entries written by `DecisionJournal.log_decision()`.

Both sources are searched and combined in the result. Never raises.

---

### ── FUTURE Capabilities (stubs) ─────────────────────────────────────────────

Each raises `NotImplementedError`. A console command may only be added the day
its backend phase is fully gated. See `ARCHITECTURE_BACKLOG.md` and
`CLIENT_01_CONSOLE.md`.

| Function | STATUS | Why deferred |
|----------|--------|--------------|
| `continueTask(task_id, *, registry)` | `future` | Requires session-state / task-continuation engine — not designed anywhere in roadmap |
| `reflectOnWork(*, registry)` | `future` | Requires reflection engine — does not exist in any `ABM_SPEC.md` phase |
| `planProject(project, *, registry)` | `future` | Requires planning agent — does not exist |
| `learnTopic(topic, *, registry)` | `future` | Requires autonomous research-task queue — does not exist |

---

## Module: `abm.api` (package)

**File:** [`abm/api/__init__.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/api/__init__.py)

```python
from abm.api import (
    # Core lifecycle
    APIConfig, ServiceRegistry, HealthStatus,
    # Return types
    AnswerResult, KnowledgeResult, StatusResult, MemoryResult, ExplainResult,
    # Stable capabilities
    answerQuestion, retrieveKnowledge, getSystemStatus,
    summarizeProject, aggregateProjectMemory, explainAuditRecord,
    # Future stubs (NotImplementedError)
    continueTask, reflectOnWork, planProject, learnTopic,
)
```

All clients import from `abm.api` only — never from `abm.api.core` or
`abm.api.capabilities` directly.

---

## Phase v1.0 — Console Client (#1)

### Module: `abm.clients.console.commands`

**File:** [`abm/clients/console/commands.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/clients/console/commands.py)

Six command handlers. Each accepts plain Python scalars + `registry` keyword
arg, calls one API capability, passes the result to a formatter.

```python
def cmd_ask(question: str, *, registry: ServiceRegistry) -> str
def cmd_search(query: str, *, registry: ServiceRegistry) -> str
def cmd_status(*, registry: ServiceRegistry) -> str
def cmd_summarize(project: str, *, registry: ServiceRegistry) -> str
def cmd_memory(project: str, *, registry: ServiceRegistry) -> str
def cmd_explain(target: str, *, registry: ServiceRegistry) -> str
```

**Invariants:**
- No `cmd_*` function imports from `abm.memory`, `abm.orchestrator`,
  `abm.companion`, `abm.sandbox`, or `abm.strategic_wing` directly.
- `cmd_continue`, `cmd_reflect`, `cmd_plan`, `cmd_learn` do NOT exist —
  no backend engine is built for them.

---

### Module: `abm.clients.console.formatter`

**File:** [`abm/clients/console/formatter.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/clients/console/formatter.py)

```python
def format_ask(result: AnswerResult) -> str
def format_search(result: KnowledgeResult) -> str
def format_status(result: StatusResult) -> str
def format_summarize(result: StrategicAnalysisResult) -> str
def format_memory(result: MemoryResult) -> str
def format_explain(result: ExplainResult) -> str
```

Zero cognitive logic. Converts API result types to terminal output with
relevance bars, stream labels, snippet truncation, and degraded warnings.

---

### Module: `abm.clients.console.main`

**File:** [`abm/clients/console/main.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/clients/console/main.py)

CLI entry point. Usage:

```bash
python -m abm.clients.console.main ask "what is ABM?"
python -m abm.clients.console.main search "BLoC pattern"
python -m abm.clients.console.main status
python -m abm.clients.console.main summarize smart_transit
python -m abm.clients.console.main memory houseconnect
python -m abm.clients.console.main explain TXN_12345
python -m abm.clients.console.main --verbose ask "..."
python -m abm.clients.console.main --chroma-dir /path/to/db status
```

Boot sequence: parse args → `APIConfig()` → `ServiceRegistry.boot()` →
dispatch to `cmd_*` → print → `ServiceRegistry.shutdown()`.

Exits `0` on success, `1` on error, `130` on `KeyboardInterrupt`.

---

## Phase v1.0 Test Gate

**File:** [`tests/test_phase_v10_gate.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/tests/test_phase_v10_gate.py)

**Gate run command:**
```bash
python -m pytest tests/test_phase_v10_gate.py -v
```

**Full regression:**
```bash
python -m pytest tests/ -v
```

### Hard gate proofs (49 tests — all mocked, no live Ollama required)

| Class | Proves |
|-------|--------|
| `TestAPILayerStructureGate` | Six stable capabilities exist; four future stubs raise `NotImplementedError`; no module-leaking names; return types are typed dataclasses not raw ChromaDB types |
| `TestCapabilityStatusTagsGate` | Every stable capability tagged `stable`; every future stub tagged `future`; all stable capabilities declare OWNER, DEPENDENCIES, CONSUMERS |
| `TestServiceRegistryLifecycleGate` | Accessing services before boot raises; shutdown is idempotent; double boot is a warning not an error; health_check never raises; APIConfig defaults match v0.1–v0.5 constants |
| `TestConsoleCommandsOnlyStableGate` | Exactly six `cmd_*` functions exist; four deferred commands absent; commands.py imports only through `abm.api`; all commands accept `registry` keyword |
| `TestAPICapabilityContractGate` | Each capability delegates to correct backend; returns correct typed result; degrades gracefully (never raises) when Ollama is unavailable |
| `TestPriorPhaseRegressionGate` | v0.1–v0.5 collection names, department enum values, task state values, validation formula weights, and API config Ollama URL are all unchanged |

*Updated for ABM 2.0 Phase v1.0. Update this file whenever new capabilities or schemas are added.*

---

## Phase v1.0 — Flutter Foreground Service & Ambient Interaction Manager

> [!IMPORTANT]
> This phase adds the ABM mobile node (Flutter/Android) and the Python-side
> ambient interaction manager that feeds Stream C with retention-aware writes.
> All v0.1–v0.5 modules are sealed and unchanged (PROJECT_BRIEF.md ground rule 2).

---

### Updated File Map (v1.0 mobile additions)

```
ABM-2.0/
├── abm/
│   ├── mobile/                                 # v1.0 — Ambient Interaction
│   │   ├── __init__.py                         # Re-exports full public surface
│   │   ├── event_models.py                     # AmbientEvent dataclass + PERMITTED_SOURCE_KINDS
│   │   ├── stream_c_writer.py                  # StreamCWriter (retention-aware write path)
│   │   ├── retention_housekeeper.py            # StreamCRetentionHousekeeper + lifecycle stages
│   │   └── ambient_manager.py                  # AmbientInteractionManager + 3 sub-monitors
│   └── api/
│       ├── capabilities.py                     # + AmbientIngestionResult + ingestAmbientEvent
│       ├── __init__.py                         # + re-exports for new symbols
│       └── core/
│           └── registry.py                     # + ambient_manager property (boot step 7)
├── mobile/                                     # v1.0 — Flutter Mobile Node
│   ├── pubspec.yaml
│   ├── android/app/src/main/AndroidManifest.xml
│   └── lib/
│       ├── main.dart                           # Entry point + foreground task callback registration
│       ├── app.dart                            # MultiBlocProvider root + dark Material 3 theme
│       └── features/
│           ├── foreground/
│           │   ├── bloc/                       # ForegroundBloc + events + states
│           │   ├── service/abm_foreground_service.dart
│           │   └── ui/foreground_status_widget.dart
│           └── telemetry/
│               ├── bloc/                       # TelemetryBloc + events + states
│               ├── models/ambient_event_model.dart
│               └── repository/telemetry_repository.dart
└── tests/
    └── test_phase_v10_mobile_gate.py           # 48-test gate (all mocked)
```

---

## Module: `abm.mobile.event_models`

**File:** [`abm/mobile/event_models.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/mobile/event_models.py)

### Constant `PERMITTED_SOURCE_KINDS`

```python
PERMITTED_SOURCE_KINDS: frozenset[str] = frozenset({
    "git_commit",     # GitTreeMonitor
    "workspace_file", # WorkspaceStateMonitor
    "design_doc",     # DesignDocMonitor
})
```

Exhaustive set of permitted ambient telemetry source kinds for Phase v1.0.
Clipboard, voice, and browser are structurally absent — not runtime-gated.

### Dataclass `AmbientEvent`

```python
@dataclass
class AmbientEvent:
    source_kind: str           # Must be in PERMITTED_SOURCE_KINDS
    active_repository: str     # Git repo name (empty string if no repo)
    source_path: str           # Absolute path of the artefact (constitution rule 3)
    text: str                  # Non-empty human-readable event description
    epoch_timestamp: int       # Defaults to int(time.time()) at construction
    device_source: str         # Always "dynamic_mobile_node" (set in __post_init__)
    extra: dict                # Optional diagnostics; never written to ChromaDB
```

`__post_init__` raises `ValueError` if `source_kind ∉ PERMITTED_SOURCE_KINDS` or `text` is empty/whitespace.
`device_source` is always `"dynamic_mobile_node"` regardless of any kwarg.

---

## Module: `abm.mobile.stream_c_writer`

**File:** [`abm/mobile/stream_c_writer.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/mobile/stream_c_writer.py)

### Constant `COMPRESS_WINDOW_SECONDS`

```python
COMPRESS_WINDOW_SECONDS: int = 3_600   # 1 hour
```

### Dataclass `WriteResult`

```python
@dataclass
class WriteResult:
    status: str             # "ok" | "compressed" | "invalid" | "error"
    doc_id: str = ""        # ChromaDB doc ID (empty on non-ok)
    reason: str = ""        # Human-readable explanation (empty on "ok")
    housekeeper_ran: bool = False
```

### Class `StreamCWriter`

Retention-aware Stream C write path. **Never raises to callers.**

```python
class StreamCWriter:
    def __init__(
        self,
        controller: ChromaController,
        embedder: OllamaEmbeddingWrapper,
        housekeeper: StreamCRetentionHousekeeper,
        compress_window_seconds: int = COMPRESS_WINDOW_SECONDS,
    ) -> None: ...

    def write(self, event: AmbientEvent) -> WriteResult
```

**`write()` lifecycle stages:**

| Stage | What |
|-------|------|
| 1 Capture | Receives `AmbientEvent`; checks `source_kind ∈ PERMITTED_SOURCE_KINDS` |
| 2 Validate | Inline type checks on `epoch_timestamp`, `active_repository`, `device_source` |
| 3 Compress | Dedup gate: `(source_kind, active_repository, sha256(text)[:16])` within `compress_window_seconds` → `"compressed"` |
| 4 Store | Calls `ChromaController.add_document()` with **exactly 3 metadata fields**: `epoch_timestamp`, `active_repository`, `device_source` |
| 5–7 Housekeeping | Calls `StreamCRetentionHousekeeper.run_if_due()` (rate-limited to once/hour) |

**Metadata contract:** ChromaDB metadata written by `StreamCWriter` contains
exactly `{epoch_timestamp, active_repository, device_source}`.  Extra diagnostic
data (`source_kind`, `source_path`, `text_hash`) lives in the document text body only.

> [!NOTE]
> `active_repository` in the ChromaDB metadata field accepts **any** repo name.
> The v0.1 `AmbientTelemetryMetadata` Pydantic model is NOT called directly
> (it is scoped to a Literal of two project names). `StreamCWriter` performs
> structural type validation instead, keeping the v0.1 model sealed.

---

## Module: `abm.mobile.retention_housekeeper`

**File:** [`abm/mobile/retention_housekeeper.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/mobile/retention_housekeeper.py)

### Constants

```python
COLLECTION_AMBIENT_ARCHIVE: str = "abm_ambient_telemetry_archive"
SUMMARIZE_AFTER_DAYS: int = 14
ARCHIVE_AFTER_DAYS: int = 30
DELETE_AFTER_DAYS: int = 180
HOUSEKEEPING_INTERVAL_SECONDS: int = 3_600   # 1 hour
```

### Dataclass `HousekeeperResult`

```python
@dataclass
class HousekeeperResult:
    summarized: int = 0
    archived: int = 0
    deleted: int = 0
    skipped: bool = False
    error: str = ""
```

### Class `StreamCRetentionHousekeeper`

Implements MEMORY_LIFECYCLE_POLICY.md lifecycle stages 5–7 for Stream C.

```python
class StreamCRetentionHousekeeper:
    def __init__(
        self,
        controller: ChromaController,
        embedder: OllamaEmbeddingWrapper,
        archive_persist_dir: str = "./memory/chroma_archive",
        housekeeping_interval_seconds: int = HOUSEKEEPING_INTERVAL_SECONDS,
    ) -> None: ...

    def run_if_due(self) -> HousekeeperResult
    def force_run(self, now_epoch: int | None = None) -> HousekeeperResult
```

**Stage assignments:**

| Stage | Trigger | Action |
|-------|---------|--------|
| 5 Summarize | Entry age ≥ `SUMMARIZE_AFTER_DAYS` (14d) with `lifecycle_stage="raw"` | Write summary doc to Stream C; mark originals `lifecycle_stage="summarized"` |
| 6 Archive | Entry age ≥ `ARCHIVE_AFTER_DAYS` (30d) with `lifecycle_stage="summarized"` | Write to `abm_ambient_telemetry_archive` (separate `ArchiveController`); delete from hot-path |
| 7 Delete | Entry age ≥ `DELETE_AFTER_DAYS` (180d) with any raw stage | Hard-delete from hot-path; summary retained |

**Cold archive:** Uses a **separate `ChromaController` instance** pointing to
`archive_persist_dir`, keeping the v0.1 controller sealed.

- **`run_if_due()`**: Runs at most once per `housekeeping_interval_seconds`. Never raises.
- **`force_run(now_epoch)`**: Bypasses the interval guard (for tests / manual ops).

---

## Module: `abm.mobile.ambient_manager`

**File:** [`abm/mobile/ambient_manager.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/mobile/ambient_manager.py)

### Telemetry scope (Phase v1.0 guardrail)

| Source | Monitor | `source_kind` |
|--------|---------|---------------|
| Git commits | `GitTreeMonitor` (wraps `GitPipeline`) | `git_commit` |
| Non-code workspace files | `WorkspaceStateMonitor` (wraps `WorkspaceFileWatcher`) | `workspace_file` |
| Static design docs | `DesignDocMonitor` (one-shot scan) | `design_doc` |

**OFFLINE (not implemented):** Clipboard, voice, browser — absent structurally.

### Constant `DESIGN_DOC_EXTENSIONS`

```python
DESIGN_DOC_EXTENSIONS: frozenset[str] = frozenset(
    {".md", ".txt", ".rst", ".yaml", ".yml", ".json", ".toml"}
)
```

### Dataclass `ManagerConfig`

```python
@dataclass
class ManagerConfig:
    watch_paths: list[str] = field(default_factory=list)
    design_doc_paths: list[str] = field(default_factory=list)
    git_repo_path: str | None = None
    archive_persist_dir: str = "./memory/chroma_archive"
    debounce_seconds: float = 1.0
    git_poll_interval_seconds: int = 60
```

### Class `GitTreeMonitor`

```python
class GitTreeMonitor:
    def __init__(
        self, git_pipeline: GitPipeline, on_event: Callable[[AmbientEvent], None]
    ) -> None: ...
    def poll(self) -> int    # Returns number of new commit events emitted
```

- Polling-based (not event-driven). Initialises `_last_sha` on first call without emitting (avoids replaying history).

### Class `WorkspaceStateMonitor`

```python
class WorkspaceStateMonitor:
    def __init__(
        self,
        watch_paths: list[str],
        on_event: Callable[[AmbientEvent], None],
        debounce_seconds: float = 1.0,
    ) -> None: ...
    def start(self) -> None
    def stop(self) -> None
```

- Wraps `WorkspaceFileWatcher`; forwards only `DESIGN_DOC_EXTENSIONS` paths.
- Code changes are ignored here (already handled by v0.2 `IngestionCoordinator` → Stream A).

### Class `DesignDocMonitor`

```python
class DesignDocMonitor:
    def __init__(
        self,
        scan_paths: list[str],
        on_event: Callable[[AmbientEvent], None],
        extensions: frozenset[str] | None = None,
    ) -> None: ...
    def scan(self) -> int    # Returns number of events emitted
```

- One-shot recursive scanner. Called by `AmbientInteractionManager.start()`.

### Class `AmbientInteractionManager`

```python
class AmbientInteractionManager:
    def __init__(
        self,
        controller: ChromaController,
        embedder: OllamaEmbeddingWrapper,
        config: ManagerConfig | None = None,
    ) -> None: ...

    def start(self) -> None           # One-shot design-doc scan + start workspace watcher
    def stop(self) -> None            # Stop workspace watcher
    def poll_git(self) -> int         # Poll for new commits if interval elapsed
    def ingest_event(self, event: AmbientEvent) -> WriteResult
    @property def is_running(self) -> bool
```

- All events from all three monitors route through a single shared `StreamCWriter` instance.
- `stop()` is idempotent.
- `poll_git()` is rate-limited by `ManagerConfig.git_poll_interval_seconds`.

---

## Module: `abm.mobile` (package)

**File:** [`abm/mobile/__init__.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/abm/mobile/__init__.py)

Re-exports `AmbientInteractionManager`, `ManagerConfig`, `GitTreeMonitor`,
`WorkspaceStateMonitor`, `DesignDocMonitor`, `AmbientEvent`, `StreamCWriter`,
`StreamCRetentionHousekeeper`, `WriteResult`, `HousekeeperResult`, and all constants.

---

## Flutter Encrypted Cross-Node Sync Channel

The Flutter mobile node encrypts sync payloads before sending them to the
desktop daemon. It uses the Dart `cryptography` package with AES-256-GCM and
stores the symmetric key through `flutter_secure_storage`, which delegates to
Android Keystore / iOS Keychain. No custom cipher or custom key-exchange scheme
is implemented.

### `mobile/pubspec.yaml`

Required packages:

```yaml
cryptography: ^2.7.0
flutter_secure_storage: ^9.2.2
```

### `SyncHandshake`

**File:** [`mobile/lib/features/sync/models/sync_handshake.dart`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/mobile/lib/features/sync/models/sync_handshake.dart)

```dart
const int kSyncProtocolVersion = 1;
const String kSyncAlgorithm = 'AES-256-GCM';
const String kSyncContentTypeJson = 'application/json';

class SyncHandshake {
  final int protocolVersion;
  final String nodeId;
  final String keyId;
  final String algorithm;
  final int createdAtEpoch;
  final List<String> capabilities;

  Map<String, dynamic> toJson();
  factory SyncHandshake.fromJson(Map<String, dynamic> json);
}
```

**Handshake payload format:**

```json
{
  "protocol_version": 1,
  "node_id": "dynamic_mobile_node",
  "key_id": "base64url-truncated-sha256",
  "algorithm": "AES-256-GCM",
  "created_at_epoch": 1784370192,
  "capabilities": ["ambient_event_ingest", "state_snapshot", "encrypted_payload_v1"]
}
```

The handshake advertises protocol version, node identity, key identity,
algorithm, timestamp, and supported capabilities. It does not transmit key
material and does not negotiate keys with custom cryptography.

### `EncryptedSyncPayload`

**File:** [`mobile/lib/features/sync/models/encrypted_sync_payload.dart`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/mobile/lib/features/sync/models/encrypted_sync_payload.dart)

```dart
class EncryptedSyncPayload {
  final int protocolVersion;
  final String keyId;
  final String algorithm;
  final String nodeId;
  final int createdAtEpoch;
  final String contentType;
  final String nonce;       // base64 AES-GCM nonce
  final String ciphertext;  // base64 encrypted body
  final String mac;         // base64 AES-GCM authentication tag

  Map<String, dynamic> toJson();
  factory EncryptedSyncPayload.fromJson(Map<String, dynamic> json);
}
```

**Encrypted payload format:**

```json
{
  "protocol_version": 1,
  "key_id": "base64url-truncated-sha256",
  "algorithm": "AES-256-GCM",
  "node_id": "dynamic_mobile_node",
  "created_at_epoch": 1784370192,
  "content_type": "application/json",
  "nonce": "base64-nonce",
  "ciphertext": "base64-ciphertext",
  "mac": "base64-authentication-tag"
}
```

Associated authenticated data is derived from
`abm-sync|protocol_version|key_id|node_id|created_at_epoch|content_type`.
Changing any of those fields causes AES-GCM authentication failure during
decrypt.

### `CrossNodeKeyStore`

**File:** [`mobile/lib/features/sync/crypto/cross_node_key_store.dart`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/mobile/lib/features/sync/crypto/cross_node_key_store.dart)

```dart
const String kCrossNodeSyncKeyStorageKey = 'abm_cross_node_sync_aes_gcm_key';
const String kCrossNodeSyncKeyIdStorageKey = 'abm_cross_node_sync_key_id';

class CrossNodeKeyMaterial {
  final SecretKey secretKey;
  final String keyId;
}

class CrossNodeKeyStore {
  CrossNodeKeyStore({FlutterSecureStorage? storage, AesGcm? algorithm});

  Future<CrossNodeKeyMaterial> ensureKey();
  Future<CrossNodeKeyMaterial?> readKey();
  Future<CrossNodeKeyMaterial> rotateKey();
  Future<void> clearKey();
}
```

`ensureKey()` creates an AES-256-GCM key using `AesGcm.with256bits()` when no
stored key exists, persists it through `flutter_secure_storage`, and derives
`keyId` from SHA-256 using `cryptography`.

### `SyncCryptoChannel`

**File:** [`mobile/lib/features/sync/crypto/sync_crypto_channel.dart`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/mobile/lib/features/sync/crypto/sync_crypto_channel.dart)

```dart
const List<String> kSyncCapabilities = [
  'ambient_event_ingest',
  'state_snapshot',
  'encrypted_payload_v1',
];

class SyncCryptoChannel {
  SyncCryptoChannel({
    required CrossNodeKeyStore keyStore,
    required String nodeId,
    AesGcm? algorithm,
  });

  Future<SyncHandshake> buildHandshake({int? createdAtEpoch});
  Future<EncryptedSyncPayload> encryptJson(
    Map<String, dynamic> json, {
    int? createdAtEpoch,
    String contentType = kSyncContentTypeJson,
  });
  Future<Map<String, dynamic>> decryptJson(EncryptedSyncPayload payload);
}
```

`encryptJson()` and `decryptJson()` delegate AES-GCM operations to
`package:cryptography`.

### `CrossNodeSyncRepository`

**File:** [`mobile/lib/features/sync/repository/cross_node_sync_repository.dart`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/mobile/lib/features/sync/repository/cross_node_sync_repository.dart)

```dart
const String kDefaultSyncBaseUrl = 'http://127.0.0.1:8765';
const String kSyncHandshakeEndpoint = '/api/sync/handshake';
const String kSyncPayloadEndpoint = '/api/sync/payload';
const Duration kSyncRequestTimeout = Duration(seconds: 10);

class SyncSendResult {
  final bool success;
  final String? status;
  final String? error;
}

class CrossNodeSyncRepository {
  CrossNodeSyncRepository({
    required String baseUrl,
    required SyncCryptoChannel channel,
    http.Client? httpClient,
  });

  Future<SyncSendResult> sendHandshake();
  Future<SyncSendResult> sendEncryptedJson(Map<String, dynamic> json);
  Future<Map<String, dynamic>> decryptPayload(EncryptedSyncPayload payload);
  void dispose();
}
```

`sendHandshake()` posts `SyncHandshake.toJson()` to `/api/sync/handshake`.
`sendEncryptedJson()` encrypts the supplied JSON and posts
`EncryptedSyncPayload.toJson()` to `/api/sync/payload`.

---

## API Layer extension: `ingestAmbientEvent`

### `abm.api.capabilities`

#### `ingestAmbientEvent(event, *, registry) → AmbientIngestionResult`

```python
def ingestAmbientEvent(
    event: AmbientEvent,
    *,
    registry: ServiceRegistry,
) -> AmbientIngestionResult
```

- **STATUS:** `stable`
- **OWNER:** `abm.mobile.ambient_manager.AmbientInteractionManager`
- **DEPENDENCIES:** `ServiceRegistry.ambient_manager` (→ controller + embedder)
- **CONSUMERS:** Flutter foreground service (via local HTTP stub)

Delegates to `AmbientInteractionManager.ingest_event()`. Never raises.

#### Dataclass `AmbientIngestionResult`

```python
@dataclass
class AmbientIngestionResult:
    status: str             # "ok" | "compressed" | "invalid" | "error"
    doc_id: str = ""
    reason: str = ""
    housekeeper_ran: bool = False
    degraded: bool = False  # True if ambient_manager raised unexpectedly
```

### `abm.api.core.registry` — new service (boot step 7)

```python
@property
def ambient_manager(self) -> AmbientInteractionManager: ...
```

Constructed in `boot()` after `StrategicAssetAnalyzer` (step 6). Config uses
`chroma_persist_directory + "_archive"` as the cold archive path.
`shutdown()` calls `ambient_manager.stop()` if running.

---

## Flutter Mobile Node

### Plugin: `flutter_foreground_task: ^8.0.0`

Device-agnostic persistent Android Foreground Service. Prevents OS low-memory
killer from terminating the execution thread. Required permissions in
`AndroidManifest.xml`:

| Permission | Reason |
|---|---|
| `FOREGROUND_SERVICE` | Core foreground service |
| `FOREGROUND_SERVICE_DATA_SYNC` | Android 14+ typed foreground service |
| `POST_NOTIFICATIONS` | Android 13+ persistent notification |
| `WAKE_LOCK` | Keeps CPU running during ambient monitoring |
| `RECEIVE_BOOT_COMPLETED` | Auto-restart after device reboot |

### `AbmForegroundService` singleton

**File:** [`mobile/lib/features/foreground/service/abm_foreground_service.dart`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/mobile/lib/features/foreground/service/abm_foreground_service.dart)

```dart
class AbmForegroundService {
    static final AbmForegroundService instance = AbmForegroundService._();
    void init() → void
    Future<void> start() → void    // raises ForegroundServiceStartException on failure
    Future<void> stop() → void
    Future<bool> get isRunning
    void onDataReceived(void Function(Object) callback) → void
    void removeDataCallback(void Function(Object) callback) → void
}
```

Notification channel ID: `"abm_foreground_service"`. `autoRunOnBoot: true`.

### `ForegroundBloc`

**File:** [`mobile/lib/features/foreground/bloc/foreground_bloc.dart`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/mobile/lib/features/foreground/bloc/foreground_bloc.dart)

```
Events:  StartForegroundService | StopForegroundService | ForegroundServiceStatusUpdated
States:  ForegroundInitial | ForegroundRunning | ForegroundStopped | ForegroundError(message)
```

### `TelemetryBloc`

**File:** [`mobile/lib/features/telemetry/bloc/telemetry_bloc.dart`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/mobile/lib/features/telemetry/bloc/telemetry_bloc.dart)

```
Events:  ObserveWorkspaceFile | RecordGitActivity | ObserveDesignDoc
States:  TelemetryIdle | TelemetrySending(sourceKind) | TelemetrySent(docId, status, sourceKind) | TelemetryFailed(error, sourceKind)
```

No event type exists for clipboard, voice, or browser — scope enforced at the Dart type level.

### `AmbientEventModel` (Dart)

**File:** [`mobile/lib/features/telemetry/models/ambient_event_model.dart`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/mobile/lib/features/telemetry/models/ambient_event_model.dart)

```dart
enum AmbientSourceKind { gitCommit, workspaceFile, designDoc }

class AmbientEventModel {
    final AmbientSourceKind sourceKind;
    final String activeRepository;
    final String sourcePath;
    final String text;
    final int epochTimestamp;
    final String deviceSource;   // always "dynamic_mobile_node"

    Map<String, dynamic> toJson() → ...
    factory AmbientEventModel.fromJson(Map<String, dynamic>) → ...
}
```

JSON field names match the Python `AmbientEvent` dataclass exactly.

### `TelemetryRepository`

**File:** [`mobile/lib/features/telemetry/repository/telemetry_repository.dart`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/mobile/lib/features/telemetry/repository/telemetry_repository.dart)

```dart
class TelemetryRepository {
    TelemetryRepository({required String baseUrl, ...})
    factory TelemetryRepository.defaultInstance()   // baseUrl = "http://127.0.0.1:8765"

    Future<TelemetryResult> sendEvent(AmbientEventModel event) → never throws
    Future<List<TelemetryResult>> sendBatch(List<AmbientEventModel> events)
    void dispose()
}
```

`kIngestEndpoint = "/api/ingest_ambient_event"`. Timeout: 10s. All failures returned
as `TelemetryResult.success == false` (constitution rule 9 — degrade gracefully).

---

## Phase v1.0 Mobile Test Gate

**File:** [`tests/test_phase_v10_mobile_gate.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/tests/test_phase_v10_mobile_gate.py)

**Gate run command:**
```bash
python -m pytest tests/test_phase_v10_mobile_gate.py -v
```

**Full regression:**
```bash
python -m pytest tests/ -v
```

### Hard gate proofs (54 tests — all mocked, no live Ollama required)

| Class | Proves |
|-------|--------|
| `TestAmbientEventSchemaGate` | Only PERMITTED_SOURCE_KINDS accepted; clipboard/voice/browser/unknown raise ValueError; device_source always "dynamic_mobile_node"; empty text raises; epoch_timestamp defaults to positive int |
| `TestStreamCWriterRetentionAwareGate` | Unique event → ok; duplicate within compress window → compressed; same event beyond window → ok; metadata has exactly 3 fields; embedding failure → error; ChromaDB failure → error; housekeeper called after ok; not called after compressed |
| `TestRetentionHousekeeperLifecycleGate` | run_if_due skips before interval; runs after interval; force_run deletes past 180d; force_run summarizes past 14d; lifecycle constants match MEMORY_LIFECYCLE_POLICY |
| `TestAmbientInteractionManagerScopeGate` | Git monitor None without repo; poll_git returns 0 without monitor; poll_git rate-limited; ingest permitted kind → ok/compressed; prohibited kind blocked at AmbientEvent construction; is_running False before start; design doc extensions correct |
| `TestIngestAmbientEventCapabilityGate` | Returns AmbientIngestionResult; compressed status passed through; manager exception → degraded=True; STATUS tag is "stable"; OWNER names AmbientInteractionManager |
| `TestEncryptedCrossNodeSyncGate` | Flutter sync declares `cryptography` and `flutter_secure_storage`; key store uses `AesGcm.with256bits()` and secure storage; channel uses AES-GCM encrypt/decrypt with AAD; handshake and encrypted payload fields are fixed |
| `TestV01ToV10MobileRegressionGate` | All v0.1 collection names unchanged; PERMITTED_SOURCE_KINDS exactly 3; compress window 3600; housekeeping interval 3600; lifecycle thresholds 14/30/180; AmbientTelemetryMetadata has exactly 3 fields; archive collection name correct; device_source correct |

*Updated for ABM 2.0 Phase v1.0 Flutter Foreground Service & Ambient Interaction Manager. Update this file whenever new capabilities, monitors, or schemas are added.*

---

## Phase v1.0 Roadmap Completion Gate

**File:** [`tests/test_phase_v1_completion_gate.py`](file:///c:/Users/araba/Desktop/Projects/ABM-2.0/tests/test_phase_v1_completion_gate.py)

**Gate run command:**
```bash
python -m pytest tests/test_phase_v1_completion_gate.py -v
```

**Full roadmap regression:**
```bash
python -m pytest tests/ -v
```

### Hard gate proofs (36 tests — final roadmap gate)

| Class | Proves |
|-------|--------|
| `TestForegroundServiceSurvivalGate` | No Tecno Spark 40 / hardware hardcoding; uses `flutter_foreground_task`; wake lock + boot restart + repeat heartbeat survive simulated low-memory trim |
| `TestEncryptedSyncIntegrityGate` | Only `cryptography` + `flutter_secure_storage`; unencrypted payloads rejected; tampered ciphertext/MAC/AAD fail AES-GCM auth |
| `TestAmbientManagerSourceAllowlistGate` | Only `git_commit`, `workspace_file`, `design_doc`; code files ignored; clipboard/voice/browser absent in Python + Dart + manifest |
| `TestStreamCCompressionWindowGate` | Duplicates within 3600 s → `compressed`; after window → stored again; housekeeper summarizes past 14 d and deletes past 180 d |
| `TestRoadmapRegressionGate` | All prior gates (`v0.1`–`v0.5`, Client #1, mobile gate) subprocess-verified still 100% green |
