# Shallow history in CI is not a bandwidth saving, it is a merge-base outage

## Question

`.github/workflows/pr-validation.yml` runs `scripts/ci/merge_tree_ratchet_check.py`,
which needs a merge base. The job reached it two different ways: a checkout that
took the depth-1 default, and `git fetch --depth=1 origin "$BASE_REF"` inside a
`run:` block. Is depth-limited history a harmless saving on a disposable runner?

## Conventional answer

Yes. The runner is thrown away, only the base tip is needed, and a depth-limited
fetch transfers one commit instead of a history. The workflow said so in a
comment: "CI-only: `--depth=1` keeps this disposable checkout shallow to save
bandwidth." The known hazard was thought to be local only, that copying the line
into a working clone writes `.git/shallow` and breaks later pushes.
`git_hook_policy.py:2468` still describes it that way, as something that escapes
from CI into a clone.

## First-principles position

No, and it fires in CI first. Depth-limited history writes `.git/shallow` in the
runner's own clone and grafts the fetched tip parentless. From that point
`git merge-base` returns nothing for the rest of the job, so
`merge_tree_ratchet_check.py` runs `git merge-tree --write-tree` and gets
`fatal: refusing to merge unrelated histories`, exit 128, which the wrapper
turns into exit 3 and a red required check.

There are two independent routes to the graft, and they have different
populations. Fixing one leaves the other red.

1. **The fetch route.** A `git fetch --depth=<n>` in a `run:` body. Only grafts
   when the fetched tip is new to the clone, which is exactly when the PR
   checkout predates the base tip. Fresh branches pass, stale branches fail
   every time, so it reads as a flake.
2. **The checkout route.** An `actions/checkout` that omits `fetch-depth: 0`.
   Grafts unconditionally, at step one, before any fetch runs.

`validate-pr` had both. It carries two checkout steps selected by `if:` on a
bot-actor guard: the human leg pins `fetch-depth: 0`, the bot leg took the
default. The ratchet steps below are deliberately unconditional (issue #4151, so
Renovate and Dependabot cannot smuggle a workflow change past a gate). So every
bot PR ran the merge-tree ratchet against a depth-1 clone and the required check
was red for all of them, deterministically, with no stale-branch precondition at
all.

`security-suppressions-diff` is **not** a second consumer, and an earlier draft
of this memory claimed it was. `check_suppression_diff` builds
`range_spec = f"{base_ref}..HEAD"`, a two-dot range, and hands it straight
through `_added_suppression_violations_for_range` to `git diff`. Two dots
compare two endpoints and need no merge base. The three-dot `_changed_line_map`
that does need one belongs to the mypy path and is not reached by that command.
The gpt-5.6-sol adversarial review caught this; it had been asserted from a
grep hit rather than from reading the call chain.

## Evidence

Measured against real git, not reasoned about. Build an upstream whose main
advanced three commits past a feature branch, clone it completely, then:

```
shallow before:  absent      merge-base: 2e757f4c8ea8c79e4480d4ff643186e180cf1484
git fetch --depth=1 origin main
shallow after:   EXISTS      merge-base: (empty)
git merge-tree --write-tree FETCH_HEAD feature
                             fatal: refusing to merge unrelated histories
```

Two production sightings, one per route.

- **Fetch route:** PR #4521 failed `Validate PR` at the merge-tree ratchet with
  that exact error, reproducibly across a `gh run rerun --failed`, while PR
  #4556 passed the identical job 24 minutes later. #4521 was 18 commits behind
  main; #4556 was cut from a recent tip.
- **Checkout route:** Renovate PR #4552 (`app/renovate`, so `skip == 'true'`)
  failed the same step with the same error. Its log shows the fetch that ran was
  the depth-limited one, and the branch was current, so staleness explains
  nothing here. The bot leg's checkout is the whole cause.

## The measurement that decides how wide the fix has to be

