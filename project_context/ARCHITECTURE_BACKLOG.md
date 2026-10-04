# ABM 2.0 — Architecture Backlog (Candidates, Not Commitments)

Ideas in this document are explicitly NOT scoped to any current phase.
They are preserved here so they aren't lost, and so they don't get
smuggled into the current phase out of fear of losing them. Nothing here
gets built until it has its own phase brief and test gate, per
constitution rule 12 (backend before interface) and rule 2 (phases are
gated, not assumed).

## System-level (candidates for Phase v2.0 — System Kernel & Governance)
- Formal Boot Manager / Lifecycle Manager as its own subsystem (not just
  folder organization — an actual state machine).
- Dependency Injection / Service Registry (e.g. `ServiceRegistry.get()`
  instead of direct instantiation) — enables swapping ChromaDB for
  another vector store without touching clients.
- Event Bus — decoupled publish/subscribe communication between services.
  [Delivered & Gated in Phase v2.0 Increment 2: `abm/api/core/bus.py`,
  `EventBusInterface`, and `test_phase_v20_increment2_event_bus_gate.py`].
- Plugin Architecture — a registration interface (`register()`,
  `capabilities()`, `permissions()`) so new departments/agents don't
  require editing core.
- Capability Registry — lets the orchestrator choose between multiple
  competing agents for the same task. Needed once there are multiple
  agents capable of the same thing; not needed with one agent per domain.

## API-level
- Capability versioning (v1/v2 contracts) — needed once a second client
  can't tolerate a breaking change alongside the API. Not needed while
  you are the only client and the only developer.
- Authentication on the API layer — needed if the API is ever exposed
  beyond local-first, single-user access (e.g. a future ABM Cloud
  scenario). Not needed today.
- Workflow Layer (retrieve → filter → rank → summarize → return as a
  named abstraction) — worth building once commands have genuinely
  different multi-step pipelines. Today's six console commands are
  direct passthroughs to single existing functions; the abstraction
  would have no real variation to justify it yet.

## Memory/governance-level
- Evaluation Framework — benchmark suites scoring each release on
  memory retrieval, planning, reasoning, coding, security, performance.
  Valuable once there's enough capability variance between versions to
  measure; premature while the system is still being built out phase
  by phase.
- Trust Model — confidence-weighting by source (official docs vs.
  Stack Overflow vs. a random blog). Relevant once external, variable-
  quality sources are being ingested at scale; current ingestion is
  Git/IDE/design-docs, which don't need source-trust weighting yet.
- Versioned Memory/Identity — tracking that a principle or recommendation
  applied "as of 2026," not timelessly. Worth doing once Stream D
  entries actually get revised over time; not yet exercised.

## Deferred from earlier reviews (still valid, still not now)
- Knowledge Distillation (100 commits → one lesson, archive the rest).
- Temporal Reasoning / recency-weighted retrieval.
- Project Isolation (explicit boundaries so a Flutter recommendation for
  one project doesn't bleed into a Python-only project's context).
- Observability (metrics, tracing, decision timeline).
- Full dedicated Security Architecture pillar (identity, secrets,
  certificates, audit, beyond what's already enforced by local-first +
  the v0.4 sandbox + the crypto rule).
