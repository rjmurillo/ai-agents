---
name: pr-quality-all
version: 1.0.0
description: Run all six PR quality axes (security, QA, analyst, architect, DevOps, roadmap) against your working changes and merge their verdicts into one. Use when you say `run all the quality gates`, `pr-quality all`, or `full pre-push review`. Do NOT use to run one axis on its own (use pr-quality-security or its sibling for that axis), and do NOT use as the pre-merge gate (use review).
license: MIT
allowed-tools: Bash(git:*), Skill
argument-hint: base-branch
model: haiku
model-rationale: cost. The 'haiku' rolling alias resolves via the platform model_tiers map to a tier priced below the sonnet-tier harness default; this unit is routing/mechanical work where the cheaper tier suffices (ADR-080 rule 3).
user-invocable: true
---

# PR Quality Gate: All Axes

<!-- vendor-portability: contributor-facing pre-push gate for the rjmurillo/ai-agents
     repo itself. It cites .claude/lib/ai_review_common/verdict.py and
     .claude/lib/ai_review_common/issue_triage.py as the canonical merge and emoji
     tables, so its audience is repo contributors, not plugin consumers
     (ADR-083, issue #5632). -->

Run all six quality axes against your working changes, then merge their verdicts
into one answer about whether this branch is safe to push.

Migrated from the pr-quality/all command under ADR-064, which makes skills the
single user-invocable surface and renames the namespaced sub-command
pr-quality/all to pr-quality-all. The command file is gone, so its path is named
here in plain text rather than as a citation to something a reader could open.

## Triggers

`run all the quality gates`, `pr-quality all`, `full pre-push review`,
`run every review axis`

## Arguments

Base branch: the problem statement from the conversation (under Copilot CLI the skill tool takes no argument vector, so state it in your message)

If `$ARGUMENTS` names a branch, forward it to every axis. Otherwise default to
`main`. The base is forwarded verbatim so all six judge the same diff.

## Process

1. Run `git branch --show-current` to name the current branch.
2. Resolve the base branch from `$ARGUMENTS`, defaulting to `main`.
3. Run `git diff "<base_branch>" --name-only | wc -l`. If it reports zero
   changed files, emit PASS and stop; there is nothing for any axis to read.
4. Invoke each axis through the `Skill` tool, forwarding the base branch:
   `pr-quality-security`, `pr-quality-qa`, `pr-quality-analyst`,
   `pr-quality-architect`, `pr-quality-devops`, `pr-quality-roadmap`.
5. Parse each axis's `VERDICT: TOKEN` line. An axis that crashed or returned no
   parseable verdict is UNKNOWN, never PASS.
6. Merge the six tokens with the table below, then emit the summary.

## Verdict Aggregation

Canonical: `.claude/lib/ai_review_common/verdict.py:merge_verdicts`.

- ANY `CRITICAL_FAIL`, `REJECTED`, `FAIL`, `NEEDS_REVIEW`, or `NON_COMPLIANT` -> Final: **CRITICAL_FAIL**
- ANY `WARN` or `PARTIAL` (no critical failures) -> Final: **WARN**
- ANY `UNKNOWN` (no critical, no warn) -> Final: **UNKNOWN**
- ALL `PASS` or `COMPLIANT` -> Final: **PASS**
- Empty input -> Final: **UNKNOWN**

UNKNOWN downgrades a would-be PASS so a missing or crashed axis cannot silently
produce a green verdict. Real WARN and CRITICAL_FAIL findings override UNKNOWN.

## Output Summary

Generate the consolidated report in EXACTLY this format. Do not add preambles or explanations before the table:

| Agent | Verdict | Status | Key Findings |
|-------|---------|--------|--------------|
| Security | [verdict] | [emoji] | [summary] |
| QA | [verdict] | [emoji] | [summary] |
| Analyst | [verdict] | [emoji] | [summary] |
| Architect | [verdict] | [emoji] | [summary] |
| DevOps | [verdict] | [emoji] | [summary] |
| Roadmap | [verdict] | [emoji] | [summary] |

**FINAL VERDICT**: [PASS|WARN|UNKNOWN|CRITICAL_FAIL]

Emoji mapping, canonical at `.claude/lib/ai_review_common/issue_triage.py:get_verdict_emoji`:
PASS and COMPLIANT are a check mark, WARN and PARTIAL a warning sign,
CRITICAL_FAIL / REJECTED / FAIL / NEEDS_REVIEW / NON_COMPLIANT a cross mark, and
UNKNOWN a question mark.

**Next Steps**:

- **PASS**: Safe to commit and push
- **WARN**: Review findings, address if time permits, safe to push
- **UNKNOWN**: At least one axis failed to evaluate (skill crashed, no parseable verdict). Investigate which axis and re-run; do NOT treat as PASS.
- **CRITICAL_FAIL**: Fix blocking issues before pushing

## Verification

- [ ] All six axes ran, or each absent one is reported UNKNOWN by name
- [ ] Every axis received the same resolved base branch
- [ ] The final verdict follows the merge table, not a judgement call
- [ ] No axis returning UNKNOWN was rolled up into PASS
- [ ] The table is the first thing emitted, with no preamble
- [ ] Each row's findings cite a file, or say the axis found nothing

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Stopping after the first CRITICAL_FAIL axis | The author gets one finding per round instead of the whole list, which is the iteration paradox this gate exists to avoid | Run all six, then merge |
| Rolling UNKNOWN up into PASS | A crashed axis then reads as a clean one, so the gate is green exactly when it measured least | Let UNKNOWN downgrade, and name the axis that failed |
| Re-deriving the merge rules here | Two copies of a table drift, and the copy in a prompt drifts first | Follow the canonical merge function; this page quotes it |
| Running the axes on different bases | Six verdicts about six diffs do not merge into one answer | Resolve the base once and forward it verbatim |
| Treating this as the pre-merge gate | It reads working changes, not the PR; `review` is the gate `ship` checks | Run this before pushing, and `review` before shipping |

## Extension Points

- **A seventh axis.** Add its `pr-quality-<name>` skill, then add one row here and
  one line to step 4. The merge table is unchanged: it is token-based, not
  axis-count-based.
- **Different merge policy.** The rules live in `verdict.py`. Change them there
  and every consumer, this skill and CI alike, moves together.
- **Machine consumption.** Each axis emits schema-bound JSON alongside its
  verdict, so a downstream reader parses those rather than this table.
