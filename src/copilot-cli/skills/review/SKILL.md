---
name: review
version: 1.0.0
description: Review before merge. Stage-1 spec-compliance gate, then risk-selected Stage-2 review axes from the canonical set. analyst always runs, callers can pin extra always-on axes, and explicit deep review runs every canonical axis. Run after /test. Do NOT invoke code-qualities-assessment, doc-accuracy, golden-principles, or taste-lints directly for a full review; review can select them when requested or when deep review is explicit.
argument-hint: branch-or-pr-number
allowed-tools: Task, Skill, Read, Glob, Grep, Bash(*)
user-invocable: true
license: MIT
metadata:
  capability:
    kind: orchestrator
    owns: [technical-review]
    depends-on: [code-archaeology, untrusted-content-handling]
    status: active
  routing:
    role: front-door
    invoker: autoplan
    trigger: lifecycle review request
    user-facing: true
---

# Review

Review: the problem statement from the conversation (under Copilot CLI the skill tool takes no argument vector, so state it in your message)

If no argument, review the current branch diff against the base branch. Detect the base branch from `gh pr view --json baseRefName` or fall back to `main`.

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `/review` | Run the Stage-1 spec-compliance gate, then the Stage-2 review against the current branch diff |
| `/review BRANCH_OR_PR` | Run the Stage-1 gate, then the Stage-2 review against the named branch or PR |
| `review before merge` | Same as `/review` |

## Convergence contract (REQ-008-04)

`/review` evaluates the canonical review axes by change risk, not by blind fan-out. The canonical axis prompts are authored at `references/{role}.md` co-located with this skill, with the canonical path expressed as `.claude/skills/review/references/{role}.md` in the source repo (the single source of truth). `/review` auto-discovers the axis set from `references/*.md` at runtime for `--deep` review; risk mode needs a table entry, or the axis is `skipped` (axis-selection.md). Enrollment is not edit-free: the axis names and counts in this body document that directory rather than drive it, and a contract test reds on drift. A project with CI syncs the axes into its CI prompts with its own generator and drift checks. The build copies the whole skill directory into vendored installs (see "Vendored install"), so `/review` needs no CI.

The canonical set is `spec-compliance` as the Stage-1 gate plus 11 Stage-2 canonical axes (`analyst`, `architect`, `qa`, `security`, `devops`, `roadmap`, `reliability`, `observability`, `agent-safety`, `decision-rigor`, `code-quality`). `spec-compliance` and `analyst` always run. Callers can pin more always-on axes; `select_axes.py` selects the rest from verified changed paths and diff effects (Process step 4), never by prompt prose. Only a Stage-1 `CRITICAL_FAIL` short-circuits the review; a Stage-1 `UNKNOWN` does not (Process step 2). The caller decides how the merged verdict gates its workflow.

`/review` is a strict superset of CI only in deep-review mode, when it runs the full canonical set. Risk-selected `/review` can be narrower than CI, because it may skip axes that do not apply. The 4 local-only skill axes need local code execution and repo state, so CI cannot run them; they are language-agnostic, risk-selected or pinned like any axis, and tracked in a set of their own (step 4b).

**Self-audit round cap (hard stop).** `/review` runs each axis once per invocation; no internal fix-and-re-review loop. The cap binds the caller: any skill, command, or agent chaining "fix, re-invoke `/review`, repeat" with no human checkpoint MUST NOT exceed 3 rounds for that invocation, even across a diff, branch, or PR switch. The caller tracks its own count for the whole invocation; `/review` holds no shared state. Only a new invocation, or a human checkpoint, resets the count. Round 3: `PASS` ships; `WARN`, `CRITICAL_FAIL`, or `UNKNOWN` escalates to the operator with every open finding (axis, verdict, location, recommendation); no self-acknowledging a `WARN` to ship.

Modeled on `.claude/skills/github/scripts/pr/check_pr_round_cap.py`. Quoted (lines 39-40, 188-189): "0 = round recorded, under both caps (ACT); 1 = a cap is exceeded (ESCALATE)"; `_DEFAULT_MAX_ROUNDS = 5`, `_DEFAULT_MAX_HOURS = 4.0`.

