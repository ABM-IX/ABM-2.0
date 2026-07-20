# ABM 2.0 — Client #1: Console (Interim Interaction Shell)

Per Architectural Constitution rule 6 (services communicate through
contracts, not direct coupling): this console — and every future client
(Flutter, voice, VS Code extension) — talks ONLY to a single API layer,
never directly to internal modules. Build the API layer first if it
doesn't exist yet; the console is its first consumer, not a special case.

## API layer implementation notes (free, no new work — just structure)
- Organize the API layer's own internals cleanly (e.g. a `core/` module
  with clear boot/config/service-registration/shutdown responsibilities)
  — this is folder/code organization for work already being done this
  session, not a new Kernel milestone. See FUTURE_ARCHITECTURE.md if a
  real Boot/Lifecycle Manager subsystem is ever warranted later.
- Tag each exposed capability with a maturity status: `stable`,
  `experimental`, or `future`. Only `stable` capabilities may be wired to
  a console command in this phase. This is metadata on functions you're
  already writing — not a new system.

## Commands to build now (compose existing, tested capabilities only)

- `ask <question>` — routes through the v0.3 classification router,
  retrieves from the relevant memory stream(s), returns an answer.
- `search <query>` — direct memory query across streams via the existing
  embedding/retrieval layer.
- `status` — read-only view via the existing v0.5 workflow monitor
  (orchestrator + sandbox task state).
- `summarize <project>` — uses the existing v0.5 strategic asset analyzer
  to summarize a project from memory.
- `memory <project>` — read-only aggregated view across all four streams
  filtered by project (decisions, docs, conversations, files, code,
  timeline). No new engine — a composed retrieval view over existing data.
- `explain <target>` — formats already-recorded audit data for a past
  action: v0.3's routing classification/confidence, v0.4's gate scores
  (M_align/S_val/Test_succ/quarantine_flag), or a v0.5 decision journal
  entry's context. No new engine — this data is already recorded per
  constitution rule 5 (every action is auditable); this command just
  makes it readable.

## Explicitly NOT in scope for this client — no underlying engine exists

- `continue` — requires session-state/task-continuation tracking not yet
  designed anywhere in the roadmap.
- `reflect` — requires a reflection engine; does not exist in any phase
  of ABM_SPEC.md.
- `plan` — requires a planning agent; does not exist.
- `learn <topic>` — requires an autonomous research-task queue; does not
  exist.

Each of these gets a console command the day its backend phase is
actually built and gated — not before. Adding them now means informally
building new architecture without a brief or a test gate, which is the
exact failure mode the phase-gate process exists to prevent.
