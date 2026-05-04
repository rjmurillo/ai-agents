---
type: requirement
id: REQ-005
title: Reduce PR iteration cost via pre-push validation
status: draft
priority: high
category: developer-experience
epic: shift-left-validation
related:
  - issue: 1884
  - issue: 1885
author: spec-agent
date: 2026-05-03
---

# REQ-005: Reduce PR iteration cost via pre-push validation

## Problem

Agent-authored PRs in this repo burn 10-22 commits and 3-6 review rounds because three classes of
mechanical errors (markdown style violations, manifest count drift, session log placeholders) are
caught in CI/review rather than pre-push. Block these at push time and they cannot reach review.

## User Stories and Requirements

### REQ-005-US1: Block markdown style violations pre-push

**Requirement Statement**

WHEN an agent invokes `git push` AND any file in the changeset matches `*.md`
THE SYSTEM SHALL run markdownlint-cli2 on those files
SO THAT style violations are caught before review rather than after 3-6 commit fix loops.

**Context**

Agent-authored markdown files regularly violate the repo's markdownlint configuration (em-dash
usage, heading hierarchy, bare URLs). These violations are flagged in review, triggering
multi-commit fix loops. The markdownlint-cli2 binary is already available on developer machines
and used in CI. Running it at push time on the changed-file set catches violations before they
reach reviewers.

**Acceptance Criteria**

- [ ] AC-1: WHEN an agent invokes `git push` AND any file in the changeset matches `*.md`
  THE SYSTEM SHALL run markdownlint-cli2 on those files.
- [ ] AC-2: WHEN markdownlint-cli2 reports any violation THE SYSTEM SHALL block the push with
  a non-zero exit code and print each violation with file path, line, rule code, and rule
  description SO THAT the agent can fix without consulting external docs.
- [ ] AC-3: WHEN markdownlint-cli2 binary is not available on PATH THE SYSTEM SHALL print a
  WARN message and allow the push SO THAT a missing tool does not block work on machines without
  the binary.
- [ ] AC-8 (partial): WHEN no `*.md` files are in the changeset THE SYSTEM SHALL exit zero
  immediately without invoking markdownlint-cli2.

**Rationale**

Markdown style violations are purely mechanical. CI already catches them, but at a cost of one
commit per violation batch. Shifting left to push time costs nothing when the changeset has no
markdown files and costs one pre-push subprocess when it does.

**Dependencies**

- markdownlint-cli2 binary on PATH (soft dependency; WARN on absence)
- `git diff --name-only` output available at hook invocation time
- Claude Code PreToolUse hook infrastructure (`hooks.json`, shared lib bootstrap)

---

### REQ-005-US2: Block manifest count drift pre-push

**Requirement Statement**

WHEN an agent invokes `git push` AND any file in the changeset matches
`templates/agents/*.md`, `.claude/skills/*/SKILL.md`, or `.claude/commands/*.md`
THE SYSTEM SHALL count files in each glob, compare the counts to the corresponding fields in
`marketplace.json` and `SEMANTIC_INDEX.yaml`, and block on any disagreement
SO THAT manifest count drift cannot reach CI.

**Context**

Agents adding or removing skills, agents, or commands frequently forget to update
`marketplace.json` and `SEMANTIC_INDEX.yaml`. The counts in those files are projections derived
from the filesystem (per `.claude/rules/templates.md`). CI validates count consistency but after
multiple commits. Deriving counts from the filesystem at push time and comparing to the
projection files makes the inconsistency visible before the first CI run.

**Data model**

| Entity | SoR | Projection |
|--------|-----|------------|
| Agent count | `templates/agents/*.md` | `marketplace.json`, `SEMANTIC_INDEX.yaml` |
| Skill count | `.claude/skills/*/SKILL.md` | `marketplace.json`, `SEMANTIC_INDEX.yaml` |
| Command count | `.claude/commands/*.md` | `marketplace.json`, `SEMANTIC_INDEX.yaml` |

**Acceptance Criteria**

- [ ] AC-4: WHEN an agent invokes `git push` AND any file in the changeset matches
  `templates/agents/*.md`, `.claude/skills/*/SKILL.md`, or `.claude/commands/*.md`
  THE SYSTEM SHALL count files in each glob and compare the counts to the corresponding fields
  in `.claude-plugin/marketplace.json` and `docs/SEMANTIC_INDEX.yaml`.
