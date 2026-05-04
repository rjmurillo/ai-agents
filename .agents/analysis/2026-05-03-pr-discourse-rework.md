# PR Discourse Rework Analysis: 2026-04-19 to 2026-05-04

## Problem Framing

PRs in this repo routinely require 10-22 commits and 3-6 review rounds before merge. The discourse
between first push and merge is dominated by style violations, CI failures from preventable
contract breaks, and scope-creep caught in review rather than pre-flight. This investigation
quantifies where the rework comes from and ranks interventions by iteration cost.

## Scope

- Window: 2026-04-19 to 2026-05-04 (closed PRs)
- Total closed PRs: 94 (excluding renovate[bot])
- Deep-dived: 9 PRs with highest commit × days score
- Human review comments analyzed across: #1790, #1796, #1766, #1721, #1819, #1851, #1873

---

## Evidence

### PR Metrics Summary

| PR | Commits | Human review comments | CI-fail commits | Days open | Description |
|----|---------|----------------------|-----------------|-----------|-------------|
| #1873 | 59 | 20 (top-level) | 2 | 1 | feat(evals): eval harness + ADR-058 |
| #1790 | 22 | 72 (human total) | 12 | 6 | refactor: relocate Principle 6 autonomy |
| #1766 | 15 | 26 (top-level) | 10 | 3 | feat: negotiation agent + skills |
| #1819 | 120 | 3 | 0 | 2 | feat(spec+plan+adr): REQ-003 (656 files) |
| #1851 | 14 | 14 | 0 | 1 | fix(security-scan): delegate CWE-22 |
| #1812 | 14 | 0 | 0 | 2 | feat(skills): requirements-interview |
| #1796 | 9 | 11 | 4 | 2 | feat(skills): stuck-detection |
| #1721 | 3 | 22 | 0 | 6 | feat(orchestrator): Session Capture Protocol |
| #1810 | 9 | 0 | 0 | 2 | feat(skills): panning-for-gold port |

### CI Failure Pattern (what checks fail per commit)

From tracing all commits in PRs #1790, #1796, and #1766:

- `Validate PR` fails repeatedly, caused by: PR description not matching diff, missing issue
  linkage keywords, QA report absent for code-touching PRs. Fires on commits 1, 3, 5, 8...
  meaning the fix loop repeats 3-4 times per PR before the description settles.
- `Run Python Tests` fails 3 commits in a row on #1790 (commits 15-17): tests written after
  the fact, each attempt tightens the regex one notch.
- `Validate Marketplace Counts` fires 6 of 15 commits on #1766: agent count in marketplace
  JSON drifts from actual file count every time a new file is added.
- `Respond to @rjmurillo-bot` fails persistently across PRs: automation artifact, not
  human-driven. Skipping this in the cost analysis.

### Review Comment Taxonomy (across all deep-dived PRs)

Categories with exemplar PRs and comment counts:

**A. Em-dash / style violations**: 25+ comments across #1790, #1766, #1721, #1873, #1851
- The project bans em/en dashes in Markdown. The agent that authors content (rjmurillo-bot)
  uses them anyway. Each new file gets flagged. These are always caught by Copilot in review,
  never pre-flight.
- Examples: #1790 (16 em-dash fix commits), #1766 (multiple files flagged on 3 separate review
  rounds), #1873 (em-dash sweep took 5 commits across INTERVIEW/PLAN/REQ/ADR/README).

**B. Marketplace / count contract breaks**: 15+ comments across #1766, #1790, #1796
- `.claude-plugin/marketplace.json` plugin description strings embed agent/skill/command/hook
  counts as numbers in natural-language descriptions. The CI workflow `validate-marketplace-counts.yml`
  runs `build/scripts/validate_marketplace_counts.py`, which parses the descriptions via regex
  and compares against filesystem-derived counts using `templates/marketplace-counters.yaml`.
