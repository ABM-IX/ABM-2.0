# ABM 2.0 — Architectural Constitution

Short, immutable, and binding on every module and every phase. When a
phase brief and this document conflict, this document wins. Every agent
working on this repo should read this alongside `PROJECT_BRIEF.md`.

1. **Local-first by default.** No cloud LLM API, ever, unless a future
   version of this document explicitly revises this rule.
2. **Human approval before irreversible actions.** Nothing deletes,
   overwrites, or ships without ABM's explicit action.
3. **Memory must be explainable.** Every stored entry traces to a source
   and a reason it was kept — no opaque or unexplained persistence.
4. **Identity constrains reasoning.** Stream D's principles are not just
   retrievable memory; they are a runtime constraint on what agents are
   allowed to recommend or do.
5. **Every action is auditable.** Decision journal entries, quarantine
   events, and sandbox runs are logged, not silently dropped.
6. **Services communicate through contracts, not direct coupling.**
   `interfaces.md` is the contract of record between modules and between
   the tools building them.
7. **No hand-rolled cryptography.** Vetted libraries only, every phase,
   no exceptions.
8. **Every memory stream has a lifecycle.** No collection accumulates
   forever without a defined compress/summarize/archive/delete policy —
   see `MEMORY_LIFECYCLE_POLICY.md`.
9. **The system degrades gracefully, never catastrophically.** A missing
   dependency (Ollama down, Docker unavailable) produces a documented
   fallback, not a crash — as already implemented in the v0.3 router.
10. **Phases are gated, not assumed.** No phase's work is "done" until its
    own test suite passes 100% AND the full regression suite from every
    prior phase still passes.
11. **Clients expose capabilities; they never create capabilities.** A
    CLI command, GUI screen, or voice intent may only surface a backend
    capability that already exists, is tested, and is gated. If a client
    feature requires a new engine to power it, that engine gets its own
    phase brief and test gate first — never built informally "behind" a
    client command.
12. **Backend before interface, always.** Every capability follows:
    design → implement → test → gate → expose via API → expose via client.
    Never reversed, for any client (CLI, Flutter, voice, browser, IDE).
13. **All clients communicate exclusively through the API layer and own
    no persistent cognitive state.** No client owns memory, planning,
    reflection, reasoning, or routing — those live only inside the
    engine. (Ordinary presentation-level state — e.g. a CLI's command
    history, a Flutter screen's scroll position — is fine; the rule is
    about not duplicating engine state or logic per-client.)
14. **The API layer exposes capabilities, not modules.** Name functions
    for what they do (`retrieveKnowledge()`, `summarizeProject()`), not
    for which internal module currently implements them
    (`memory.search()`). Capability names survive refactoring; module
    names don't.
