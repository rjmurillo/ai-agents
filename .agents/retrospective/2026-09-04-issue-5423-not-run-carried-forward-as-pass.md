# Retrospective: "28/28 tests pass" answered a question nobody had asked

## Session Info

- **Date**: 2026-09-04
- **Agents**: Claude Code (Opus 5), remote session
- **Task Type**: Review and ship a finished checkpoint
- **Outcome**: Success. The checkpoint was one line short of mergeable and the line is now on the branch.
- **Failure Mode**: #4 False completion markers (`.agents/governance/FAILURE-MODES.md`). Two prior passes recorded the work as validated and ready; the gate that decides whether it can merge had never run in either.

Scope: [issue #5423](https://github.com/rjmurillo/ai-agents/issues/5423), branch
`feat/issue-5423-harness-capability-matrix`, feature commit `bbe3b835b` (2026-08-31),
fix commit `7acb80328` (2026-09-04) added this session, shipped as
[PR #5547](https://github.com/rjmurillo/ai-agents/pull/5547). Head of the
[#5422](https://github.com/rjmurillo/ai-agents/issues/5422) dependency chain
(#5424 -> #5425 -> #5426).

## Phase 0: Data Gathering

### What the record said

Two triage comments stood on #5423. Both were careful, both cited real commands, and both
concluded the code was finished and only needed a pull request:

| Claim | Verified this session | Holds |
|---|---|---|
| Five additive files, 1162 lines | `git diff --stat origin/main...` | Yes |
| None of the five exists on `main` | `git cat-file -e origin/main:<path>` x5 | Yes |
| 28/28 tests at branch tip and ported onto `main` | `pytest tests/eval/test_harness_capability.py` | Yes, 28 passed |
| CLI fails closed with no Codex or Copilot | `eval_harness_capability.py --dry-run` | Yes, every cell `UNVERIFIED` |
| Merges cleanly with `main` | `git merge-tree --write-tree` | Yes, exit 0 |

Every factual claim in both comments was accurate. The conclusion drawn from them was not.

### What no one had run

The first comment recorded it explicitly, in its own validation table:

```text
scripts/validation/pre_pr.py | NOT RUN (blocked)
```

It was blocked for a real reason at the time: the wheel CDN was firewalled and the venvs
were wiped. The second comment, four days later in a working environment, re-verified the
tests and the fail-closed behavior and did not re-run it. `NOT RUN` was carried across two
sessions and read, by the third, as though the remaining work were clerical.

Running it took 24 seconds to the first failure:

```text
taste count ratchet: REGRESSION. 576 violations > baseline 575 (+1).
  scripts/eval/_harness_capability.py: [file-size] File exceeds 500 lines (517 lines)
```

One failure out of roughly sixty checks. It is enforced in CI at
`.github/workflows/pr-validation.yml:304`, so the pull request would have opened red on a
merge-blocking check.

## Phase 1: Analysis

### Why the passing evidence could not have caught it

The three signals everyone cited answer three questions, and none of them is the merge
question:

| Signal | Answers | Silent about |
|---|---|---|
| 28/28 tests | Does the code do what it claims? | Everything outside its own behavior |
| Clean port onto `main` | Do the files apply? | Whether the applied tree passes the gates |
| `--dry-run` fails closed | Is the negative control real? | Same |

A file-size ratchet is invisible to all three by construction. It is not a property of the
code's behavior, so no test can observe it; it is not a property of the diff's
applicability, so no merge check can observe it. It is a property of the resulting tree,
and `pre_pr.py` is the only thing in the repository that reads that.

The trap is that the passing signals were strong and numerous. Three independent green
results felt like coverage. They were three answers to the same kind of question.

### Ruling out the cheaper explanation first

`.claude/rules/ci-scripts.md:46` (MUST item 14) says a tripped count ratchet is usually a
stale base, not a regression, and that merging `origin/main` is the first diagnostic step
rather than the last resort. That hypothesis was live here: the branch's last merge of
`main` was at `843db243a` (2026-08-31) and `main` had moved to `fd438940e` (2026-09-03).

Two checks settled it without the merge:

```text
branch baseline: 575        main baseline: 575
remove _harness_capability.py -> "taste count ratchet: OK (count == baseline 575)"
```

Equal baselines mean `main` did not move the number underneath the branch, and the removal
test attributes the entire `+1` to the one file. That is the rule's own attribution
procedure ("`git rm --cached <suspect>` and re-run"), and it is worth preferring over the
merge when the merge is expensive, because it answers the attribution question directly
instead of by elimination.

### Choosing the fix

`.claude/rules/ci-scripts.md:95` (MUST NOT 4) forbids raising the baseline and names three
permitted responses: fix the violation, split the file, or take the documented
`# taste-lint: ignore <rule>` escape with a reason (issue #3779).

The file is 517 lines, of which 228 are code, 217 are comments and docstrings, and 72 are
blank. The overage is entirely documentation: the per-negative-control rationale issue
#5423 requires each capability cell and classifier to carry. A split would move the JSON
parsing helpers into a second module to satisfy a line count, and would put the
fail-closed contract, every `VERIFIED` path routing through `HarnessCapabilityError`,
behind an import seam. That contract is the property the file exists to make checkable in
one place.

So the escape was taken with that reasoning inline, which is the shape
`.claude/rules/code-quality.md:224` asks for under "Suppressions Are a Last Resort": scoped to
one rule in one file, with a short note saying what the check wants and why the idiomatic
fix is worse here. The repository carries 188 such declarations, several under
`scripts/eval/`, so this is the sanctioned path rather than an invention.

One self-inflicted detail worth recording: the first draft of the justification comment
opened with "517 lines", which the comment itself falsified by making the file 522. A
number that describes the file it lives in goes stale on write. The rewritten form says
"just over the 500-line ceiling" and "fewer than half those lines are code", which stay
true as the file moves.

## Phase 2: Two Obstacles Worth Recording

### The branch's working tree cannot be made clean

Three files on this branch are committed with CRLF while `.gitattributes` sets
`text=set, eol=lf` for them:

```text
.agents/sessions/handoffs/2026-09-01-4789-handoff.md
.agents/sessions/handoffs/2026-09-01-5361-handoff.md
.serena/memories/pr-autofix/pr-5438-main-red-multi-session-race.md
```

Git normalizes the working copy to LF before comparing it against a blob that holds CRLF,
so the comparison can never match. `git checkout --`, `git stash push`, and a re-checkout
all leave them modified, because each one restores the same mismatch. `git diff
--ignore-cr-at-eol` reports zero changed lines in all three, which is how you tell this
apart from real local edits.

The consequence is that `git merge origin/main` refuses to run: it will not overwrite
files it believes are locally modified. `main` already carries normalized copies of all
three, so the condition clears itself the moment the merge lands, and the merge is the
thing it blocks. Do not spend time trying to clean the tree; either merge through it
deliberately or, as here, establish that the merge is not required. It was not: the
baselines are equal, attribution was proved directly, and `git merge-tree` reports no
conflicts.

### The retrospective gate reads the tree, not the session

`git push` was rejected by the `retrospective-policy` pre-push job:

```text
ERROR: git push requires retrospective evidence for this session
```

`check_retrospective_evidence` in `scripts/validation/git_hook_policy.py` passes when
`.agents/retrospective/` holds a file dated today or yesterday. `main` holds three from
2026-09-03. This branch does not, because it predates them. So the gate fires on a branch
whose base is a few days old regardless of what the session did, and the two ways out are
to merge `main` (blocked here, see above) or to write the retrospective. `SKIP_RETROSPECTIVE_GATE`
exists and is forbidden: `.claude/rules/universal.md:35` (MUST NOT 2) lists six bypass
mechanisms and states that policy forbids all of them.

Writing it was the correct exit anyway. This file is the artifact.

## Phase 3: What To Carry Forward

**A `NOT RUN` is a hole, not a result.** It has no expiry and it does not become a pass by
being restated. When a prior session records a gate as blocked, the next session in a
working environment runs it before repeating that session's conclusion. Two passes here
inherited one honest `NOT RUN` and shipped a readiness verdict on top of it.

**Ask which question each green signal answers.** Three passing signals that all answer
"does the code behave correctly" are one signal, not three. Merge-readiness is a separate
question with exactly one instrument in this repository, and it is named in `AGENTS.md`
under the Pre-PR gate.

**Prefer direct attribution to attribution by elimination.** The removal test named the
offending file in one command. The merge that item 14 recommends first would have taken
longer and, on this branch, could not run at all.

**A justification comment must not quote a number it changes.** State the property, not
the measurement, when the measurement includes the comment.

## Evidence

| Check | Command | Result |
|---|---|---|
| Full pre-PR suite | `uv run python scripts/validation/pre_pr.py` | 1 failed of ~60, taste count ratchet |
| Attribution | remove file, re-run ratchet | `OK (count == baseline 575)` |
| Baseline parity | `git show origin/main:scripts/ci/taste_count_baseline.txt` | 575 on both |
| After fix | `uv run python scripts/ci/taste_count_ratchet.py` | `OK (count == baseline 575)` |
| Tests | `uv run pytest tests/eval/test_harness_capability.py -q` | 28 passed |
| Lint | `uv run ruff check scripts/eval/ tests/eval/test_harness_capability.py` | All checks passed |
| Types | `uv run mypy scripts/eval/_harness_capability.py scripts/eval/eval_harness_capability.py` | no issues in 2 source files |
| Fail-closed | `uv run python scripts/eval/eval_harness_capability.py --dry-run` | every capability `UNVERIFIED`, 6 arms |
| Module docstring survived the header | import and read `__doc__` | intact |

## References

- [Issue #5423](https://github.com/rjmurillo/ai-agents/issues/5423). The capability probe this branch implements.
- [Issue #5422](https://github.com/rjmurillo/ai-agents/issues/5422). The parent experiment; #5424, #5425, #5426 follow.
- [PR #5547](https://github.com/rjmurillo/ai-agents/pull/5547). Where this branch shipped, opened 2026-09-04.
- Commit `bbe3b835b` (2026-08-31), `feat(eval): checkpoint harness capability matrix`. The checkpoint two prior passes read as ready.
- Commit `7acb80328` (2026-09-04), `fix(eval): keep the capability matrix module under the taste ratchet`. The one line that was missing.
- `.claude/rules/ci-scripts.md:46` and `:95`. Count-ratchet attribution (MUST 14) and the baseline prohibition (MUST NOT 4).
- `.claude/rules/code-quality.md:224`. "Suppressions Are a Last Resort".
- `.claude/rules/universal.md:35`. MUST NOT 2, the forbidden bypass mechanisms.
- `.agents/governance/FAILURE-MODES.md:128`. Mode 4, false completion markers.
