---
name: review
version: 1.0.0
model: claude-sonnet-4-6
description: Review before merge. Stage-1 spec-compliance gate, then 11 Stage-2 canonical axes (analyst, architect, qa, security, devops, roadmap, reliability, observability, agent-safety, decision-rigor, code-quality) plus 3 chained skills (code-qualities-assessment, golden-principles, taste-lints). Run after /test. Run for a full pre-merge review. Do NOT invoke code-qualities-assessment, golden-principles, or taste-lints directly for a full review; review chains them.
argument-hint: branch-or-pr-number
allowed-tools: Task, Skill, Read, Glob, Grep, Bash(*)
user-invocable: true
license: MIT
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

`/review` evaluates every canonical axis the project ships, plus three local-only skill axes that CI cannot afford. The canonical axis prompts are authored at `references/{role}.md` co-located with this skill, with the canonical path expressed as `.claude/skills/review/references/{role}.md` in the source repo (the single source of truth). `/review` auto-discovers the axis set from `references/*.md` rather than hardcoding a list, so adding a `references/{role}.md` file enrolls the axis with no edit to this skill body. When CI exists in a project, the project syncs the canonical axes into its own CI prompts via the project's generator and drift checks. The build pipeline copies the entire skill directory (including `references/` and `scripts/`) into vendored plugin installs so the command runs without a CI dependency in any harness that supports plugins.

The canonical set is `spec-compliance` as the Stage-1 gate plus 11 Stage-2 canonical axes (`analyst`, `architect`, `qa`, `security`, `devops`, `roadmap`, `reliability`, `observability`, `agent-safety`, `decision-rigor`, `code-quality`). `spec-compliance` runs first and gates Stage 2: only a `CRITICAL_FAIL` short-circuits the review (see Process step 2). A Stage-1 `UNKNOWN` (INCONCLUSIVE) does NOT short-circuit; Stage 2 still runs and the UNKNOWN is preserved as an UNKNOWN in the merge, because no spec or acceptance criteria could be located and that absence must never suppress a real Stage-2 finding. The caller decides how the merged verdict gates its workflow.

`/review` is a strict superset of CI: any finding CI surfaces, `/review` will surface first locally. CI may wire a subset of the canonical axes (its per-axis job list can lag the `references/` directory); `/review` always runs the full discovered set, so it never surfaces fewer axes than CI. The 3 chained skill extras (`code-qualities-assessment`, `golden-principles`, `taste-lints`) need local code execution and repo state, so CI cannot run them, but they are language-agnostic and run on ANY repo locally as part of `/review`.

## Path resolution (harness-agnostic)

This skill runs in two layouts: the source Claude Code project (where `.claude/` is the repo root) and a vendored plugin install (Copilot CLI and similar harnesses) where the consumer repo has no `.claude/` directory and the plugin lives outside the consumer's tree.

- **Canonical axis prompts** (`{role}` is the stem of each `references/*.md` file: `spec-compliance|analyst|architect|qa|security|devops|roadmap|reliability|observability|agent-safety|decision-rigor|code-quality`, discovered, not hardcoded): resolve the `references/` directory via the first candidate that exists, then glob `*.md` inside it for the axis set:
  1. `${CLAUDE_SKILL_DIR}/references/` (if `CLAUDE_SKILL_DIR` is set by the harness)
  2. `.claude/skills/review/references/` (Claude Code project layout)
  3. `skills/review/references/` resolved relative to plugin install root (vendored install)
- **Verdict library** (`merge_verdicts`, `extract_verdict`, `get_verdict_emoji`, `FAIL_VERDICTS`): try each candidate in order, use the first that exists:
  1. `.claude/lib/ai_review_common/verdict.py` (Claude Code project layout)
  2. `lib/ai_review_common/verdict.py` resolved relative to the plugin install root (vendored install)
- **Complexity tiers reference** (`engineering-complexity-tiers.md`): try each candidate in order, use the first that exists:
  1. `.claude/skills/analyze/references/engineering-complexity-tiers.md` (Claude Code project layout)
  2. `skills/analyze/references/engineering-complexity-tiers.md` resolved relative to plugin install root (vendored install)