A later plain fetch does not repair the graft. Only `--unshallow` does.

```
after --depth=1 fetch:   shallow=YES  merge-base=(empty)
after plain git fetch:   shallow=YES  merge-base=(empty)
after --unshallow fetch: shallow=no   merge-base=2e757f4c8...
```

Two consequences. The flag has to come off every fetch in the job, not just the
one above the consumer, because the first fetch grafts and every later step
inherits it. And removing the flags cannot rescue the checkout route, because
the graft is already written before the first `run:` block executes. The depth
has to be right at checkout.

## Where issue #4518 gets the remedy wrong

Issue #4518 diagnosed the fetch route first and correctly, including the graft,
the `.git/shallow` write, and a controlled reproduction. It then prescribed a
remedy scoped to one step:

> The fix below should be scoped to the merge-tree step and not applied blindly
> to the other two.

Its premise is sound: the taste-lint and type-ignore ratchets read a baseline
blob at the base ref, walk no history, and passed in the same run that failed.
The conclusion does not follow, because the damage is not scoped to the step
that does it. Measured across the four job shapes on the issue's own two-commit
reproduction, where `depth` means that step fetched with `--depth=1`:

| step 1 | step 2 | step 3 | shallow | `git merge-tree` |
| --- | --- | --- | --- | --- |
| depth | depth | depth | YES | 128, unrelated histories (control) |
| depth | depth | full | YES | 128, unrelated histories (#4518's remedy) |
| full | depth | depth | YES | 128, unrelated histories |
| full | full | full | no | 0 |

The control failing is what makes the other three readable. Implementing #4518
as written ships a change that leaves the check exactly as red as it was. The
issue also does not mention the checkout route, which is the one that was
failing every bot PR.

## Decision

Pinned `fetch-depth: 0` on the bot leg's checkout in `pr-validation.yml`, and
removed `--depth=1` from all seven fetch sites across `pr-validation.yml` and
`pytest.yml`. Because the checkout is already complete, the undepthed fetch
transfers only the commits the base gained since checkout.

The `pytest.yml` half fixes no live failure and should not be described as if it
did. Nothing in that job needs a merge base: `ruff_count_ratchet.py` reads
blobs with `git show <ref>:<path>` and the suppression check is two-dot. It is
removed because the graft is a trap for whoever adds the next consumer there.

`tests/ci/test_shallow_fetch_breaks_merge_base.py` guards both routes. It scans
every workflow rather than a fixed list, flags any job that reaches a merge-base
consumer with either a depth flag in a `run:` body or a checkout that does not
pin `fetch-depth: 0`, and asserts it found at least one consumer so it cannot
pass vacuously if the scripts are renamed. Both routes were mutation-tested by
reverting each fix independently and confirming the guard goes red naming the
offending step.

## How to recognize it

`refusing to merge unrelated histories` from a CI step, on a branch whose
history is demonstrably related to main. Check two things before believing the
histories are unrelated: a depth-limited fetch earlier in the same job, and the
`fetch-depth` on every checkout that leg could have taken. A job with two
conditional checkouts can be correct on one leg and broken on the other.
Locally:

```bash
git rev-parse --is-shallow-repository   # true means a graft is in effect
cat .git/shallow                        # the grafted tips
git fetch --unshallow origin main       # the only repair
```

This is distinct from the count-ratchet freshness block recorded in
`ci/ci-count-ratchets-require-branch-freshness.md`. That one returns a
REGRESSION verdict with numbers and is fixed by merging main. This one is a tool
error with no verdict at all, and merging main does not fix it, because the job
re-grafts on its next run.

## Transferable lesson

A conditional checkout is a second configuration of the same job, and the
unconditional steps below it run under both. Auditing the leg you are looking at
proves nothing about the other one. The original search here was "grep the
workflows for `--depth`", which by construction could not see a checkout whose
defect is an absent key rather than a present flag.
