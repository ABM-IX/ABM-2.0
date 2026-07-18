# interfaces.md
# ABM 2.0 — Phase v0.1 Memory Brain Core
# Complete API Reference: Every Function Signature, Collection Name, and Metadata Shape

> This document is the single source of truth for every public interface
> created in Phase v0.1. Any tool or agent building on this phase must
> consult this file before writing integration code.

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
9. [Constants Reference](#constants-reference)
10. [Test Suite](#test-suite)

---

## File Map

```
ABM-2.0/
├── abm/
│   ├── __init__.py                    # Package root — version and phase metadata
│   └── memory/
│       ├── __init__.py                # Re-exports ChromaController, OllamaEmbeddingWrapper
│       ├── chroma_controller.py       # ChromaDB collection manager
│       └── embedding_wrapper.py       # Ollama nomic-embed-text connector
├── tests/
│   ├── __init__.py
│   ├── test_phase_v01_gate.py         # Hard gate: isolation + chunking + embed consistency
│   ├── test_memory_isolation.py       # Mock-assertion isolation / embed contract tests
│   └── test_metadata_and_chunking.py  # Metadata + chunking contract tests
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
