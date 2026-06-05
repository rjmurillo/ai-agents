# CI-Feedback Sub-Loop

> **Purpose**: Name and define the lifecycle primitive that runs when CI review returns findings on a pushed branch. Replace ad-hoc "read the comment, edit the file, push" with a laddered sub-pass.
> **Source**: Issue #2014 (CI-feedback sub-loop is an unnamed primitive). Parent epic #1933 (lifecycle-gate convergence).

## The primitive

The initial lifecycle is well-defined: `/spec` to `/plan` to `/build` to `/test` to `/review` to `/ship`. It covers the first pass on a change.

What happens after a reviewer (Architect, Security, QA, DevOps, Roadmap, Reliability, or a bot like Copilot or CodeRabbit, or a human) flags a finding on a pushed branch has been implicit. The observed default is ad-hoc: read the comment, edit the file, push. That default produced PR #1965 (58 commits, 18 rounds) and PR #1979 (30 commits, 18 rounds).

The **CI-Feedback Sub-Loop** is the named response primitive for that situation. It has the same status as the initial lifecycle, but its scope is one cluster of related findings, not the whole change. Each cluster gets its own laddered pass: a sub-spec, a sub-build, a sub-test, a sub-review, and a sub-ship. The mental model: **when operating on change requests from CI review, the build to test to review to ship sub-process repeats, scoped to one cluster at a time.**

This document is the bounded naming and documentation slice. The session-log schema extension and the CI workflow scope-reduction are named as follow-ups at the end; they are out of scope for this document.

## Trigger

Any unresolved CI, bot, or human review comment on a pushed branch triggers the sub-loop. A single flagged thread is enough. The agent does not respond comment-by-comment; it clusters first, then runs one sub-loop pass per cluster.

## Phases

Each phase reuses an existing lifecycle command with sub-loop scope. Do not fork the commands; invoke them narrowed to the cluster.

1. **Sub-spec**: Cluster the open threads by gist (consume the #1917 cluster-by-gist output when available). Pick one cluster. Write a one-paragraph "what is this fix actually doing." That paragraph is the sub-spec. It names the root cause the cluster shares, not the per-thread symptoms.
2. **Sub-build**: Apply the same `/build` exit gates the initial pass uses (code-qualities-assessment, taste-lints, doc-accuracy, plus whatever #1911 lands as the mandatory set). The fix runs through the gates locally before it is pushed, so it does not go straight to CI and bounce.
3. **Sub-test**: Run the deterministic test suite that covers the changed area. Do NOT run the full advisory AI reviewer fleet here; that is the reviewer's job after the push, not the author's job before it.
4. **Sub-review**: Re-run only the axes that flagged the original cluster, not all axes. A docs-only fix does not re-run the security axis.
5. **Sub-ship**: Push only when the sub-review for the cluster's own axes returns clean.

## Exit conditions

A sub-loop pass exits when:

- The cluster's own axes return clean on the local sub-review, AND
- The sub-build exit gates pass, AND
- The deterministic sub-test suite for the changed area passes.

The branch is done with the sub-loop when every open cluster has exited. A new finding on a fix is itself a new cluster and starts its own pass; it does not reopen a closed cluster.

## Commit-prefix convention

Sub-loop fix commits use the prefix `fix(subloop):` so the commit log and, later, CI can detect a sub-loop turn unambiguously.

Format:

```text
fix(subloop): <axis> cluster <id>
```

- `<axis>` is the reviewer axis the cluster addresses. Use one of the canonical review axes defined by `CANONICAL_ROLES` in `tests/lib/test_axis_schema.py` (for example `architect`, `security`, `qa`, `code-quality`). That tuple is the single source of truth; this doc does not restate the full list, so the allowlist cannot drift out of sync with it.
- `<id>` is the cluster identifier from the sub-spec phase (a short letter or slug).

Example: `fix(subloop): architect cluster B`.

This standardizes on `fix(subloop):` rather than the ad-hoc `fix(roundN):` used in PR #1965. `fix(roundN):` records a manual round; `fix(subloop):` records a structured sub-loop turn. The distinction lets the CI side (follow-up below) reduce reviewer scope only for structured turns, and lets a retrospective separate manual churn from laddered passes.

`fix(subloop):` is a `fix` type under the conventional-commit contract in `.claude/rules/universal.md`, so it satisfies branch-discipline and commit-format gates without a change to the commit-type allowlist.

## Why this matters

The #1933 epic fixes the structural question (CI as backstop, `/review` as primary). This primitive fixes the procedural question: what happens after a reviewer fires. Without it, even a clean #1933 landing restarts the N-round loop on the first CI miss, because the only known response is "edit and push." With it, the work is a small number of cluster passes, each gate-checked locally before the push that triggers the next reviewer fire.

## Out of scope for this document (named follow-ups)

This document delivers the naming and the procedure. Two pieces of issue #2014 remain and should land as separate changes:

1. **Session-log schema extension**: add a `sub_loop_turns` array to the session log, each entry recording `{cluster_id, axes_run, verdicts, sha}`. This makes "Round 7 of N" a structured artifact instead of a commit-message convention. The validator at `scripts/validate_session_json.py` does not reject unknown top-level fields today, so the field is additive; the schema change is the validation and the documentation of the field shape, plus tests. Tracked under #2014.
2. **CI workflow scope-reduction**: when the head SHA is a `fix(subloop):` push, CI should skip axes the cluster does not claim to address and compare verdict-per-axis against the prior push so regressions surface explicitly. This is the larger slice and depends on the commit-prefix convention defined here. Tracked under #2014.

A worked example in `.agents/retrospective/` applying the sub-loop to a real CI-feedback cluster is also a follow-up, deferred until the first PR runs the procedure end to end.

## References

- Issue #2014. Origin: CI-feedback sub-loop is an unnamed primitive.
- Issue #1933. Lifecycle-gate convergence epic (the structural complement).
- Issue #1917. Cluster-by-gist (consumed as input to the sub-spec phase).
- Issue #1940. Iteration-paradox retrospective (the failure mode this primitive prevents).
- `.claude/rules/universal.md`. Conventional-commit contract that `fix(subloop):` satisfies.
- `scripts/validate_session_json.py`. Session-log validator (target of the `sub_loop_turns` follow-up).