**Stricter/looser/different than canonical**: stricter on round count (3 vs. default 5). Looser on time (canonical also caps elapsed hours; this has none) and persistence (canonical persists state across restarts via a PR-comment marker; this uses in-invocation tracking only). Different in kind: canonical only gates `ACT`/`ESCALATE`, never ships; round 3 here can ship `PASS`.

## Frozen finding contract (rounds after the first)

The caller supplies `ROUND: N` context. In round 2 or 3 only a defect the diff introduced (fix commits included) and an unmet acceptance criterion the PR claims count. The rest are flagged notes: listed in Output, never merged, never a reason for another round. Append `--frozen` to the step 4a arguments. Read `resources/frozen-finding-contract.md`. The caps stay.

## Path resolution (harness-agnostic)

This skill runs in two layouts: the source Claude Code project (where `.claude/` is the repo root) and a vendored plugin install (Copilot CLI and similar harnesses) where the consumer repo has no `.claude/` directory and the plugin lives outside the consumer's tree.

- **Canonical axis prompts** (`{role}` is the stem of each `references/*.md` file, discovered, not hardcoded; the current set is listed in the convergence contract above): resolve the `references/` directory via the first candidate that exists, then glob `*.md` inside it for the axis set:
  1. `${CLAUDE_SKILL_DIR}/references/` (if `CLAUDE_SKILL_DIR` is set by the harness)
  2. `.claude/skills/review/references/` (Claude Code project layout)
  3. `skills/review/references/` (vendored install)
- **Verdict library** (`merge_verdicts`, `extract_verdict`, `get_verdict_emoji`, `FAIL_VERDICTS`): try each candidate in order, use the first that exists:
  1. `.claude/lib/ai_review_common/verdict.py` (Claude Code project layout)
  2. `lib/ai_review_common/verdict.py` (vendored install)
- **Complexity tiers reference** (`engineering-complexity-tiers.md`): try each candidate in order, use the first that exists:
  1. `.claude/skills/analyze/references/engineering-complexity-tiers.md` (Claude Code project layout)
  2. `skills/analyze/references/engineering-complexity-tiers.md` (vendored install, plugin-root relative)
- **Chained-skill scripts** (`assess.py`, `doc_accuracy.py`, `scan_principles.py`, `taste_lints.py` for local axes 1-4): these are sibling skills, not under this skill's `references/`, so `CLAUDE_SKILL_DIR` does not locate them. For each, use the first candidate that exists:
  1. `.claude/skills/{skill}/scripts/{script}` (Claude Code project layout)
  2. `skills/{skill}/scripts/{script}` (vendored install, plugin-root relative)

The skill body MUST NOT hard-fail when the `.claude/` path is missing; it MUST attempt the vendored-install path for the verdict library and the chained-skill scripts before reporting an error. If neither candidate for a chained-skill script exists, mark that axis `UNKNOWN` (per UNKNOWN handling), do not abort the review.

## Scripts

| Script | Purpose | Exit codes |
|--------|---------|------------|
| `scripts/validate_review_marker.py` | Validates the SHA-bound `Reviewed-By: /review@...` marker `/ship` requires and the review report its `Review-Artifact` digest covers. `--digest REPORT_FILE` prints that digest. | `0` valid, `1` missing, stale, bad axis list, or no valid review report, `2` config error |
| `select_axes.py` (same directory) | Selects the Stage-2 canonical axes and the local-only skill axes from verified changed paths and diff effects. Emits the selection, per-axis reasons, and skips as JSON. | `0` selection emitted, `2` config error (unknown pinned axis, or references directory missing or empty) |

## Process

Run axes sequentially. Each axis emits a verdict token (`PASS`, `WARN`, `CRITICAL_FAIL`, or `UNKNOWN`) plus structured findings (severity, category, location, recommendation). The final merged verdict comes from `merge_verdicts` (resolve via the "Path resolution" section above).

