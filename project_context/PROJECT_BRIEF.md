# ABM 2.0 — Project Brief (read this before ABM_SPEC.md)

**Status:** Phases v0.1 through v0.5 complete and gated — 456 tests passing,
tagged `v0.1-memory-core` through `v0.5-strategic-wing`. Now starting Phase
v1.0 ("Cognitive OS Release").

**What this project is:** A local-first, privacy-isolated Cognitive OS acting as
a digital twin of the developer (Araba/ABM) and administrative overseer for
First Minds Proprietary Limited. Full detail in `ABM_SPEC.md`.

**Ground rules for any agent working in this repo:**
1. Read this file and `ABM_SPEC.md` in full before writing any code.
2. We are strictly scoped to **Phase v1.0** right now (see ABM_SPEC.md section 10
   and the hardware-agnostic blueprint corrections). This is the final phase
   on the roadmap — there is no v1.1 to defer to, so scope creep here means
   scope creep into an unbounded "everything" phase. Build ON TOP of the
   existing v0.1–v0.5 modules — do not modify their collections, schemas,
   chunking, watcher, ingestion, routing, sandbox, or strategic-wing logic.
6. **Framework:** the mobile node is built in **Flutter/Dart**, not native
   Kotlin — this matches the `framework: "flutter"` / `state_pattern: "bloc"`
   literals already fixed in Stream A's schema since v0.1. Use the BLoC
   pattern for the app's own state management, for the same consistency
   reason.
7. **Crypto rule:** the encrypted cross-node sync channel must use a vetted
   Dart crypto package (e.g. the `cryptography` package for AES-GCM, with
   `flutter_secure_storage` for key storage — which itself wraps Android
   Keystore / iOS Keychain) — never a hand-rolled cipher or custom
   key-exchange scheme.
8. **Telemetry scope for this phase:** ambient interaction managers ingest
   Git trees, IDE workspace state, and static design docs only — matching
   the v0.1 rollout guardrail. Clipboard tracking, voice logs, and browser
   tracking stay OFFLINE until explicitly re-scoped by ABM in a future brief.
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

**Phase v0.2 (complete):**
- IDE file-watcher hooks routing changes into v0.1 ingestion.
- Local Git integration pipeline (commits, diffs, branch state).
- Code structure analyzer extending the v0.1 AST chunker.
- Style fingerprint extraction engine writing schema-valid Stream A entries.

**Phase v0.3 (complete):**
- Non-generating classification router (routes only, never generates content).
- Sub-agent department worker sandboxes scoped per department.
- JSON task delegation / result-reporting contracts.

**Phase v0.5 (complete):**
- Decision journal writing strategic decisions into Stream D's existing schema.
- Read-only workflow monitor aggregating orchestrator/sandbox task state.
- Strategic asset analyzer — analysis only, never writes decisions itself.

**Phase v1.0 deliverables (from spec section 10, item 6, and the
hardware-agnostic blueprint corrections in section 2 — now built in
Flutter/Dart per ground rule 6):**
- Flutter-based Android Foreground Service (via a maintained plugin such as
  `flutter_foreground_task`, not raw platform channels reinventing the
  wheel): modular, device-agnostic, using a persistent notification to
  prevent the OS low-memory killer from stripping its execution thread.
  BLoC pattern for state management.
- Encrypted cross-node synchronization channel between this desktop repo
  and the Flutter mobile node, connecting to the existing v0.1–v0.5 memory
  core. Must use a vetted Dart crypto package — see ground rule 7.
- Ambient interaction managers feeding Stream C (`abm_ambient_telemetry`)
  using its existing `dynamic_mobile_node` device_source schema — scope
  limited per ground rule 8.
- This is the final phase on the current roadmap. Its test gate is the
  project's completion gate.
