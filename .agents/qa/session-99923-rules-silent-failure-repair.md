---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-21-session-99923-2dd747176-rules-silent-failure-repair.json
qaCommit: 14d6c91f1979747c56c1d76c2b24be7dfd59694b
---

# QA Report: repair-to-a-silent-failure rule (issue #5188)

- Issue: #5188
- Branch: `claude/issue-5188-silent-failure-repair`
- QA commit: `14d6c91f1979747c56c1d76c2b24be7dfd59694b`
- Session log: `.agents/sessions/2026-08-21-session-99923-2dd747176-rules-silent-failure-repair.json`

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