- [ ] AC-5: WHEN any count comparison from AC-4 disagrees THE SYSTEM SHALL block the push with
  a non-zero exit code and print each disagreement as `<file>:<field> expected <N>, got <M>`
  SO THAT the agent can fix the manifest in one edit.
- [ ] AC-8 (partial): WHEN no manifest-affecting files are in the changeset THE SYSTEM SHALL
  exit zero immediately without invoking count derivation.
- [ ] AC-9: WHEN the count-derivation script runs in isolation
  (`python3 scripts/validation/manifest_counts.py`) THE SYSTEM SHALL print the derived counts
  and exit zero SO THAT debugging count disagreements is possible without re-pushing.

**Rationale**

Count fields are mechanical projections. Their value at push time must equal the filesystem.
A standalone script (`manifest_counts.py`) gives agents a low-friction debug path without
requiring a push attempt.

**Dependencies**

- `marketplace.json` and `SEMANTIC_INDEX.yaml` readable at hook invocation time
- `git diff --name-only` output for change detection
- `scripts/validation/manifest_counts.py` (new, created as part of this spec)

---

### REQ-005-US3: Block session log placeholder values pre-push

**Requirement Statement**

WHEN an agent invokes `git push` AND the changeset contains any `.agents/sessions/*.json` file
THE SYSTEM SHALL parse each session log and check that `schemaVersion` is present and
non-empty, `endingCommit` is present and not the literal string `"pending"`, and
`markdownLintRun.scanned` (if present) lists at least one `.md` file when the changeset
contains any `.md` files,
SO THAT placeholder session logs cannot reach review.

**Context**

Session logs with placeholder values (`endingCommit: "pending"`, empty `schemaVersion`) are
flagged in every PR review. These placeholders indicate an incomplete `session-end` flow. The
fix is always the same three-field edit. A narrow validator at push time catches this class of
error before the log appears in the PR diff.

**Acceptance Criteria**

- [ ] AC-6: WHEN an agent invokes `git push` AND the changeset contains any
  `.agents/sessions/*.json` file THE SYSTEM SHALL parse each session log and check:
  (a) `schemaVersion` is present and non-empty,
  (b) `endingCommit` is present and not the literal string `"pending"`,
  (c) `markdownLintRun.scanned` (if present) lists at least one file ending in `.md` if the
  changeset contains any `.md` files.
- [ ] AC-7: WHEN any session log check from AC-6 fails THE SYSTEM SHALL block the push with a
  non-zero exit code and print each failure as `<session-log-path>:<field> <reason>`
  SO THAT the agent can fix the log in one edit.
- [ ] AC-8 (partial): WHEN no `.agents/sessions/*.json` files are in the changeset THE SYSTEM
  SHALL exit zero immediately.

**Rationale**

Placeholder values are definitively wrong. A narrow three-field check has low false-positive
risk and directly addresses the most common review comment on session log commits.

**Dependencies**

- `.agents/sessions/` directory and JSON session log format (existing)
- `git diff --name-only` output for change detection

---

### REQ-005-CROSS: Shared hook framework (common behaviors)

**Requirement Statement**

WHEN any pre-push hook is invoked
THE SYSTEM SHALL read the changed-file list from `git diff --name-only`, dispatch to the
appropriate validator only when relevant files are present, format output matching existing
hook output patterns, and block with exit code 2 on any violation
SO THAT all three hooks share a consistent behavior contract.

**Context** (CVA summary from PRD)

Common across all three hooks: invoked from PreToolUse on `git push`, run only on changed files
(from `git diff`), produce stdout summary, block with non-zero exit on failure, no auto-fix, no
network. Varies: the validator body, the file globs scoped, and the specific error message
format. Relationship: a thin shared hook framework with three specific validator implementations
behind it (Strategy pattern).

**Acceptance Criteria**

- [ ] AC-8: WHEN no relevant files (no `.md`, no manifest-affecting, no session log) are in the
  changeset THE SYSTEM SHALL exit zero immediately without invoking any subprocess.
- [ ] AC-10: Each new hook MUST have unit tests under `tests/` covering positive case (pass),
  negative case (fail), edge case (empty changeset, missing binary, malformed file). Coverage
  MUST meet the 80% business-logic floor from AGENTS.md.

**Rationale**

A shared framework eliminates duplicate changeset-reading and output-formatting logic across
three hooks, reduces maintenance surface, and ensures consistent behavior under edge cases
(empty diff, hook crash).

**Dependencies**

