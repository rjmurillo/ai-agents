---
type: design
id: DESIGN-023
title: Control-plane baseline capture for v0.7.0
status: draft
priority: P0
related:
  - REQ-024
created: 2026-09-11
updated: 2026-09-11
author: spec-generator
tags:
  - control-plane
  - baseline
  - measurement
---

# DESIGN-023: Control-plane baseline capture for v0.7.0

## Requirements Addressed

- REQ-024: Control-plane baseline capture for v0.7.0

## Design Overview

**Amendment (independent review, post-implementation, 2026-09-11)**:
`fanout_residue` was removed (review F2). It measured `git worktree list`
on the machine running the script, not a property of the repository, so
a rerun elsewhere changed the number with no repository change at all.
Seven dimensions remain; "eight"/"four" counts below are historical (as
originally specced) and superseded by this note, per this task's
minimal-edit instruction.

`scripts/metrics/control_plane_baseline.py` is a read-only CLI that measures
seven dimensions of the repository's control plane as of one pinned commit
and emits `--json PATH` and `--markdown PATH` reports. It is a thin
aggregator: four dimensions call into existing measurement authorities
(`instruction_budget`, `validate_workspace_budget`, `skill_registry`, the
pre-push budget summation `tests/ci/test_lefthook_declared_budget.py` uses),
and three dimensions (`activation`, `accepted_tasks`, and the
lefthook-job-name portion of `canonical`) are new counting logic written
for this script because no prior authority exists for them.

The script never returns a nonzero exit for a metric value. Its only
nonzero paths are a dirty working tree without `--allow-dirty` (exit 1) and
a missing or non-git repository path (exit 2), matching ADR-035's exit-code
convention and DR1 (measurement-only).

## Component Architecture

**Revised at implementation time (design review, 2026-09-11)**: the
`dimensions/` package below was rejected in review in favor of one module.
Eight dimensions with a thin, mostly-import body each do not carry enough
independent logic to justify eight files and a package `__init__.py`; a
`dimensions/` package is exactly the kind of unrequested structural
abstraction `.claude/rules/builder-ethos.md`'s Boil-the-Lake / lazy-ladder
guidance (also mirrored by the `ponytail` house style) argues against when a
single well-organized module covers the same eight functions under the same
per-function complexity ceiling. The eight dimensions remain eight discrete,
independently callable functions; only the file count and import path
changed.

```text
scripts/metrics/control_plane_baseline.py
├── _safe_open(path)                    (shared symlink-refusing writer, T3/AC-10)
├── canonical(repo)                     -> CanonicalOwners | None
├── policy_owners(repo)                 -> PolicyOwners | None
├── always_loaded(repo)                 -> dict[str, AlwaysLoadedContext] | None
├── generated_historical(repo)          -> GeneratedHistorical | None
├── gate_budget(repo)                   -> GateBudget | None
├── activation(repo)                    -> Activation | None
├── accepted_tasks(repo)                -> AcceptedTasks | None
├── Baseline                            (O4 aggregate root dataclass)
├── write_json(baseline, path)          (dataclass -> dict -> json, O_NOFOLLOW)
├── write_markdown(baseline, path)      (dataclass -> markdown, O_NOFOLLOW)
└── main(argv)                          (argparse, exit-code contract)
```

Each dimension function returns its dataclass or `None` (with a logged
reason appended to `Baseline.exclusions`) independently of the others;
`main()` composes the eight into one `Baseline` dataclass (the O4 aggregate
root) and hands it to both report writers. This separation is what makes
AC-07 (missing-dimension degrades to `null`, not a crash) and AC-11
(reproducibility) each testable in isolation: a dimension function has no
side effect on any other, and the aggregator's own logic (compose, then
write) is the only place idempotency and exit-code contract live. The module
stays under 400 lines; every function stays at or under cyclomatic
complexity 10 and 60 lines, matching the same ceiling the `dimensions/`
design would have enforced per-file, just enforced per-function in one file
instead.

## Technology Decisions

| Decision | Choice | O5 source | Rationale |
|---|---|---|---|
| Language | Python 3.14 | ADR-042 | Repository standard for new scripts |
| Token estimator | Import `instruction_budget`'s estimator | DR4 | Never disagree with the existing gate on the same file |
| Gate-budget summation | Import (or extract to shared module) `test_lefthook_declared_budget.py`'s summation | DR4 | AC-06 parity; two independent implementations of the same sum is the exact anti-pattern the epic's `#5394` prohibition names |
| Output writing | `O_NOFOLLOW`, refuse symlink target | T3 (Security) | Matches `metrics_writer.py`'s established pattern for a caller-writable path in this codebase |
| Exit codes | 0 always for metric values; 1 dirty tree; 2 config error | ADR-035, DR1 | The script must be structurally incapable of gating |
| Serialization | stdlib `dataclasses` + `json`, no schema library | OQ1 | Avoids adding a new dependency for eight known fields; a schema library is a new mechanism the epic's Abort-if clause 3 would flag |

