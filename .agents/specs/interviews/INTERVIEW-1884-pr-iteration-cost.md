---
type: interview
issue: 1884
related:
  - REQ-005
  - DESIGN-005
  - TASK-005
  - PLAN-1884
  - issue: 1885
slug: pr-iteration-cost
status: historical
created: 2026-05-03
updated: 2026-05-04
---

# Interview: Reduce PR review iteration cost

> **Status: historical record**, edited for consistency with final scope. Original transcript
> captured five user stories and a draft PRD. Post-interview gap analysis, pre-mortem, and
> decision-critic surfaced four BLOCK findings. This file has been edited to match the final
> scope at REQ-005, DESIGN-005, TASK-005, and PLAN-1884. Where the original interview disagreed
> with current scope (notably: `docs/SEMANTIC_INDEX.yaml` was incorrectly identified as a count
> manifest; `markdownLintRun.scanned` does not exist; `scripts/validation/manifest_counts.py` <!-- orphan-ref-ignore -->
> was not created), the text has been corrected. The narrative shape of the interview is
> preserved; the facts are now accurate.

## Problem (confirmed)

Agent-authored PRs in this repo burn 10 to 22 commits and 3 to 6 review rounds because three
classes of mechanical errors (markdown style violations, marketplace count drift, session log
placeholders) are caught in CI or review rather than at push time. The fix is to shift
validation left so these classes cannot be pushed.

## Branch walk

### 1. User stories

- **US-1: Block markdown style violations pre-push.** CONFIRMED. PreToolUse hook runs
  markdownlint on changed `.md` files in the changeset before `git push`.
- **US-2: Block marketplace count drift pre-push.** CONFIRMED. Pre-push validator invokes the
  existing `build/scripts/validate_marketplace_counts.py` against `.claude-plugin/marketplace.json`.
  Counts are embedded in plugin description strings; the existing validator parses them via
  regex against filesystem-derived counts using `templates/marketplace-counters.yaml`.
  `docs/SEMANTIC_INDEX.yaml` is NOT in scope (it is a semantic search index, not a count
  manifest).
- **US-3: Block session log placeholder values pre-push.** CONFIRMED. Validator rejects logs
  missing `schemaVersion`, with `endingCommit: "pending"`, or with placeholder
  `markdownLintRun.Complete`/`markdownLintRun.Evidence`. The real schema is
  `markdownLintRun: {Complete: bool, Evidence: str}`. There is no `.scanned` field.
- **US-4: PR description staleness.** OUT_OF_SCOPE for #1884. Tracked as #1885 (blocking
  follow-up).
- **US-5: Spec-before-code enforcement (FM-5).** OUT_OF_SCOPE. Governance change, not a
  mechanical validator. Deferred.

### 2. Data model

- No new entities. All changes operate on existing files.
- **Counts become derived data.** Filesystem (under `templates/agents/`,
  `.claude/skills/*/SKILL.md`, `.claude/commands/`) is SoR. The numbers embedded in
  `.claude-plugin/marketplace.json` plugin description strings are the projection. The existing
  validator parses them via regex.
- **Q2 CONFIRMED**: Agent count from `templates/agents/*.md` (per `.claude/rules/templates.md`
  SoR rule). Skill count from `.claude/skills/*/SKILL.md`. Command count from
  `.claude/commands/*.md`. Generated files in `src/claude/` are not counted.

### 3. Integrations

- **markdownlint-cli2**: subprocess from hook. Available as binary on dev machines; verify on
  hook startup; fail-open when missing.
- **git diff**: source of changeset file list. Use `git diff --name-only @{push}..HEAD` with
  `origin/main...HEAD` fallback (per ADR-043).
- **Existing `build/scripts/validate_marketplace_counts.py`**: the manifest count guard imports
  this and translates exit codes; the script is unmodified.
- **Q3 CONFIRMED**: Claude Code PreToolUse hooks only. Rationale: 100% of high-iteration PRs in
  the RCA window were agent-authored. Git pre-push hook is not auto-installed and is out of
  scope. Existing `invoke_session_log_guard.py` is the proven template.

### 4. Failure modes

- **markdownlint binary missing**: WARN, allow push. Tooling-gap, not a code problem.
- **Large changeset**: limit to changed files only (from `git diff --name-only`). Subprocess
  timeout 60s; on `TimeoutExpired` fail-open with stderr warning (CI runner latency is
  infrastructure noise, not a lint violation).
- **Marketplace count validator returns non-zero**: block; surface stdout as violation lines
  with the `--fix` hint.
- **Session log validator false positive**: narrow scope (three fields plus a 20-character
  minimum on Evidence and a placeholder list).
- **Pre-existing violations in unchanged files**: validators run on changeset only, not full
  repo.
- **Q4 CONFIRMED**: Block on violation, do not auto-fix. Auto-fix would mutate files without
  explicit agent decision. Block with clear error message; the agent fixes.

### 5. Security

- No secrets, no PII, no network.
- Subprocesses use argument lists (not shell strings), per existing `pre_pr.py` pattern.
  CWE-78 mitigated by construction.
- File paths from `git diff` are read-only inputs. CWE-22 not applicable (no writes).

### 6. Observability

- **Q5 CONFIRMED**: Stdout only. No structured log file. Trend analysis via CI history if
  needed later.
- Each hook prints: check name, files checked count, pass/fail, specific violations on fail.
  Match existing hook output pattern.

### 7. Scope boundaries

**In scope:**

- FM-1: PreToolUse hook for markdownlint on changed `.md` files.
- FM-2: PreToolUse hook that invokes the existing marketplace-counts validator.
- FM-4: PreToolUse hook for session log field validation.

**Out of scope:**

- FM-3 (PR description staleness): tracked as #1885 (blocking follow-up).
- FM-5 (spec-before-code): governance, separate issue if pursued.
- Auto-fix.
- Git pre-push hook bootstrapping.
- CI workflow changes (CI is backstop, not primary gate).
- Full-repo remediation of existing violations.
- `docs/SEMANTIC_INDEX.yaml` (it is not a count manifest).

**Deferred:**

- Auto-installation of git hooks. If human pushes become a problem, revisit.

### Q1 CONFIRMED: FM-5 deferred. FM-3 deferred to #1885.

## Verification

- [x] Every branch has a recorded decision.
- [x] Every requirement is testable as pass/fail.
- [x] Every "we will figure it out later" promoted to deferred or out-of-scope.
- [x] Problem restatement and acceptance criteria confirmed by user.

## Outcome

The structured PRD captured here was formalized into REQ-005, DESIGN-005, TASK-005, and
PLAN-1884. The acceptance criteria, data model, integrations, failure modes, security,
observability, and scope boundaries live in those artifacts. This interview file does not
duplicate them; it records the conversation that produced them.

For the current scope and ACs, see:

- `.agents/specs/requirements/REQ-005-pr-iteration-cost.md`
- `.agents/specs/design/DESIGN-005-pr-iteration-cost.md`
- `.agents/specs/tasks/TASK-005-pr-iteration-cost.md`
- `.agents/plans/active/PLAN-1884-pr-iteration-cost.md`

### CVA summary

- **Common across all three hooks**: invoked from PreToolUse on `Bash(git push*)`, run only on
  changed files, produce stdout summary, block with exit code 2 on violation, fail-open on
  infrastructure errors, no auto-fix, no network.
- **Varies**: the validator body (markdownlint subprocess vs. existing-validator import vs.
  JSON field check), the file globs scoped, and the specific error message format.
- **Relationship**: a thin shared hook framework (`push_guard_base.py`) with three specific
  validator implementations behind it. Strategy pattern.
