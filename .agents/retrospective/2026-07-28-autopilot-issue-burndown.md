# Retrospective: autopilot issue burndown, 2026-07-28

## Session Info

- **Date**: 2026-07-28
- **Agents**: Copilot CLI orchestrator, ~70 background sub-agents
  (`code-review` on gpt-5.6-sol for every adversarial pass, `general-purpose`
  on claude-opus-4.8 for fixes)
- **Task Type**: Bug burndown
- **Outcome**: In progress. Roughly 30 PRs open at the time of writing,
  reviewed adversarially by a model different from the authoring model.

## Phase 0: Data Gathering

### 4-Step Debrief

- **Observe**: Every adversarial review that ran a validator against
  adversarial input found a defect the authoring agent had not. Every review
  that only read the diff found style nits. The delta was not model quality;
  it was whether the reviewer executed anything.
- **Respond**: The standing review brief was rewritten to demand a command,
  its verbatim output, and an exit code behind every claim, plus a per-test
  PASS or FAIL under revert table.
- **Analyze**: Two defect shapes account for the majority of findings across
  more than a dozen PRs. They are recorded below because they will recur.
- **Apply**: Pre-load the known false positives into every rework brief.
  Reviewers who were not inoculated repeated the same wrong finding twice.

## Findings

### Defect shape 1: a permissive result for input that was never evaluated

Seven separate validators shipped this in a single day. The phrasing that
made it legible to the fixing agents:

> A measurement you did not take is not a measurement of zero.

Instances found:

- A scanner truncating its finding list at a budget, discarding a live
  finding, and still exiting 0. Which finding survived depended on unsorted
  filesystem iteration order.
- Broken symlinks failing open in both the directory walker and the checker.
- A UTF-16 file decoded with `errors="replace"`, producing mojibake that then
  matched nothing and "passed".
- File-scope ignores counted as scanned but never reported as suppressed.
- `markdown-it` with `maxNesting: 20` silently ceasing to emit fence tokens,
  so a marker inside fenced example code became an active finding.
- A missing timestamp treated as an early timestamp, and an unknown event
  type treated as a test event, in causal-link extraction.

The review question that catches it: for every early return, `continue`,
`except`, budget cap, and nesting or size limit, does this path report clean
for input it never evaluated?

### Defect shape 2: tautological tests

Eight sibling PRs shipped tests that pass with the production change
reverted. Shapes seen:

- Asserting an absence (no finding, exit 0), which is equally true when the
  matcher does not exist at all.
- A fixture that trips an earlier guard before the code under test is reached.
- Invariants that were already green before the change, presented as
  red-before evidence. Nine of seventeen on one PR, seven on another.

The only method that reliably catches it is mechanical: revert the production
change in a scratch copy and record PASS or FAIL for every test.

### Defect shape 3: a test suite nothing collects

`testpaths = ["tests"]`, so the 60 test files under `.claude/skills/*/tests/`
are never selected by CI or by pre-push. A PR landed ten regression tests
there; default collection selected zero. Filed as issue #3593.

## Phase 1: What Went Wrong

1. **The same false positive was reported by two independent reviewers.**
   Both claimed the two plugin manifests must be byte-identical, citing a
   `cmp` difference at line 3. `check_plugin_manifest_parity.py` compares the
   `version` field only, and main deliberately ships different `description`
   strings. Cost: two rework cycles on correct code. Fix applied: the
   correction is now pre-loaded into every rework brief.

2. **A test-environment artifact was misattributed to a PR for hours.**
   Twenty-eight failures reproduce only when `TMPDIR` and `--basetemp` point
   inside the worktree; a fixture directory meant to be "not a git
   repository" then sits inside the real repo and `git check-ignore` returns
   the real repo's rules. Reviewers using the default out-of-tree `/tmp`
   measured zero and reported the PR clean. Fix applied: every suite count
   must now be reported alongside its TMPDIR configuration.

3. **Merge blocking was diagnosed against the wrong mechanism.**
   `repos/OWNER/REPO/branches/main/protection` returns 404 here; the
   protection is a ruleset. The blocker on a green PR was an unresolved
   review thread under the `code_quality` rule, not a missing approval.
   `gh api repos/OWNER/REPO/rules/branches/main` is the correct probe.

4. **Two independent PRs were opened for the same issue, twice.** Concurrent
   agents claimed issue #3511 in two PRs and issue #3565 in two more.
   Checking `closingIssuesReferences` before assigning is necessary and was
   not always done.

## Phase 2: What Went Right

- Splitting review from implementation across model families surfaced
  defects that the authoring model consistently missed on its own diff.
- Merging `origin/main` rather than rebasing kept squash-merged ancestors
  from replaying as phantom conflicts. Two conflicted PRs became mergeable
  with zero manual hunks.
- Guarded fast-forward pushes with a live-state check before edit and again
  before push preserved every concurrent commit despite two agents pushing
  under the same git author.

## Phase 3: Actions

- [x] File issue #3593 for the uncollected skill test suites.
- [x] Record the manifest-parity semantics as a durable memory so the false
      positive is not reported a third time.
- [ ] Decide whether the duplicate PRs for #3511 and #3565 are merged,
      narrowed, or closed.
- [ ] Add a regression guard that fails when the count of collected skill
      tests drops to zero.

## References

- `build/scripts/check_plugin_manifest_parity.py`
- `scripts/validation/git_hook_policy.py`
- `pyproject.toml`
- Issues #3511, #3565, #3593, #3371