1. Read the diff with three-dot range syntax (`git diff "origin/$BASE_BRANCH"...HEAD`, where `BASE_BRANCH` is the detected base branch and the remote-tracking ref is used because the local base branch may not exist in fresh clones) so every evaluation step uses the same change set as the diff-scoped gates in step 5.
   - Build one `CONTEXT_MODE` value before invoking any canonical axis: use `full` only when the complete diff plus any linked REQ/DESIGN/TASK docs or PR-body acceptance criteria are present; use `summary` when only file names or diff stats are present; use `partial` when only a bounded slice is present. If context completeness is unknown, use `partial`.
   - Every Task input for a canonical axis MUST begin with `CONTEXT_MODE: $CONTEXT_MODE`, followed by a blank line and then the diff and supporting context. This is the local `/review` equivalent of the CI header. A missing or unrecognized value remains not `full`, so the axis prompts cannot emit `PASS` on absent evidence.
2. **Run the Stage-1 spec-compliance gate before the complexity classifier and all Stage-2 axes.** Load the canonical `spec-compliance` axis prompt via the "Path resolution" section above and invoke `agent_type: "project-toolkit:general-purpose"` with that prompt as the system instruction and the CONTEXT_MODE-prefixed diff plus any linked REQ/DESIGN/TASK docs (or PR-body acceptance criteria) as input. Extract its verdict with `extract_verdict`.
   - **CRITICAL_FAIL only**: short-circuit. Do NOT run the complexity classifier, the remaining axes, or any local skill axes. Mark all of them `SKIPPED` in the output table, set the FINAL VERDICT to the Stage-1 `CRITICAL_FAIL`, and emit only the Stage-1 findings. The author fixes the unmet criterion, then re-runs `/review`. A Stage-1 UNKNOWN (no spec or acceptance criteria located) is NOT a short-circuit and never suppresses a real Stage-2 finding.
   - **PASS, WARN, or UNKNOWN (INCONCLUSIVE)**: record the Stage-1 verdict and continue to step 3. A WARN or UNKNOWN here does not block Stage 2; it is merged alongside the other axes (an otherwise-PASS run with a Stage-1 UNKNOWN surfaces why no spec was found). The full FINAL VERDICT comes from `merge_verdicts` in step 7.

3. **Classify complexity tier**: `agent_type: "project-toolkit:analyst"`: Read `engineering-complexity-tiers.md` (resolved via the "Path resolution" section above) and the diff. Assess as Tier 1-5. Use this to calibrate axis depth.
4. **Select the Stage-2 axes with `select_axes.py`, then run the canonical ones.** Pass every path from step 1 and every effect from the diff hunks. Pass each path as one argument. Never shell-expand Git-controlled paths. The selector is deterministic, so do not re-derive routing from prose. The co-located `resources/axis-selection.md` defines effects, risks, and output fields.

   Pass `--deep` when the caller asks for a deep or full review, when the invocation is a pre-merge gate that must be a strict superset of CI. Deep skips a local axis whose scanner reads no changed file. Unsure of the paths? Pass none; that fails closed.

   Run the axes in `canonical_selected` (`analyst` unless `references/analyst.md` is missing, which fails the run closed). `fail_closed: true` means the change could not be classified, or a demanded axis has no prompt, and every candidate was selected; that is intended, not an error. Report every axis in `unresolved_axes` as UNKNOWN: demanded, but with no prompt to load. A skipped axis is never PASS.

   For each selected axis load `references/{role}.md`, then invoke `agent_type: "project-toolkit:{role}"` with that prompt as the system instruction, the same CONTEXT_MODE-prefixed diff as input, and that file's Output Schema as the response contract. A `When This Axis Applies` section, where an axis has one, calibrates depth; it never overrules the selection. If the harness registers no `{role}` subagent type (Copilot CLI today, and any axis with no matching agent such as `reliability` or `decision-rigor`), fall back to `agent_type: "project-toolkit:general-purpose"`; the prompt drives the review, not the subagent identity.

