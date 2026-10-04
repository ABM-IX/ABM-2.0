# ABM 2.0 — Project Brief (read this before ABM_SPEC.md)

## Document authority (read this first — prevents contradicting sources of truth)

| Document | Purpose | Authority |
|---|---|---|
| `ABM_SPEC.md` | System architecture | Highest authority for architecture |
| `ARCHITECTURAL_CONSTITUTION.md` | Immutable rules | Highest authority for governance |
| `MISSION_VISION_PHILOSOPHY.md` | Why ABM exists | Highest authority for judgment calls no rule covers |
| `MEMORY_LIFECYCLE_POLICY.md` | Retention/compression/archival per stream | Authority for memory lifecycle |
| `PROJECT_BRIEF.md` (this file) | Current phase scope and status | Authority for what's in scope right now |
| `CLIENT_01_CONSOLE.md` | Client #1 (console) contract | Authority for console scope only |
| `interfaces.md` | Public API/function contracts | Authority for exact signatures |
| `ARCHITECTURE_BACKLOG.md` | Future candidates | Non-authoritative — nothing here is committed |

If two documents conflict, the higher-authority one wins, and the
lower one should be corrected to match — flag it rather than silently
picking one.

**Status:** Phases v0.1 through v1.0 complete and gated (original roadmap
finished), plus Client #1 (API layer + console) and a post-roadmap
"Conversational & Task Execution Layer" (synthesis-grounded `ask`, the
`run <task>` command, a dedicated `conversational` department). Phone ↔
desktop encrypted sync verified working end-to-end with real data.
Phase v2.0, Increment 1 (Service Interfaces) complete and gated.
Phase v2.0, Increment 2 (Asynchronous Event Bus) complete and gated.

**What this project is:** A local-first, privacy-isolated Cognitive OS acting as
a digital twin of the developer (Arabang/ABM) and administrative overseer for
First Minds Proprietary Limited. Full detail in `ABM_SPEC.md`.

**Ground rules for any agent working in this repo:**
1. Read this file, `ABM_SPEC.md`, and `ARCHITECTURAL_CONSTITUTION.md` in full
   before writing any code.
2. We are strictly scoped to **Phase v2.0, Increment 1** right now (see
   below). Do NOT build Event Bus, Plugin Architecture, Capability Registry,
   or any other item from `ARCHITECTURE_BACKLOG.md` — those remain
   deliberately deferred until this narrower increment lands and a real need
   for the next one is demonstrated, not assumed. Build ON TOP of the
   existing `ServiceRegistry` (`abm/api/core/registry.py`) — do not replace
   its boot/shutdown lifecycle, which already works correctly.
3. **Local-first only.** No cloud LLM APIs. All inference and embeddings
   route through a local Ollama instance at `127.0.0.1:11434`.
4. Use the **exact** metadata schemas and collection names already
   established — do not rename fields or restructure them.
5. Before finishing your task, write or update `interfaces.md` in the repo
   root documenting every function signature, file path, and metadata shape
   you created or changed.
6. **Framework:** the mobile node is Flutter/Dart, BLoC pattern.
7. **Crypto rule:** vetted libraries only (Dart `cryptography` package,
   `flutter_secure_storage`) — never hand-rolled cryptography.
8. **Telemetry scope:** ambient interaction managers ingest Git trees, IDE
   workspace state, and static design docs only. Clipboard, voice, and
   browser tracking stay OFFLINE until explicitly re-scoped.

**Phase v0.1 (complete):** ChromaDB with 4 isolated collections, local
embedding via `nomic-embed-text`, isolation tests.

**Phase v0.2 (complete):** File-watcher hooks, Git integration pipeline,
code structure analyzer, style fingerprint extraction.

**Phase v0.3 (complete):** Non-generating classification router, department
worker sandboxes, JSON task delegation contracts.

**Phase v0.4 (complete):** Background Docker container init/teardown per
delegated task, compiler/test-check loop, multi-factor validation gate
(C formula + S_val/Test_succ floor gates) with quarantine routing.

**Phase v0.5 (complete):** Decision journal into Stream D, read-only
workflow monitor, strategic asset analyzer (analysis only).

**Phase v1.0 (complete):** Flutter Foreground Service, encrypted cross-node
sync channel (AES-256-GCM, manually-paired keys), ambient interaction
manager with retention housekeeping. Verified end-to-end with real
phone-originated telemetry correctly encrypted, decrypted, and attributed.

**Client #1 (complete):** API layer (capability-oriented, not module-oriented
function names, per constitution rule 14) + CLI console with `ask`,
`search`, `status`, `summarize`, `memory`, `explain`.

**Conversational & Task Execution Layer (complete, post-roadmap addition):**
Synthesis-grounded natural-language answers (with strict anti-hallucination
handling for identity/factual questions — extractive, not generative, for
"what is ABM"-type questions), a `conversational` department for small talk
scoped to Streams C+D, and a `run <task>` command dispatching real work
through the v0.3 classifier + v0.4 sandbox + confidence gate.

**Phase v2.0, Increment 1 deliverables — Service Interfaces (Complete & Gated):**
- `ServiceRegistry` (`abm/api/core/registry.py`) properties typed to
  abstract interfaces (`VectorStoreInterface`, `EmbedderInterface`,
  `ModelGatewayInterface`).
- Tested with dedicated gate `tests/test_increment1_service_interfaces_gate.py`
  (100% pass, swappability proved with in-memory stubs).

**Phase v2.0, Increment 2 deliverables — Asynchronous Event Bus (Complete & Gated):**
- Centralized decoupled publish/subscribe Event Bus subsystem (`EventBus`,
  `EventBusInterface`, `Event`, `SystemTopic`) implemented in `abm/api/core/bus.py`
  and `abm/api/core/interfaces.py`.
- Features:
  - Exact and wildcard topic matching (`*`, `code.*`, `system.*`).
  - Priority-ordered subscriber execution.
  - Strict error isolation per Constitution Rule 9 (faulty subscriber exceptions are caught, logged, and isolated without crashing the bus or sibling subscribers).
  - Non-blocking asynchronous dispatch (`publish_async`) with thread-safe background queue worker and lifecycle management (`start`, `stop`, `drain`).
  - Full integration into `ServiceRegistry` (`registry.event_bus`) with automatic `SYSTEM_BOOT` and `SYSTEM_SHUTDOWN` event broadcast.
- Tested and verified with hard gate `tests/test_phase_v20_increment2_event_bus_gate.py`
  (13/13 passed in ~4s with zero regressions).