- #1766: 6 commits fixing "Validate Marketplace Counts" failures. The counts in the
  marketplace plugin descriptions drifted from the filesystem.
- This is a derived-data problem: the source of truth is the files, the counts are
  hand-maintained in description prose, and the agent does not audit the descriptions before
  push.
- Note: `docs/SEMANTIC_INDEX.yaml` is sometimes mentioned in the same context but is a
  semantic search index (with fields like `total_docs_indexed`), not an agent/skill/command
  count manifest.

**C. PR description does not match diff**: 8+ fires across #1796, #1790
- The `Validate PR` check compares the PR description against actual changed files. When the
  scope evolves during implementation, the description becomes stale.
- #1796: Commit 1 immediately fails "Description matches diff: FAIL" because the PR was
  opened before implementation was complete.
- #1790: 8 commits fail "Validate PR" as the scope shifts from adding a new governance file
  to centralizing it into AGENTS.md to renaming it.

**D. Session log / protocol compliance failures**: 10+ comments across #1796, #1766, #1721
- Every PR is expected to include a `schemaVersion` field in session JSON, an `endingCommit`
  SHA (not "pending"), and complete `markdownLintRun` evidence.
- #1796: Copilot flags missing schemaVersion, "pending" endingCommit, incorrect
  markdownLintRun evidence (claims "no markdown changed" when .claude/skills/*.md was added).
- #1721: Missing schemaVersion flagged. Multiple "pending" placeholders not resolved.
- #1766: "endingCommit is pending" even though this field must be a real SHA.
- Pattern: agents fill in session logs with placeholder values and never replace them.

**E. Generated files out of sync with templates**: 8+ comments across #1766, #1790
- The build system generates `src/claude/*.md`, `src/vs-code-agents/*.md`,
  `src/copilot-cli/*.md` from `templates/agents/*.md`. When a template changes, all three
  targets must be regenerated.
- #1766: Copilot flags that `src/claude/negotiation.md` is missing while the catalog claims
  Claude is a supported platform. Fix took 3 commits.
- #1790: After renaming "Principle 6" to "Autonomy Guardrail", generated files still
  contained the old name. Tests catch this but they were written mid-PR.

**F. Scope executed before design confirmed**: high commit counts on #1873, #1819
- #1873 (59 commits, 9221 additions): The entire eval harness was built during the PR.
  Spec/plan/test/implementation all evolved in the same branch. Copilot and rjmurillo found
  spec-to-implementation mismatches (AC-10 contingency not implemented, RecommendationLiteral
  missing a variant, module docstring contradicting actual behavior) because there was no
  stable spec before coding started.
- #1819 (120 commits, 656 files): Multi-tool artifact build: spec+plan+ADR in one PR. The
  commit log shows spec iteration (rounds 3, 4, 5) happening alongside implementation.

**G. Copilot re-raising already-declined comments**: 5+ instances in #1796, #1790
- #1796: rjmurillo explicitly declines a comment (with evidence: "project targets Python 3.14,
  `datetime.UTC` required by ruff"). Same or similar comment reappears from Copilot on the
  next review round.
- This inflates comment counts without producing fixes. Not a root-cause failure mode for
  iteration, but visible noise.

---

## Findings

**True (verified):**

1. Em-dash violations are the single most common review comment across all high-discourse PRs.
   They appear in generated content (agent templates, skills, specs, ADRs). The agent that
   generates content does not run the style linter pre-push.

2. Marketplace count drift causes 30-40% of CI failures in content-adding PRs. Counts are
   embedded in `.claude-plugin/marketplace.json` plugin description prose ("24 specialized
   agent definitions"). They are hand-maintained and drift when files are added or removed.
   The existing CI validator parses descriptions via regex, but only after multiple commits
   have already failed.

3. Session logs are filled with placeholders ("pending", missing schemaVersion) and committed
   without resolution. This triggers Copilot review comments and sometimes CI validation.

4. PRs that run spec-design-implement in the same branch (monolithic PRs like #1873, #1819)
   have 3-10x the commit counts of PRs with a confirmed design upfront. The commit log reveals
   spec-to-impl mismatches found only after coding.

5. "Validate PR" fires on commit 1 for PRs opened before implementation is complete (#1796,
   some #1790 commits). This is a known workflow anti-pattern.

**Unknown:**

- Whether the Copilot bot reads declined comments and deliberately re-raises them, or if
  these are separate independent observations from separate review passes.
- Whether the "Run retrospective agent" CI failure on merged PRs (#1790, #1796, #1766, #1873)
  is a flaky check or a systematic gate that was never green.

---

## Hypotheses (ranked by likelihood)

1. **Agents do not run the style linter on generated content before push** (HIGH). Em-dash
   violations are mechanically preventable by running markdownlint pre-push. If the
   pre-commit hook or a pre-push script ran markdownlint on all .md files in the changeset,
   this class would be zero.

2. **Marketplace description counts have no pre-push gate** (HIGH). The numbers embedded in
   `.claude-plugin/marketplace.json` plugin descriptions ("24 specialized agent definitions")
   drift whenever files are added or removed. The fix loop is: fail CI, run
   `build/scripts/validate_marketplace_counts.py --fix`, repeat. The existing validator runs
   in CI but not pre-push; wiring it to a pre-push hook closes the loop locally.

3. **Spec-before-code discipline is inconsistently enforced** (HIGH). The session gates say
   to gate on issues with confirmed spec/plan artifacts. PRs #1873 and #1819 show the spec
   evolving in the PR itself. The /spec and /plan lifecycle commands exist but their outputs
   are not required to exist and be stable before a /build PR is opened.

4. **Session log placeholders are not caught pre-flight** (MEDIUM). The session-end skill
   exists but is not enforced as a hard gate before the PR is opened. Placeholder values
   pass the schema validator because they are optional, or the validator is not run.

5. **PR description is written once and not updated as scope evolves** (MEDIUM). The
   Validate PR check compares description to diff. Descriptions are stale by the time CI
   runs. A reminder/validator could be run pre-push to flag description-diff mismatch.

---

## Root Cause Analysis (Five Whys: em-dash cluster)

1. **Why do PRs have 5-20 em-dash fix commits?** Copilot flags em-dashes in review.
2. **Why are they in review?** Pre-push linting does not cover all .md files in changeset.
3. **Why does pre-push linting miss them?** `.markdownlint-cli2.yaml` exists but the
   pre-commit hook scope is not verified to cover skill, template, spec, and ADR files.
4. **Why is the scope not verified?** No test pins the exact set of file patterns that
   markdownlint runs against, so drift in the config is not caught.
5. **Root cause:** markdownlint pre-push is not wired to the same glob the Copilot review
   applies. The config exists; the enforcement gap is the hook invocation scope.

---

## Failure Mode Taxonomy (Ranked by Total Iteration Cost)

Metric: (review comments + fix commits) × PRs affected.

### FM-1: Style violations in generated/authored content (em-dash, MD040, markdown tables)
- PRs affected: #1873, #1790, #1766, #1721, #1851 (5+ PRs, 40+ fix commits)
- Root cause: pre-push markdownlint does not cover all .md files authored by agents
- Iteration cost: HIGH (appears in every substantial content PR)

### FM-2: Marketplace description-string count drift (.claude-plugin/marketplace.json)
- PRs affected: #1766, #1790, #1796 (3 PRs, 20+ fix commits, 6 CI failure loops on #1766)
- Root cause: counts embedded in plugin description prose are hand-maintained; the existing
  validator runs in CI but not pre-push
- Iteration cost: HIGH

### FM-3: PR description stale vs diff (Validate PR fails on commit 1-3)
- PRs affected: #1796, #1790, and likely most code-touching PRs opened before complete
- Root cause: PR opened before implementation complete; description not updated as scope evolves
- Iteration cost: MEDIUM-HIGH

### FM-4: Session log placeholder values (schemaVersion, endingCommit, markdownLintRun)
- PRs affected: #1796, #1766, #1721, and likely all bot-authored PRs
- Root cause: session-end skill fills placeholders but no pre-push validator enforces them
- Iteration cost: MEDIUM (1-3 comments per PR, easy to miss)

### FM-5: Spec-before-code not enforced (monolithic PRs with in-branch spec evolution)
- PRs affected: #1873 (59 commits), #1819 (120 commits)
- Root cause: /spec and /plan outputs are not required artifacts before /build PR opens
- Iteration cost: HIGH (absolute commit count, but fewer PRs)

---

## Recommendations

### R-1 (Highest leverage): Fix markdownlint pre-push scope
- File: `.claude/hooks/PreToolUse/` or `.pre-commit-config.yaml` / the CI markdownlint step
- Change: Ensure markdownlint runs on `**/*.md` including `templates/`, `.agents/`, `.claude/skills/`,
  `evals/`, `wiki/`, `docs/`, `src/` before the Bash tool triggers a push.
- This eliminates FM-1 entirely. 40+ fix commits across 5 PRs in 14 days.
- Reference: `.claude/rules/code-quality.md` style self-review already calls this out under
  "No commented-out code / dead branches": add a markdownlint enforcement clause.

### R-2 (High leverage): Wire existing marketplace count validator to pre-push
- File: new pre-push hook under `.claude/hooks/PreToolUse/`
- Change: Add a PreToolUse hook that imports
  `build/scripts/validate_marketplace_counts.validate_known_marketplaces` and blocks the push
  on non-zero return. The validator already exists, runs in CI, parses the description-string
  counts, and supports a `--fix` mode. The new hook simply moves the gate left.
- This eliminates FM-2. 20+ fix commits across 3 PRs.
- Reference: `.agents/architecture/ADR-006-thin-workflows-testable-modules.md`: the count
  derivation logic already lives in a testable Python module.

### R-3 (High leverage): Add pre-push session-log validator
- File: `.claude/skills/session-end/` SKILL.md or the pre-push hook
- Change: Before a PR-push Bash command executes, run a fast validator that:
  1. Checks all `.agents/sessions/*.json` files modified in the branch have `schemaVersion`.
  2. Checks `endingCommit` is not "pending".
  3. Checks `markdownLintRun` evidence is accurate (matches files in diff).
  Fail with a clear message rather than letting Copilot catch it in review.
- This eliminates FM-4. 10+ comments across 3 PRs.
- Reference: `.agents/SESSION-PROTOCOL.md` already documents the required fields. The
  validator just needs to enforce them at the boundary.

---

## Open Questions

1. Is the `Run retrospective agent` CI failure on merged PRs (#1790, #1796, #1766, #1873)
   a systemic infrastructure issue or a real gate? If it always fails, it is noise. If it
   intermittently fails, it is a flaky gate producing false urgency.

2. FM-5 (spec-before-code): Is the intent that /spec and /plan artifacts must be merged to
   main before /build PRs open? Or is same-branch spec+impl acceptable for spike work? The
   current rules are ambiguous. ADR-058 documents the eval spike was intentionally
   exploratory, but the commit count (59) and review-comment count (140, mostly bot) still
   represent real waste.

3. The `Validate PR` check fails on "Description matches diff" but does not output what
   specifically mismatches. Making this failure message specific (which files are uncovered)
   would reduce the fix-resubmit loop from 3 rounds to 1.

---

## Confidence Level

HIGH for FM-1 through FM-4: direct evidence from commit messages, CI failure names, and
review comment text. LOW-MEDIUM for FM-5: limited to 2 PRs; the spike pattern may be
intentional for exploratory work.