- Existing `hook_utilities` lib bootstrap pattern (from `invoke_session_log_guard.py`)
- `hooks.json` `Bash(git push*)` matcher (existing, additional hooks appended)

---

## Out of Scope

- FM-3 (PR description staleness): tracked as issue #1885.
- FM-5 (spec-before-code enforcement): governance change, not a mechanical validator.
- Auto-fix of violations.
- Git pre-push hooks (Claude Code PreToolUse only).
- CI workflow changes (CI remains backstop, not primary gate).
- Full-repo remediation of pre-existing violations in unchanged files.

## Deferred

- Bootstrapping git pre-push hooks if human-authored PRs become a source of iteration cost.
  Owner: repo maintainer. Trigger: human-authored PRs start showing same classes of errors.
- Auto-fix mode behind a `--fix` flag if blocking turns out to slow agents more than it helps.
  Owner: implementer post-rollout. Trigger: 4+ weeks of data showing false-positive rate > 5%.

## Open Questions

None remaining. All confirmed during interview documented in
`.agents/specs/interviews/INTERVIEW-1884-pr-iteration-cost.md`.

---

## Amendments (post gap-analysis, pre-mortem, decision-critic)

### Amendment 1: AC-3 exit code (BLOCK finding)

AC-3 must state explicitly: "THE SYSTEM SHALL print a WARN message, exit zero, and allow the
push." Tests must assert exit code 0 on the WARN path.

### Amendment 2: AC-4/AC-5/AC-9 target files (BLOCK finding)

`marketplace.json` has no structured count fields. Counts are embedded in description strings
("24 specialized agent definitions"). `SEMANTIC_INDEX.yaml` has no count fields at all.

Existing validation already handles this: `build/scripts/validate_marketplace_counts.py` parses
description strings via regex and uses `templates/marketplace-counters.yaml` for config. It has
a `--fix` mode.

**Resolution**: AC-4/AC-5/AC-9 are amended:

- Remove `SEMANTIC_INDEX.yaml` from scope entirely.
- Remove `scripts/validation/manifest_counts.py` (does not need to be created).
- Hook calls existing `build/scripts/validate_marketplace_counts.py` (or imports its
  `validate_known_marketplaces()` function) to check marketplace.json description counts.
- AC-9 becomes: "WHEN the existing count-validation script runs in isolation
  (`python3 build/scripts/validate_marketplace_counts.py`) THE SYSTEM SHALL print derived
  counts and mismatches, and `--fix` auto-corrects the descriptions."
- This is already true. The hook simply wires the existing script to pre-push.

### Amendment 3: AC-6 markdownLintRun schema (BLOCK finding)

Real session log schema has `markdownLintRun: {Complete: bool, Evidence: str}`, not
`.scanned: list[str]`. AC-6(c) is restated:

- Check `markdownLintRun.Complete` is `true` (not `false` or absent).
- Check `markdownLintRun.Evidence` is a non-empty string (not blank or placeholder).
- Drop the `.scanned` list check. The temporal ordering issue (session log evidence predates
  final diff) makes a file-level accuracy check unsound. The validator catches placeholder
  and incomplete evidence, not semantic accuracy.

### Amendment 4: Shared hook framework scope (MAJOR finding)

The shared `push_guard_base.py` is NET-NEW code. Existing PreToolUse hooks
(`invoke_session_log_guard.py`, `invoke_skill_first_guard.py`) are NOT refactored to use it.
Migration of existing hooks is deferred to a follow-up if the pattern proves stable.

### Amendment 5: Success metric (decision-critic REVISE)

The original target "reduce 10-15 rounds to 1-2" is revised to:
"reduce mechanical-error review iterations by at least 50%." FM-3 (PR description staleness,
#1885) remains a surviving cause of iteration cost and is marked as a **blocking follow-up**,
not an optional enhancement.

### Amendment 6: Hook matcher pattern (pre-mortem mitigation)

The exact `hooks.json` matcher must cover all `git push` invocations the agent uses. The
existing pattern `Bash(git push*)` is confirmed as the matcher. A negative test must verify
that no bypass via `--no-verify` or non-standard syntax is available through the Claude Code
PreToolUse hook system (Claude Code hooks are runtime-enforced and cannot be skipped by the
agent).

### Amendment 7: markdownlint-cli2 version pinning (pre-mortem mitigation)

The markdownlint hook should log the binary version on each run for diagnostic purposes. If
version divergence between local and CI causes false positives post-rollout, add a version
check as a fast-follow. Not in initial scope.
