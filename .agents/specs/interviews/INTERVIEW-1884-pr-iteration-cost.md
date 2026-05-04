---
type: interview
issue: 1884
related:
  - REQ-005
  - DESIGN-005
  - TASK-005
  - issue: 1885
slug: pr-iteration-cost
status: historical
created: 2026-05-03
updated: 2026-05-04
---

# Interview: Reduce PR review iteration cost

> **Status: historical transcript.** This file captures the requirements interview as it
> happened on 2026-05-03. After the interview, gap analysis, pre-mortem, and decision-critic
> review surfaced four BLOCK findings and a REVISE verdict. The final scope and acceptance
> criteria live in `REQ-005-pr-iteration-cost.md`. Where this transcript and REQ-005 disagree,
> REQ-005 wins. Notable post-interview changes:
>
> - `docs/SEMANTIC_INDEX.yaml` removed from scope (it has no count fields; it is a semantic
>   search index).
> - `scripts/validation/manifest_counts.py` not created. The existing
>   `build/scripts/validate_marketplace_counts.py` is the canonical validator and is wired to
>   the hook.
> - Session log schema confirmed as `markdownLintRun: {Complete: bool, Evidence: str}`. There
>   is no `.scanned: list[str]` field; the validator checks `Complete`/`Evidence`, not
>   `.scanned`.
> - Success metric revised to "50% reduction in mechanical-error iterations." FM-3 (#1885) is
>   a blocking follow-up, not an optional enhancement.

## Problem (confirmed)

Agent-authored PRs in this repo burn 10-22 commits and 3-6 review rounds because five classes of mechanical errors are caught in CI/review rather than pre-push. The fix is to shift validation left so these classes are impossible to push.

## Branch walk

### 1. User stories

- **US-1: Block markdown style violations pre-push.** CONFIRMED. PreToolUse hook runs markdownlint on all `.md` files in changeset before `git push`.
- **US-2: Block manifest count drift pre-push.** CONFIRMED. Pre-push validator derives counts from filesystem and compares to `marketplace.json`, `SEMANTIC_INDEX.yaml`, `agent-catalog.md`.
- **US-3: Block session log with placeholder values pre-push.** CONFIRMED. Validator rejects logs missing `schemaVersion`, with `endingCommit: "pending"`, or with inaccurate `markdownLintRun` evidence.
- **US-4: PR description staleness.** OUT_OF_SCOPE for #1884. Tracked as #1885.
- **US-5: Spec-before-code enforcement (FM-5).** OUT_OF_SCOPE. Governance change, not a mechanical validator. Defer to follow-up issue.

### 2. Data model

- No new entities. All changes operate on existing files.
- **Counts become derived data.** Filesystem (under `templates/agents/`, `.claude/skills/`, `.claude/commands/`) is SoR. `marketplace.json` and `SEMANTIC_INDEX.yaml` count fields are projections.
- **Q2 CONFIRMED**: Agent count from `templates/agents/*.md` (per `.claude/rules/templates.md` SoR rule). Skill count from `.claude/skills/*/SKILL.md`. Command count from `.claude/commands/*.md`. Generated files in `src/claude/` are not counted.

### 3. Integrations

- **markdownlint-cli2**: subprocess from hook. Available as binary on dev machines; verify on hook startup.
- **git diff**: source of changeset file list.
- **Existing `scripts/validation/pre_pr.py`**: extend, do not duplicate.
- **Q3 CONFIRMED**: Claude Code PreToolUse hooks only. Rationale: 100% of high-iteration PRs in RCA window were agent-authored. Git pre-push hook is not auto-installed and is out of scope. Existing `invoke_session_log_guard.py` is the proven template.

### 4. Failure modes

- **markdownlint binary missing**: WARN, allow push. Tooling-gap, not a code problem.
- **Large changeset**: limit to changed files only (from `git diff --name-only`). Timeout 60s.
- **Manifest count script bug**: unit tests + CI backstop. Disagreement = bug, not policy violation.
- **Session log validator false positive**: narrow scope (3 fields), low risk.
- **Pre-existing violations in unchanged files**: validators run on changeset only, not full repo.
- **Q4 CONFIRMED**: Block on violation, do not auto-fix. Rationale: auto-fix mutates files without explicit agent decision; violates "no side effects beyond function name." Block + clear error message + agent fixes.

### 5. Security

- No secrets, no PII, no network.
- Subprocesses use argument lists (not shell strings), per existing `pre_pr.py` pattern. CWE-78 mitigated by construction.
- File paths from `git diff` are read-only inputs. CWE-22 not applicable (no writes).

### 6. Observability

- **Q5 CONFIRMED**: Stdout only. No structured log file. Trend analysis via CI history if needed later.
- Each hook prints: check name, files checked count, pass/fail, specific violations on fail. Match existing hook output pattern.

### 7. Scope boundaries

**In scope:**

- FM-1: PreToolUse hook for markdownlint on changed `.md` files.
- FM-2: Python script that derives manifest counts; pre-push hook validates `marketplace.json` and `SEMANTIC_INDEX.yaml` match filesystem.
- FM-4: PreToolUse hook for session log field validation.

**Out of scope:**

- FM-3 (PR description staleness): tracked as #1885.
- FM-5 (spec-before-code): governance, separate issue if pursued.
- Auto-fix.
- Git pre-push hook bootstrapping.
- CI workflow changes (CI is backstop, not primary gate).
- Full-repo remediation of existing violations.

**Deferred:**

- Auto-installation of git hooks. If human pushes become a problem, revisit.

### Q1 CONFIRMED: FM-5 deferred. FM-3 → #1885

## Verification

- [x] Every branch has a recorded decision.
- [x] Every requirement is testable as pass/fail.
- [x] Every "we will figure it out later" promoted to deferred or out-of-scope.
- [x] Problem restatement and acceptance criteria confirmed by user.

## Structured PRD

### Problem

Agent-authored PRs in this repo burn 10-22 commits because three classes of mechanical errors (em-dash style violations, manifest count drift, session log placeholders) are caught in CI/review rather than pre-push. Block these at push time and they cannot reach review.

### User stories

- **US-1**: As a Claude Code agent pushing markdown content, I want the push blocked if any changed `.md` file violates markdownlint rules, so reviewers do not waste rounds on mechanical fixes.
- **US-2**: As a Claude Code agent adding or removing skills/agents/commands, I want the push blocked if `marketplace.json` or `SEMANTIC_INDEX.yaml` counts disagree with the filesystem, so CI does not run a 3-6 commit count-fix loop.
- **US-3**: As a Claude Code agent ending a session, I want the push blocked if my session log has placeholder values (`endingCommit: "pending"`, missing `schemaVersion`, inaccurate `markdownLintRun`), so reviewers do not flag the same issues every PR.

### Data model

| Entity | Identity | SoR | Projection used |
|--------|----------|-----|-----------------|
| Markdown content | File path under repo | File on disk | n/a (validated in place) |
| Agent count | Count of `templates/agents/*.md` | Filesystem | `marketplace.json`, `SEMANTIC_INDEX.yaml` |
| Skill count | Count of `.claude/skills/*/SKILL.md` | Filesystem | `marketplace.json`, `SEMANTIC_INDEX.yaml` |
| Command count | Count of `.claude/commands/*.md` | Filesystem | `marketplace.json`, `SEMANTIC_INDEX.yaml` |
| Session log | `.agents/sessions/YYYY-MM-DD-session-N.json` | File on disk | n/a |

Invariants:

- Counts in projections MUST equal filesystem counts at push time.
- Session log fields `schemaVersion` (present), `endingCommit` (≠ "pending", looks like SHA), `markdownLintRun.scanned` (matches diff) MUST hold at push time.

### Integrations

| System | Direction | Failure mode | Idempotency |
|--------|-----------|--------------|-------------|
| markdownlint-cli2 | subprocess out | binary missing → WARN; timeout → fail closed | read-only |
| git diff --name-only | subprocess out | empty diff → no-op | read-only |
| File read of `marketplace.json`, `SEMANTIC_INDEX.yaml`, session log | local I/O | parse error → fail with specific error | read-only |

### Failure modes

- **markdownlint binary missing**: WARN, allow push.
- **Subprocess timeout (60s)**: fail closed with timeout message.
- **Session log JSON malformed**: fail with parse error and pointer to offending file.
- **Manifest JSON/YAML malformed**: fail with parse error.
- **Hook itself crashes**: Claude Code surfaces stack trace; agent fixes and retries.

No retries (read-only, deterministic). No replay. No schema evolution beyond what session protocol already defines.

### Security

- Subprocess calls use argument lists, not shell strings. CWE-78 mitigated.
- All file access is read-only. CWE-22 not applicable.
- No secrets, no PII, no network calls.

### Observability

- Each hook prints to stdout: hook name, files checked count, pass/fail verdict, violations on fail.
- Format matches existing PreToolUse hook pattern (e.g., `invoke_session_log_guard.py`).
- No structured log file.

### Acceptance criteria (EARS syntax)

1. **AC-1**: WHEN an agent invokes `git push` AND any file in the changeset matches `*.md` THE SYSTEM SHALL run markdownlint-cli2 on those files SO THAT style violations are caught before review.
2. **AC-2**: WHEN markdownlint-cli2 reports any violation THE SYSTEM SHALL block the push with a non-zero exit code and print each violation with file path, line, rule code, and rule description SO THAT the agent can fix without consulting external docs.
3. **AC-3**: WHEN markdownlint-cli2 binary is not available on PATH THE SYSTEM SHALL print a WARN message and allow the push SO THAT a missing tool does not block work on dev machines without the binary.
4. **AC-4**: WHEN an agent invokes `git push` AND any file in the changeset matches `templates/agents/*.md`, `.claude/skills/*/SKILL.md`, or `.claude/commands/*.md` THE SYSTEM SHALL count files in each glob and compare the counts to the corresponding fields in `.claude-plugin/marketplace.json` and `docs/SEMANTIC_INDEX.yaml` SO THAT count drift cannot reach CI.
5. **AC-5**: WHEN any count comparison from AC-4 disagrees THE SYSTEM SHALL block the push with a non-zero exit code and print each disagreement as `<file>:<field> expected <N>, got <M>` SO THAT the agent can fix the manifest in one edit.
6. **AC-6**: WHEN an agent invokes `git push` AND the changeset contains any `.agents/sessions/*.json` file THE SYSTEM SHALL parse each session log and check: (a) `schemaVersion` is present and non-empty, (b) `endingCommit` is present and not the literal string `"pending"`, (c) `markdownLintRun.scanned` (if present) lists at least one file ending in `.md` if the changeset contains any `.md` files SO THAT placeholder logs cannot reach review.
7. **AC-7**: WHEN any session log check from AC-6 fails THE SYSTEM SHALL block the push with a non-zero exit code and print each failure as `<session-log-path>:<field> <reason>` SO THAT the agent can fix the log in one edit.
8. **AC-8**: WHEN no `.md` files, no manifest-affecting files, and no session log files are in the changeset THE SYSTEM SHALL exit zero immediately without invoking any subprocess SO THAT pushes with no relevant changes do not pay validation cost.
9. **AC-9**: WHEN the count-derivation script runs in isolation (`python3 scripts/validation/manifest_counts.py`) THE SYSTEM SHALL print the derived counts and exit zero, providing a way to inspect what the validator sees SO THAT debugging count disagreements is possible without re-pushing.
10. **AC-10**: Each new hook MUST have unit tests under `tests/` covering: positive case (pass), negative case (fail), edge case (empty changeset, missing binary, malformed file). Coverage MUST meet the 80% business-logic floor from AGENTS.md.

### Out of scope

- FM-3 (PR description staleness): tracked as #1885.
- FM-5 (spec-before-code): governance change, not in scope here.
- Auto-fix of violations.
- Git pre-push hooks (Claude Code PreToolUse only).
- CI workflow changes (CI remains backstop).
- Full-repo remediation of pre-existing violations.

### Deferred

- Bootstrapping git pre-push hooks if human-authored PRs become a source of iteration cost. Owner: repo maintainer.
- Auto-fix mode behind a `--fix` flag if blocking turns out to slow agents more than it helps. Owner: implementer post-rollout.

### Open questions

None remaining at end of interview.

### CVA summary

- **Common across all three hooks**: invoked from PreToolUse on `git push`, run only on changed files (from `git diff`), produce stdout summary, block with non-zero exit on failure, no auto-fix, no network.
- **Varies**: the validator body (markdownlint subprocess vs. count comparison vs. JSON field check), the file globs scoped, and the specific error message format.
- **Relationship**: a thin shared hook framework (read changeset, dispatch to validator, format output) with three specific validator implementations behind it. Strategy pattern.