4a. **Validate scope of each axis output against the PR diff.** After each axis (steps 2, 3, and every axis in step 4) returns its findings text, run `scripts/validate_findings_scope.py` (resolved via the "Path resolution" section) to find `location:` fields naming files outside the three-dot diff of step 1: `python3 <validate_findings_scope.py> --worktree <WORKTREE_PATH> --base-branch <BASE_BRANCH> --text <AXIS_TEXT> --emit-adjusted-text`. On exit 1 (out-of-scope locations found), replace the axis output with the script's stdout before extracting the verdict; the adjusted text marks each flagged location `[pre-existing - not in this PR diff]`. When every cited location is out of scope and the axis emitted a blocking verdict, the script downgrades that verdict to `WARN`, so an unrelated finding cannot block the reviewed PR. Do NOT suppress or skip the finding; preserve it with the label. On exit 0 (all in scope, or diff empty or unavailable), record stdout when present, otherwise the axis output unmodified.
4b. **Keep the local-only skill axes in their own selected set.** The 4 local axes (`code-qualities-assessment`, `doc-accuracy`, `golden-principles`, `taste-lints`) are sibling skills invoked with `skill: "{name}"`. None has a `references/{name}.md` file, so a local axis in the canonical set resolves to a prompt path that does not exist. `select_axes.py` reports them in `local_selected`, never in `canonical_selected`, including when `--pin` names one; keep the two lists separate for the rest of the run.
4c. **Always-on correctness pass.** Load `resources/technical-review.md`, resolved like the axis prompts with `resources/` in place of `references/`. Invoke `agent_type: "project-toolkit:code-reviewer"`, falling back to `general-purpose`, with that contract as the response contract and the same CONTEXT_MODE-prefixed diff as input. Scope-check its output as in 4a, then `extract_verdict`; any failure is `UNKNOWN`.

5. **Run the selected chained skill axes** (local-only; CI does not run these). Run every axis in `local_selected` after the canonical ones; report the rest as skipped with its reason. Resolve each `<script>` per "Path resolution" (chained-skill scripts). Scope every axis to the PR diff with the base branch detected in step 1 (stored as `BASE_BRANCH`), quoted, so the gates evaluate only changed files, not the whole tree:

- local axis 1: `skill: "code-qualities-assessment"`, invoking `python3 <assess.py> --target . --changed-only --base "origin/$BASE_BRANCH" --format json`. Its report labels authored, test, and generated files; review generated files' source. For rules, skills, agents, or new abstractions, see the `code-qualities-assessment` skill's `references/executable-nl-artifacts.md`.
- local axis 2: `skill: "doc-accuracy"`, invoking `python3 <doc_accuracy.py> --target . --diff-base "origin/$BASE_BRANCH" --format gate`. Also run it when the `test` skill's `doc_accuracy_trigger.py` says `activate`; see `resources/documentation-findings.md`.
- local axis 3: `skill: "golden-principles"`, invoking `python3 <scan_principles.py> --diff-scope "origin/$BASE_BRANCH" --format json`. Scope: toolkit-artifact governance for GP-001, GP-003, GP-004, GP-005, GP-006 (script language, skill frontmatter, agent definitions, YAML logic, pinned Actions); GP-002 is hooks and review practice, GP-007 and GP-008 are taste-lints. A clean result on a non-toolkit repo means no rule applied, not that design was reviewed.
- local axis 4: `skill: "taste-lints"`, invoking `python3 <taste_lints.py> --diff-scope "origin/$BASE_BRANCH" --format json`.

