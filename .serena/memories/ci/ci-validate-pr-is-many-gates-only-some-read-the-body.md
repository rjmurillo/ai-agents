# `Validate PR` Is Many Gates, Only Some Read the Body

## First: a red `Validate PR` is usually not about the description at all

`Validate PR` is a 23-step job as of `origin/main` at `03dc6a9ca` (2026-08-03).
Description validation is steps 5 through 10. Steps 11 through 23 are separate gates
that share the check name and can red it on their own.

Parse the workflow rather than grepping it, and parse it in a tree that is actually
at current `origin/main`. A grep for step names miscounts, and the shared checkout at
`~/src/GitHub/rjmurillo/ai-agents` sits on a detached HEAD that is usually behind
main, so a parse there answers about the wrong commit:

```bash
uv run --frozen python -c "import yaml,pathlib;\
d=yaml.safe_load(pathlib.Path('.github/workflows/pr-validation.yml').read_text());\
[print(i,'SOFT' if s.get('continue-on-error') else 'HARD','if' if s.get('if') else '--',s.get('name')) \
 for i,s in enumerate(d['jobs']['validate-pr']['steps'],1)]"
```

| Step | Hard? | Fails when |
|---|---|---|
| 5. Validate PR Description vs Diff | **no** | never. Maps the verdict into `validation_result` and returns 0 |
| 6. Validate PR Description Standards | hard | the standards validator errors |
| 7. Check QA Report Exists | hard | the step errors; a missing report only warns |
| 8. Generate Validation Report | **no** | never. `build_pr_validation_report.py` ends in an unconditional `return 0` |
| 9. Post PR Comment | **soft** | never reds the job |
| 11. Check PR commit count | hard | the counting step errors |
| 12, 13. needs-split label ops | **soft** | never red the job |
| 14. Enforce Blocking Issues | hard | `OVERALL_STATUS` is `FAIL`/`ERROR`, or `COMMIT_STATUS` is `BLOCKED` |
| 17. Validate workflow YAML | hard | a changed workflow does not parse or lint |
| 18. Check bare-python3 documentation entrypoints | hard | docs invoke bare `python3` where `uv run` is required |
| 19. ADR-006 run-block ratchet | hard | inline logic added to workflow YAML |
| 20. taste-lint error-count ratchet | hard | the recorded baseline sits above the base branch's |
| 21. type-ignore count ratchet | hard | type-ignore count rose |
| 22. Check for conflict markers | hard | a merge marker survived into the diff |
| 23. Enforce model pin policy | hard | a model reference is unpinned |

Three consequences that are easy to miss.

**A description failure surfaces as `Enforce Blocking Issues`, not as a description
step.** This is the single most misleading thing about this job. Steps 5 and 8 both
compute a verdict and then exit 0, writing it into a step output instead of failing:

```python
# scripts/ci/map_pr_description_result.py  (step 5)
return _append_output("validation_result", _status_for_exit_code(result.returncode))
```

`scripts/ci/enforce_pr_validation.py` (step 14) is the only script in the description
path that returns 1:

```python
if overall_status in {"FAIL", "ERROR"}: ... return 1
if commit_status == "BLOCKED": ...      return 1
```

Its name reads as "a linked issue is blocking." It has no linked-issue logic at all.
It aggregates the earlier step outputs. So the advice one section down, "read the
failing step name," is necessary but not sufficient: the name you get for a bad
description is `Enforce Blocking Issues`, and chasing issue links from there wastes
the trip. Read the step's `OVERALL_STATUS` and `COMMIT_STATUS` inputs instead.

**Steps 16 through 23 carry no `if` guard.** Steps 3 through 14 are gated on
`steps.should-run.outputs.skip != 'true'`, and step 15 runs only on the inverse. So on
a PR where description validation is skipped, `Validate PR` still runs eight gates and
can still go red. A red check is not evidence that the description was even read.

**The count ratchets fail on branch staleness, not on anything the branch did.**
`BASELINE ABOVE BASE. This tree records 598, FETCH_HEAD records 597` means main
lowered the baseline after this branch forked. `gh pr update-branch <N>` merges main
server-side and fixes it without a local worktree. See
[ci-count-ratchets-require-branch-freshness](ci-count-ratchets-require-branch-freshness.md).

Measured 2026-08-03: PRs #4438, #4411, and #4392 were red on `Validate PR` with
descriptions that passed the description validator cleanly. All three were step 20
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
**file-mention** CRITICALs and downgrades the verdict to `BYPASSED`, which is recorded
in the job summary with the suppressed count.

It does not suppress everything. `scripts/validation/pr_description.py:872` carves out
the dash rule and checks it before the bypass:

```python
dash_issue_types = {"Em/en-dash in PR title", "Em/en-dash in PR description"}
has_dash_critical = any(...)
if args.ci and has_dash_critical:
    return print_results(issues, ci=args.ci)   # exits 1 regardless of the label
```

So a body with an em-dash stays red with the label applied. Reaching for the bypass on
a dash failure looks like a broken escape hatch and is working as designed. Fix the
dash.

## Evidence

PRs #4428, #4433, #4438, #4431, #4426, #4411, #4392, and #4412 all failed the
description check with `[CRITICAL] File mentioned but not in diff`. None was a
template WARN. Template-only fixes applied to #4428 and #4412 in an earlier pass left
both PRs red, which is what exposed the mistake.

Fixing the descriptions did not turn every one of those PRs green. Several stayed red
on a second, unrelated gate inside the same job, which is why the first section of
this memory exists. Two independent causes can hide behind one check name, and
clearing one of them proves nothing about the other. #4438, #4411, and #4392 were the
confirmed cases: all three were step 20 at 598 versus 597, with descriptions that
passed the description validator cleanly.

## Related

- [ci-infrastructure-003-job-status-verdict-distinction](ci-infrastructure-003-job-status-verdict-distinction.md).
  Same shape one gate over: a job's status is not the same as its verdict.
