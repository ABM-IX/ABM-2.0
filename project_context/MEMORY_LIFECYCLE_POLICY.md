# ABM 2.0 — Memory Lifecycle Policy

Every memory stream defines WHERE data lives. This document defines WHEN it
dies. No write path may be considered complete until it has an answer to
each stage below. This is most urgent for Stream C
(`abm_ambient_telemetry`), which begins continuous, high-volume writes the
moment Phase v1.0's ambient interaction manager goes live.

## The seven stages

1. **Capture** — raw event enters the pipeline (file save, git commit, IDE
   focus change, etc).
2. **Validate** — passes its stream's Pydantic schema (existing since v0.1).
3. **Store** — written to its collection with full metadata.
4. **Compress** — near-duplicate or low-information entries within a short
   window are merged rather than stored individually (e.g. ten IDE
   focus-change events in one minute collapse to one).
5. **Summarize** — after a retention window, raw entries are distilled into
   a single higher-level entry and the originals are eligible for archive.
   This is knowledge distillation, not just deletion — a lesson can outlive
   the events that produced it.
6. **Archive** — summarized-but-not-deleted entries move to cold storage
   (a separate, cheaper-to-query collection or export), out of the hot
   path used by retrieval.
7. **Delete** — entries with no summary value and past their retention
   window are removed outright.

## Per-stream retention (starting defaults — tune as real volume is observed)

- **Stream A (`abm_code_topologies`):** no automatic deletion. Code
  topology entries are cheap in volume and high in retrieval value
  long-term. Compress only (dedupe identical AST fingerprints).
- **Stream B (`abm_technical_mastery`):** summarize after 90 days;
  archive raw source after summarization; never hard-delete a summary.
- **Stream C (`abm_ambient_telemetry`):** compress aggressively (session-
  level, not event-level, after the first hour). Summarize after 14 days.
  Archive after 30 days. Delete raw archived telemetry after 180 days —
  the summary is what persists past that point, not the raw events.
- **Stream D (`abm_cognitive_identity`):** no automatic deletion, ever.
  Decision journal entries are immutable per their schema. This stream is
  the one place "forever" is the correct default.

## Enforcement

This is Phase v1.0 scope, not a future phase: the ambient interaction
manager must call into a retention-aware write path from its first
version, not have retention bolted on afterward. A test proving Stream C
entries older than the retention window are actually compressed/archived
is part of the v1.0 gate, not a v2.0 addition.
