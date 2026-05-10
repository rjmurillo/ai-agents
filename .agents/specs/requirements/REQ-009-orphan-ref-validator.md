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

**Wedge revision (documented at /spec critic 9c, then expanded again during PR #1979 review)**: actual ship-with-PR wedge is AC1+AC2+AC3+AC5+AC6+AC7+AC9 (~5.5h). Rationale: (a) AC1+AC5+AC6 are infrastructure prerequisites without which AC2+AC3 cannot run; (b) AC7 (/build wiring) is required for the skill to execute during M2 PR #1946 review; (c) AC3 (script_path detection) was originally deferred but ships in PR1 because the regex and detection logic were trivial to author alongside AC2 and the canonical-source-mirror review surfaced the inconsistency between the deferred-list and the implementation. AC4 (count_claim emission) is delegated to `build/scripts/validate_marketplace_counts.py` per `.claude/rules/canonical-source-mirror.md`; orphan-ref-validator extracts claims via regex but emits no Findings (deduplication, not divergence). AC8 (/test gate-5 wiring) is deferred to follow-up PR.

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
- [ ] REQ-009-AC2: WHEN a scan target file mentions a skill name (kebab-case identifier matching `[a-z][a-z0-9-]+`) absent from `.claude/skills/`, THE SYSTEM SHALL emit `Finding(kind=skill_name, severity=critical, file, line)`, SO THAT skill-description staleness is detected.
- [ ] REQ-009-AC3: WHEN a scan target references a script path matching `(build/scripts|scripts/validation|scripts)/[a-zA-Z0-9_/-]+\.py` absent on disk, THE SYSTEM SHALL emit `Finding(kind=script_path, severity=critical, file, line)`, SO THAT unenforceable AC strings are detected.
- [ ] REQ-009-AC4: WHEN plugin manifest count claims (e.g. "67 skills", "23 agents") diverge from actual catalog enumeration, THE SYSTEM SHALL emit `Finding(kind=count_claim, severity=critical, file, line, expected, actual)`, SO THAT manifest drift is detected.
- [ ] REQ-009-AC5: WHEN scan completes, THE SYSTEM SHALL emit ADR-056 envelope `{Success, Data: {findings, verdict, counts}, Error, Metadata}` to stdout followed by a final line `VERDICT: PASS|WARN|CRITICAL_FAIL|ERROR` (where `ERROR` accompanies exit code 2 configuration failures and a populated `Error` block per the skill-output schema), SO THAT downstream gates parse machine-readable output.
- [ ] REQ-009-AC6: WHEN a target path is absent (vendored-install scenario where `.agents/`, `.serena/`, `.github/` may not exist), THE SYSTEM SHALL log INFO `skipping <path>: not present` and continue, NOT raise, SO THAT the skill survives vendored deployment.
- [ ] REQ-009-AC7: WHEN `/build` runs Mandatory Exit Gates, THE SYSTEM SHALL invoke `orphan-ref-validator` and block on CRITICAL_FAIL, SO THAT orphans cannot pass `/build`.
- [ ] REQ-009-AC8: WHEN `/test` runs Gate 5 (DX), THE SYSTEM SHALL invoke `orphan-ref-validator` and surface findings in test summary, SO THAT cross-cutting orphan detection runs in test phase.
- [ ] REQ-009-AC9: WHEN `pytest .claude/skills/orphan-ref-validator/tests/` runs, THE SYSTEM SHALL report ≥80% line coverage on `scan.py` with positive (orphan present), negative (no orphans), and edge cases (empty target file, missing target path, mixed living+dead refs), SO THAT regression risk is bounded.

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

- AC4 (count_claim Finding emission) -- delegated to `build/scripts/validate_marketplace_counts.py` per `.claude/rules/canonical-source-mirror.md`. PR1 detects the claim shape (regex + label map mirror canonical) but emits no Findings; an opt-in `--enforce-counts` flag for single-plugin enforcement is available for future PR2 wiring.
- AC8 (/test Gate 5 wiring) -- follow-up PR. Owner: rjmurillo. Trigger: PR1 ships and skill scaffold proves stable.
- Wave 2 wiki-import detection (Epic #1933 Child 4) once `docs/skill-reference.md` becomes a scan target.
- Auto-fix mode (out of scope for v1; track separately if demand surfaces).
- ADR-051 frontmatter validation (separate concern; `validate_design_review.py` exists).

## Out of Scope

- Auto-fixing orphan refs (skill flags, never rewrites)
- Code-comment scanning (analyzer scope: structured artifacts only)
- Network calls (no remote validation)
- Dead-code detection in source files (separate concern)
