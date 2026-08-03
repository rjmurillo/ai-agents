# The `Validate PR` Job Has Four Signals But Only One Blocks

## The contradiction

Conventional reading of a red `Validate PR` check: the job printed `WARN`, warnings
are complaints, so fix the warnings and the check goes green.

That is wrong here, and acting on it wastes a full CI round trip. Three of the four
signals feeding the job's verdict can never turn it red. Only one can. Fixing the
loud advisory output while leaving the quiet blocker in place leaves the check red
and looks like the fix did not take.

## The mapping

`scripts/ci/build_pr_validation_report.py` is authoritative. `_overall_status`
assigns `status` from exactly one input:

| Input | Source | Can set `status = FAIL`? |
|---|---|---|
| `description` | `pr_description.py` exit code | **Yes.** `FAIL` blocks, `ERROR` blocks |
| `template` | the github-skill template validator | No. Appends to `warnings` only |
| `keywords` | issue-linking keyword scan | No. Appends to `warnings` only |
| `qa_exists` | QA report presence | No. Appends to `warnings` only |

So a missing Specification References table, a missing `[x]`, a `## Changes`
followed by `###`, and a missing `Fixes #N` are all advisory. None of them reds the
job.

## The one blocker

`description` is the exit code of `scripts/validation/pr_description.py`, mapped by
`scripts/ci/map_pr_description_result.py`:

- exit `0` maps to `PASS`
- exit `1` maps to `FAIL`
- anything else maps to `ERROR`

`pr_description.py` emits two severities and only one of them changes the exit code:

- `[CRITICAL] File mentioned but not in diff`. Exits 1. **This is the blocker.**
- `[WARNING] Significant file not mentioned`. Exits 0. Advisory.

The check is one-directional on purpose. Claiming a file you did not change is a
lie about the diff and blocks. Changing a file you did not mention is an omission
and only warns.

## Diagnose by exit code, never by grepping output

A warnings-only run prints a paragraph of `[WARNING]` blocks and does not print the
clean-pass line. Grepping stdout for a success string therefore reports a passing PR
as failing. A fleet sweep built that way produced twelve false positives against
twelve PRs that were already green.

Use the exit code:

```bash
uv run --frozen python scripts/validation/pr_description.py --pr-number <N> --ci
echo $?   # 0 = not blocking, 1 = blocking
```

The script reads the **live** PR from GitHub, so push the body with
`gh pr edit <N> --body-file <path>` before validating. Validating a local file
proves nothing.

## Fixing the blocker

The validator states its own parsing rule in the failure text: inline-backtick file
paths **outside** `## Changes`, `## Per-file changes`, `## Files Changed`, and
`## Changed Files` are informational. Inside those headings they parse as claims
about the diff.

The recurring trap is naming a *tool* or a *reference* under `## Changes`:

```markdown
## Changes

- `.serena/memories/memory-index.md`: entry measured with `count_memory_tokens.py`
```

`count_memory_tokens.py` is the measuring instrument, not a changed file, but under
`## Changes` it parses as a claim and blocks. Move the mention under `## Verification`
or `## Testing`, or drop the extension so it stops looking like a path.

Escape hatch of last resort: the `description-validation-bypass` label. It suppresses
CRITICALs and downgrades the verdict to `BYPASSED`, which is recorded in the job
summary with the suppressed count.

## Evidence

PRs #4428, #4433, #4438, #4431, #4426, #4411, #4392, and #4412 were all red on
`Validate PR`. Every one was `[CRITICAL] File mentioned but not in diff`. None was a
template WARN. Template-only fixes applied to #4428 and #4412 in an earlier pass left
both PRs red, which is what exposed the mistake.

## Related

- [ci-infrastructure-003-job-status-verdict-distinction](ci-infrastructure-003-job-status-verdict-distinction.md).
  Same shape one gate over: a job's status is not the same as its verdict.
