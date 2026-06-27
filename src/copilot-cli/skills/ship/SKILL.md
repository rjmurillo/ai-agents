---
name: ship
description: Ship it. Pre-flight validation, CI check, and PR creation. Run after /review.
argument-hint: target-branch
allowed-tools: Task, Skill, Read, Glob, Grep, Bash(*)
user-invocable: true
---

<!-- Copilot CLI: project instructions (CLAUDE.md) load via the plugin instructions tree; no include directive needed. -->
Ship: the problem statement from the conversation (under Copilot CLI the skill tool takes no argument vector, so state it in your message)

Default target is main unless specified. If the problem statement from the conversation (under Copilot CLI the skill tool takes no argument vector, so state it in your message) names a different branch, use that as the target.

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
  - `host=github`: `gh pr view --json number,author,state,url` for the current branch. Treat the result as an open PR only when the JSON `state` field is exactly `OPEN`. A non-zero exit or any other state means no open PR for contributor-mode detection.
  - `host=ado`: derive `branch_ref="refs/heads/$(git rev-parse --abbrev-ref HEAD)"`, then run `az repos pr list --source-branch "$branch_ref" --status active --output json`. An empty array means no open PR for the branch.

Set the mode:

- If an open PR exists AND you are not its author (you are pushing onto a colleague's branch), `mode=contributor`.
- Otherwise `mode=owner`.

`mode=contributor` means you may run readiness checks and the `/review` axes, but you MUST NOT write a marker commit onto the shared branch, create a PR, or merge. Writing a SHA-bound review marker commit onto a branch you do not own pollutes the owner's PR with a foreign workflow artifact and is prohibited in this mode.

## Pre-flight Checks

Task(subagent_type="devops"): You are a release engineer. Run all 4 pre-flight checks below, branching by the `host` and `mode` set in Mode Detection. Report pass/fail for each with specific evidence. Any failure blocks shipping.

1. **Pipeline health**
   - `host=github`: Invoke Skill(skill="pipeline-validator"). All CI checks green? No suppressed failures?
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
2. **Security posture** - Invoke Skill(skill="security-scan"). No new CWE findings? No secrets in diff? This check is host-agnostic: the scan is regex over the diff and applies identically to GitHub and ADO repos.
3. **Reviewed on this SHA** - The shipped code must carry SHA-bound `/review` proof (Issue #1938). The proof shape depends on `mode`:
   - **`mode=owner` (marker commit required; behavior unchanged).** First confirm `git status --porcelain` is empty. If any file is staged or modified, this check FAILS: commit the change, re-run `/review`, then re-run `/ship`. `/push-pr` must only push the existing marker commit; it must not create a new commit after this check passes. Then run the review-skill validator:
     - If `CLAUDE_SKILL_DIR` is set: `python3 "$CLAUDE_SKILL_DIR/../review/scripts/validate_review_marker.py" --ref HEAD --repo-root "$(pwd)"`
     - If `COPILOT_PLUGIN_ROOT` is set: `python3 "$COPILOT_PLUGIN_ROOT/skills/review/scripts/validate_review_marker.py" --ref HEAD --repo-root "$(pwd)"`
     - If `CLAUDE_PLUGIN_ROOT` is set: `python3 "$CLAUDE_PLUGIN_ROOT/skills/review/scripts/validate_review_marker.py" --ref HEAD --repo-root "$(pwd)"`
     - Source checkout fallback: `python3 .claude/skills/review/scripts/validate_review_marker.py --ref HEAD --repo-root "$(pwd)"`
     - Vendored plugin fallback: `python3 skills/review/scripts/validate_review_marker.py --ref HEAD --repo-root "$(pwd)"`

     The validator exits `0` only when HEAD is a `/review` marker commit whose `Reviewed-By: /review@<axes> on <sha>` trailer binds the reviewed tip (its parent). Exit `1` means no marker, a stale marker, or new code landed after review; exit `2` is a config error. On any non-zero exit, this check FAILS: run `/review` on this branch (it writes the marker on a PASS verdict), then re-run `/ship`. This replaces the old "has /review been run somewhere?" check with proof it passed on the exact code being shipped. Because `/review` is the strict superset of CI (Child 1 #1934), a passing marker covers golden-principles, taste-lints, and code-quality too; there is no separate standards check.
   - **`mode=contributor` (advisory; no marker commit).** Writing the empty `Reviewed-By` marker commit onto a shared branch is PROHIBITED here: it pollutes the owner's PR. Do NOT run the marker validator and do NOT commit a marker. Instead, run the `/review` axes and accept a non-commit attestation as the proof: a `/review` run logged in the ship report (the axes run plus verdict on the current HEAD SHA), or that same result posted as a PR comment. This check is advisory in contributor mode: a clean `/review` result records the attestation; it never blocks and never mutates the branch.
4. **Tests passing** - All tests green? No skipped tests without justification?

> `golden-principles` + `taste-lints` + `code-quality` are now part of `/review` (Child 1 #1934), so `/ship` does not invoke them separately. `/pr-quality:all` is likewise no longer a required separate step before `/ship`: a passing `/review` marker (check 3) already runs the same canonical axes locally, and CI runs the same prompts as a backstop.

## Process

1. Run all 4 pre-flight checks, branching by `host` and `mode`.
2. If any blocking check fails: report what failed, why, and how to fix. Stop. (In `mode=contributor`, check 3 is advisory and never blocks.)
3. If all pass:
   - `mode=owner`, `host=github`: run /validate-pr-description to validate PR metadata, then run /push-pr to commit, push, and open the GitHub PR.
   - `mode=owner`, `host=ado`: run /validate-pr-description, then create the PR with `az repos pr create` (the gh-based /push-pr does not apply to ADO).
   - `mode=contributor`: do NOT create a PR and do NOT merge. The PR already exists and is the owner's call. Emit the ship report with `RESULT: VALIDATED` and the recorded `/review` attestation.
4. Report: host, mode, what was validated or shipped, PR link, any warnings.

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

PRE-FLIGHT:
  Pipeline:  PASS|FAIL (evidence)
  Security:  PASS|FAIL (evidence)
  Reviewed:  PASS|FAIL|ADVISORY (owner: SHA-bound /review marker on HEAD; contributor: /review attestation, no marker commit)
  Tests:     PASS|FAIL (evidence)

RESULT: SHIPPED|VALIDATED|BLOCKED
PR: [link if created; "existing, not modified" in contributor mode]
WARNINGS: [non-blocking concerns]
NEXT: [monitoring, follow-up items]
```

`RESULT: VALIDATED` is the contributor-mode terminal state: readiness checks and `/review` axes ran, no marker commit was written, no PR was created, and nothing was merged.

## Copilot CLI invocation reference

This skill body uses Claude Code call syntax. Under GitHub Copilot CLI, translate as follows (verified against Copilot CLI 1.0.66-1).

### Sub-skill calls

| Claude Code syntax | Copilot CLI equivalent |
| --- | --- |
| `Skill(skill="pipeline-validator")` | `skill` tool, `skill: "pipeline-validator"` |
| `Skill(skill="security-scan")` | `skill` tool, `skill: "security-scan"` |

### Sub-agent calls

| Claude Code syntax | Copilot CLI equivalent |
| --- | --- |
| `Task(subagent_type="devops")` | `task` tool, `agent_type: "project-toolkit:devops"` |

If a referenced skill or agent is unavailable in the Copilot CLI environment, perform that step inline and note the reduced coverage.
