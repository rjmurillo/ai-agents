# `Validate PR` Is Many Gates, Only Some Read the Body

## First: a red `Validate PR` is usually not about the description at all

`Validate PR` is a 22-step job. Description validation is steps 5 through 10.
Steps 11 through 22 are separate gates that share the check name and can red it on
their own. Parse the workflow rather than grepping it; a grep for step names
overcounts and picks up neighbours:

```bash
uv run --frozen python -c "import yaml,pathlib;\
d=yaml.safe_load(pathlib.Path('.github/workflows/pr-validation.yml').read_text());\
[print(i,s.get('name'),'SOFT' if s.get('continue-on-error') else 'HARD') \
 for i,s in enumerate(d['jobs']['validate-pr']['steps'],1)]"
```

Measured 2026-08-03 against `.github/workflows/pr-validation.yml`:

| Step | Hard? | Fails when |
|---|---|---|
| 5. Validate PR Description vs Diff | hard | the body claims a file the diff does not touch |
| 6. Validate PR Description Standards | hard | the standards validator errors |
| 7. Check QA Report Exists | hard | the step itself errors, a missing report only warns |
| 8. Generate Validation Report | hard | `description` came back `FAIL` or `ERROR` |
| 9. Post PR Comment | **soft** | never reds the job |
| 11. Check PR commit count | hard | the counting step errors |
| 12, 13. needs-split label ops | **soft** | never red the job |
| 14. Enforce Blocking Issues | hard | a linked issue is marked blocking |
| 15. ADR-006 run-block ratchet | hard | inline logic added to workflow YAML |
| 18. Validate workflow YAML | hard | a changed workflow does not parse or lint |
| 19. taste-lint error-count ratchet | hard | the recorded baseline sits above the base branch's |
| 20. type-ignore count ratchet | hard | type-ignore count rose |
| 21. Check for conflict markers | hard | a merge marker survived into the diff |
| 22. Enforce model pin policy | hard | a model reference is unpinned |

Two consequences that are easy to miss.

**Steps 17 through 22 carry no `if` guard.** Every earlier step is gated on
`steps.should-run.outputs.skip != 'true'`. So on a PR where description validation
is skipped entirely, `Validate PR` still runs six gates and can still go red. A red
check is not evidence that the description was even read.

**The count ratchets fail on branch staleness, not on anything the branch did.**
`BASELINE ABOVE BASE. This tree records 598, FETCH_HEAD records 597` means main
lowered the baseline after this branch forked. Merging main fixes it. See
[ci-count-ratchets-require-branch-freshness](ci-count-ratchets-require-branch-freshness.md).

Measured 2026-08-03: PRs #4438, #4411, and #4392 were red on `Validate PR` with
descriptions that passed the description validator cleanly. All three were step 19
at 598 versus 597.

**So read the failing step name before touching the PR body.**

```bash
gh pr checks <N> --json name,state,link -q '.[] | select(.name=="Validate PR" and .state=="FAILURE") | .link'
gh run view --job <job-id> --log-failed
```

## When the description IS the cause

Conventional reading of a red description check: the job printed `WARN`, warnings
are complaints, so fix the warnings and the check goes green.

That is wrong here, and acting on it wastes a full CI round trip. Three of the four
signals feeding the validation report can never turn it red. Only one can. Fixing the
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

PRs #4428, #4433, #4438, #4431, #4426, #4411, #4392, and #4412 all failed the
description check with `[CRITICAL] File mentioned but not in diff`. None was a
template WARN. Template-only fixes applied to #4428 and #4412 in an earlier pass left
both PRs red, which is what exposed the mistake.

Fixing all eight descriptions turned `Validate PR` green on only five. The other
three were red for a second, unrelated reason in the same job, which is why the first
section of this memory exists. Two independent causes can hide behind one check name,
and clearing one of them proves nothing about the other.

## Related

- [ci-infrastructure-003-job-status-verdict-distinction](ci-infrastructure-003-job-status-verdict-distinction.md).
  Same shape one gate over: a job's status is not the same as its verdict.
