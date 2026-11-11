# Run /review before you merge

## Goal

Run `/review` on a branch or PR. Read the verdict, and know when the review marker
is still good.

## Before you start

- A branch with commits against `main`, or a PR number.
- Claude Code with the `project-toolkit` plugin.
- Read the [tutorial](review-and-feedback.md) first if you have not used `/review`.

## Steps

1. Run the review on your current branch, or name a branch or PR:

   ```text
   /review
   /review 7255
   ```

2. Read the Stage-1 result. `spec-compliance` runs first. Only a `CRITICAL_FAIL`
   there stops the review. Fix the unmet requirement and run `/review` again. A
   Stage-1 `UNKNOWN` means no spec or acceptance criteria were found. The review
   goes on.

3. Check which axes ran. `/review` picks them from the changed paths and the
   effects in the diff, not from a fixed list. The `analyst` axis and the
   correctness pass always run. To preview the pick, run `select_axes.py` with
   each changed path:

   ```bash
   python3 .claude/skills/review/scripts/select_axes.py --changed-path <path> | jq -c '{canonical_selected, local_selected, fail_closed}'
   ```

   Ask for a deep review when you want every axis. Deep review runs all 11
   canonical axes. It is the strict superset of CI.

4. Read the findings table. Each row is one axis with a verdict. Skipped axes show
   a reason. A skipped axis is never a pass.

5. Read the CodeQL line. When the `security` axis runs, `/review` first reads
   CodeQL results and prints a status line under the table. The line is one of:

   | Status | Meaning |
   |---|---|
   | `CURRENT` | Alerts match the head you reviewed. |
   | `CLEAN` | A local scan found nothing. |
   | `FINDINGS` | A local scan found results. |
   | `STALE` | The analysis is for a different head, or your tree has uncommitted changes. Not clean. |
   | `NOT ANALYZED` | CodeQL has no analysis for this change. Not clean. |
   | `SKIPPED` | Nothing was read. Not clean. |

   CodeQL alerts are candidates. The `security` axis confirms or rejects each one
   against the diff. A CodeQL result never sets the verdict on its own.

6. Fix the findings that matter, commit, and run `/review` again.

7. Stop after round 3. A caller that loops "fix, then re-review" must not go past
   3 rounds. On round 3, a `PASS` ships. A `WARN`, `CRITICAL_FAIL`, or `UNKNOWN`
   goes to a person with every open finding. In rounds 2 and 3, only defects your
   fix commits introduced, and unmet acceptance criteria, count.

## What the marker binds

On a `PASS`, `/review` writes an empty commit on top of your branch. This is the
SHA-bound marker. It holds:

- A report with one `<axis>: <VERDICT>` row for each axis that ran.
- A `Reviewed-By: /review@<axes> on <reviewed commit SHA>` trailer.
- A `Review-Artifact: sha256:<digest>` trailer that covers the report text.

The marker binds your branch to one commit. `/ship` reads it to prove that
exact code was reviewed. A new code commit voids it. A merge of a clean
`origin/main` above the marker does not. A rebase or an amend rewrites the
reviewed commit, so it needs a new review.

Check it any time:

```bash
python3 .claude/skills/review/scripts/validate_review_marker.py
```

It exits 0 for a valid marker. It exits 1 for a missing or stale one.

## Check your result

- The final verdict is `PASS`, or `WARN` with every warning acknowledged.
- `validate_review_marker.py` exits 0 on your branch tip.
- The CodeQL line, if printed, is not `STALE`, `NOT ANALYZED`, or `SKIPPED`.

## If it fails

| What you see | What to do |
|---|---|
| `UNKNOWN` for an axis | The axis crashed or its output was unreadable. Read its row and re-run. |
| `[FAIL]` from the marker check after new commits | Run `/review` again on the new tip. |
| A harness with no `Task` tool | A subagent must not review its own diff. Run each axis as its own `claude -p` process. With no `claude` on `PATH`, every axis is `UNKNOWN` and no marker is written. |

## Next

- [Respond to review threads](how-to-respond-to-review-threads.md)

## Reference

- [review skill](../../.claude/skills/review/SKILL.md)
- [Marker format](../../.claude/skills/review/resources/marker-and-no-task.md)
- [Axis selection](../../.claude/skills/review/resources/axis-selection.md)
- [CodeQL pre-step](../../.claude/skills/review/resources/codeql-prestep.md)
- [ADR-041: CodeQL integration](../../.project-toolkit/architecture/ADR-041-codeql-integration.md)
