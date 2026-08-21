---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-21-session-99923-2dd747176-rules-silent-failure-repair.json
qaCommit: bc980a8698ffba26e510f86c254e7087b9e6dcbe
---

# QA Report: repair-to-a-silent-failure rule (issue #5188)

- Issue: #5188
- Branch: `claude/issue-5188-silent-failure-repair`
- QA commit: `bc980a8698ffba26e510f86c254e7087b9e6dcbe`
- Session log: `.agents/sessions/2026-08-21-session-99923-2dd747176-rules-silent-failure-repair.json`




## Claims this session got wrong about other components

Four, all found by reviewers, none by a gate. Three share one shape: a statement
about what some other code or rule does, written without opening it.

| Claim as written | What the source actually says |
|---|---|
| `claude-agents.md` MUST NOT 2 forbids bundling rule changes with code | It forbids bundling skill code changes with memory changes. Nothing about rule changes or code generally. |
| `branch-context-policy` requires a log naming the current branch | `check_branch_context` returns 0 when no log exists for today. It errors only when another recent log names a different branch, and a current-branch log is one of several remedies. |
| No skill applies to a rule-text edit | `ai-agents-generation-and-release` owns `.claude/rules/` mirror regeneration and names `build_all.py`. |
| SHOULD 4 cites "MUST 10 through 12" | `10.` appears twice in this file's MUST section, so the ordinal resolves two ways. The item now names the three headings. |

`canonical-source-mirror.md` has a section for the first three, "Behavioral claims:
read the body, not the name", and `knowledge-persistence.md` MUST NOT 4 covers the
third specifically, since "no skill applies" is an absence asserted from no search.
Both rules were loaded for the whole session.

The cost is visible rather than hypothetical. The misread citation reached this
log, the extracted episode, three PR bodies, several commit messages, and then an
automated spec validator, which listed "Not bundled with code (claude-agents.md
MUST NOT 2)" as a requirement it had verified. A wrong citation that names a real
file and a real item number does not read as a guess, so downstream readers adopt
it without re-deriving it.

One near-miss worth recording. The first check of the duplicate-numbering claim
used `head -20`, which truncated before the second `10.` at line 48 and returned a
clean 1-to-20 sequence. That output looked like disconfirming evidence. The claim
survived only because the reviewer cited line 48 and line 48 was absent from the
output. A vaguer report would have been "refuted" with a plausible transcript.

Also removed: `src/copilot-cli/skills/**`, added during the scope expansion and
subsumed by the pre-existing `src/copilot-cli/skills/**/scripts/**` and
`.../tests/**`. The spec validator caught the redundancy.

Not fixed here, because it is pre-existing and repo-wide: `ci-scripts.md` has two
MUST items numbered 10 in its MUST section, and `testing.md` has two numbered 12
in its own, so every ordinal citation to those four items is ambiguous.

The count in an earlier version of this paragraph was six, which was a guess
rather than a measurement and is the mistake this report exists to catch. Filed
as issue #5211 with a real sweep instead: 13 ambiguous citations in tracked files
at `7d76c4d7f`, 4 to `ci-scripts.md` MUST 10 and 9 to `testing.md` MUST 12.

That number is recorded as a floor, not a total. Both regexes require the file
name near the ordinal, so a bare "MUST 10" with the file named a sentence earlier
does not match. The issue carries the commands so the next reader re-runs them
rather than trusting the figure. Citations to `testing.md` MUST 10 and
`ci-scripts.md` MUST 12 also exist and are **not** ambiguous, so the sweep cannot
be done by ordinal alone.

Renumbering touches every downstream reference and belongs in its own change.

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

Measured after the final scope, `.claude/commands/**`, `.github/scripts/**`, and
`tests/**`: the `.py` row reads 98236 / 99000 with 764 free, byte-identical to
the baseline before the change.

Two corrections to how that number was first written up, both from review.

`src/copilot-cli/skills/**` was in this sentence and is not in the shipped rule.
It was added during the expansion and dropped two commits later as redundant
against the pre-existing `skills/**/scripts/**` and `skills/**/tests/**`
entries, and this line kept naming it, so a reader checking the frontmatter
would not have found it.

The expansion was also called **free**, which overstates what was measured.
`instruction_budget.py` counts only language-universal globs, so a byte-identical
`.py` row proves the *always-on* baseline is unchanged and proves nothing about
total cost. A directory-scoped rule is still loaded, in full, by anyone editing a
file the glob matches. The accurate claim is narrower and is the one that
mattered for the decision: the expansion costs nothing against the ceiling this
repository gates on, which is why it did not have to be traded against coverage.
Whether it is free to a contributor editing `tests/` is a different question and
the answer there is no.

## Verdict

PASS.

## Scope under test

Two edits to `.claude/rules/ci-scripts.md`, plus its two instruction mirrors
regenerated from both. SHOULD 4 is the new item. The frontmatter `paths:` gains
`.claude/commands/**` and `tests/**`, so the item loads on the two trees the
incident actually happened in. No code, no test, no workflow.

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
`ci-scripts.md`'s three MUST items on non-zero exits already govern converting every failure signal
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

## The rule's own evidence is now checkable in-tree

When SHOULD 4 was written, its four measured repairs lived on PR #5176's
unmerged branch, so the item quoted them. That PR merged to `main` at 2026-08-21
06:03:28 UTC as `15f95d2b6`, and `origin/main` is merged into this branch, so
the code the item describes is here.

The third repair is the one worth checking, because it is the one that granted a
merge: a bare `tostring` coerced the string `"true"` into boolean `true`, so
malformed evidence satisfied the guard built to reject it. Checked rather than
assumed. `.claude/commands/pr-autofix.md:462` now reads:

```
PAGES_COMPLETE=$(printf '%s' "$MERGE_READY" | jq -r 'if (.fetched_pages_complete | type) == "boolean" then (.fetched_pages_complete | tostring) else "unknown" end')
```

The type check precedes the coercion, and lines 457 to 458 above it carry the
comment naming the defect the rule cites. So the item's central claim, that
converting instead of validating fails open on exactly the path the guard exists
to protect, has a fix in the tree a reader can open.

Line numbers drift. Re-derive with `grep -n "fetched_pages_complete | type"
.claude/commands/pr-autofix.md` rather than trusting the number here; that is
the same discipline the rule asks for and this report has already broken twice
by pinning a measurement where a property belonged.

## What is deliberately not claimed

The item is a SHOULD and nothing enforces it. A gate that could enforce it would
have to know which repairs address a silent failure, which is not derivable from a
diff. This report does not claim coverage the change does not have.