- **Chained-skill scripts** (local axes 2 and 3: `golden-principles/scripts/scan_principles.py`, `taste-lints/scripts/taste_lints.py`): these are sibling skills, not under this skill's `references/`, so `CLAUDE_SKILL_DIR` does not locate them. For each, try each candidate in order, use the first that exists:
  1. `.claude/skills/{skill}/scripts/{script}` (Claude Code project layout)
  2. `skills/{skill}/scripts/{script}` resolved relative to plugin install root (vendored install)

The skill body MUST NOT hard-fail when the `.claude/` path is missing; it MUST attempt the vendored-install path for the verdict library and the chained-skill scripts before reporting an error. If neither candidate for a chained-skill script exists, mark that axis `UNKNOWN` (per UNKNOWN handling), do not abort the review.

## Scripts

| Script | Purpose | Exit codes |
|--------|---------|------------|
| `scripts/validate_review_marker.py` | Validates the SHA-bound `Reviewed-By: /review@...` marker that `/ship` requires. | `0` valid marker, `1` missing or stale marker, `2` config error |

## Process

Run axes sequentially. Each axis emits a verdict token (`PASS`, `WARN`, `CRITICAL_FAIL`, or `UNKNOWN`) plus structured findings (severity, category, location, recommendation). The final merged verdict comes from `merge_verdicts` (resolve via the "Path resolution" section above).

1. Read the diff with three-dot range syntax (`git diff "origin/$BASE_BRANCH"...HEAD`, where `BASE_BRANCH` is the detected base branch and the remote-tracking ref is used because the local base branch may not exist in fresh clones) so every evaluation step uses the same change set as the diff-scoped gates in step 5.
   - Build one `CONTEXT_MODE` value before invoking any canonical axis: use `full` only when the complete diff plus any linked REQ/DESIGN/TASK docs or PR-body acceptance criteria are present; use `summary` when only file names or diff stats are present; use `partial` when only a bounded slice is present. If context completeness is unknown, use `partial`.
   - Every Task input for a canonical axis MUST begin with `CONTEXT_MODE: $CONTEXT_MODE`, followed by a blank line and then the diff and supporting context. This is the local `/review` equivalent of the CI header. A missing or unrecognized value remains not `full`, so the axis prompts cannot emit `PASS` on absent evidence.
2. **Run the Stage-1 spec-compliance gate before the complexity classifier and all Stage-2 axes.** Load the canonical `spec-compliance` axis prompt via the "Path resolution" section above and invoke `Task(subagent_type="general-purpose")` with that prompt as the system instruction and the CONTEXT_MODE-prefixed diff plus any linked REQ/DESIGN/TASK docs (or PR-body acceptance criteria) as input. Extract its verdict with `extract_verdict`.
   - **CRITICAL_FAIL only**: short-circuit. Do NOT run the complexity classifier, the 11 Stage-2 canonical axes, or the 3 chained skills. Mark all of them `SKIPPED` in the output table, set the FINAL VERDICT to the Stage-1 `CRITICAL_FAIL`, and emit only the Stage-1 findings. The author fixes the unmet criterion, then re-runs `/review`. UNKNOWN is NOT a short-circuit (see next bullet): a Stage-1 UNKNOWN means no spec or acceptance criteria could be located, so it must never suppress a real Stage-2 finding (e.g. a security or qa `CRITICAL_FAIL`).
   - **PASS, WARN, or UNKNOWN (INCONCLUSIVE)**: record the Stage-1 verdict and continue to step 3. A WARN or UNKNOWN here does not block Stage 2; it is merged alongside the other axes (per UNKNOWN handling, a Stage-1 UNKNOWN never overrides a real Stage-2 finding, and on an otherwise-PASS run it surfaces the one-line reason no spec or acceptance criteria could be located). The full FINAL VERDICT comes from `merge_verdicts` in step 7.

