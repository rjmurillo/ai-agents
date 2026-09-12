---
name: ship
version: 1.0.0
description: Run the four pre-flight checks, then create the PR or validate a contributor branch without touching it. Use when you say `ship it`, `ship this branch`, or `run pre-flight and open the PR`, and run it after review. Do NOT use to open a PR without the gates (use push-pr), and do NOT use to run the review axes themselves (use review).
license: MIT
allowed-tools: Task, Skill, Read, Glob, Grep, Bash(*)
argument-hint: target-branch
user-invocable: true
---

# Ship

Pre-flight validation, CI check, and PR creation, branching on VCS host and on
whether the branch is yours.

Migrated from `.claude/commands/ship.md` under ADR-064, which makes skills the
single user-invocable surface.

## Triggers

`ship it`, `ship this branch`, `run pre-flight and open the PR`,
`is this ready to ship`

## Arguments

Ship: the problem statement from the conversation (under Copilot CLI the skill tool takes no argument vector, so state it in your message)

Default target is main unless specified. If `$ARGUMENTS` names a different branch, use that as the target.

## Mode Detection

Run this block BEFORE the pre-flight checks. It sets two variables, `host` and `mode`, that branch every step below. State the detected `host` and `mode` in the ship report.

### 1. VCS host detection

Derive the host from the origin remote URL:

```bash
remote_url="$(git remote get-url origin 2>/dev/null || true)"
if [ -z "$remote_url" ]; then
  echo "ERROR: origin remote is not configured; cannot detect VCS host." >&2
  exit 2
fi
case "$remote_url" in
  *dev.azure.com*|*visualstudio.com*) host=ado ;;
  *) host=github ;;
esac
redacted_remote_url="$(printf '%s' "$remote_url" | sed -E 's#(https://)[^/@]+@#\1[redacted]@#')"
echo "host=$host (origin: $redacted_remote_url)"
```

`dev.azure.com` or `visualstudio.com` anywhere in the URL means `host=ado`; everything else is `host=github`. This match covers both Azure DevOps remote URL shapes:

- HTTPS: `https://dev.azure.com/<org>/<project>/_git/<repo>` and the legacy `https://<org>.visualstudio.com/<project>/_git/<repo>`.
- SSH: `git@ssh.dev.azure.com:v3/<org>/<project>/<repo>` and the legacy `<org>@vs-ssh.visualstudio.com:v3/<org>/<project>/<repo>`.

### 2. PR ownership and existence detection

Determine two facts:

- **(a) Branch ownership.** Are you on a branch you own (you created it and push to it freely), or are you a contributor pushing commits onto someone else's feature branch? Treat a branch whose open PR lists a different author as not yours.
- **(b) Open PR exists for this branch.** Query the host:
  - `host=github`: `gh pr view --json number,author,state,url` for the current branch. Treat the result as an open PR only when the JSON `state` field is exactly `OPEN`. A non-zero exit can mean "no PR exists" or "the query itself failed" (auth, network, API rate limit). Distinguish these: capture both stdout and stderr, then check whether stderr contains the documented no-PR message (e.g. "no pull requests found"). Only set `pr=none` on that specific signal. On any other non-zero exit, stop with an error; do not assume no PR exists.
  - `host=ado`: derive `branch_ref="refs/heads/$(git rev-parse --abbrev-ref HEAD)"`, then run `az repos pr list --source-branch "$branch_ref" --status active --output json`. An empty array means no open PR for the branch.

Set the mode:

