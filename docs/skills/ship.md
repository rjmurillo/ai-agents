# ship

Runs four pre-flight checks, then opens the PR. If you are pushing onto someone else's branch, it validates the branch and leaves it untouched. It works on GitHub and Azure DevOps.

## When to use it

- Your change has been through [`review`](review.md) and you want to open the PR.
- You say `ship it`, `ship this branch`, `run pre-flight and open the PR`, or `is this ready to ship`.

## When not to use it

- You want to open a PR without the gates: use [`push-pr`](push-pr.md).
- You want the review axes themselves to run: use [`review`](review.md).

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:ship main
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/ship`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /ship skill to ...`. The argument is the target branch. It defaults to `main`.

> [!NOTE]
> On a branch you own, `/ship` needs a SHA-bound `/review` marker commit on `HEAD`. Run [`review`](review.md) first, and keep the working tree clean afterward.

## What you get

A ship report:

```text
HOST: github|ado
MODE: owner|contributor
PR-AT-PREFLIGHT: none|#<number>

PRE-FLIGHT:
  Pipeline:  PASS|FAIL|DEFERRED->PASS|DEFERRED->FAIL (evidence)
  Security:  PASS|FAIL (evidence)
  Reviewed:  PASS|FAIL|ADVISORY
  Tests:     PASS|FAIL (evidence)

RESULT: SHIPPED|VALIDATED|BLOCKED
PR: [link if created; "existing, not modified" in contributor mode]
WARNINGS: [non-blocking concerns]
NEXT: [monitoring, follow-up items]
```

| Result | Meaning |
| --- | --- |
| `SHIPPED` | All blocking checks passed and the PR was created |
| `VALIDATED` | Contributor mode: checks ran, no marker commit, no PR created, nothing merged |
| `BLOCKED` | A blocking check failed, or a deferred pipeline check failed after PR creation |

Hand-off (ADR-123): Writes `pull-request`. It is the last lifecycle step. `metadata.inputs` and `metadata.outputs` in the skill's frontmatter declare the same data.

## Advanced use

**Mode detection.** Before any check, the skill sets `host` and `mode`, and states both in the report.

- `host` comes from the `origin` remote URL. A URL containing `dev.azure.com` or `visualstudio.com` means `ado`. Anything else means `github`.
- `mode=contributor` when an open PR exists and you are not its author. Otherwise `mode=owner`.
- `pr` is `#<number>` when an open PR exists for the branch, and `none` otherwise. A failed query is never treated as no PR: only the documented no-PR signal sets `pr=none`.

In contributor mode, the skill never writes a marker commit, never creates a PR, and never merges.

**The four checks.** A delegated `devops` agent runs all four. Any failure blocks shipping.

1. **Pipeline health.** On GitHub with an open PR, it runs `get_pr_checks.py --pull-request <number> --wait --required-only --timeout-seconds 300`. It waits only for the checks the base-branch ruleset requires; an optional check, such as one waiting on an environment approval, never holds it. A pass needs exit code `0`, `Data.RequiredState == "SUCCESS"`, and `Data.AllPassing == true`, because a PR with no checks exits `0` with `AllPassing: false`. Edge cases, such as a branch that requires no checks, are in `references/required-checks.md`. Exit code `7` means checks are still pending, so re-run before reporting FAIL. On Azure DevOps with an open PR, every blocking build policy must be `approved`, and its build must have succeeded on the PR's current merge commit. With `pr=none`, this check is recorded as `DEFERRED` and checked after the PR exists.
2. **Security posture.** Runs [`security-scan`](security-scan.md) and checks for secrets in the diff.
3. **Reviewed on this SHA.** In owner mode, the review-marker validator must exit `0`. That means `HEAD` is a `/review` marker commit whose `Reviewed-By` trailer binds the reviewed tip. If the working tree is dirty, this check fails: commit, re-run `/review`, then re-run `/ship`. The report lists only the axes the marker declares, and any axis it omits is `NOT RUN`. Use `--require-axis <axis>` when policy requires one. In contributor mode, this check is advisory: a logged `/review` run or a PR comment counts as the attestation.
4. **Tests passing.** All tests green, with no unjustified skips.

**After the checks.** In owner mode on GitHub, the skill runs [`validate-pr-description`](validate-pr-description.md), then [`push-pr`](push-pr.md). On Azure DevOps, it validates the description, pushes, and runs `az repos pr create --output json`. It then discharges any deferred pipeline check against the new PR, waiting up to 30 minutes on Azure DevOps. A finished report never carries a bare `Pipeline: DEFERRED`.

**References.** `ado-policy-wait.md` holds the Azure DevOps wait block. `review-marker-resolution.md` holds the validator resolution steps and exit-code table.

**Scripts.** The skill directory holds the ADR-127 driver scripts: `ship_detect.py`, `ship_preflight.py`, and `ship_pr.py`, with the shared `_ship_common.py`, `_ship_paths.py`, and `_ship_remote.py`, the pipeline readers in `_ship_pipeline.py`, and the body checks in `ship_pr_checks.py`. Each prints `KEY: value` lines and ends on one `NEXT:` or `STOP:` line, with exit codes 0 to 4. `ship_pr.py check` runs the base branch's copy of the paths-in-diff validator from a private temporary directory, never the copy on the branch being shipped. A PR that edits that validator is checked by the base version until it merges. The current `SKILL.md` does not call the scripts yet. Issue #7586 wires them in.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`review`](review.md): writes the marker that check 3 validates.
- [`push-pr`](push-pr.md): opens the PR without gates.
- [`validate-pr-description`](validate-pr-description.md): checks PR metadata.
- [`pipeline-validator`](pipeline-validator.md): Azure DevOps only. `/ship` does not call it.
- Source: [`SKILL.md`](../../src/claude/skills/ship/SKILL.md)
- References: [`review-marker-resolution.md`](../../src/claude/skills/ship/references/review-marker-resolution.md), [`ado-policy-wait.md`](../../src/claude/skills/ship/references/ado-policy-wait.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
