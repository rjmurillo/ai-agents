# A Nested Worktree Turned 110 Green Tests Red, and the Session Log Blamed the Base

Date: 2026-08-01
Failure mode: Class 4, verification theater. A failure count was explained by an
unverified claim about the base branch instead of by a control run.

## Summary

The memory cluster branch (`fix/memory-hooks-ids-episodes`, issues #4010, #4011,
#4071) recorded this in its session log under `validationPassed`:

> uv run pytest tests/ -q reports 110 failures, every one of them reproduced on
> the unmodified branch base

The count was right. The explanation was wrong, and wrong in the direction that
stops anyone from looking further. The 110 failures have nothing to do with the
base branch. They are an artifact of running pytest from a checkout nested under
`.claude/worktrees/`.

`tests/ci/test_validation_scripts_are_reachable.py:110` filters the source walk:

```python
skip = ("__pycache__", ".venv", ".cache", "worktrees", "node_modules")
...
sources.extend(p for p in base.rglob("*.py") if not any(s in p.parts for s in skip))
```

The filter reads `p.parts`, which is absolute. For a checkout at
`.../ai-agents2/.claude/worktrees/wf_bf35d506-d78-1/`, every path under it
already contains `worktrees` from the repo root itself. So `_python_sources()`
returns an empty tuple, `_reference_graph()` returns `{}`, and all 109 parametrized
reachability cases plus the probe's own self-tests fail at once. The 110th is
`tests/test_skill_bundle_suites_run.py::test_bundle_tree_suite_passes[src/copilot-cli/skills]`,
which fails from the same checkout for the same class of reason.

## Impact

| Area | Severity | Effect |
|------|----------|--------|
| Push gate | High | `lefthook` pre-push runs the full suite, so the branch could not be pushed from the worktree it was developed in. |
| Diagnosis | High | The session log's explanation, if trusted, sends the next reader to the base branch, where nothing is wrong. |
| Blast radius | Medium | Any agent working in a `.claude/worktrees/` checkout hits this. This repo had 45 such worktrees live at the time. |

## Evidence

Four runs, same two test files:

| Checkout | Commit | Result |
|----------|--------|--------|
| `ai-agents2/` (top level, on `main`) | `f90054218` | 144 passed, 2 skipped |
| `.claude/worktrees/wf_bf35d506-d78-1/` (this branch) | `d9c5e4e6c` | 110 failed, 34 passed, 2 skipped |
| `/tmp/wt-push-4011/` (same commit, not nested) | `d9c5e4e6c` | 144 passed, 2 skipped |
| `.claude/worktrees/wf_bf35d506-d78-2/` (unrelated branch) | `5b1161644` | fails identically |

Rows two and three are the whole argument: identical commit, identical
dependencies, opposite result. The only variable is the path the checkout sits
at. Row four rules out the branch content, because an unrelated branch in a
sibling worktree fails the same way.

## What Went Wrong

- The session log asserted the failures "reproduced on the unmodified branch
  base" without a recorded control run against that base. Nothing in the log
  names a command or a commit for that claim, and running it does not hold.
- The obvious control (same commit, different directory) is one `git worktree
  add --detach` away and was never run.
- A path filter written for repo-relative paths was applied to absolute ones.
  It is correct for the top-level checkout, which is where its author ran it.

## What Went Right

- The full-suite pre-push gate refused the push. Without it, the false
  explanation would have shipped in the session log unchallenged.
- Pushing from a non-nested detached worktree at the same commit kept every gate
  running rather than bypassing them. The suite passed there, which is the
  evidence the PR carries.

## Remediation

| Action | Owner | Tracking |
|--------|-------|----------|
| Push from a non-nested checkout for this branch | shipped | this PR |
| Correct the session log's `validationPassed` evidence | shipped | this PR |
| Anchor the `worktrees` skip on the path relative to `_REPO_ROOT` | open | issue #4159 |

## Follow-Ups Not Yet Filed

None. The one open remediation above is filed as #4159.

## Learning

"It also fails on the base" is a claim, not an observation, and it is the single
most load-bearing sentence a failing-test note can contain, because it closes the
investigation. It needs a command and a commit next to it or it is a guess
wearing evidence clothes.

The control that settles it is cheap and general: run the identical commit in a
different directory. When the same bytes produce different results, the
environment is the variable, and no amount of reading the diff will show it.
