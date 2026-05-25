---
type: requirement
id: REQ-005
title: Reduce PR iteration cost via pre-push validation
status: draft
priority: P1
category: developer-experience
epic: shift-left-validation
related:
  - DESIGN-005
  - issue: 1884
  - issue: 1885
author: spec-agent
created: 2026-05-03
updated: 2026-05-04
---

# REQ-005: Reduce PR iteration cost via pre-push validation

## Problem

Agent-authored PRs in this repo burn 10 to 22 commits and 3 to 6 review rounds because three classes of mechanical errors (markdown style violations, manifest count drift, session log placeholders) are caught in CI or review rather than at push time. Block these at push time and they cannot reach review.

Success metric: reduce mechanical-error review iterations by at least 50% measured against the 14-day RCA window. FM-3 (PR description staleness, tracked as #1885) remains a surviving cause of iteration cost and is a blocking follow-up to this work.

## User Stories and Requirements

### REQ-005-US1: Block markdown style violations pre-push

**Requirement Statement**

WHEN an agent invokes `git push` AND any file in the changeset matches `*.md`
THE SYSTEM SHALL run markdownlint-cli2 on those files
SO THAT style violations are caught before review rather than after 3 to 6 commit fix loops.

**Context**

Agent-authored markdown files regularly violate the repo's markdownlint configuration (em-dash usage, MD040 missing language identifiers, MD041 first-line heading). These violations are flagged in review, triggering multi-commit fix loops. The markdownlint-cli2 binary is already available on developer machines and used in CI. Running it at push time on the changed-file set catches violations before they reach reviewers.

**Acceptance Criteria**

- [ ] AC-1: WHEN an agent invokes `git push` AND any file in the changeset matches `*.md` THE SYSTEM SHALL run markdownlint-cli2 on those files.
- [ ] AC-2: WHEN markdownlint-cli2 reports any violation THE SYSTEM SHALL block the push with a non-zero exit code and print each violation with file path, line, rule code, and rule description SO THAT the agent can fix without consulting external docs.
- [ ] AC-3: WHEN markdownlint-cli2 binary is not available on PATH THE SYSTEM SHALL print a WARN message to stderr, exit zero, and allow the push SO THAT a missing tool does not block work on machines without the binary. Tests MUST assert exit code zero on this path.
- [ ] AC-3a: WHEN the markdownlint hook runs THE SYSTEM SHALL log the markdownlint-cli2 binary version to stderr for diagnostic purposes SO THAT version divergence between local and CI is observable post-rollout.
- [ ] AC-8 (partial): WHEN no `*.md` files are in the changeset THE SYSTEM SHALL exit zero immediately without invoking markdownlint-cli2.

**Rationale**

Markdown style violations are purely mechanical. CI already catches them, but at a cost of one commit per violation batch. Shifting left to push time costs nothing when the changeset has no markdown files and costs one pre-push subprocess when it does.

**Dependencies**

- markdownlint-cli2 binary on PATH (soft dependency; WARN on absence per AC-3)
- `git diff --name-only @{push}..HEAD` (with `origin/main...HEAD` fallback) at hook invocation time
- Claude Code PreToolUse hook infrastructure (`hooks.json`, shared lib bootstrap)

---

### REQ-005-US2: Block marketplace count drift pre-push

**Requirement Statement**

WHEN an agent invokes `git push` AND any file in the changeset matches `templates/agents/*.md`, `.claude/skills/*/SKILL.md`, `.claude/commands/*.md`, or `.claude-plugin/marketplace.json`
THE SYSTEM SHALL invoke the existing `build/scripts/validate_marketplace_counts.py` validator (function `validate_known_marketplaces`) and block on any reported count mismatch
SO THAT manifest count drift cannot reach CI.

**Context**

Agents adding or removing skills, agents, or commands frequently forget to update the embedded counts in `.claude-plugin/marketplace.json` plugin descriptions. The counts live as numbers in description strings (for example, "24 specialized agent definitions"). The existing CI workflow `validate-marketplace-counts.yml` runs `build/scripts/validate_marketplace_counts.py`, which parses the descriptions via regex and compares against filesystem-derived counts using `templates/marketplace-counters.yaml`. CI catches drift, but only after multiple commits. This requirement wires the same validator to a pre-push hook so the inconsistency is visible before the first CI run.

`docs/SEMANTIC_INDEX.yaml` is NOT in scope: it is a semantic search index, not a count manifest, and has no agent/skill/command count fields.

**Data model**

| Entity | SoR | Projection |
|--------|-----|------------|
| Agent count | Files matched by `templates/marketplace-counters.yaml` strategies | Number embedded in `.claude-plugin/marketplace.json` plugin description strings |
| Skill count | Same | Same |
| Command count | Same | Same |
| Hook count | Same | Same |

**Acceptance Criteria**

- [ ] AC-4: WHEN an agent invokes `git push` AND any file in the changeset matches `templates/agents/*.md`, `.claude/skills/*/SKILL.md`, `.claude/commands/*.md`, or `.claude-plugin/marketplace.json` THE SYSTEM SHALL invoke `build/scripts/validate_marketplace_counts.validate_known_marketplaces(repo_root=project_dir)` and capture its return code and stdout.
- [ ] AC-5: WHEN the validator returns non-zero (mismatch or config error) THE SYSTEM SHALL block the push, print the captured stdout as violation lines, and append the hint "Run `python3 build/scripts/validate_marketplace_counts.py --fix` to auto-correct" SO THAT the agent can fix the manifest in one edit.
- [ ] AC-8 (partial): WHEN no manifest-affecting files are in the changeset THE SYSTEM SHALL exit zero immediately without invoking the validator.
- [ ] AC-9: The existing `build/scripts/validate_marketplace_counts.py` is the canonical count validator. Running it directly (`python3 build/scripts/validate_marketplace_counts.py`) prints derived counts and any mismatches; `--fix` auto-corrects the descriptions. No new derivation script is created by this spec.

**Rationale**

Counts are mechanical projections. Their value at push time must equal the filesystem. The validator already exists, is tested, and is wired to CI. The pre-push hook is a thin adapter that calls the same code and translates exit codes.

**Dependencies**

- `build/scripts/validate_marketplace_counts.py` (existing)
- `templates/marketplace-counters.yaml` (existing config)
- `git diff --name-only @{push}..HEAD` for change detection

---

### REQ-005-US3: Block session log placeholder values pre-push

**Requirement Statement**

WHEN an agent invokes `git push` AND the changeset contains any `.agents/sessions/*.json` file
THE SYSTEM SHALL parse each session log and check that `schemaVersion` is present and non-empty, that `endingCommit` is present and not the literal string `"pending"`, and that `markdownLintRun.Complete` is `true` with `markdownLintRun.Evidence` non-empty
SO THAT placeholder session logs cannot reach review.

**Context**

Session logs with placeholder values (`endingCommit: "pending"`, missing `schemaVersion`, empty or placeholder `markdownLintRun.Evidence`) are flagged in every PR review. These placeholders indicate an incomplete `session-end` flow. The fix is always the same field-level edit. A narrow validator at push time catches this class of error before the log appears in the PR diff.

The real session log schema is `markdownLintRun: {Complete: bool, Evidence: str}`. There is no `.scanned: list[str]` field. The validator checks structural completeness (placeholder detection), not semantic accuracy of the evidence string against the diff (semantic accuracy is intractable: session log evidence may predate the final diff).

**Acceptance Criteria**

- [ ] AC-6: WHEN an agent invokes `git push` AND the changeset contains any `.agents/sessions/*.json` file THE SYSTEM SHALL parse each session log and check:
  - (a) `schemaVersion` is present and non-empty.
  - (b) `endingCommit` is present and not the literal string `"pending"`.
  - (c) `markdownLintRun.Complete` is `true` (not `false` or absent) AND `markdownLintRun.Evidence` is a non-empty, non-placeholder string.
- [ ] AC-7: WHEN any session log check from AC-6 fails THE SYSTEM SHALL block the push with a non-zero exit code and print each failure as `<session-log-path>:<field> <reason>` SO THAT the agent can fix the log in one edit.
- [ ] AC-8 (partial): WHEN no `.agents/sessions/*.json` files are in the changeset THE SYSTEM SHALL exit zero immediately.

**Rationale**

Placeholder values are definitively wrong. A narrow field-level check has low false-positive risk and directly addresses the most common review comment on session log commits.

**Dependencies**

- `.agents/sessions/` directory and JSON session log format (existing)
- `git diff --name-only @{push}..HEAD` for change detection

---

### REQ-005-CROSS: Shared hook framework (common behaviors)

**Requirement Statement**

WHEN any pre-push hook in this spec is invoked
THE SYSTEM SHALL read the changed-file list using `git diff --name-only @{push}..HEAD` (with `origin/main...HEAD` fallback when `@{push}` is unset), dispatch to the appropriate validator only when relevant files are present, format output matching existing PreToolUse hook patterns, and block with exit code 2 on any violation
SO THAT all three hooks share a consistent behavior contract.

**Context**

Common across all three hooks: invoked from PreToolUse on the matcher `Bash(git push*)`, run only on changed files, produce stdout summary, block with exit code 2 on failure, fail-open on infrastructure errors, no auto-fix, no network access. Varies: the validator body, the file globs scoped, and the specific error message format. Relationship: a thin shared hook framework with three specific validator implementations behind it (Strategy pattern).

The shared framework `push_guard_base.py` is net-new code. Existing PreToolUse hooks (`invoke_session_log_guard.py`, `invoke_skill_first_guard.py`) are NOT refactored to use it. Migration of existing hooks is deferred to a follow-up if the pattern proves stable.

**Acceptance Criteria**

- [ ] AC-8: WHEN no relevant files (no `.md`, no manifest-affecting, no session log) are in the changeset THE SYSTEM SHALL exit zero immediately without invoking any subprocess.
- [ ] AC-10: Each new hook MUST have unit tests under `tests/hooks/` covering positive case (pass), negative case (fail), and edge cases (empty changeset, missing binary for AC-3, malformed file). Coverage MUST meet the 80% business-logic floor from AGENTS.md.
- [ ] AC-11: Hook registration MUST use the matcher `Bash(git push*)` in `hooks.json`. A negative test MUST confirm the Claude Code PreToolUse system has no agent-invokable bypass (the hook is runtime-enforced; `--no-verify` does not apply to PreToolUse).

**Rationale**

A shared framework eliminates duplicate changeset-reading and output-formatting logic across three hooks, reduces maintenance surface, and ensures consistent behavior under edge cases (empty diff, hook crash).

**Dependencies**

- Existing `hook_utilities` lib bootstrap pattern (mirrored from `invoke_session_log_guard.py`)
- `hooks.json` `Bash(git push*)` matcher (existing; additional hook entries appended after current ones)

---

## Out of Scope

- FM-3 (PR description staleness): tracked as issue #1885 (blocking follow-up).
- FM-5 (spec-before-code enforcement): governance change, not a mechanical validator.
- Auto-fix of violations.
- Git pre-push hooks (Claude Code PreToolUse only).
- CI workflow changes (CI remains backstop, not primary gate).
- Full-repo remediation of pre-existing violations in unchanged files.
- Refactor of existing PreToolUse hooks to use `push_guard_base.py`.
- markdownlint-cli2 version pinning (only logged for diagnostics; pin if false positives appear).

## Deferred

- Bootstrapping git pre-push hooks if human-authored PRs become a source of iteration cost. Owner: repo maintainer. Trigger: human-authored PRs start showing same classes of errors.
- Auto-fix mode behind a `--fix` flag if blocking turns out to slow agents more than it helps. Owner: implementer post-rollout. Trigger: 4+ weeks of data showing false-positive rate above 5%.
- Migration of existing PreToolUse hooks to share `push_guard_base.py`. Owner: implementer. Trigger: framework proves stable across the three new hooks.

## Open Questions

None. All scope questions resolved during the interview at `.agents/specs/interviews/INTERVIEW-1884-pr-iteration-cost.md` and during gap-analysis, pre-mortem, and decision-critic review.