6. **Extract verdict per axis**. Canonical axes end with a line matching `(?m)^\s*(?i:(?:Final\s+)?Verdict):\s*\[?(PASS|WARN|CRITICAL_FAIL|REJECTED|FAIL|NEEDS_REVIEW|NON_COMPLIANT|COMPLIANT|PARTIAL|UNKNOWN)(?![|A-Z_])\]?` (label case-insensitive; tokens case-sensitive uppercase; trailing lookahead rejects template-form lines like `VERDICT: [PASS|WARN|CRITICAL_FAIL]` and token-prefix collisions). Parse them with `extract_verdict` from the verdict library. Local axes emit JSON or `Gate:` instead, so normalize them first with `adapt_local_axis_verdict` from that library: it maps code-quality exit codes, `doc-accuracy` `gate_result.verdict`, and golden/taste `error_count` plus `warning_count` into PASS, WARN, FAIL, or UNKNOWN. On a crash, malformed output, or an unclassified result, record `UNKNOWN` and continue.
7. **Merge verdicts** via `merge_verdicts([...])`, passing the Stage-1 `spec-compliance` verdict, the step 4c correctness verdict, plus one verdict per axis that actually ran (the selected Stage-2 axes plus any selected local skills; at most 16 total in deep-review mode with the current set). Rules: any token in `FAIL_VERDICTS` (`CRITICAL_FAIL`/`REJECTED`/`FAIL`/`NEEDS_REVIEW`/`NON_COMPLIANT`) -> `CRITICAL_FAIL`; any `WARN` or `PARTIAL` -> `WARN`; any `UNKNOWN` or unrecognized token -> `UNKNOWN`; all `PASS`/`COMPLIANT` -> `PASS`; empty -> `UNKNOWN`. When Stage 1 returns `CRITICAL_FAIL` (step 2 short-circuit), skip this merge: the FINAL VERDICT is `CRITICAL_FAIL`. A Stage-1 `UNKNOWN` does NOT short-circuit; it is merged like any other axis.
8. **Emit findings table** (see Output below).

## Running without the Task tool

A subagent with no `Task` tool MUST NOT review its own diff and write the marker. Run each axis as its own `claude -p` process, as `resources/marker-and-no-task.md` says. If `claude` is not on `PATH`, record `UNKNOWN` for every axis, which writes no marker.

## Vendored install (REQ-008-06)

`/review` MUST work in a vendored plugin install in any harness (Claude Code, Copilot CLI, and similar). No axis or skill assumes one hard-coded layout; resolve every dependency through "Path resolution". The build copies the whole skill directory into each plugin install. CI prompts, generators, and sync scripts named here are maintainer context, not runtime dependencies.

## UNKNOWN handling

- A skill that crashes or exits with a status step 6's adapter does not recognize -> mark `UNKNOWN`, log it, continue.
- A canonical axis whose output cannot be parsed by `extract_verdict` -> mark `UNKNOWN`.
- UNKNOWN does NOT override real findings: `merge_verdicts(["WARN", "UNKNOWN"])` returns `WARN`. UNKNOWN only matters when it would otherwise be PASS.
- UNKNOWN axes are surfaced in the output table so the reviewer sees what was not evaluated.
- A local axis skipped as unreadable is not PASS and gets no marker row; its Summary names the language-native checks run instead, or `none run`.

## Output

Findings table with one row per axis:

| Axis | Verdict | Selection | Emoji | Summary |
|------|---------|-----------|-------|---------|
| spec-compliance | PASS | always-on | (from get_verdict_emoji) | (Stage-1 gate; SKIPPED rows below when it short-circuits) |
| analyst | PASS | always-on | (from get_verdict_emoji) | (one-line summary) |
| architect | WARN | selected - risk category | ... | ... |
| devops | UNKNOWN | skipped - reason from `skipped` | ... | ... |

One row per axis in the step-4 candidate set, then one per local axis: 16 rows with the current set. Append one `UNKNOWN` row per `unresolved_axes` entry. Append one always-on `correctness` row for step 4c. Each Selection cell reads `always-on`, or `selected / skipped` plus its reason from `selection_reasons` or `skipped`.

**FINAL VERDICT**: [PASS|WARN|CRITICAL_FAIL|UNKNOWN] (from `merge_verdicts`)

In round 2 or 3, add **Flagged notes (not counted)** after it: axis, `file:line`, reason (`pre-existing`, `nice-to-have`, `new scope`), or `none`. They never change the verdict.

Followed by per-axis findings in detail. Each finding:

- **severity**: CRITICAL | IMPORTANT | SUGGESTION
- **category**: short keyword
- **location**: `file:line`
- **recommendation**: one-sentence fix

Categorize a finding as **Critical** if its axis verdict is `CRITICAL_FAIL`, **Important** if `WARN`, **Suggestion** otherwise.

## Write the SHA-bound PASS marker

