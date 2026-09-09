# Retrospective: two of five efficiency issues had no implementable scope, and only reading the tree showed which

**Date**: 2026-09-09
**Scope**: issues #5626, #5610, #5539, #5067, #5400; new issue #5672; branch `claude/efficiency-improvements-ldwxem`
**Failure mode classification**: #10, Silent defaults and guard-clause suppression
(`.agents/governance/FAILURE-MODES.md`), for the defect found in
`validate_mypy_changed_files`. The selection half of this session produced no
failure; it is recorded here because the near miss is the reusable part.

## What happened

The task was to find five open issues that would improve efficiency, investigate
them, and implement the ones with merit. Five were selected from the
`technical-debt` and `performance` label sets, and every factual claim in each
was re-measured against the working tree before any code was written.

Three survived that check and were implemented. Two did not, and neither could
have been sorted out from the issue text alone:

- **#5067** proposes consuming the SHA-bound review marker so
  `ai-pr-quality-gate.yml` stops re-running ten review axes, and deleting the
  `.claude/commands/pr-quality/` family. Neither exists now. `ls
  .github/workflows/` has no `ai-pr-quality-gate.yml`, and ADR-064's migration
  removed `.claude/commands/` entirely. Two of its three acceptance criteria are
  already satisfied by unrelated work, and the first names a file to edit that
  is not there.
- **#5400** asks for an instruction-context growth ratchet. Its own dependency
  list names #5396, #5397, #5384 through #5389, #5391 through #5394, #5398, and
  #5399, and its acceptance criteria require a controlled runtime experiment
  across a fixed model and harness. That is an ocean by `builder-ethos.md`'s
  threshold, not a lake, and partial delivery would produce a metric with no
  activation data to consume.

Both were reported rather than implemented.

## The defect the work surfaced

Clearing `scripts/validation/pre_pr.py` before pushing failed on
`validate_mypy_changed_files` with `reason=mypy.regression ... examined=15`. The
branch had no type error. The gate hands every changed `.py` to one mypy
invocation, and this change touched two generated mirror trees, so mypy exited
with:

```
$ uv run --frozen python -m mypy .claude/lib/ai_review_common/workflow.py src/copilot-cli/lib/ai_review_common/workflow.py
src/copilot-cli/lib/ai_review_common/workflow.py: error: Duplicate module named "ai_review_common.workflow" (also at ".claude/lib/ai_review_common/workflow.py")
Found 1 error in 1 file (errors prevented further checking)
```

Each copy alone is clean, which is the control. `errors prevented further
checking` means zero files were examined, so the gate reported a regression
having checked nothing, while printing a count of files it did not check. That
is the inverse of `.claude/rules/ci-scripts.md` MUST 12.

It fires on the workflow `.claude/rules/generated-artifacts.md` mandates: edit
the canonical copy, regenerate, and both mirrors land in the same change.
Tracked as #5672 and fixed on this branch.

## Impact

| Area | Severity | Effect |
|---|---|---|
| Wasted implementation | None | Both non-viable issues were caught before code was written |
| Blocked pushes | Medium | Any change regenerating two mirrors hit a false `mypy.regression`; the named remedy did not exist |
| CI cost removed | Medium | One always-green job per PR, plus a 57,152-character comment (roughly 14k tokens) read by every agent on the thread |
| Red `main` removed | Medium | The count-ratchet clock no longer runs in a contended shard, where it tripped at 87.7s against an 85s deadline on a shrinking corpus |
| Issue hygiene | Low | #5067 and #5400 remain open with stale and blocked scope respectively; both got a comment rather than a silent skip |

## Root cause of the mypy defect, five whys

1. Why did the gate report a regression? Because `run_mypy` exited 1.
2. Why did mypy exit 1 with no type error? Because two input paths resolved to
   one module name, and it aborts on that before checking anything.
3. Why do two paths share a module name? Because neither `.claude/lib/` nor
   `src/copilot-cli/lib/` holds an `__init__.py`, so both mirrors of
   `ai_review_common/workflow.py` resolve to `ai_review_common.workflow`. The
   canonical copy under `scripts/` does not collide, because `scripts/__init__.py`
   gives it a longer name.
4. Why did the gate pass both to one invocation? Because it treats the changed
   file list as a flat set of paths, which is true for every tree in the
   repository except the generated mirrors.
5. Why was this not caught earlier? Because the gate's own tests drive it with
   mocked subprocess results and single-file sets. Nothing exercised it against
   a real changed-file list spanning two mirrors, which is the only shape that
   fails.

Root cause: **the gate modelled changed files as paths when mypy models them as
modules.** The mirrors are the one place in this repository where those two
models disagree, and they are produced by the repository's own generators, so
the disagreement is routine rather than exotic.

## What went well

- **Re-measuring every issue claim first.** `#5626` was accurate to the
  character, and the live ruleset query cleared the one claim its author had
  marked NOT VERIFIED. `#5067` was stale. The same three tool calls established
  both, and neither could have been settled by reading.
- **Negative controls caught two no-op tests.** The wiring test for the timing
  guard and the snapshot test for `git add --force` both pass against an
  unfixed tree until the control is added. Reverting `--force` fails 2 of 3;
  removing `-p no:xdist`, the merge-group condition, or the env var fails 1, 1,
  and 3.
- **Coverage followed the gates instead of retiring with them.** Deleting
  `memory-validation.yml` would have dropped five assertions in
  `test_lefthook_gate_config.py`. They were re-pointed at the surviving
  server-side leg in `pr-validation.yml` rather than deleted.

## What to do differently

- **A gate that reports a failure count should prove it examined that count.**
  `examined=15` was printed by a run that examined zero. The evidence contract
  in `scripts/validation/evidence.py` carries the field; nothing checks it
  against reality.
- **Test a gate against the diff shapes the repository's own generators
  produce.** Mocked single-file sets cannot find a defect whose precondition is
  two paths.

## Remediation

| Action | Owner | Tracking |
|---|---|---|
| Deduplicate mypy module paths in the pre-PR gate | this branch | #5672, fixed here |
| Report #5067's stale premise so it is rescoped, not implemented as written | this branch | comment on #5067 |
| Report #5400's dependency chain so partial delivery is not attempted | this branch | comment on #5400 |
| Consider asserting `examined` against the checker's own reported input count | unassigned | #5672 discussion |

## Evidence

- Issues: #5626, #5610, #5539, #5067, #5400, #5672
- Commits on `claude/efficiency-improvements-ldwxem`: `12b5c90`, `bf729e4`,
  `12a00e1`, `340827f`, `8f05ced`, `48f4c0e`, `422fb35`, `8d17003`
- Red `main` run cited by #5610: job 101352438675 at `19f257b5b`
- Live ruleset: `gh api repos/rjmurillo/ai-agents/rulesets/11104075` returns
  nine required contexts; "Memory Validation" is not among them