3. **Classify complexity tier**: Task(subagent_type="analyst"): Read `engineering-complexity-tiers.md` (resolved via the "Path resolution" section above) and the diff. Assess as Tier 1-5. Use this to calibrate axis depth.
4. **Run every Stage-2 canonical axis**, discovered from `references/*.md` after excluding `spec-compliance` (already run in step 2). Resolve the directory via the "Path resolution" section, then glob `*.md` and sort by stem for a stable order. Do not hardcode the axis list; the directory is the source of truth. For each axis, load the canonical prompt for `{role}` (the file stem), then invoke `Task(subagent_type="{role}")` with that prompt as the system instruction, the same CONTEXT_MODE-prefixed diff as input, and the structured Output Schema from the canonical file as the response contract. If the harness does not register a `{role}` subagent type in its `Task` enum (Copilot CLI today, and any axis with no matching agent such as `reliability`, `observability`, `agent-safety`, `decision-rigor`), fall back to `Task(subagent_type="general-purpose")` with the canonical axis prompt as the system instruction; the prompt drives the review, not the subagent identity. The current Stage-2 canonical set (11 axes) is:
   - axis 1: `analyst`
   - axis 2: `architect`
   - axis 3: `qa`
   - axis 4: `security`
   - axis 5: `devops`
   - axis 6: `roadmap`
   - axis 7: `reliability` (general-purpose fallback; no dedicated subagent)
   - axis 8: `observability` (general-purpose fallback; no dedicated subagent)
   - axis 9: `agent-safety` (general-purpose fallback; no dedicated subagent)
   - axis 10: `decision-rigor` (general-purpose fallback; no dedicated subagent)
   - axis 11: `code-quality` (general-purpose fallback; no dedicated subagent)
5. **Run 3 chained skill axes** (local-only; CI does not run these). These run after every canonical axis. Scope the golden-principles and taste-lints axes to the PR diff by passing the base branch detected in step 1 (stored as `BASE_BRANCH`) as `--diff-scope`, quoted, so the gates evaluate only changed files, not the whole tree:
   - local axis 1: Skill(skill="code-qualities-assessment")
   - local axis 2: Skill(skill="golden-principles"), invoking `python3 <scan_principles.py> --diff-scope "origin/$BASE_BRANCH"`, where `<scan_principles.py>` is `golden-principles/scripts/scan_principles.py` resolved via the "Path resolution" section (chained-skill scripts). Do not assume the `.claude/` layout. Scope: golden-principles enforces toolkit-artifact governance for GP-001, GP-003, GP-004, GP-005, and GP-006 (script language, skill frontmatter, agent definitions, YAML logic, pinned Actions). GP-002 is enforced by hooks and review practice; GP-007 and GP-008 are enforced by taste-lints. A clean result on a non-toolkit repo means no rule applied, not that design was reviewed.
   - local axis 3: Skill(skill="taste-lints"), invoking `python3 <taste_lints.py> --diff-scope "origin/$BASE_BRANCH"`, where `<taste_lints.py>` is `taste-lints/scripts/taste_lints.py` resolved via the "Path resolution" section (chained-skill scripts). Do not assume the `.claude/` layout.