On a **PASS** final verdict (or a WARN where every WARN was acknowledged), write a
SHA-bound marker so `/ship` can prove the shipped code was reviewed at its current
state without re-running the review. Skip this on `CRITICAL_FAIL`, a Stage-1
short-circuit, `UNKNOWN`, or an unacknowledged WARN: none may leave a marker.

The marker is an empty commit on top of the reviewed tip. Its body holds a review
report (the reviewed SHA plus one `<axis>: <VERDICT>` row per axis that ran), then
the trailers `Reviewed-By: /review@<axis-list> on <reviewed-tip-sha>` and
`Review-Artifact: sha256:<digest of the report lines>`. A bare `Reviewed-By`
trailer is rejected: any agent can type one. Write the marker only as
`resources/marker-and-no-task.md` says, and never add a row for an axis that did
not run.

The marker is valid only while its parent (the reviewed tip) is HEAD's parent or a clean `origin/main` merge sits above it. New code makes it stale.

Re-running `/review` after the verdict is still PASS writes another marker commit;
that is safe (idempotent in effect: the latest marker binds the current tip).

## Principles

- **Deep review is the strict superset of CI**. In deep review, `/review` surfaces every CI finding first.
- **Drift fails closed**. If `.claude/skills/review/references/` and `.github/prompts/` diverge, pre-push blocks. CI re-checks.
- **UNKNOWN is information**. A skill that did not evaluate is not a silent PASS. Loops, not files: `evidence-provenance`.
- **Vendored survival**. `/review` works in a `.claude/`-only checkout. No axis or skill references `.agents/` or `.github/`.
- **Voice**. Read `resources/writing-style.md` before writing findings (glossing, completeness scores).

## Verification

- [ ] The `spec-compliance` Stage-1 axis file exists under `references/spec-compliance.md` and runs before Stage 2 (Process step 2)
- [ ] Every non-spec `references/*.md` file is either selected by change risk or reported as SKIPPED with a reason, and deep review still runs the full set (11 with the current set: analyst, architect, qa, security, devops, roadmap, reliability, observability, agent-safety, decision-rigor, code-quality)
- [ ] Stage-2 selection came from `select_axes.py` over the verified three-dot diff; the 4 local axes stayed in `local_selected`; an unclassifiable path, a blank-only path list, or an unknown `--effect` gave `fail_closed: true` and the full set
- [ ] Each axis emits a parseable verdict line per the `extract_verdict` regex
- [ ] The verdict library resolves under one of the two documented candidate paths
- [ ] `merge_verdicts` produces a single final verdict consistent with the rules in Process step 7
- [ ] On a Stage-1 `CRITICAL_FAIL`, Stage 2 axes are marked `SKIPPED` and the final verdict is the Stage-1 `CRITICAL_FAIL`; on a Stage-1 `UNKNOWN` (INCONCLUSIVE), Stage 2 STILL runs and the UNKNOWN is carried into the merge (it never suppresses a real Stage-2 finding such as a security `CRITICAL_FAIL`)
- [ ] When Stage 2 runs, the output table contains the spec-compliance row plus one row per candidate axis with selection status and reason, and deep review still yields 16 rows with the current set, plus the final verdict line
- [ ] Step 4c ran, its verdict joined the step 7 merge, and the table has a `correctness` row
- [ ] Round 2 or 3: step 4a used `--frozen`; flagged notes stayed out of `merge_verdicts`

## Refs

- Skill chain: the 4 local axes at `.claude/skills/{code-qualities-assessment,doc-accuracy,golden-principles,taste-lints}/`. Plus the 11 Stage-2 canonical axes and the Stage-1 gate: 16 rows.

<!-- vendor-portability: declared. This skill body cites .claude/lib/ai_review_common/verdict.py (ships in the vendor install; the skill names the plugin-root-relative lib/ai_review_common/verdict.py fallback for the vendored layout) and mentions .agents/ only to assert that /review needs no .agents/ access. Also cites .claude/skills/github/scripts/pr/check_pr_round_cap.py as canonical-source-mirror evidence: a sibling in-plugin script cited for its contract, not resolved or run by /review. No upstream-only runtime dependency. -->