- If an open PR exists AND you are not its author (you are pushing onto a colleague's branch), `mode=contributor`.
- Otherwise `mode=owner`.

Set `pr` from fact (b): `pr=#<number>` when an open PR exists for this branch, `pr=none` otherwise. `pr` selects the pipeline-validation ordering in pre-flight check 1 and MUST appear in the ship report. `mode=contributor` implies `pr=#<number>`; only `mode=owner` can reach `pr=none`.

`mode=contributor` means you may run readiness checks and the `/review` axes, but you MUST NOT write a marker commit onto the shared branch, create a PR, or merge. Writing a SHA-bound review marker commit onto a branch you do not own pollutes the owner's PR with a foreign workflow artifact and is prohibited in this mode.

## Pre-flight Checks

A gate is any check whose failure would falsify your conclusion. Only a current result on the exact state and scope clears it. Failure, timeout, stale run, skip, or subset leaves the claim unproved. Say what ran and what returned. If blocked, name who can clear it.

`agent_type: "project-toolkit:devops"`: You are a release engineer. Run all 4 pre-flight checks below, branching by the `host`, `mode`, and `pr` set in Mode Detection. Report pass/fail for each with specific evidence. Any failure blocks shipping.

1. **Pipeline health**
   - `host=github`, `pr=#<number>` (open PR exists): Invoke `skill: "pipeline-validator"`. All CI checks green? No suppressed failures?
   - `host=github`, `pr=none` (no open PR; `mode=owner` only): pipeline validation is DEFERRED, not skipped. The pipeline-validator skill's Step 1 states its contract verbatim: "**No PR found:** Report to user. A PR must exist before pipeline validation. The calling skill should have created one." Invoking it here stops the run before Process step 3, which is the step that creates the first PR, so the branch can never leave this state (Issue #4841). Do NOT invoke it now. Record `Pipeline: DEFERRED (pr=none; validated in Process step 4)` and run checks 2-4, which are the local readiness checks. Process step 4 discharges the deferral against the PR that `/push-pr` creates; a failure there fails the ship.
   - `host=ado`: pipeline-validator does not apply. Evaluate ADO build policies for the branch behind a Bash step instead. List the active branch policies and the latest policy or build status, then confirm every required policy is satisfied:

     ```bash
     branch_ref="refs/heads/$(git rev-parse --abbrev-ref HEAD)"
     pr_id="$(az repos pr list --source-branch "$branch_ref" --status active --query '[0].pullRequestId' --output tsv)"
     if [ -n "$pr_id" ]; then
       az repos pr policy list --id "$pr_id" --output table
     else
       az pipelines build list --branch "$branch_ref" --status completed --top 1 --output table
     fi
     ```

     PASS only when every required ADO build policy reports succeeded. No required policy queued, failed, or waiting.
2. **Security posture** - Invoke `skill: "security-scan"`. No new CWE findings? No secrets in diff? This check is host-agnostic: the scan is regex over the diff and applies identically to GitHub and ADO repos.
3. **Reviewed on this SHA** - The shipped code must carry SHA-bound `/review` proof (Issue #1938). The proof shape depends on `mode`:
   - **`mode=owner` (marker commit required; behavior unchanged).** First confirm `git status --porcelain` is empty. If any file is staged or modified, this check FAILS: commit the change, re-run `/review`, then re-run `/ship`. `/push-pr` must only push the existing marker commit; it must not create a new commit after this check passes. Then run the review-skill validator:
     - Resolve the validator through the skill dir when available, otherwise
       through the portable plugin-root form. The root walk and its exit-code
       table live in `references/review-marker-resolution.md`; run the command
       it gives you, then read the exit code below.

     The validator exits `0` only when HEAD is a `/review` marker commit whose `Reviewed-By: /review@<axes> on <sha>` trailer binds the reviewed tip (its parent). Exit `1` means no marker, a stale marker, or new code landed after review; exit `2` is a config error. On any non-zero exit, this check FAILS: run `/review` on this branch (it writes the marker on a PASS verdict), then re-run `/ship`. This replaces the old "has /review been run somewhere?" check with proof it passed on the exact code being shipped. Because `/review` is the strict superset of CI (Child 1 #1934), a passing marker covers golden-principles, taste-lints, and code-quality too; there is no separate standards check.

   - **`mode=contributor` (advisory; no marker commit).** Writing the empty `Reviewed-By` marker commit onto a shared branch is PROHIBITED here: it pollutes the owner's PR. Do NOT run the marker validator and do NOT commit a marker. Instead, run the `/review` axes and accept a non-commit attestation as the proof: a `/review` run logged in the ship report (the axes run plus verdict on the current HEAD SHA), or that same result posted as a PR comment. This check is advisory in contributor mode: a clean `/review` result records the attestation; it never blocks and never mutates the branch.

4. **Tests passing** - All tests green? No skipped tests without justification?

> `golden-principles` + `taste-lints` + `code-quality` are now part of `/review` (Child 1 #1934), so `/ship` does not invoke them separately. `/pr-quality:all` is likewise no longer a required separate step before `/ship`: a passing `/review` marker (check 3) already runs the same canonical axes locally, and CI runs the same prompts as a backstop.

## Process

1. Run all 4 pre-flight checks, branching by `host`, `mode`, and `pr`.
2. If any blocking check fails: report what failed, why, and how to fix. Stop. (In `mode=contributor`, check 3 is advisory and never blocks. A `Pipeline: DEFERRED` result from check 1 is not a failure and does not stop the run.)
3. If no blocking check failed:
   - `mode=owner`, `host=github`: run /validate-pr-description to validate PR metadata, then run /push-pr to commit, push, and open the GitHub PR.

     Commit messages MUST follow `<type>(<scope>): <desc>` and include a `Co-Authored-By:` trailer when authored with an AI agent.
   - `mode=owner`, `host=ado`: run /validate-pr-description, then create the PR with `az repos pr create` (the gh-based /push-pr does not apply to ADO).
   - `mode=contributor`: do NOT create a PR and do NOT merge. The PR already exists and is the owner's call. Emit the ship report with `RESULT: VALIDATED` and the recorded `/review` attestation.
4. Discharge a deferred pipeline check. When check 1 recorded `Pipeline: DEFERRED` (`host=github`, `mode=owner`, `pr=none`), validate CI on the PR that `/push-pr` just created. Capture the PR number from the `/push-pr` output. The pipeline-validator skill is host-aware only for ADO; for GitHub, query CI status directly through the GitHub skill's check-status flow (`python3 "$SCRIPTS_DIR/pr/get_pr_checks.py" --pull-request <number> --wait --timeout-seconds 300`, where `SCRIPTS_DIR` is resolved per the GitHub skill pattern). The discharge requires BOTH exit code 0 AND `Data.AllPassing == true` in the structured output; a no-check PR exits 0 with `AllPassing: false`, so exit code alone is insufficient. All CI checks green and `Data.AllPassing == true` makes the check `DEFERRED->PASS`. Otherwise it is `DEFERRED->FAIL`, `RESULT: BLOCKED`, and the report names the failing checks; the PR stays open and the fix lands on the branch. A deferred check MUST NOT be reported as PASS without this run.
5. Report: host, mode, `pr` at pre-flight time, what was validated or shipped, PR link, any warnings.

## Principles

- **Faster is safer**: Small, frequent shipments reduce blast radius. Ship early.
- **No deliberate debt**: If it is not ready, do not ship it. Fix it or defer it.
- **Observability first**: If you cannot measure it, you cannot ship it safely.
- **Do not pollute shared branches**: In contributor mode, never write a marker commit, create a PR, or merge onto a branch you do not own.

## Output

Ship report:

```text
HOST: github|ado
MODE: owner|contributor
PR-AT-PREFLIGHT: none|#<number>

PRE-FLIGHT:
  Pipeline:  PASS|FAIL|DEFERRED->PASS|DEFERRED->FAIL (evidence; DEFERRED-> forms mean pr=none at check 1 and validated after /push-pr)
  Security:  PASS|FAIL (evidence)
  Reviewed:  PASS|FAIL|ADVISORY (owner: SHA-bound /review marker on HEAD; contributor: /review attestation, no marker commit)
  Tests:     PASS|FAIL (evidence)

RESULT: SHIPPED|VALIDATED|BLOCKED
PR: [link if created; "existing, not modified" in contributor mode]
WARNINGS: [non-blocking concerns]
NEXT: [monitoring, follow-up items]
```

`RESULT: VALIDATED` is the contributor-mode terminal state: readiness checks and `/review` axes ran, no marker commit was written, no PR was created, and nothing was merged.

> After reporting a completed requested result, remove any unsolicited offer, question, or invitation whose only function is to continue the interaction.

A bare `Pipeline: DEFERRED` in a finished report is a defect: the deferral is discharged by Process step 4, so a completed run reports `DEFERRED->PASS` or `DEFERRED->FAIL`.

> When every requested deliverable satisfies the frozen task contract and no blocker remains, the current task is terminal. Stop autonomous work.

## Claude Model Behavioral Patches

These nudges are tuned for the Claude model family (Anthropic models) and bind whenever Claude is the runtime model, regardless of harness. They are subordinate to this skill's own workflow steps, STOP points, and exit gates: when a patch below conflicts with one of those, the skill wins.

### Todo-list Discipline

When working through a multi-step plan, mark each task complete individually as you finish it. Do not batch-complete at the end. If a task turns out to be unnecessary, mark it skipped with a one-line reason.

Reason: a batched complete-everything-at-the-end pattern hides progress from the user and from any orchestrator watching the run. If the model crashes or the session ends mid-run, the todo list still reflects reality up to the last completed step. Batched updates make every recovery start from zero.

Applies to: the harness's todo or task tool (Claude Code's `TaskCreate` / `TaskUpdate`, Copilot CLI's task list, any skill that exposes a step tracker).

**Parallel tasks.** Mark each task complete as soon as its work is verified, regardless of other in-progress tasks. Do not wait for siblings to finish.

### Think Before Heavy Actions

For complex operations, state your approach in 2 to 3 sentences before executing. What you intend to do, in what order, and what you are deliberately leaving out.

What counts as a "heavy action":

- A refactor that touches 4 or more files.
- A migration (schema, format, API version, dependency major bump).
- A new feature that touches more than one file OR more than one logical component.
- Anything that changes a public contract (signature, exported type, wire format, configuration shape).
- Anything irreversible without significant cleanup (delete, rewrite, force-push, schema drop).

The cost of a two-sentence preamble is roughly zero. The cost of a 30-minute rollback is everything. The user course-corrects cheaply when the plan is visible up front; not when the diff is already on disk.

**When a heavy action fails midway.** Mark the in-flight task as failed with a one-line reason. If partial changes are reversible (uncommitted edits, unpushed commits), revert them. If not (pushed commits, mutated external state), state what was changed and what was not. Ask the user before retrying; do not retry blindly.

### Dedicated Tools Over Bash

Prefer Read, Edit, Write, Glob, Grep over their shell equivalents (`cat`, `sed`, `find`, `grep`).

Why:

- **Cheaper.** The dedicated tools have lower context impact. Bash pipes paste full outputs into the conversation; the dedicated tools surface only what they actually need.
- **Clearer.** The tool name announces the intent. A reviewer scanning the transcript can read "Edit auth.ts" faster than parsing `sed -i 's/foo/bar/g' auth.ts`.
- **Safer.** No shell quoting traps. No command-injection surface. No accidental glob expansion against paths the model did not intend.

Reserve Bash for operations the dedicated tools cannot perform: `git`, package managers (`npm`, `pip`, `uv`, `cargo`), build runners (`make`, `uv run python build/scripts/build_all.py`), anything that needs a real shell environment or a multi-stage pipe.

**When a dedicated tool is unavailable in the current harness.** Fall back to the closest Bash equivalent and state the fallback in your response so the user knows the tool boundary was crossed.

Specific anti-patterns to reject:

- `cat <file>` to read for analysis. Use Read.
- `grep <pattern>` for symbol or text search. Use Grep.
- `find . -name <pattern>` for file location. Use Glob.
- `sed -i` to mutate a file. Use Edit.
- Heredocs to create a new file. Use Write.

Allowed Bash patterns:

- `git status`, `git log`, `git diff`, `git add`, `git commit`, `git push`.
- `gh <subcommand>` for GitHub API operations the harness does not expose.
- `python3 build/scripts/<name>.py` and other repo-specific runners.
- `mkdir`, `rm`, `mv` for directory operations.
- One-shot diagnostics (`uname`, `which`, `ls -la <specific path>`) when a dedicated tool does not cover it.

### Quick Self-Check

Run this check only at decision points: starting a heavy action, switching tasks, or about to call Bash. Not every turn; the per-turn overhead would compete with throughput.

- If this is one step in a multi-step plan, is the previous step's todo already marked complete?
- If this action is heavy (per the list above), did I state the approach?
- If I am about to call Bash, is there a dedicated tool that would do this better?

If any answer is "no" or "not sure," adjust before proceeding.

<!-- vendor-portability: declared. `build/scripts/build_all.py` and `build/scripts/<name>.py` above are example Bash-allowed runners describing what the upstream checkout permits, not a runtime instruction a vendored install resolves; `build/` ships in neither plugin root. Migrated from the retired `.claude/rules/claude-model-patches.md` (epic #5456). Issue #2050. -->

## Verification

- [ ] `host` and `mode` detected before any pre-flight check, and both stated in the report
- [ ] `pr` set from a real query, with a failed query distinguished from no-PR
- [ ] All four pre-flight checks ran, each with specific evidence
- [ ] In owner mode, the SHA-bound review marker validated against HEAD and its parent
- [ ] In contributor mode, no marker commit written, no PR created, nothing merged
- [ ] Any `Pipeline: DEFERRED` discharged in Process step 4 and reported as `DEFERRED->PASS` or `DEFERRED->FAIL`
- [ ] The discharge checked both exit code 0 and `Data.AllPassing == true`

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Treating a failed PR query as no PR | A network or auth failure then reads as `pr=none`, and the run ships against a PR it never checked | Only set `pr=none` on the documented no-PR message; stop on any other non-zero exit |
| Invoking pipeline-validator when `pr=none` | Its own contract stops the run before the step that creates the first PR, so the branch can never leave that state (#4841) | Record `Pipeline: DEFERRED` and discharge it in step 4 |
| Reporting a bare `Pipeline: DEFERRED` as finished | The deferral is the promise, not the result; a finished report carrying it never checked CI | Discharge it, or report `DEFERRED->FAIL` |
| Reading exit code 0 alone as CI green | A PR with no checks exits 0 with `AllPassing: false` | Require both exit 0 and `Data.AllPassing == true` |
| Writing a review marker onto a shared branch | Pollutes the owner's PR with a foreign workflow artifact | In contributor mode, attest without committing |
| Committing to clear a dirty tree at check 3 | The marker then binds a tip nobody reviewed | Commit, re-run review, then re-run ship |

## Extension Points

- **Another VCS host.** Mode Detection's `case` and each check's host branch are
  the only host-aware parts; the review-marker and security checks are
  host-agnostic by construction.
- **New pre-flight check.** Add it to the numbered list, to the report block, and
  to the Verification list together, so it cannot run unreported.
- **Different review proof.** Check 3 accepts a marker commit in owner mode and
  an attestation in contributor mode. A project with a different proof swaps
  those two branches and nothing else.
