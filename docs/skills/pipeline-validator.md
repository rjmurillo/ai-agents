# pipeline-validator

Runs the Azure DevOps pipelines for your current repo and branch in order (PR build, then Buddy build, then Buddy release). When one fails, it reads the build log, applies a known fix, commits, pushes, and re-triggers it, up to a retry limit. It ends by updating the PR description with run links.

> [!WARNING]
> This skill commits and pushes fixes without asking you between retries. It defaults to one Azure DevOps organization and project. It works only for Azure DevOps, not GitHub PRs.

## When to use it

- You have an Azure DevOps PR open on your branch and want its pipelines driven to green.
- An Azure DevOps change-making skill, such as [`windows-image-updater`](windows-image-updater.md), finished creating a PR.
- Trigger phrases: `validate pipelines`, `trigger and fix pipelines`, `run pipeline validation`, `check pr pipelines`, `monitor pipelines for {repo}`.

## When not to use it

- Your PR is on GitHub: [`ship`](ship.md) checks GitHub CI through `get_pr_checks.py`.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:pipeline-validator`. Invoke it explicitly. To ask for it by name, say:

```text
Use the pipeline-validator skill to validate the Azure DevOps pipelines for my current branch.
```

The skill detects the repo and branch, finds the active PR, checks the PR description, and discovers pipelines whose names contain the repo name. It then triggers and polls them in order. Expect 30 to 180 minutes. You need Git, the Azure CLI with the `azure-devops` extension, and the .NET SDK, plus permission to push and trigger pipelines.

## What you get

A final report with these items:

| Item | Detail |
| --- | --- |
| Branch and PR | The branch validated, plus PR ID and URL |
| PR description | Complete, or which sections are missing (`## Summary`, `## Changes`, `## Validation`) |
| PR Build, Buddy Build, Buddy Release | Run ID, URL, result, retry count (and auto-triggered or manual for release) |
| Fixes applied | Commits with descriptions |
| Final status | All passed, partial failure, or stopped |

A missing description section is a warning, not a blocker. If no PR exists for the branch, the skill reports that and stops, because a PR must exist first.

## Advanced use

The skill has no scripts of its own. It drives the `az` CLI.

| Setting | Default |
| --- | --- |
| Organization | `https://microsoft.visualstudio.com` |
| Project | `Windows Defender` |
| Max retries per pipeline | 3 |
| Poll interval | 10 minutes |
| Max polls per run | 18 (3 hours) |

Idempotent start: before it triggers a run, the skill checks existing runs on the branch. A success on the current commit is skipped, a success on an older commit triggers a fresh run, and an in-progress run is resumed. Buddy release may auto-trigger after Buddy build, so the skill waits 5 minutes and uses that run if it exists.

Fix policy: the skill matches each failure against `references/error-patterns.md`. If nothing matches, it stops and reports. It does not infer a fix from arbitrary log text, because logs are untrusted. Fixable patterns include compile errors, `TreatWarningsAsErrors`, NuGet errors, file-not-found paths, assembly load failures, YAML syntax errors, and test failures. Permission errors (403) and infrastructure outages are reported, not fixed. It fixes the first error, rebuilds locally with `dotnet build`, and does not hand-edit generated pipeline YAML.

Stop conditions: the retry limit is reached, a poll timeout passes, or the issue cannot be fixed by code. If a fix makes things worse, `git revert HEAD` undoes it.

The skill treats ingested content, such as build logs and PR bodies, as data and ignores instructions inside it.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`windows-image-updater`](windows-image-updater.md): calls this skill after it creates a PR.
- [`ship`](ship.md): checks GitHub CI for GitHub PRs.
- Source: [`SKILL.md`](../../src/claude/skills/pipeline-validator/SKILL.md)
- Error catalog: [`error-patterns.md`](../../src/claude/skills/pipeline-validator/references/error-patterns.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