## Decision-rule Traceability

| Decision rule | OntologyFragment O5 source | Where enforced |
|---|---|---|
| DR1 (measurement-only) | `control-plane-subtraction-cohort-1.md` O5 | Exit-code contract in `control_plane_baseline.py`'s `main()`; AC-08's synthetic-value test matrix |
| DR2 (KEEP completeness) | same | Not enforced by this design; DR2 governs REQ-022's ledger, not this baseline script |
| DR3 (already-fixed is KEEP) | same | Not enforced by this design; recorded as prior art in REQ-024's Prior Art block for REQ-022 to consume |
| DR4 (reuse over duplication) | same | `always_loaded()` and `gate_budget()` import rather than reimplement; AC-04 and AC-06 test the parity |

## Security Considerations

See REQ-024's Security section for the full threat-modeling summary (T1-T3).
Design-level mitigations:

- `write_json()` and `write_markdown()` share one `_safe_open(path)`
  helper that resolves the path, checks `os.path.islink`, and opens with
  `os.O_NOFOLLOW` where the platform supports it, refusing and exiting 1
  otherwise (AC-10, CWE-59).
- No dimension module reads file content beyond what it needs to count or
  hash a size; `policy_owners()`'s always-on-membership check parses only
  the YAML frontmatter block of each rule file, not its body (AC-09).
- The script accepts `--repo PATH` but never executes arbitrary commands
  constructed from repository content; `_git_output()`'s only subprocess
  calls are fixed argv lists (`["git", "rev-parse", "HEAD"]`,
  `["git", "status", "--porcelain"]`), not a string built from file
  contents, closing the CWE-78 class this repository's
  `search-before-building.md` rule specifically calls out for any
  subprocess invocation over author-controlled input. (`fanout_residue()`,
  this bullet's original subject, was removed per review F2; the fixed-argv
  discipline it demonstrated still applies to the git calls that remain.)

## Testing Strategy

`tests/metrics/test_control_plane_baseline.py`:

- **Positive**: a fixture repo (or a temp git repo built in the test) with
  known counts for each of the eight dimensions; asserts the JSON and
  markdown outputs contain the expected numbers.
- **Negative**: dirty tree without `--allow-dirty` exits 1 and writes
  nothing (AC-02); missing/non-git `--repo` path exits 2 (AC-03); a
  symlinked `--json` target exits 1 and writes nothing (AC-10).
- **Edge**: empty directories for a dimension (zero agents, zero skills);
  a rule file with a block-list `paths:` (non-`**`) correctly excluded from
  `always_loaded`; a missing `harness-capability-matrix.json` degrades
  `accepted_tasks` to `null` with a reason, exit 0 (AC-07).
- **CLI exit-code coverage**: 0 (success, any metric values), 1 (dirty tree
  or symlink refusal), 2 (config error), matrixed against synthetic metric
  values including values deliberately exceeding every release target in
  the committed baseline doc, asserting exit 0 in every case (AC-08, the
  gate that DR1 exists to make testable).
- **Parity**: `gate_budget`'s total equals
  `test_lefthook_declared_budget.py`'s total on the same fixture commit
  (AC-06).
- **Reproducibility**: two runs against the same pinned commit produce
  byte-identical `dimensions` JSON, excluding `captured_at` (AC-11).
- **Live smoke** (not gating CI by default, run manually or in a
  slower-tier job): runs against this repository's actual `main` and
  asserts every one of the eight top-level keys is present, catching a
  dimension silently dropped during refactors.
- **Redaction/no-content-leak**: asserts no dimension's serialized output
  contains a token shape matching `scripts/redact_secrets.py`'s patterns
  (AC-09, defense in depth; the script should never read secret-shaped
  content in the first place, but the test guards the contract).

`uv run pytest tests/metrics -x`, `uv run ruff check scripts/metrics
tests/metrics`, `uv run python scripts/validation/pre_pr.py` per the seed
plan's test plan for PR1.

## Open Questions

- Whether `gate_budget`'s summation function is currently importable or
  test-local (REQ-024 OQ3); TASK-028 resolves this before writing
  `gate_budget()`, and if extraction is needed, the extraction itself is
  a small, in-scope refactor (moving a pure function, not changing its
  behavior).
- Whether `policy_owners`'s always-on-membership parser should be its own
  small YAML-frontmatter reader or should also import from
  `instruction_budget`'s `is_language_universal` if that function is
  reusable outside its current module; TASK-028 checks the module's public
  surface before deciding to import vs. write a narrower parser scoped to
  frontmatter only (this design's own read is narrower: `is_language_universal`
  answers "does this rule apply to this language", while `policy_owners`
  only needs "is this rule always-on", a simpler question that may not need
  the full function).
