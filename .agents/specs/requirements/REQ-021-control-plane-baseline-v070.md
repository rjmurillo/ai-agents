---
type: requirement
id: REQ-021
title: Control-plane baseline capture for v0.7.0
status: draft
priority: P0
category: functional
epic: EPIC-5456
source: GH-5456
related:
  - DESIGN-020
created: 2026-09-11
updated: 2026-09-11
author: spec
tags:
  - control-plane
  - baseline
  - measurement
  - v0.7.0
---

# REQ-021: Control-plane baseline capture for v0.7.0

## Step 0 First Principles

### Q1 Demand Reality

Four named entities demand this work: (1) rjmurillo, author of epic #5456 and
owner of its binding "Decision" and "Release gates" sections; (2) the v0.7.0
Release gates checklist itself, whose first item ("Canonical behavior owners
decrease from the pinned baseline") cannot be checked true or false without a
committed baseline to decrease from; (3) ADR-100
(`.agents/architecture/ADR-100-retire-pr-size-ceilings.md`), an accepted
decision naming items 2-6 as retirement work, items 2-4 unclaimed at spec
time; (4) issue #5241, named in the epic's Execution section as an initial
release candidate for this same cohort.

### Q2 Status Quo

No committed baseline exists. `.agents/metrics/baseline-report.md` and
`STEP-0-METRICS.md` measure a different, narrower scope (Step 0 gate
telemetry, not control-plane inventory) and are stale relative to this
question. The four reusable measurement authorities named in the epic's
Baseline bullets (`scripts/validation/instruction_budget.py`,
`scripts/validate_workspace_budget.py`, `scripts/skill_registry.py`,
`tests/ci/test_lefthook_declared_budget.py`) exist but have never been run
together, pinned to one SHA, with exclusions and release targets recorded in
one place. The only prior attempt at this baseline is an uncommitted
scratchpad plan file from this session, not a durable artifact. Contributors
today act on scattered or stale evidence instead: this cohort's own Step 0.5
search found a Serena memory
(`.serena/memories/ci/ci-pre-push-wall-clock-is-python-tests.md`, dated
2026-08-19) claiming a duplicate pre-push gate execution that commit
`becde1660` (PR #5418, landed before this memory's date but the memory was
not corrected) had already fixed via the `AI_AGENTS_PRE_PR_FAST_STAGE_RAN`
skip mechanism, which this cohort's own analysis rediscovered by reading
`scripts/validation/pre_pr_sequence.py` directly rather than trusting the
memory.

### Q3 Desperate Specificity

Epic #5456's own Baseline section: "Before the first deletion cohort, capture
a reproducible baseline from one pinned `main` SHA." Every other candidate
the epic names (#5394, #5395, #5396, #5420, #5421, #5241 items 2-6) is
blocked from being scored as a release win until this baseline exists,
because the Release gates checklist requires "decrease from the pinned
baseline" and there is nothing to decrease from yet.

### Q4 Narrowest Wedge

Approximately 7-8 hours: a read-only measurement CLI
(`scripts/metrics/control_plane_baseline.py`) covering the eight dimensions
the epic's Baseline section lists (reduced to seven post-implementation;
see the Amendment note under Data model), its test suite
(`tests/metrics/test_control_plane_baseline.py`), and the committed baseline
doc pair (`.agents/metrics/control-plane-baseline-v0.7.0.md` and `.json`)
generated from one pinned `main` SHA.

### Q5 Observation

Commit `cd0f9561d` (the pinned `main` SHA at spec time), with the live
numbers already gathered as evidence for this cohort: agents 31, skills 113
directories / 111 `SKILL.md` files, rules 30 (5 always-on), hooks 12 Python
files under `.claude/hooks`, validators 63, workflows 58, lefthook jobs 76,
`.github/instructions` 30, `src/copilot-cli/instructions` 24, ADRs 109,
governance docs 43, Serena memories 1,037, episodes 750, sessions 1,467,
archive 816 files; workspace pool 6,306/6,600 bytes; `instruction_budget`
`.md` 56,889/83,000, `.py` 98,247/99,000. Also
`scripts/eval/examples/harness-capability-matrix.json` with every cell
`UNVERIFIED`.

### Q6 Future-fit

Yes. A read-only script that reuses existing authorities scales linearly as
the corpus grows (more rows out of the same dimensions, same exit-code
contract); it does not become a liability at 10x. The alternative, no
baseline, becomes more dangerous at 10x: the exact failure mode this
cohort's own research hit (a stale memory citing a fixed problem) compounds
as the corpus and its history grow, because nobody has one place to check
"is this still true" against a pinned commit.

## Prior Art / Constraints

### Direct prior art from memory

- `.serena/memories/decision-the-instruction-budget-gate-already-exists.md`
  ("The always-on instruction budget gate already exists, and it is nearly
  full"): documents the exact failure this REQ's DR4 exists to prevent, an
  analysis note prescribing a new instrument for a gap `main` had already
  closed a day earlier. Relevance: direct precedent for reuse-over-rebuild
  on this REQ's `always_loaded` dimension. Decision: honor; REQ-021 AC-04
  imports `instruction_budget`'s estimator rather than re-implementing it.
- `.serena/memories/ci/ci-pre-push-wall-clock-is-python-tests.md`
  ("Pre-push wall clock is python-tests; everything else is noise", dated
  2026-08-19): the section "The same work runs twice in one hook" is now
  stale. `scripts/validation/pre_pr_sequence.py:253-257` (`_Gate("Count
  Ratchets", ..., already_run_by="count-ratchets")`) and the
  `FAST_STAGE_RAN_ENV` skip at `pre_pr_sequence.py:543-556` resolve exactly
  the duplication this memory describes, wired to `lefthook.yml:590`, and <!-- citation-freshness: ignore -- lefthook.yml:590 holds the literal env var name `AI_AGENTS_PRE_PR_FAST_STAGE_RAN`, not the Python constant `FAST_STAGE_RAN_ENV` that stores it; verified present by direct read during REQ-021/TASK-024 implementation, 2026-09-11. -->
  pinned by `tests/validation/test_pre_pr_sequence_registry.py:133-266`
  (`FAST_STAGE_DUPLICATES`, five gates: Count Ratchets, Unreachable Code
  Detection, Path Normalization, Planning Artifacts, Em/en-dash
  Prohibition). Relevance: this was the evidentiary basis for a fourth PR
  ("delete duplicate gate execution") in this cohort's original seed plan;
  the mechanism it targeted is already fixed. Decision: propose-amend. The
  cohort drops that PR; the baseline script's `dispositions` reuse note in
  DESIGN-020 records this finding so the memory itself can be corrected in
  a later, non-worktree session.
- `.serena/memories/ci/run-count-ratchets-before-the-expensive-pre-push.md`:
  documents the staging fix (issue #5066) that moved count ratchets to a
  fast pre-push stage. Relevance: background for how the fast-stage/
  pre-pr-validation split this REQ's `gate_budget` dimension measures came
  to exist. Decision: honor as background context, no action required.
- `.serena/memories/decision-stop-orders-are-not-a-control-plane.md`: uses
  "control plane" for scheduling/process contention across concurrent
  agents, a different sense of the term than this epic's (governance
  mechanism inventory). Adjudicated out-of-scope below; not prior art for
  this REQ.

### Connected context from prior-art search

- Connected entity: `scripts/validate_workspace_budget.py` `WORKSPACE_FILES`
  (four files: `CLAUDE.md`, `AGENTS.md`, `.claude/CLAUDE.md`,
  `.github/copilot-instructions.md`). Adjudication: in-scope (Q4 names the
  epic's "always-loaded instruction bytes" bullet; this REQ's `always_loaded`
  dimension reuses this list and extends it per-harness). Note: the plan
  seed's own gap table already recorded the extension need ("four files
  only" -> Claude source tree gap).
- Connected entity: `.serena/memories/decision-stop-orders-are-not-a-control-plane.md`
  (found by the literal string "control plane"). Adjudication: out-of-scope.
  Different referent (process scheduling, not governance-mechanism
  inventory); no relationship to this REQ's data model.
- Connected entity: `scripts/eval/examples/harness-capability-matrix.json`.
  Adjudication: in-scope (epic Baseline bullet "accepted-task outcomes
  available from #5422 through #5426"; this REQ's `accepted_tasks`
  dimension reports verified-vs-UNVERIFIED cell counts, not the outcomes
  themselves, since the paid probes are unavailable).
- (Search depth: medium, matched to ProvisionalTier 4's deep-tier intent but
  degraded; see Coverage notes.)

### Coverage notes

- Topic `control-plane-baseline`: 4 grep variants against
  `.serena/memories/` (`control.plane`, `count.ratchet|duplicate.gate|fast.stage`,
  `instruction.budget`, `disposition|v0\.7\.0|5456`). Results: 2 directly
  relevant hits (above), several false positives from index/skills files
  excluded after read. Confidence: medium. MCP-based `memory` skill search
  (`mcp__serena__read_memory` via the `Skill(skill="memory")` path) was
  unavailable in this worktree session per the invoking task's explicit
  instruction; grep against `.serena/memories/` was substituted, which finds
  filename and content matches but not the `memory` skill's ranked
  relevance scoring. This is a degraded search, recorded rather than hidden.
- Topic `adr-100-items`: 3 grep variants (`adr.100|pr.size.ceiling`,
  `check_atomic_commit`, `detect_scope_explosion|SKIP_SCOPE_CHECK`). Zero
  direct hits beyond generic index files. Absence of evidence, not evidence
  of absence; no memory documents ADR-100's items 2-4 specifically, which is
  expected since ADR-100 itself (committed in-repo) is the authoritative
  record for that decision and this REQ does not touch items 2-4 (REQ-023
  does).
- `chestertons-fence` and `memory` were applied by direct git/code
  archaeology in-line (reading `pre_pr_sequence.py`, `checks_ratchet.py`,
  `lefthook.yml`, `ADR-100`, and the memories above) rather than through a
  live `Skill()` invocation, per this cohort's operating constraints
  (worktree session, no MCP). Search ran; it did not fail silently.

## Requirement Statement

WHEN a contributor runs `scripts/metrics/control_plane_baseline.py` against a
clean `main` checkout,
THE SYSTEM SHALL emit a JSON and Markdown report covering canonical owners,
policy owners, always-loaded context per harness, generated/historical
volume, declared gate budget, worktree fan-out residue, skill activation
evidence, and accepted-task verification counts, all as of the pinned commit
SHA, with exit code 0 regardless of the values measured,
SO THAT every later deletion cohort under epic #5456 has one committed number
to decrease from, per the epic's Release gates checklist.

## Context

Engineering tier: 3 (CVA analysis required; single-team; reversible;
cross-cutting within one repository, not cross-team). Problem domain:
Complicated (the eight dimensions are enumerable and each has a known or
discoverable measurement method; nothing here requires probe-sense-respond
experimentation). Methodology: sense-analyze-respond, standard
acceptance-criteria spec extended with a mandatory reuse constraint (DR4).

This is the first of three requirements in epic #5456's first cohort. It
must land before REQ-022 (the disposition ledger classifies candidates using
this baseline's numbers) and does not depend on REQ-023.

## Ontology

See `.agents/specs/ontology/control-plane-subtraction-cohort-1.md`. This
requirement's data model is the `Baseline` aggregate root: it produces the
JSON/markdown pair, the pinned SHA, exclusions, and release targets as one
unit (O4). It measures `CanonicalOwner`, `PolicyOwner`, `AlwaysLoadedContext`,
`GeneratedArtifact`, and `GateBudget` counts (O3), and its exit-code contract
is decision rule DR1 (measurement-only). DR4 (reuse over duplication) binds
every dimension that an existing script already measures.

## Data model

**Amendment (independent review, post-implementation, 2026-09-11)**:
`fanout_residue` (below) was removed. It measured `git worktree list` on
the machine running the script, a property of that machine, not of the
repository; a rerun on a different machine or a different day changed the
number with no repository change at all. Seven dimensions remain; every
"eight" below is historical (as originally specced) and superseded by
this note, kept rather than rewritten throughout per this task's
minimal-edit instruction.

- `Baseline` (aggregate root): `commit_sha`, `captured_at` (UTC ISO-8601),
  `command` (the exact invocation), `dimensions` (the eight sub-objects
  below), `exclusions` (list of `{dimension, reason}`), `release_targets`
  (list of `{metric, target, direction}`).
- `canonical`: counts for agents, skills, rules, hooks, validators,
  workflows, lefthook jobs.
- `policy_owners`: rule mirror counts, ADR count, governance doc count,
  Serena memory count, always-on rule membership (parsed from mirror
  `applyTo` per the canonical-source-mirror rule's `**` test).
- `always_loaded`: per-harness `{bytes, tokens}` for Claude Code, Copilot,
  Codex, using `instruction_budget`'s token estimator (DR4; imported, not
  reimplemented).
- `generated_historical`: file count and bytes for episodes, sessions,
  Serena memories, archive, eval-results, plus generated projections
  (`src/copilot-cli/**`, `.github/instructions/**`), reported apart from
  `canonical` (O3 relationship).
- `gate_budget`: declared pre-commit and pre-push worst-case latency, summed
  the way `tests/ci/test_lefthook_declared_budget.py` sums it (reused, not
  reimplemented, per DR4; if the summation helper is test-local, this
  requirement's design moves it to an importable module both callers share).
- `fanout_residue`: removed; see the Amendment note above this list.
- `activation`: skills referenced by name from `AGENTS.md`, `CLAUDE.md`, and
  `.claude/skills/autoplan/SKILL.md`'s routing table; skills with a
  `tests/skills/<name>/` directory.
- `accepted_tasks`: verified vs. `UNVERIFIED` cell counts from
  `scripts/eval/examples/harness-capability-matrix.json`.

## Integrations

- Reads (does not modify): `.claude/agents/`, `.claude/skills/`,
  `.claude/rules/`, `.claude/hooks/`, `.claude/settings.json`,
  `scripts/validation/`, `.github/workflows/`, `lefthook.yml`,
  `.github/instructions/`, `src/copilot-cli/instructions/`,
  `.agents/architecture/`, `.agents/governance/`, `.serena/memories/`,
  `.agents/memory/episodes/`, `.agents/sessions/`, `.agents/archive/`,
  `.agents/eval-results/`, `src/copilot-cli/`, `scripts/eval/examples/harness-capability-matrix.json`.
- Imports (does not shell out to, where avoidable): `instruction_budget`'s
  token estimator, `skill_registry`'s skill inventory, and the pre-push
  budget summation used by `tests/ci/test_lefthook_declared_budget.py`.
- Failure modes: a missing dimension source (for example a repo without
  `.serena/memories/`) degrades that one dimension to `null` with a logged
  reason; it does not fail the run (exit 0 still, per DR1). A dirty working
  tree refuses the run (exit 1) unless `--allow-dirty` is passed, because an
  uncommitted baseline is not reproducible from a pinned SHA. Idempotency:
  running the script twice against the same commit produces byte-identical
  JSON (no wall-clock-derived fields inside `dimensions`; `captured_at` is
  the one field allowed to vary between runs).

## Failure modes

(Populated from a pre-mortem run in-line; see the plan's pre-mortem section
for the cohort-level version. Requirement-scoped risks below.)

- **Scenario**: the script silently drifts into a gate (nonzero exit on a
  metric value) after a future edit adds a threshold check. **Category**:
  process. **Early warning**: a test asserting exit 0 across a matrix of
  synthetic metric values starts failing. **Prevention**: AC-08 requires
  this test to exist and run in CI. **Detection**: CI failure on the exit
  code assertion, not on a metric threshold. **Response**: revert the
  threshold check; a baseline script is measurement-only per DR1 and the
  epic's "Abort if" clause 3.
- **Scenario**: `gate_budget` double-counts a job already summed by
  `test_lefthook_declared_budget.py`, producing a baseline number nobody can
  reproduce by hand. **Category**: technical. **Early warning**: the two
  summation paths (test and script) diverge on a snapshot repo fixture.
  **Prevention**: DR4 requires importing the same summation function, not
  re-deriving it. **Detection**: AC-06's parity test. **Response**: extract
  the shared function to an importable module if it is currently test-local.
- **Scenario**: `.agents/metrics/` becomes a write target another in-flight
  effort (#5420) wants to relocate, creating a conflicting PR.
  **Category**: organizational. **Early warning**: a second open PR touches
  `.agents/metrics/` paths. **Detection**: PR conflict on push.
  **Response**: relocation is a `git mv` after this REQ lands; the epic
  counts relocation apart from deletion, so this is not a blocking
  dependency, only a sequencing note (recorded as Deferred below).

## Security

Threat-modeling summary (Tier 3, mandatory). Trust boundary: the script runs
locally or in CI with the same filesystem read access as any other pre-push
validator; it introduces no new network calls, no new write path outside
`.agents/metrics/`, and no new authentication surface.

- **T1 (Tampering)**: a crafted `.claude/rules/*.md` with a malformed
  `applyTo` value could cause the always-on parser to misclassify a rule.
  Mitigation: reuse `instruction_budget`'s existing `is_language_universal`
  parser (DR4) rather than writing a second one; it already handles this
  case (see the instruction-budget memory's discussion of matching vs.
  enumeration).
- **T2 (Information Disclosure)**: the JSON/markdown output could include
  file contents or secrets if a dimension accidentally dumps file bodies
  instead of counts. Mitigation: AC-09 requires every dimension to emit
  counts and paths only, never file content; a negative test asserts no
  dimension's output contains a token matching the redaction patterns in
  `scripts/redact_secrets.py`'s matched shapes.
- **T3 (Path traversal / symlink)**: `--json PATH` and `--markdown PATH`
  accept a caller-supplied output path. Mitigation: refuse a symlinked
  target and open with `O_NOFOLLOW` where supported, matching the pattern
  `.claude/skills/spec/scripts/metrics_writer.py` already uses (CWE-59,
  CWE-367); this is new code for this script, not a reuse, because
  `metrics_writer.py` appends to a fixed tally path and this script writes
  caller-chosen report paths.
- No threat rated High or Critical: the script is read-only over
  already-readable repository content and writes only to caller-specified
  paths under the same trust boundary as the invoking user or CI job.

## Observability

Lightweight SLO (Tier 3 permits the full SLI/SLO/error-budget form or the
lightweight "what metric proves this works" form; this REQ uses the latter,
because the script is a point-in-time CLI, not a running service with a
user-facing latency or availability target).

- **What proves this works**: the script's own wall-clock time on this repo,
  logged in its markdown output header. No numeric target is set for v0.7.0;
  the observable is "it completes and exits 0", which AC-01 and AC-08
  test directly. A future cohort may add a wall-clock ceiling once repeated
  runs establish a baseline distribution (Deferred).
- **Alert**: none. This is a manually or CI-invoked CLI, not a monitored
  service.

## Acceptance Criteria

- [ ] REQ-021-AC1: WHEN `control_plane_baseline.py` runs against a clean
      checkout with `--repo <path>`, THE SYSTEM SHALL emit both `--json PATH`
      and `--markdown PATH` outputs containing all seven dimensions
      (`canonical`, `policy_owners`, `always_loaded`, `generated_historical`,
      `gate_budget`, `activation`, `accepted_tasks`; `fanout_residue`
      removed per the Data model Amendment note) SO THAT no dimension is
      silently omitted.
- [ ] REQ-021-AC2: WHEN the working tree is dirty (uncommitted changes)
      AND `--allow-dirty` is not passed, THE SYSTEM SHALL exit 1 without
      writing output SO THAT a baseline is never captured from an
      unreproducible state.
- [ ] REQ-021-AC3: WHEN the repository path does not exist or is not a git
      repository, THE SYSTEM SHALL exit 2 SO THAT configuration errors are
      distinguishable from logic errors, per ADR-035.
- [ ] REQ-021-AC4: WHEN `always_loaded` tokens are computed, THE SYSTEM
      SHALL call `instruction_budget`'s token estimator rather than
      reimplementing token counting SO THAT the script and
      `instruction_budget.py` never disagree on the same file (DR4).
- [ ] REQ-021-AC5: WHEN `canonical` and `generated_historical` are computed
      for overlapping directories (for example `src/copilot-cli/`), THE
      SYSTEM SHALL report `generated_historical` separately from
      `canonical` and SHALL NOT sum them into one total SO THAT the epic's
      "reported separately from canonical product inputs" requirement holds.
- [ ] REQ-021-AC6: WHEN `gate_budget` is computed, THE SYSTEM SHALL produce
      the same total as `tests/ci/test_lefthook_declared_budget.py` on the
      same commit SO THAT the two never silently diverge (a parity test
      asserts this in CI).
- [ ] REQ-021-AC7: WHEN any dimension's underlying data is absent (for
      example no `.serena/memories/` directory), THE SYSTEM SHALL record
      that dimension as `null` with a logged reason and SHALL exit 0 SO
      THAT a missing optional signal never blocks measurement (DR1).
- [ ] REQ-021-AC8: WHEN the script runs to completion on any input, THE
      SYSTEM SHALL exit 0 regardless of the numeric values measured SO THAT
      the script can never function as a gate, ratchet, or evaluator, per
      the epic's "Abort if" clause 3 and decision rule DR1. A test matrix
      of synthetic metric values (including values exceeding every plan-seed
      release target) SHALL assert exit 0 in every case.
- [ ] REQ-021-AC9: WHEN the script emits JSON or markdown output, THE
      SYSTEM SHALL emit counts, paths, and byte/token figures only, and
      SHALL NOT include full file contents, SO THAT the baseline artifact
      cannot leak secrets or large bodies of text.
- [ ] REQ-021-AC10: WHEN `--json PATH` or `--markdown PATH` resolves to a
      symlink, THE SYSTEM SHALL refuse to write and exit 1 SO THAT the
      script cannot be used to overwrite an arbitrary file via a symlink
      swap (CWE-59).
- [ ] REQ-021-AC11: WHEN run twice against the same pinned commit with the
      same flags, THE SYSTEM SHALL produce byte-identical `dimensions`
      content in both JSON outputs (excluding the `captured_at` timestamp)
      SO THAT the baseline is reproducible, per the epic's Baseline
      section.
- [ ] REQ-021-AC12: WHEN the committed baseline doc pair is written at
      commit `cd0f9561d` (or the pinned SHA current when this REQ lands),
      THE SYSTEM SHALL record the exact command, every exclusion with its
      reason, and the release targets from this REQ's Deferred and Out of
      Scope sections SO THAT the epic's "Commit the baseline, measurement
      commands, exclusions, and release targets" instruction is satisfied
      in one artifact.

## Co-change checklist

- [ ] scripts/metrics/control_plane_baseline.py:"new file" -- read-only
      measurement CLI, eight dimensions, exit-code contract per DR1
- [ ] tests/metrics/test_control_plane_baseline.py:"new file" -- positive,
      negative, edge, CLI exit-code, and exit-0-regardless-of-value coverage
- [ ] .agents/metrics/control-plane-baseline-v0.7.0.md:"new file" -- committed
      baseline doc, pinned SHA `cd0f9561d` (or later pinned SHA)
- [ ] .agents/metrics/control-plane-baseline-v0.7.0.json:"new file" --
      machine-readable twin of the markdown doc
- [ ] scripts/validation/instruction_budget.py:"token estimator" -- imported,
      not modified (DR4)
- [ ] tests/ci/test_lefthook_declared_budget.py:"summation function" --
      imported or extracted to a shared module, not re-derived (DR4, AC-06)

## Out of Scope

- The reduced-configuration comparison against this baseline (epic Release
  gate: "At least one reduced-control configuration is compared with the
  full baseline on identical downstream tasks"). Owned by #5422-#5426.
- The final release report distinguishing deletion from relocation,
  generation, and archival. Owned by the epic itself at release time, after
  all cohorts land.
- Any deletion, consolidation, or mechanism-level change. This REQ only
  measures; child issues own the mechanism work (O6 bounded-context
  boundary).
- Gate p50/p95 sampling. No sampler exists; the baseline records the two
  single measurements already cited in ADR-104 and
  `.serena/memories/ci/ci-pre-push-wall-clock-is-python-tests.md` as
  provisional evidence, not a statistically sound p50/p95.
- Fan-out routing changes (#5651 already routes #5436's fix to the harness);
  this REQ measures `fanout_residue` as a count only.

## Deferred

- A wall-clock ceiling for the baseline script itself, pending a
  distribution of repeated-run timings (Observability section).
- Relocating `.agents/metrics/` if #5420 lands a generated-state separation
  that wants a different write target; tracked as a `git mv` follow-up, not
  blocking this REQ (Failure modes, R3-equivalent risk).
- Extending `gate_budget` to include a real p95 sampler; needs multiple
  measured pushes across contributors, not available at spec time.

## Open Questions

- **OQ1**: Should `.agents/metrics/control-plane-baseline-v0.7.0.json`
  additionally be validated by a schema file, the way spec frontmatter is
  validated by `validate_spec_frontmatter.py`? Owner: implementer, at
  TASK-024 time. Assumption made here: no, a Python dataclass-to-dict
  serialization with a test asserting the eight top-level keys is
  sufficient at this scale; the epic does not ask for a new schema registry
  and one would itself be a new mechanism (Abort-if clause 3).
- **OQ2**: Does `activation` (skills referenced by name plus
  `tests/skills/<name>/` presence) need to distinguish "referenced in
  routing table" from "referenced in prose elsewhere"? The epic's Baseline
  bullet says "activation or demonstrated-consumer evidence for
  capabilities where observable" without specifying precision. Assumption:
  the two named sources (AGENTS.md/CLAUDE.md/autoplan routing table
  references, and `tests/skills/<name>/` directory presence) are the
  observable proxy; a stronger signal (real invocation telemetry) does not
  exist in this repo and is explicitly excluded (Out of Scope).
- **OQ3**: `gate_budget`'s summation function may currently be defined
  inside `tests/ci/test_lefthook_declared_budget.py` rather than an
  importable module. If so, is moving it a within-scope refactor for this
  REQ, or a separate PR? Assumption: within scope, because AC-06 cannot
  otherwise be satisfied without either duplicating the function (violates
  DR4) or importing test code from production code (a code-quality
  violation this repo's standards forbid). TASK-024 verifies the current
  location before implementation and adjusts scope only if the function
  already lives in an importable module.

## CVA summary

**Commonalities** across the eight dimensions: each is a read-only count or
byte/token measurement over a well-known repository path set, each degrades
to `null`-with-reason rather than failing the run, and each must cite its
source authority rather than recompute independently (DR4).
**Variabilities**: some dimensions have an existing authority to import
(`always_loaded`, `gate_budget`, parts of `canonical` via `skill_registry`);
others (`fanout_residue`, `activation`, `accepted_tasks`) have no prior
script and are written fresh for this REQ. **Relationships**: `canonical`
and `generated_historical` are deliberately kept as separate totals (O3);
`policy_owners` and `canonical` overlap for a rule that is also a validator
trigger, and that overlap is reported in both dimensions rather than
de-duplicated, matching the ontology's O7 open question rather than forcing
a premature resolution.

## Buy-vs-build decision

Quick tier (Phase 1 + Phase 2 lite), per the spec skill's Step 4a gate: this
REQ introduces a new script.

- **Core vs Context**: Context. A repository-inventory measurement CLI is
  undifferentiating support work, not a competitive capability; default is
  BUY.
- **Alternatives evaluated**: (1) a generic OSS repo-metrics tool (for
  example `cloc`, `scc`, or a dependency-graph visualizer): none of these
  understand this repository's specific taxonomy (agent vs. skill vs. rule
  vs. hook vs. validator vs. lefthook job as distinct countable categories,
  or the always-on `applyTo: **` classification rule); adopting one would
  still require a custom layer on top, which is most of the work anyway.
  (2) `instruction_budget.py`, `validate_workspace_budget.py`,
  `skill_registry.py`, `test_lefthook_declared_budget.py` individually: each
  covers one dimension but none aggregates all eight into one pinned-SHA
  snapshot with exclusions and targets, which is exactly what the epic's
  Baseline section asks for. (3) A spreadsheet or manual count: not
  reproducible, fails the epic's "reproducible baseline" requirement
  outright.
- **Recommendation**: build, as a thin aggregator that imports the four
  existing authorities (DR4) and adds new counting logic only for the four
  dimensions with no prior script. This is not a new capability so much as
  a composition of existing ones; the epic's Abort-if clause 3 (no new
  registry, evaluator, ratchet, or governance layer) is satisfied because
  the script computes and reports, and asserts nothing.
- **Rationale**: Context classification defaults to BUY, but no vendor or
  generic tool exists for "this repository's specific control-plane
  taxonomy", so the red-line "Never Buy" criterion (no viable vendors)
  applies, and build is the only viable path. TCO is trivial at Quick tier
  (single script, ~7-8h, no ongoing license or vendor relationship).

## Complexity classification

Engineering tier: 3 (Senior). Rationale: touches shared repository
infrastructure (reads across nearly every governance surface), requires CVA
analysis (commonalities/variabilities above) and a design review gate, but
is single-repository, reversible (a read-only script can be deleted with no
data-loss risk), and does not require multi-org consensus or an ADR (Tier
4-5 only). Problem domain: Complicated (Cynefin). Rationale: every dimension
has a discoverable measurement method via expert analysis of the existing
authorities; nothing here requires experimentation to find a pattern.
Methodology: sense-analyze-respond, standard acceptance-criteria spec with a
mandatory-reuse constraint (DR4) layered on top.

## Rationale

The epic is explicit and ordered: "Before the first deletion cohort, capture
a reproducible baseline... Commit the baseline, measurement commands,
exclusions, and release targets before using the metrics to choose winners."
No child issue's deletion or KEEP claim can be scored against the Release
gates checklist without this baseline. Building a thin, read-only, reuse-first
script is the narrowest wedge that satisfies both the ordering requirement
and the epic's Abort-if clause 3 (no new gate, ratchet, registry, or
evaluator).

## Dependencies

- `scripts/validation/instruction_budget.py` (token estimator, DR4)
- `scripts/validate_workspace_budget.py` (`WORKSPACE_FILES`, extended per-harness)
- `scripts/skill_registry.py` (skill inventory)
- `tests/ci/test_lefthook_declared_budget.py` (gate-budget summation, DR4)
- `.claude/skills/spec/scripts/metrics_writer.py` (pattern reference for
  symlink-safe output writing, AC-10)
- `scripts/eval/examples/harness-capability-matrix.json`
- ADR-104 (300s pre-push target, cited as a ceiling not a goal for
  `gate_budget` release targets)
