---
type: requirement
id: REQ-009
title: Orphan-Ref Validator Skill
status: draft
priority: P2
category: non-functional
epic: lifecycle-gate-convergence
related:
  - REQ-007
  - DESIGN-009
  - TASK-009
created: 2026-05-10
updated: 2026-05-10
author: richard
---

# REQ-009: Orphan-Ref Validator Skill

## Step 0 First Principles

### Q1 Demand Reality

rjmurillo (filed #1939); Epic #1933 lifecycle-gate convergence (parent epic, explicitly named in issue body); PR #1942 fix-loop (5 surfaced classes documented in issue body table); retro #1940 (iteration paradox tracking).

### Q2 Status Quo

Bot reviewers (copilot, coderabbit, cursor, devin) flag orphan refs at `/pr-quality:all` round 2-3. PR #1942 paid 3 fix-loop rounds for 21 threads; 4 of 5 orphan-ref classes were caught only post-PR by bots, not by `/review`.

### Q3 Desperate Specificity

M2 PR (#1946 session-qa-eligibility fold), the next planned PR. Spec/plan files for M2 reference `session`, `session-qa-eligibility`, `session-migration` skills, all of which mutate during M2 execution. Without pre-commit detection, M2 will repeat PR #1942's iteration cost.

### Q4 Narrowest Wedge

Original wedge: skill detecting skill-name orphan refs in plugin manifest + skill descriptions only (subset of AC2 + AC4). 4-6 hours implementation.

**Wedge revision (documented at /spec critic 9c, then expanded again during PR #1979 review)**: PR1 ships all eight ACs (AC1 through AC8). AC4 emission is delegated to `build/scripts/validate_marketplace_counts.py` per `.claude/rules/canonical-source-mirror.md`; orphan-ref-validator extracts claims via regex but emits no Findings (deduplication, not divergence). The opt-in `--enforce-counts` single-plugin emission path and the `/test` Gate 5 wiring are tracked in the "PR2 follow-up" section below; they are not ACs of PR1.

### Q5 Observation

"Failure modes this skill prevents (all 5 surfaced on the source PR `feat/skill-eval-triage`)" -- issue #1939 body table. 5 distinct classes documented with file:line evidence (`tests/evals/skills/triage-prompts.json`, `.agents/specs/requirements/REQ-006-...:35`, `.agents/architecture/ADR-040:119`, `.claude/.claude-plugin/plugin.json:3`, `.claude/skills/doc-accuracy/SKILL.md:7`). PR #1942 review-thread record cites these as direct cause of fix-loop iteration.

### Q6 Future-fit

At 10x catalog growth (67 skills -> 670+), manifest-count drift becomes harder to track manually; skill-name orphan refs proliferate as deletions outpace cross-reference updates. Skill remains useful at 10x. Maintenance: regex patterns may need extension as new artifact types emerge, but the architecture (target paths + reference patterns + findings) generalizes.

## Requirement Statement

WHEN a developer runs `/build` or `/test` on a branch that modifies structured artifacts (specs, ADRs, eval fixtures, plugin manifests, skill descriptions),
THE SYSTEM SHALL invoke `orphan-ref-validator` to scan target paths for references to skill names, script paths, and count claims that do not match working-tree state, emit findings per ADR-056 envelope with verdict line `VERDICT: PASS|WARN|CRITICAL_FAIL|ERROR` (where `ERROR` accompanies exit code 2 configuration failures and a populated `Error` block per the skill-output schema), and exit nonzero on CRITICAL_FAIL,
SO THAT orphan refs are blocked pre-commit instead of surfacing in `/pr-quality:all` review iterations.

## Context

PR #1942 (M1 of skill-catalog triage) merged after 3 fix-loop rounds and 21 review threads. Bot reviewers (copilot, coderabbit, cursor, devin) surfaced 5 distinct orphan-ref classes that `/review` had reported PASS on. Each class is a reference in a structured artifact to an entity that no longer exists (or never did) in the working tree. Examples: a SKILL.md describing a deleted skill, a REQ AC referencing a missing script, a plugin manifest claiming a stale count.

The skill closes this gate by scanning target paths pre-commit and emitting structured findings. It lives at `.claude/skills/orphan-ref-validator/` to ship with vendored installs of the plugin.

## Acceptance Criteria

- [ ] REQ-009-AC1: WHEN `/build` ships, THE SYSTEM SHALL provide `.claude/skills/orphan-ref-validator/` with `SKILL.md` (frontmatter + body, ≤500 lines), `.claude/skills/orphan-ref-validator/scripts/scan.py`, and `.claude/skills/orphan-ref-validator/tests/test_scan.py`, SO THAT the skill is discoverable, executable, and testable.
- [ ] REQ-009-AC2: WHEN a scan target file mentions a backticked kebab-case identifier matching `[a-z][a-z0-9]*(?:-[a-z0-9]+)+` (at least one hyphen, no trailing hyphen) absent from `.claude/skills/`, THE SYSTEM SHALL emit `Finding(kind=skill_name, severity=critical, file, line)`, SO THAT skill-description staleness is detected. Single-token names (no hyphens) and trailing-hyphen tokens are not matched. <!-- orphan-ref-ignore -->
- [ ] REQ-009-AC3: WHEN a scan target references a script path matching `(build/scripts|scripts/validation|scripts)/[a-zA-Z0-9_/-]+\.py` absent on disk, THE SYSTEM SHALL emit `Finding(kind=script_path, severity=critical, file, line)`, SO THAT unenforceable AC strings are detected.
- [ ] REQ-009-AC4: WHEN plugin manifest count claims (matching the canonical `COUNT_PATTERN` from `build/scripts/validate_marketplace_counts.py`: `"<N> agent[s]"`, `"<N> slash command[s]"`, `"<N> lifecycle hook[s]"`, `"<N> reusable skill[s]"`, plus `"<N> specialized agent definition[s]"` / `"<N> agent definition[s]"`) appear in plugin or marketplace manifests, THE SYSTEM SHALL extract them via `extract_count_claims` so the regex shape and label map mirror canonical byte-for-byte. **Emission of `Finding(kind=count_claim)` is delegated to `build/scripts/validate_marketplace_counts.py` per `.claude/rules/canonical-source-mirror.md`.** PR1 ships extraction only; an opt-in `--enforce-counts` flag (`scan_file(enforce_counts=True)`) is reserved for PR2 single-plugin enforcement. The canonical's YAML-driven per-plugin source-dir resolution and `--fix` path are not duplicated here.
- [ ] REQ-009-AC5: WHEN scan completes, THE SYSTEM SHALL emit ADR-056 envelope `{Success, Data: {findings, verdict, counts}, Error, Metadata}` to stdout followed by a final line `VERDICT: PASS|WARN|CRITICAL_FAIL|ERROR` (where `ERROR` accompanies exit code 2 configuration failures and a populated `Error` block per the skill-output schema), SO THAT downstream gates parse machine-readable output.
- [ ] REQ-009-AC6: WHEN a target path is absent (vendored-install scenario where `.agents/`, `.serena/`, `.github/` may not exist), THE SYSTEM SHALL log INFO `skipping <path>: not present` and continue, NOT raise, SO THAT the skill survives vendored deployment.
- [ ] REQ-009-AC7: WHEN `/build` runs Mandatory Exit Gates, THE SYSTEM SHALL invoke `orphan-ref-validator` and block on CRITICAL_FAIL, SO THAT orphans cannot pass `/build`.
- [ ] REQ-009-AC8: WHEN `pytest .claude/skills/orphan-ref-validator/tests/` runs, THE SYSTEM SHALL report ≥80% line coverage on `scan.py` with positive (orphan present), negative (no orphans), and edge cases (empty target file, missing target path, mixed living+dead refs), SO THAT regression risk is bounded.

## PR2 follow-up (out of PR1 scope)

These items are intentionally out of scope for PR1 and are tracked as PR2 work in `TASK-009`:

- `/test` Gate 5 (DX) wiring: when `/test` runs Gate 5, invoke `orphan-ref-validator` and surface findings in the test summary. PR2 will add the wiring to `.claude/commands/test.md`.
- `--enforce-counts` opt-in flag: PR1 ships count_claim regex extraction only; emission is delegated to `build/scripts/validate_marketplace_counts.py`. PR2 will add a single-plugin enforcement path under `--enforce-counts` for consumers that want orphan-ref-validator to emit `Finding(kind=count_claim)` directly.

## Rationale

- Closes the gate between `/review` (semantic correctness) and `/pr-quality:all` (adversarial completeness). PR #1942 retro names the iteration paradox as `/review` reporting PASS while `/pr-quality:all` produces BLOCKED on the same diff.
- Vendor-survivable. The skill works in a vendored install where `.agents/` may be absent.
- Schema-tolerant. Adding a new artifact type means extending the target-paths default; the regex set generalizes.

## Dependencies

- ADR-056 (skill output envelope) -- required envelope shape.
- ADR-035 (exit codes) -- 0/1/2 standardization.
- ADR-042 (Python-first) -- scan.py is Python.
- `build/scripts/validate_marketplace_counts.py` -- existing reference for count-claim parsing patterns.
- `build/scripts/validate_plugin_manifests.py` -- existing reference for manifest enumeration patterns.

## Deferred

- Wave 2 wiki-import detection (Epic #1933 Child 4) once `docs/skill-reference.md` becomes a scan target.
- Auto-fix mode (out of scope for v1; track separately if demand surfaces).
- ADR-051 frontmatter validation (separate concern; `validate_design_review.py` exists).

(See "PR2 follow-up" above for the `--enforce-counts` opt-in and `/test` Gate 5 wiring.)

## Out of Scope

- Auto-fixing orphan refs (skill flags, never rewrites)
- Code-comment scanning (analyzer scope: structured artifacts only)
- Network calls (no remote validation)
- Dead-code detection in source files (separate concern)