6. **Extract verdict per axis**. Each axis output ends with a line matching `(?m)^\s*(?i:(?:Final\s+)?Verdict):\s*\[?(PASS|WARN|CRITICAL_FAIL|REJECTED|FAIL|NEEDS_REVIEW|NON_COMPLIANT|COMPLIANT|PARTIAL|UNKNOWN)(?![|A-Z_])\]?` (label case-insensitive; tokens case-sensitive uppercase; trailing lookahead rejects template-form lines like `VERDICT: [PASS|WARN|CRITICAL_FAIL]` and token-prefix collisions). Use `extract_verdict` from the verdict library (resolved per "Path resolution") to parse. If a skill crashes or returns no parseable verdict, mark that axis `UNKNOWN` and continue (do not abort).
7. **Merge verdicts** via `merge_verdicts([...])`, passing the Stage-1 `spec-compliance` verdict plus one verdict per Stage-2 axis (the 11 discovered non-spec canonical axes plus the 3 chained skills; 15 total with the current set). Rules: any token in `FAIL_VERDICTS` (`CRITICAL_FAIL`/`REJECTED`/`FAIL`/`NEEDS_REVIEW`/`NON_COMPLIANT`) -> `CRITICAL_FAIL`; any `WARN` or `PARTIAL` -> `WARN`; any `UNKNOWN` or unrecognized token -> `UNKNOWN`; all `PASS`/`COMPLIANT` -> `PASS`; empty -> `UNKNOWN`. When Stage 1 returns `CRITICAL_FAIL` (step 2 short-circuit), skip this merge: the FINAL VERDICT is `CRITICAL_FAIL`. A Stage-1 `UNKNOWN` does NOT short-circuit; it is merged like any other axis (issue #2690).
8. **Emit findings table** (see Output below).

## Vendored install (REQ-008-06)

`/review` MUST work in a vendored install in any harness that supports plugins (Claude Code, Copilot CLI, and similar). The skill body and every canonical axis file MUST NOT assume a single hard-coded layout; resolve the verdict library via the "Path resolution" section. The build pipeline copies the entire skill directory (including `references/` and `scripts/`) into plugin installs at `src/copilot-cli/skills/review/`, so `${CLAUDE_SKILL_DIR}/references/` resolves in both layouts without a fallback chain, and the axis set is discovered from that directory. Project-side paths (CI prompts, generator, sync infrastructure) are mentioned in this skill for project maintainers reading the prose, not as runtime dependencies.

## UNKNOWN handling

- A skill that crashes or exits non-zero -> mark axis `UNKNOWN`, log the failure, continue with remaining axes.
- A canonical axis whose output cannot be parsed by `extract_verdict` -> mark `UNKNOWN`.
- UNKNOWN does NOT override real findings: `merge_verdicts(["WARN", "UNKNOWN"])` returns `WARN`. UNKNOWN only matters when it would otherwise be PASS.
- UNKNOWN axes are surfaced explicitly in the output table so the reviewer sees what was not evaluated.

## Output

Findings table with one row per axis:

| Axis | Verdict | Emoji | Summary |
|------|---------|-------|---------|
| spec-compliance | PASS | (from get_verdict_emoji) | (Stage-1 gate; SKIPPED rows below when it short-circuits) |
| analyst | PASS | (from get_verdict_emoji) | (one-line summary) |
| architect | WARN | ... | ... |
| qa | ... | ... | ... |
| security | ... | ... | ... |
| devops | ... | ... | ... |
| roadmap | ... | ... | ... |
| reliability | ... | ... | ... |
| observability | ... | ... | ... |
| agent-safety | ... | ... | ... |
| decision-rigor | ... | ... | ... |
| code-quality | ... | ... | ... |
| code-qualities-assessment | ... | ... | ... |
| golden-principles | ... | ... | ... |
| taste-lints | ... | ... | ... |

**FINAL VERDICT**: [PASS|WARN|CRITICAL_FAIL|UNKNOWN] (from `merge_verdicts`)

Followed by per-axis findings in detail. Each finding:

- **severity**: CRITICAL | IMPORTANT | SUGGESTION
- **category**: short keyword
- **location**: `file:line`
- **recommendation**: one-sentence fix

Categorize a finding as **Critical** if its axis verdict is `CRITICAL_FAIL`, **Important** if `WARN`, **Suggestion** otherwise.

## Write the SHA-bound PASS marker (Issue #1938)

On a **PASS** final verdict (or a WARN where every WARN was acknowledged), write a
SHA-bound marker so `/ship` can prove the shipped code was reviewed at its current
state without re-running the review. Skip this on `CRITICAL_FAIL`, on a Stage-1
short-circuit, and on `UNKNOWN`: a non-PASS verdict must not leave a marker.

The marker is a git trailer (vendor-safe: it lives in the commit, travels in every
clone, needs no `.agents/` access). Its contract, quoted verbatim from the reader
`.claude/skills/review/scripts/validate_review_marker.py` (`MARKER_TRAILER_KEY = "Reviewed-By"`),
is:

```text
Reviewed-By: /review@<comma-separated-axis-list> on <reviewed-tip-sha>
```

A commit cannot name its own SHA in a trailer (the SHA hashes the trailer, so
writing the SHA changes the SHA, with no fixed point). So record the reviewed tip,
then write an **empty marker commit** on top of it:

1. `REVIEWED_TIP=$(git rev-parse HEAD)` (the code that was reviewed).
2. Build the axis list from the axes that ran (comma-separated stems, e.g.
   `analyst,architect,qa,security,...`).
3. `git commit --allow-empty -m "review: /review PASS marker" --trailer "Reviewed-By: /review@<axis-list> on $REVIEWED_TIP"`

The marker commit adds no code. SHA-binding holds: the marker is valid only while
its parent (the reviewed tip) is HEAD's parent. Land any new code commit and the
marker no longer sits on HEAD's parent, so the review is correctly treated as stale.
Issue #1938 records the design.

Re-running `/review` after the verdict is still PASS writes another marker commit;
that is safe (idempotent in effect: the latest marker binds the current tip).

## Principles

- **Strict superset of CI**. Any finding CI surfaces, `/review` surfaces first.
- **Drift fails closed**. If `.claude/skills/review/references/` and `.github/prompts/` diverge, the pre-push hook blocks the push. CI re-checks as a backstop.
- **UNKNOWN is information**. A skill that did not evaluate is not a silent PASS.
- **Vendored survival**. `/review` works in a `.claude/`-only checkout. No axis or skill references `.agents/` or `.github/`.

## Verification

- [ ] The `spec-compliance` Stage-1 axis file exists under `references/spec-compliance.md` and runs before Stage 2 (Process step 2)
- [ ] Every non-spec `references/*.md` file is discovered and run as a Stage-2 canonical axis (11 with the current set: analyst, architect, qa, security, devops, roadmap, reliability, observability, agent-safety, decision-rigor, code-quality)
- [ ] Each axis emits a parseable verdict line per the `extract_verdict` regex
- [ ] The verdict library resolves under one of the two documented candidate paths
- [ ] `merge_verdicts` produces a single final verdict consistent with the rules in Process step 7
- [ ] On a Stage-1 `CRITICAL_FAIL`, Stage 2 axes are marked `SKIPPED` and the final verdict is the Stage-1 `CRITICAL_FAIL`; on a Stage-1 `UNKNOWN` (INCONCLUSIVE), Stage 2 STILL runs and the UNKNOWN is carried into the merge (it never suppresses a real Stage-2 finding such as a security `CRITICAL_FAIL`)
- [ ] When Stage 2 runs, the output table contains the spec-compliance row plus one row per discovered non-spec canonical axis plus the 3 chained skills (15 rows with the current set), plus the final verdict line

## Refs

- Verdict module: `.claude/lib/ai_review_common/verdict.py` (Claude layout) or `lib/ai_review_common/verdict.py` (vendored layout, plugin-root relative).
- Canonical axes: every `.claude/skills/review/references/*.md` (Claude layout) or `${CLAUDE_SKILL_DIR}/references/*.md` resolved at runtime (works in both layouts); `spec-compliance` is the Stage-1 gate, and the non-spec files form the discovered Stage-2 axis set.
- Skill chain: `.claude/skills/{code-qualities-assessment,golden-principles,taste-lints}/` (the build pipeline copies these into the plugin install too).

(Spec, generator, and drift hook live outside the vendored surface and are
not referenced from this skill body. Vendored installs work without them.)

## Copilot CLI invocation reference

This skill body uses Claude Code call syntax. Under GitHub Copilot CLI, translate as follows (verified against Copilot CLI 1.0.66-1).

### Sub-skill calls

| Claude Code syntax | Copilot CLI equivalent |
| --- | --- |
| `Skill(skill="code-qualities-assessment")` | `skill` tool, `skill: "code-qualities-assessment"` |
| `Skill(skill="golden-principles")` | `skill` tool, `skill: "golden-principles"` |
| `Skill(skill="taste-lints")` | `skill` tool, `skill: "taste-lints"` |

### Sub-agent calls

| Claude Code syntax | Copilot CLI equivalent |
| --- | --- |
| `Task(subagent_type="analyst")` | `task` tool, `agent_type: "project-toolkit:analyst"` |
| `Task(subagent_type="general-purpose")` | `task` tool, `agent_type: "project-toolkit:general-purpose"` |
| `Task(subagent_type="{role}")` | `task` tool, `agent_type: "project-toolkit:{role}"` |

If a referenced skill or agent is unavailable in the Copilot CLI environment, perform that step inline and note the reduced coverage.
