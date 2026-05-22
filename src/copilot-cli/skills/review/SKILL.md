---
name: review
version: 1.0.0
description: Review before merge. Nine-axis review across 6 canonical axes (analyst, architect, qa, security, devops, roadmap) plus 3 chained skills (code-qualities-assessment, golden-principles, taste-lints). Run after /test.
allowed-tools: Task, Skill, Read, Glob, Grep, Bash(*)
license: MIT
---

# Review

Review: $ARGUMENTS

If no argument, review the current branch diff against the base branch. Detect the base branch from `gh pr view --json baseRefName` or fall back to `main`.

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `/review` | Run the nine-axis review against the current branch diff |
| `/review BRANCH_OR_PR` | Run the nine-axis review against the named branch or PR |
| `review before merge` | Same as `/review` |

## Convergence contract (REQ-008-04)

`/review` evaluates the same axes as the project's CI quality gate, plus three local-only skill axes that CI cannot afford. The 6 canonical axis prompts are authored at `references/{role}.md` co-located with this skill, with the canonical path expressed as `.claude/skills/review/references/{role}.md` in the source repo (the single source of truth). When CI exists in a project, the project syncs the canonical axes into its own CI prompts via the project's generator and drift checks. The build pipeline copies the entire skill directory (including `references/`) into vendored plugin installs so the command runs without a CI dependency in any harness that supports plugins.

`/review` is a strict superset of CI: any finding CI surfaces, `/review` will surface first locally. The 3 chained skill extras (`code-qualities-assessment`, `golden-principles`, `taste-lints`) cannot run in CI (they require code execution + repo state) and so layer on top.

## Path resolution (harness-agnostic)

This skill runs in two layouts: the source Claude Code project (where `.claude/` is the repo root) and a vendored plugin install (Copilot CLI and similar harnesses) where the consumer repo has no `.claude/` directory and the plugin lives outside the consumer's tree.

- **Canonical axis prompts** (`{role}` in `analyst|architect|qa|security|devops|roadmap`): resolve to `${CLAUDE_SKILL_DIR}/references/{role}.md`. The skill directory variable points at this skill in both layouts (source repo and vendored install), so a single path works without a fallback chain.
- **Verdict library** (`merge_verdicts`, `extract_verdict`, `get_verdict_emoji`, `FAIL_VERDICTS`): try each candidate in order, use the first that exists:
  1. `.claude/lib/ai_review_common/verdict.py` (Claude Code project layout)
  2. `lib/ai_review_common/verdict.py` resolved relative to the plugin install root (vendored install)

The skill body MUST NOT hard-fail when the `.claude/` path is missing; it MUST attempt the vendored-install path for the verdict library before reporting an error.

## Process

Run axes sequentially. Each axis emits a verdict token (`PASS`, `WARN`, `CRITICAL_FAIL`, or `UNKNOWN`) plus structured findings (severity, category, location, recommendation). The final merged verdict comes from `merge_verdicts` (resolve via the "Path resolution" section above).

1. Read the diff (`git diff` against detected base branch).
2. **Classify complexity tier**: Task(subagent_type="analyst"): Read `.claude/skills/analyze/references/engineering-complexity-tiers.md` and the diff. Assess as Tier 1-5. Use this to calibrate axis depth.
3. **Run 6 canonical axes**, in order. For each axis, load the canonical prompt for `{role}` via the path resolution above, then invoke the matching `Task(subagent_type=...)` agent (analyst, architect, qa, security, devops, roadmap) with that prompt as the system instruction, the diff as input, and the structured Output Schema from the canonical file as the response contract. If the harness does not register these role subagent types in its `Task` enum (e.g., Copilot CLI today), fall back to `Task(subagent_type="general-purpose")` with the canonical axis prompt as the system instruction; the prompt drives the review, not the subagent identity.
   - axis 1: `analyst`
   - axis 2: `architect`
   - axis 3: `qa`
   - axis 4: `security`
   - axis 5: `devops`
   - axis 6: `roadmap`
4. **Run 3 chained skill axes** (local-only; CI does not run these):
   - axis 7: Skill(skill="code-qualities-assessment")
   - axis 8: Skill(skill="golden-principles")
   - axis 9: Skill(skill="taste-lints")
