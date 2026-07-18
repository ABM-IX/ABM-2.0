# ABM 2.0 — Memory Brain Core

**Phase:** v0.1 — Memory Brain Core  
**Status:** 🟡 Gate pending (tests must pass 100% before v0.2)

A local-first, privacy-isolated Cognitive Operating System acting as a
persistent digital twin of the developer (Araba/ABM) and administrative
overseer for First Minds Proprietary Limited.

> **Hard constraint:** All inference and embeddings route exclusively through
> a local Ollama instance at `127.0.0.1:11434`. No cloud LLM APIs are used.

---

## Phase v0.1 Deliverables

- ✅ ChromaDB initialized with 4 isolated collections
- ✅ Local embedding connector using `nomic-embed-text` via Ollama
- ✅ Mock-assertion tests proving zero data crossover between collections
- ✅ `interfaces.md` documenting every function signature and metadata shape

---

## Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai) running locally with `nomic-embed-text` pulled:
  ```bash
  ollama pull nomic-embed-text
  ```

---

## Installation

```bash
pip install -r requirements.txt
```

---

## Running the Tests

```bash
python -m pytest tests/test_memory_isolation.py -v
```

All tests use `unittest.mock` — no live Ollama or live ChromaDB required.
**Phase v0.1 does not advance to v0.2 until these pass 100%.**

---

## Quick Usage

```python
from abm.memory import ChromaController, OllamaEmbeddingWrapper
from abm.memory.chroma_controller import COLLECTION_CODE_TOPOLOGIES

# Initialize collections (in-memory for quick testing)
ctrl = ChromaController(in_memory=True)

# Check Ollama is reachable before embedding
embedder = OllamaEmbeddingWrapper()
if not embedder.health_check():
    raise RuntimeError("Ollama not running at 127.0.0.1:11434")

# Embed a document
vec = embedder.embed("class UserBloc extends Bloc<UserEvent, UserState> {}")

# Store it in the correct collection
ctrl.add_document(
    collection_name=COLLECTION_CODE_TOPOLOGIES,
    doc_id="code_001",
    text="class UserBloc extends Bloc<UserEvent, UserState> {}",
    metadata={
        "language": "dart",
        "framework": "flutter",
        "state_pattern": "bloc",
        "naming_convention": "camelCase",
    },
    embedding=vec,
)

# Query
result = ctrl.query_collection(COLLECTION_CODE_TOPOLOGIES, vec, n_results=3)
print(result.documents)
```

---

## Architecture

See [`interfaces.md`](interfaces.md) for the complete API reference and
[`project_context/ABM_SPEC.md`](project_context/ABM_SPEC.md) for the full
system specification.

```
Stream D  abm_cognitive_identity   — Identity foundations, FirstMinds philosophy
Stream A  abm_code_topologies      — Engineering DNA, Flutter/BLoC patterns
Stream B  abm_technical_mastery    — Validated docs, API references
Stream C  abm_ambient_telemetry    — Interaction history, terminal I/O
```

---

## Phase Roadmap

| Phase | Name | Status |
|-------|------|--------|
| v0.1 | Memory Brain Core | 🟡 In gate |
| v0.2 | Developer Companion Node | 🔒 Locked |
| v0.3 | Executive Orchestrator Engine | 🔒 Locked |
| v0.4 | Safe Action Sandbox | 🔒 Locked |
| v0.5 | FirstMinds Strategic Wing | 🔒 Locked |
| v1.0 | Cognitive OS Release | 🔒 Locked |
