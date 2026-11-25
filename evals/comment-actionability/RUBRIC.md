# Labeling Rubric: Review Comment Actionability

Plan task M1-T6 of `.project-toolkit/plans/active/harness-agnostic-llm-fallback.md`.
Spec: `.project-toolkit/specs/SPEC-harness-agnostic-llm-fallback.md`, section Eval method.

## What you label

One unit: one review comment node. A thread opener and a reply are both in scope.
Production scores every node in a thread, replies included, so the eval does the same.

## What you see

For each row you see four things:

- `body`: the comment text.
- `path`: the file the comment is on.
- `diff_hunk`: the diff context the comment points at. It can be empty.
- `label`: the field you fill in.

You never see the other comments in the thread, any score, the reviewer, or the split.
Do not look them up. A label that comes from a reply lets the heuristic grade itself,
because the heuristic reads replies.

Thread `isOutdated` is NOT shown. Judge the comment as written against the hunk you have.

## Label values

| Value | Use when |
|---|---|
| `actionable` | The comment asks for, or points to, a change in the code that a reasonable author should make or explicitly decline. |
| `not_actionable` | The comment needs no change and no decision from the author. |
| `unsure` | You cannot decide after reading the body and hunk once. The scorer drops these rows and counts them. |

Use `unsure` sparingly. A high `unsure` count is reported.

## Not actionable

- Praise or thanks ("Nice cleanup").
- Acknowledgement ("Got it", "Will do").
- A question whose answer needs no change.
- Restatement of what the code already does.
- Bot status noise (coverage summaries, "review started", walkthrough banners).
- An already-fixed notice ("fixed in abc123", "addressed in the latest push").

## Edge cases

| Case | Label | Reason |
|---|---|---|
| Nit that names a concrete change ("rename `x` to `count`") | `actionable` | A reasonable author makes it or declines it. |
| Nit with no concrete change ("a bit verbose") | `not_actionable` | Nothing specific to do. |
| Question whose answer implies a change ("Why no null check here?") | `actionable` | A sound answer is a code change or an explicit decline. |
| Question answered by the code in view ("Does this run on Windows?" when the hunk shows the guard) | `not_actionable` | No change follows. |
| "Fixed in abc123" reply | `not_actionable` | It reports a change already made. |
| Bot finding that repeats another bot's finding | Judge the comment alone | Duplication does not change what this comment asks. |
| Suggestion marked optional ("feel free to ignore") that names a concrete change | `actionable` | The author may decline, and declining is a valid response. |
| Comment with an empty hunk | Judge the body | If the body alone names a change, `actionable`. |

## Rule of thumb

Ask: would a reasonable author need to change the code, or write a reason for not changing it,
because of this comment? Yes means `actionable`.