5. **Extract verdict per axis**. Each axis output ends with a line matching `(?m)^\s*(?i:(?:Final\s+)?Verdict):\s*\[?(PASS|WARN|CRITICAL_FAIL|REJECTED|FAIL|NEEDS_REVIEW|NON_COMPLIANT|COMPLIANT|PARTIAL|UNKNOWN)(?![|A-Z_])\]?` (label case-insensitive; tokens case-sensitive uppercase; trailing lookahead rejects template-form lines like `VERDICT: [PASS|WARN|CRITICAL_FAIL]` and token-prefix collisions). Use `extract_verdict` from the verdict library (resolved per "Path resolution") to parse. If a skill crashes or returns no parseable verdict, mark that axis `UNKNOWN` and continue (do not abort).
6. **Merge verdicts** via `merge_verdicts(["v1", ..., "v9"])`. Rules: any token in `FAIL_VERDICTS` (`CRITICAL_FAIL`/`REJECTED`/`FAIL`/`NEEDS_REVIEW`/`NON_COMPLIANT`) -> `CRITICAL_FAIL`; any `WARN` or `PARTIAL` -> `WARN`; any `UNKNOWN` or unrecognized token -> `UNKNOWN`; all `PASS`/`COMPLIANT` -> `PASS`; empty -> `UNKNOWN`.
7. **Emit findings table** (see Output below).

## Vendored install (REQ-008-06)

`/review` MUST work in a vendored install in any harness that supports plugins (Claude Code, Copilot CLI, and similar). The skill body and every canonical axis file MUST NOT assume a single hard-coded layout; resolve the verdict library via the "Path resolution" section. The build pipeline copies the entire skill directory (including `references/`) into plugin installs at `src/copilot-cli/skills/review/`, so `${CLAUDE_SKILL_DIR}/references/{role}.md` resolves in both layouts without a fallback chain. Project-side paths (CI prompts, generator, sync infrastructure) are mentioned in this skill for project maintainers reading the prose, not as runtime dependencies.

## UNKNOWN handling

- A skill that crashes or exits non-zero -> mark axis `UNKNOWN`, log the failure, continue with remaining axes.
- A canonical axis whose output cannot be parsed by `extract_verdict` -> mark `UNKNOWN`.
- UNKNOWN does NOT override real findings: `merge_verdicts(["WARN", "UNKNOWN"])` returns `WARN`. UNKNOWN only matters when it would otherwise be PASS.
- UNKNOWN axes are surfaced explicitly in the output table so the reviewer sees what was not evaluated.

## Output

Findings table with one row per axis:

| Axis | Verdict | Emoji | Summary |
|------|---------|-------|---------|
| analyst | PASS | (from get_verdict_emoji) | (one-line summary) |
| architect | WARN | ... | ... |
| qa | ... | ... | ... |
| security | ... | ... | ... |
| devops | ... | ... | ... |
| roadmap | ... | ... | ... |
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

## Principles

- **Strict superset of CI**. Any finding CI surfaces, `/review` surfaces first.
- **Drift fails closed**. If `.claude/skills/review/references/` and `.github/prompts/` diverge, the pre-push hook blocks the push. CI re-checks as a backstop.
- **UNKNOWN is information**. A skill that did not evaluate is not a silent PASS.
- **Vendored survival**. `/review` works in a `.claude/`-only checkout. No axis or skill references `.agents/` or `.github/`.

## Verification

- [ ] All 6 canonical axis files exist under `references/{role}.md`
- [ ] Each axis emits a parseable verdict line per the `extract_verdict` regex
- [ ] The verdict library resolves under one of the two documented candidate paths
- [ ] `merge_verdicts` produces a single final verdict consistent with the rules in Process step 6
- [ ] The output table contains exactly 9 rows (6 canonical + 3 chained skills) plus the final verdict line

## Refs

- Verdict module: `.claude/lib/ai_review_common/verdict.py` (Claude layout) or `lib/ai_review_common/verdict.py` (vendored layout, plugin-root relative).
- Canonical axes: `.claude/skills/review/references/{role}.md` (Claude layout) or `${CLAUDE_SKILL_DIR}/references/{role}.md` resolved at runtime (works in both layouts).
- Skill chain: `.claude/skills/{code-qualities-assessment,golden-principles,taste-lints}/` (the build pipeline copies these into the plugin install too).

(Spec, generator, and drift hook live outside the vendored surface and are
not referenced from this skill body. Vendored installs work without them.)
