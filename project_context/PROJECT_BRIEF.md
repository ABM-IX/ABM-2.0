# ABM 2.0 — Project Brief (read this before ABM_SPEC.md)

**Status:** Phase v0.1 ("Memory Brain Core") complete and gated — 16 tests /
31 subtests passing, tagged `v0.1-memory-core`. Now starting Phase v0.2
("Developer Companion Node").

**What this project is:** A local-first, privacy-isolated Cognitive OS acting as
a digital twin of the developer (Araba/ABM) and administrative overseer for
First Minds Proprietary Limited. Full detail in `ABM_SPEC.md`.

**Ground rules for any agent working in this repo:**
1. Read this file and `ABM_SPEC.md` in full before writing any code.
2. We are strictly scoped to **Phase v0.2** right now (see ABM_SPEC.md section 10).
   Do not build Phase v0.3+ features (orchestrator, sandbox, confidence-gate
   math, mobile node) even if they seem easy to add — out of scope until v0.2
   passes its test gate. Build ON TOP of the existing v0.1 memory core — do
   not modify its collections, schemas, or chunking functions.
3. **Local-first only.** No cloud LLM APIs (no OpenAI, Gemini, Groq, Cohere,
   OpenRouter, ElevenLabs, etc.). All inference and embeddings route through a
   local Ollama instance at `127.0.0.1:11434`, per spec section 4.
4. Use the **exact** metadata schemas and collection names given in spec
   section 3 — do not rename fields or restructure them.
5. Before finishing your task, write or update `interfaces.md` in the repo
   root documenting every function signature, file path, and metadata shape
   you created, so other tools building on your work don't have to guess.

**Phase v0.1 (complete):**
- ChromaDB initialized with 4 isolated collections: `abm_cognitive_identity`,
  `abm_code_topologies`, `abm_technical_mastery`, `abm_ambient_telemetry`.
- A local embedding connector using `nomic-embed-text` via Ollama.
- Mock-assertion tests proving zero data crossover between collections.

**Phase v0.2 deliverables (from spec section 10, item 2):**
- IDE file-watcher hooks (native kernel hooks — inotify / ReadDirectoryChangesW,
  or a cross-platform equivalent such as `watchdog`) that detect file changes
  and feed them toward Stream A/C ingestion via the existing v0.1 controller.
- Local Git integration pipeline (commit history, diff tracking, branch state).
- Abstract Syntax Tree parsing tools extended from the v0.1 chunker into a
  general-purpose code structure analyzer.
- Style fingerprint extraction engine: derives naming conventions, formatting
  patterns, and architectural preferences from parsed code and writes them
  into Stream A per its existing metadata schema — do not invent new fields.
- Phase v0.2 does not advance to v0.3 until its own test gate passes 100%.
