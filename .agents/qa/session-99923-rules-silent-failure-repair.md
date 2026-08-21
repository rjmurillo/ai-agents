---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-21-session-99923-2dd747176-rules-silent-failure-repair.json
qaCommit: 54fd840da5fda5d1c3cbd81218c8a129a61a569f
---

# QA Report: repair-to-a-silent-failure rule (issue #5188)

- Issue: #5188
- Branch: `claude/issue-5188-silent-failure-repair`
- QA commit: `54fd840da5fda5d1c3cbd81218c8a129a61a569f`
- Session log: `.agents/sessions/2026-08-21-session-99923-2dd747176-rules-silent-failure-repair.json`



## A citation this session got wrong

The session evidence justified splitting this rule change out of PR #5176 by
citing `.claude/rules/claude-agents.md` MUST NOT 2 as a prohibition on bundling
rule changes with code. That is not what the item says. Read verbatim:

> 2. MUST NOT bundle skill code changes with memory changes in the same PR (separate concerns).

It governs skill code against memory, and says nothing about rule changes or
about code generally. Copilot found the misreading.

The failure is worth recording because of its shape rather than its size. The
claim named a real file and a real item number, so every artifact downstream
inherited its authority without re-deriving it: this log, the extracted episode,
the PR body, and several commit messages. `canonical-source-mirror.md` states
the cost directly, that a wrong citation is worse than no citation because it
weaponizes the next reader's trust, and `knowledge-persistence.md` MUST NOT 3
prescribes the step that would have caught it: grep the rule tree and cite the
file and item number, or drop the attribution and let the advice stand on its
own reason.

Two aggravating details. The correct reading was already in this repository: a
2026-07-26 session log quotes the item verbatim and applies it correctly to a
memory-plus-skill-code bundle, so contradicting evidence was in-tree and never
searched for. And the error reached a generated memory record, which is why the
repair regenerates the episode from the corrected log rather than editing the
episode.

The decision is unchanged, because it never needed the rule. PR #5176 already
carries `needs-split` at 17 files, and adding three rule files plus six
generated mirrors to a shell-and-tests fix makes it materially harder to review.
That reason was always sufficient on its own.

## Scope corrected after review

The rule shipped scoped to `scripts/**`, `build/**`, workflows, and skill
scripts, and the PR body defended that as a trade-off forced by the always-on
instruction budget. Copilot pointed out the consequence: two of the four
measured instances lived in `.claude/commands/pr-autofix.md` and under
`tests/commands/`, so the lesson did not load on the surfaces that produced it.

The trade-off was not real, and the error is worth recording because the
measurement behind it was sound. `scripts/validation/instruction_budget.py`
counts only rules whose generated `applyTo` is language-universal (`**`,
`**/*`, or `**/*.<ext>`); its own docstring says "Directory scoped rules (for
example `tests/**`) are situational, not always-on, so they are excluded by
design." The 764-byte headroom on the `.py` row is a constraint on
extension-scoped rules. It says nothing about adding a directory glob, which is
what the fix needed. So an accurate number was applied to the wrong question.

Measured after adding `.claude/commands/**`, `src/copilot-cli/skills/**`, and
`tests/**`: the `.py` row reads 98236 / 99000 with 764 free, byte-identical to
the baseline before the change. The expansion is free.

## Verdict

PASS.

## Scope under test

One item added to `.claude/rules/ci-scripts.md` (SHOULD 4) and its two instruction
mirrors regenerated. No code, no test, no workflow.

## The measurement that chose the file

This is the only interesting part of the change, and it is the reason the rule is
not where a reader would first expect.

The lesson is about repairing code, so the first draft went into
`pragmatic-programmer.md`, whose scope is a list of code extensions. That failed:

| Target | `.py` always-on row | Status |
|---|---|---|
| baseline before any edit | 98236 / 99000, 764 free | PASS |
| `pragmatic-programmer.md`, full item | 99645 / 99000, 645 **over** | **FAIL** |
| `pragmatic-programmer.md`, compressed | 98917 / 99000, 83 free | **WARN**, under the 600-byte reserve |
| `ci-scripts.md` (path-scoped) | 98236 / 99000, 764 free | PASS, byte-identical to baseline |

Any rule matching `**/*.py` enters that language baseline, which counts 11 files
rather than the 7 universal ones. The repo is at 99.2% there, so an extension-scoped
rule effectively cannot grow. `scripts/validation/instruction_budget.py` names the
remedy itself: "Scope rules with a narrower applyTo instead of `**` or `**/*.<ext>`."

The WARN row is worth naming rather than quietly discarding. It would have passed a
gate that only rejects FAIL, and it would have left the next contributor 83 bytes.
The reserve exists because two branches measured against the same base can each pass
and still breach once merged.

## Why ci-scripts.md is also the right home on the merits, not just the budget

`knowledge-persistence.md` SHOULD 1 prefers an existing rule over a new file.
`ci-scripts.md` MUST 10 through 12 already govern converting every failure signal
into a non-zero exit, converting every detected violation into a non-zero exit, and
distinguishing a run that did nothing from a run that succeeded. That is the
silent-failure family. Those items govern the original defect; the new item governs
the fix, which is the gap.

## What was verified

| Property | Command | Result |
|---|---|---|
| Mirrors match the rule | `build/scripts/build_all.py --check` | no staleness after commit |
| Language baseline untouched | `scripts/validation/instruction_budget.py` | `.py` row identical to baseline |
| Repository-wide validation | `scripts/validation/pre_pr.py` | all validations passed |
| Session log valid, SHA reachable | `scripts/validate_session_json.py` | PASS |

## What is deliberately not claimed

The item is a SHOULD and nothing enforces it. A gate that could enforce it would
have to know which repairs address a silent failure, which is not derivable from a
diff. This report does not claim coverage the change does not have.
