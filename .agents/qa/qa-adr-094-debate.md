---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-15-session-14712-b79742bf0-run-adr-094-multi-agent-debate.json
qaCommit: f18efba357185f4663806d5394c3d6d510dd51db
---

# QA: ADR-095 debate, rejection record, and renumber

## Scope

This report covers the whole of session 14712, not just its first commit. An
earlier revision scoped it to the debate log plus a 9-line ADR edit; the session
then went further, and the scope below is what actually merges.

| File | Change |
|---|---|
| `.agents/critique/ADR-095-debate-log.md` | New. The 6-role debate, its findings, and the re-measurement of its own claims |
| `.agents/architecture/ADR-095-scoped-re-review-axes.md` | Renamed from `ADR-094-scoped-re-review-axes.md` and rewritten from a 317-line proposal into a 139-line rejection record |
| `.agents/critique/ADR-094-debate-log.md` | Conflict resolution only. Main's file kept verbatim; it belongs to the accepted ADR-094 from PR #5024 |
| `.agents/retrospective/2026-08-15-adr-094-inert-hooks-and-number-collision.md` | New. Required by the `retrospective-policy` pre-push gate |
| `.serena/memories/memory-index.md` | Removed a duplicate `diagnosing-a-blocked-pr` row a main merge left behind |
| `.agents/qa/qa-adr-094-draft.md` | New. Session 14711 needed its own QA binding |
| Three session logs, three QA reports | Rebound to the last non-evidence commit after each of three `origin/main` merges |

No code, no generated artifact, no shipped skill change. Every authored file is
prose or evidence metadata.

## What ran

| Check | Command | Result |
|---|---|---|
| adr-review gate is satisfied | `git_hook_policy.py adr-review` via the `adr-review-policy` pre-commit job | PASS |
| Em-dash and en-dash prohibition (`.claude/rules/universal.md` MUST NOT 5) | Python count of U+2014 and U+2013 over the debate log, the rejection record, and the retrospective | 0 and 0 on all three |
| Banned vocabulary (`.claude/rules/voice.md`) | Python substring scan of the 19-word list over the debate log | 0 hits |
| Markdown lint | `markdown-autofix` and `markdown-check` pre-commit jobs | PASS |
| All three session logs bind and are not stale | `validate_session_json.py --validation-head HEAD` on 14711, 14712, 99916 | PASS on all three |
| Full pre-PR suite | `scripts/validation/pre_pr.py` | RESULT: All validations passed |
| Full pre-push suite | 24 jobs via `git push` | PUSH_RC=0 |
| The memory-index fix is real | `test_every_declared_entrypoint_runs_in_locked_environment` | PASS after the duplicate row was removed |

## Failures found and fixed during this session

| Failure | Cause | Fix |
|---|---|---|
| `adr-review-policy` blocked every commit | The ADR had never had its mandatory debate, because `core.hooksPath` pointed at a nonexistent directory (issue #5090) | Ran the debate and wrote the log the checker requires |
| Two red session-log checks, pre-existing on PR #5062 | Sessions 14711 and 99916 both named one QA report; a report binds to exactly one log | Gave 14711 its own report |
| `merge-tree-ratchet`, `Count Ratchets`, and one pytest node failed pre-push | A main merge left two `memory-index.md` rows for `diagnosing-a-blocked-pr`, at 885 and 919 tokens | `scripts/update_memory_index_tokens.py` per knowledge-persistence MUST-6 |
| `test_mutate_debate_log_path.py::test_m1_directory_name_reverted_is_detected` failed once | Flake. The harness creates git worktrees and the run had 4 parallel workers | Not fixed, diagnosed. It passes in isolation and passed on the next full run. Not a regression from this branch |

## Claims verified against their sources

Every quantitative claim recorded in the debate log was re-measured by the
orchestrator before it was written, not taken from the reporting role.

| Claim | Command | Result |
|---|---|---|
| `/review` became a skill after the cited incidents | `git log --diff-filter=A -- .claude/skills/review/SKILL.md` | `c3ddc571a` 2026-05-24 |
| The SHA-bound marker landed after the cited incidents | `git log --diff-filter=A -- .../validate_review_marker.py` | `16c960418` 2026-06-04 |
| The 009 baseline reports two different signal ratios | `grep -n "52%\|24%\|182\|173" .agents/analysis/009-phase1-agent-comment-baseline.md` | `:163` 52% over 182 comments, `:178` 24% over 173 units |
| Marker census | `git log --all --format='%(trailers:key=Reviewed-By,valueonly)'` | 14 trailer commits, 3 full-set, 11 subset, 4 naming a `code-review` axis |
| No marker commit reached main | `git merge-base --is-ancestor <sha> origin/main` on sampled marker commits, plus a trailer count over `origin/main` | 0 on `origin/main`, all 14 on unmerged refs |
| `references/code-review.md` does not exist | `ls .claude/skills/review/references/` | 12 files, no `code-review.md` |
| No marker-writer script exists | `ls .claude/skills/review/scripts/` | `validate_findings_scope.py`, `validate_review_marker.py` only |

## Correction found and applied

One reporting role's headline measurement did not reproduce. The critic built
its P0-1 on "32 merged PRs carry a review marker on `origin/main`, mean 2.22,
median 1, max 8". `origin/main` carries zero such commits, because this
repository squash-merges and the empty marker commit is discarded. The number
was removed from the recorded finding and replaced with the reproducible form,
and the non-reproduction is documented in the debate log's own verification
section rather than dropped silently.

A second role's marker census was off by one in two counts (3 full-set not 4,
11 subsets not 10). Corrected against a direct count.

## Not verified

- **The PR #5059 and PR #5062 counter evidence** was supplied to this session as
  a narrative and was not independently reproduced from the PR record. The
  debate's engagement with it is conditional on that narrative being accurate.
- **The debate's forward-looking cost arithmetic** (49% with a security safety
  core, 37% on the late-round path) is arithmetic on the ADR's own assumed
  workload, not a measurement. No scoped mode exists, so no empirical figure is
  obtainable.
- **Whether the five P0 findings are individually correct** is the maintainer's
  call. This QA confirms each P0 cites a source that says what the finding
  claims; it does not certify that the recommended remediation is the right one.

## Verdict

PASS on the scope listed above. The debate ran the six roles the skill
specifies, reached no consensus, and recorded that honestly rather than
smoothing it. Every number that entered a durable artifact was re-measured
first, and the one that did not reproduce was removed rather than kept. The
rejection record states the five findings with citations that resolve, and the
renumber to ADR-095 is forced by a real collision with the accepted ADR-094 on
`main`.

This is not a verdict on whether rejecting the proposal was the right call.
That is the maintainer's decision, made on the debate evidence and recorded in
`.agents/architecture/ADR-095-scoped-re-review-axes.md`. Note that no debate
role voted to reject; the votes were two Block, three Accept-with-changes, and
one Disagree-and-Commit, all of which argued for narrowing.
