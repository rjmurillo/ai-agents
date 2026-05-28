# ADR-060: Rework Warning Evidence Persistence in Session Log JSON

## Status

Accepted

## Date

2026-05-25

## Context

REQ-009-07 and REQ-009-08 require that rework warning lines are emitted to stdout
and appended to the session-end `changes` list during `complete_session_log.py`.
Three review threads on PR #1989 requested that those lines also be persisted into
the session log JSON so downstream tools, auditors, and retrospectives can query
rework signal without re-running git.

The session log schema is governed by ADR-014 (read-only contract on HANDOFF.md)
and the DDIA-derived rule in `.claude/rules/data-intensive-applications.md`, which
requires: explicit SoR ownership, schema evolution via optional fields with
documented defaults, and backward compatibility (old readers must not break on new
fields; old logs must still validate without the new field).

### What Currently Exists

- `complete_session_log.py` calls `_run_rework_warning_step()`, which prints lines
  to stdout and returns a one-line summary appended to the `changes` list.
- The session log JSON has no `reworkWarning` sub-key under
  `protocolCompliance.sessionEnd`.
- `validate_session_json.py` validates `SESSION_END_REQUIRED_ITEMS` (a fixed set)
  and any additional item whose `level` field equals `"MUST"` or `"MUST NOT"`.
  Unknown extra fields are ignored, so adding a new informational field is safe.

### Why Change Now

Three PR #1989 review threads requested persistence so the rework signal is
queryable without re-running git. The rework warning is already computed at
session-end; persisting it is a two-line change with zero risk. Omitting it
creates an observable gap between what the tool prints and what it records.

## Decision

1. Add an optional `reworkWarning` object under
   `protocolCompliance.sessionEnd` in the session log JSON.
   Shape:
   ```json
   "reworkWarning": {
     "Evidence": ["rework-warning: none"]
   }
   ```
   `Evidence` is a JSON array of strings, one entry per line that
   `emit_rework_warning_lines` would have printed to stdout.

2. `complete_session_log.py` (canonical `.claude/` and mirror `src/copilot-cli/`)
   sets `session_end["reworkWarning"]["Evidence"]` to the list returned by
   `emit_rework_warning_lines`, or a degraded single-element list when the
   sibling module is unavailable. The field is written before the session log
   is saved (immediately after the rework-warning step, step 4b).

3. `validate_session_json.py` accepts but does not require the field.
   The validator already ignores unknown fields that do not declare
   `level == "MUST"` or `"MUST NOT"`, so no schema change is needed for
   validation. A defensive test confirms old logs without the field
   continue to pass validation.

4. Default / absence: `reworkWarning` is absent on logs created before this
   change. Consumers MUST treat absence as equivalent to
   `{"Evidence": ["rework-warning: none"]}` (no rework signal).

## Prior Art Investigation

- ADR-014: session log write path is `complete_session_log.py`; the new field
  follows the same pattern as `markdownLintRun.Evidence` (informational, string
  evidence populated at session-end).
- `validate_checklist_section` only validates items listed in
  `SESSION_END_REQUIRED_ITEMS` or those declaring `level == "MUST"`. A field
  without a `level` key is never added to `items_to_check`, so validation
  continues to pass on both old and new logs.
- DDIA rule: the new field is additive, optional, and carries no schema version
  bump requirement because the validator already tolerates unknown fields.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Keep stdout-only | No schema change | Signal is ephemeral; lost after session | Requested change by reviewers |
| Add `level: "SHOULD"` to the field | Consistent with checklist pattern | Triggers validator MUST/SHOULD logic, complexity | Not needed; field is informational only |
| New top-level key `reworkWarningEvidence` | Simple path | Violates grouping under `protocolCompliance.sessionEnd` | Reviewers specified the nested path |

### Trade-offs

- Additive field: zero risk to existing logs or validators.
- Degraded path (sibling unavailable): persists
  `["rework-warning: skipped (sibling unavailable)"]` so absence of the field
  is still distinguishable from a failed run.
- `Evidence` is a list, not a string, because multiple files may trigger warnings.
  Downstream consumers can join with `\n` for display.

## Consequences

### Positive

- Rework signal is queryable from the session log JSON.
- Retrospective tooling can aggregate rework patterns across sessions without
  re-running git.
- Positive evidence that the check ran (`"rework-warning: none"`) vs. skipped.

### Negative

- Minimal: every session log grows by a small JSON object.

### Neutral

- Old logs without `reworkWarning` continue to validate and pass all existing
  tests unchanged.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| `complete_session_log.py` (both copies) | Direct | Persist `reworkWarning.Evidence` in session_end | Low |
| `validate_session_json.py` | Indirect | No change needed; accepts unknown fields | None |
| Session log templates in `.agents/sessions/` | Indirect | Templates may optionally add the field | Low |
| Tests for `complete_session_log.py` | Direct | Add presence and backward-compat tests | Low |

## Implementation Notes

- Modify `_run_rework_warning_step()` to return a tuple
  `(summary: str, evidence_lines: list[str])`.
- In `main()`, unpack the tuple; append summary to `changes`; set
  `session_end["reworkWarning"] = {"Evidence": evidence_lines}`.
- The field is written regardless of whether `rework_items` is empty or not;
  `emit_rework_warning_lines([])` returns `["rework-warning: none"]` by contract.

## Related Decisions

- ADR-014: Distributed Handoff Architecture (session log SoR)
- REQ-009-07, REQ-009-08, REQ-009-09: rework warning requirements

## References

- PR #1989: original rework warning implementation
- Issue #2063: follow-up persistence request
- `.claude/rules/data-intensive-applications.md`: schema evolution rules
