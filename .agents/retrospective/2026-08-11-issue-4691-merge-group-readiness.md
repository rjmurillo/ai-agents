# Retrospective: issue 4691 merge-group readiness

Session 14654, branch `fix/4691-merge-group-support`.

## What happened

A branch implementing merge-group triggers for issue #4691 had sat unpushed
since 2026-08-08. The recorded blocker was the pre-push `workflow-local-run`
gate timing out on `test-codeql-integration.yml`, which downloads a
788,113,376-byte CodeQL bundle. The branch shipped after two findings that had
nothing to do with retrying that download.

## Finding 1: the contract the branch pinned had already moved

The branch encoded 17 required contexts and 13 producing workflows, taken from
the issue body written on 2026-08-06. Ruleset 11104075 on 2026-08-10 lists 16.
`Aggregate Results` had been retired, and main had renamed its two surviving
producers to `AI Quality Gate Results` and `Session Protocol Results`.

The rebase surfaced this as two opaque lines:

```
ai-pr-quality-gate.yml: aggregate required names drifted
ai-session-protocol.yml: aggregate required names drifted
```

Nothing in the test said where the 17 came from, so the only way to read that
message correctly was to re-query the ruleset. The test now carries the `gh api`
command next to the context set.

**Lesson.** A test that mirrors external state must name the source and the
refresh command in the file. Otherwise a drift failure reads as a local defect
and invites someone to edit the expectation until it passes.

## Finding 2: the blocker dissolved instead of being solved

Two of the 12 changed workflows produced none of the 16 live contexts. Both
returned to their main content, and one of them was `test-codeql-integration.yml`
itself. The gate then had nothing heavy to run, and the whole `pre_pr.py` suite
passed with `Workflow Local Run` taking 84 seconds.

The prior session had asked "how do I make this download fit in 600 seconds"
and answered "I cannot." The question that dissolved it was "does this file
need to change at all." The evidence was already reachable: the workflow's own
jobs were all guarded by `github.event_name != 'merge_group'`, so the change
added nothing but skipped check runs to each queue entry.

**Lesson.** When a gate blocks a change, price the change before pricing the
gate. A file that does not need to change costs nothing to validate.

## Finding 3: a stale act signature blocked pushes on unmodified main

The push failed on `validate-paths.yml` with:

```
fatal: not a git repository: (null)
::error::The process '/usr/bin/git' failed with exit code 128
```

`run_workflow_local_test.py` already treats the missing `.git` in the act
container as an act-only limitation. Its per-line matcher, though, pinned the
literal `The process 'git rev-parse --abbrev-ref HEAD' failed with exit code
128`. `dorny/paths-filter` at digest `61f87a10` annotates the resolved
executable path instead, so the annotation read as unexplained and the stage
failed closed.

Reproduced against `origin/main`'s copy of the workflow with act's default
event, so it was never a property of this branch. Any push touching a workflow
that uses the action hit it. The matcher is now a regex over both shapes, still
pinned to a git executable and to exit code 128, with negative controls for a
non-git executable and for a different exit code.

**Lesson.** A limitation signature pinned to a third-party tool's exact output
is a dependency on that output. A digest bump silently converts the gate from
"downgrades a known limitation" to "blocks every push," and the failure names
the workflow rather than the signature.

## What went right

The gate's own design made finding 3 diagnosable in one read: the downgrade
rules are a table with a comment per entry naming the issue that motivated it,
and `_unexplained_error_annotations` documents precisely why a whole-run
downgrade would be wrong. The fix was 16 lines because the structure was there.

## Still open

Issue #4774 owns merge-queue enablement. `GET /repos/rjmurillo/ai-agents`
reports `owner.type = User` and ruleset 11104075 carries no `merge_queue` rule,
so no real queue entry can be observed. Nothing in this branch claims otherwise.
