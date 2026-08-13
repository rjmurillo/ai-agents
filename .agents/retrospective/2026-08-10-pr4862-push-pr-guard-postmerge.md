# PR 4862 push-pr guard: five reproduced regressions, then seven more found by review

**Date**: 2026-08-10
**Scope**: `.claude/hooks/PreToolUse/invoke_push_pr_script_identity_guard.py` and its
new sibling modules, `.claude/skills/github/scripts/pr/new_pr.py`,
`build/scripts/generate_hooks_events.py`, `build/scripts/generate_hooks_transaction.py`
**Trigger**: Issue #4764, PR #4825 merged at `5cd72a7dad`, this branch at PR #4862

## What happened

PR #4825 shipped a PreToolUse guard that closes the #4764 wildcard hole: a
prompt-injected diff could point `/push-pr` at a repository-controlled
`new_pr.py` lookalike and get user-level Python execution. The guard merged
with a full test suite and a security review.

Five defects were then reproduced against the merged tree before any fix was
written: an extglob bypass, false denials of read-only commands, a Python 3.10
ImportError that removed `/push-pr` from every 3.10 host, brace-expansion
memory amplification, and a validator warning printed under a
"validations passed" summary.

Fixing the second one, the false denials, introduced three new holes. Narrowing
relevance from "the text mentions new_pr.py" to "the path sits in an execution
position" is the right rule, and it silently dropped three ways a path reaches
execution without occupying a command position in its own segment:

1. A pipeline: `echo python3 X | sh`, `echo X | xargs python3`, `cat X | python3`.
2. Git as a command runner: `bisect run`, `submodule foreach`, `rebase -x`,
   `filter-branch --tree-filter`, `difftool -x`, `send-email --smtp-server`.
3. A per-call expansion budget, which bounded one enumeration while the guard
   ran thousands of them: 100.5 seconds against a 10 second host timeout that
   fails OPEN on Copilot.

A security review found all three. A code review then found four more,
including two that the pipeline fix itself created: a consumer the lexer cannot
parse (`| (sh)`) vanished from the segment list, and the renamed-copy rule was
never told about the pipe, so `echo python3 copy.py | sh` was allowed while
`python3 copy.py` was denied.

## Failure mode classification

**Primary: #4 False completion markers** (`.agents/governance/FAILURE-MODES.md`).
The merged guard's evidence was a passing suite and a clean review, and both
were true. Neither is evidence that the guard denies what it claims to deny,
because both measured what the author thought to measure. The five post-merge
defects were found by probing the merged binary with inputs nobody had written
a test for.

**Secondary: #8 Security drift.** Each of the three review-found holes is a
narrowing that was correct in isolation and lossy in composition. The relevance
rule got safer for `git diff` and less safe for `echo | sh` in the same commit,
and the suite could not see it because no test spanned two segments.

## Root cause

Five whys on the pipeline hole, which is the most instructive:

1. Why was `echo python3 X | sh` allowed? Because the reader's operands were
   classified as data.
2. Why? Because `_operands_are_data` asks what the segment's own command does
   with its operands, and `echo` reads them.
3. Why did that answer decide the whole command? Because `_scope_segments`
   split on shell operators and threw the operators away, so the pipe that
   joins a reader to a shell was not in the model.
4. Why was the operator dropped? Because the pre-existing splitter returned a
   list of strings, and the false-denial fix consumed it as-is rather than
   asking what a segment's output feeds.
5. Why did no test catch it? Because every guard test was a single-segment
   command. The suite had 952 cases across two dispatchers and not one
   pipeline where the two halves had different roles.

The root cause is a model gap, not a coding error: the guard modeled a command
as a set of independent segments, and a shell pipeline is a dataflow graph.

## Impact

| Area | Severity | Detail |
|---|---|---|
| Security | High | Three execution paths the merged guard denied were allowed on this branch before review. None reached `main`. |
| Availability | High | `/push-pr` was broken on every Python 3.10 host and denied ordinary `git diff` and `pytest` commands. |
| Cost | Medium | A 121 KiB command took 100.5 seconds inside the guard, against a 10 second host timeout that fails open on Copilot. |
| Trust in output | Medium | A validator failure printed under a pass summary, twice: once in Validation 4, once in the legacy session-log branch found later by review. |

## What worked

**Reproducing before fixing.** Every one of the five defects was measured
against the merged guard's own file, and the measurement is in the test
docstring. That made each fix falsifiable and made the "did this regress?"
question answerable by rerunning one command.

**Inverse controls in the same commit.** Each fix shipped with the command it
must keep allowing. The pipe rule ships with `git diff -- X | cat`; the Git
operand walk ships with `git bisect start`; the shared budget ships with
`touch log{0..99}.txt`. Two of the review findings were caught because a
control failed, not because a reviewer read carefully.

**Reviewing the fix, not the reasoning.** The security and code reviews were
given the diff and the claim, not the derivation, and both found holes the
author's own reasoning had produced. Seven of the twelve defects in this branch
came from those two reviews.

**Measuring against the previous implementation.** Both reviews ran the same
input through the merged guard and this branch. That is what turned "this looks
wrong" into "this is a regression, and here is the exit code from each".

## What did not work

**A green suite as evidence of coverage.** 952 dispatcher tests passed while
three execution classes were open. Test count measured effort, not reach.

**Trusting a narrowing to be local.** The false-denial fix changed one
predicate and altered the meaning of every rule downstream of it. Nothing in
the change made that reach visible.

**Session protocol.** This session ran without a session log until the pre-push
gate demanded one, which is failure mode #1, and it is the reason this
retrospective exists at push time rather than at the point the work was done.

## Remediation

| Action | Status | Reference |
|---|---|---|
| Pipeline dataflow in the relevance gate, with transitive walk | Done | PR #4862 |
| Git execution-operand table consulted by relevance, not only policy | Done | PR #4862 |
| One expansion budget per command instead of per call | Done | PR #4862 |
| Unparseable pipeline segment keeps its position and fails closed | Done | PR #4862 |
| Renamed-copy rule sees the operands the pipe rule opened | Done | PR #4862 |
| Legacy session-log warning recorded instead of printed | Done | PR #4862 |
| Republished hooks get a new mtime so `__pycache__` cannot go stale | Done | PR #4862 |
| atomic-commit counter miscounts generated hook shims | Filed | #4857 |
| Claude dispatcher drops the declared per-shim timeout | Filed | #4858 |
| `plugin-load-e2e` fails instead of skipping on expired CLI auth | Filed | #4861 |

## Learnings captured

- A guard that decides per segment needs a test whose segments have different
  roles. Single-segment corpora cannot detect a dataflow gap, however large
  they are.
- A budget that bounds one call bounds nothing when the caller loops. State the
  budget's scope in its name or its type, not in a comment.
- Narrowing a security rule is a composition change. The test that proves the
  narrowing correct is the one that exercises what the rule used to catch.
- Hand a reviewer the artifact and the claim, never the derivation. Both
  reviews here found defects that the author's reasoning had produced and would
  have re-derived.
