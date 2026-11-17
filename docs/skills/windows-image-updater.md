# windows-image-updater

Migrates the Windows container image in OneBranch pipeline repositories, such as LTSC2019 to LTSC2022. It bumps the `ConfigurationGeneration.AdoPipelineGeneration` package, regenerates pipeline configs with ConfigGen, confirms the old image is gone, and opens a draft PR.

## When to use it

- OneBranch warns that the LTSC2019 image is end of life.
- You need to move pipeline repositories to a newer Windows container image.
- Trigger phrases: `update windows image`, `fix ltsc2019 warning`, `migrate onebranch image`, `bump AdoPipelineGeneration`, `windows container image update for {repo}`.

## When not to use it

- You only want to validate pipelines on an existing PR: use [`pipeline-validator`](pipeline-validator.md) instead.
- You want to edit generated pipeline YAML by hand: do not. ConfigGen overwrites manual edits.

## Quick start

Start this skill yourself. Its routing is explicit-only, so the `autoplan` router never picks it for you. In Claude Code, type `/project-toolkit:windows-image-updater`. On any host, ask for it by name:

```text
Use the windows-image-updater skill to migrate the Windows container image in this repository from ltsc2019 to ltsc2022.
```

Give an Azure DevOps repository (a URL or a local path). Expect 30 to 60 minutes. You need Git, the .NET SDK, and Azure DevOps access with write and PR rights. The skill ends with a draft PR whose pipelines pass.

## What you get

A draft PR with updated pipeline YAML files and a description with Summary, Changes, Validation, and Work Items sections. After the PR exists, [`pipeline-validator`](pipeline-validator.md) runs PR, Buddy build, and Buddy release pipelines, fixes failures, and adds run links to the description.

## Advanced use

The skill has no scripts. It works in four phases.

| Phase | Work | Stop condition |
| --- | --- | --- |
| 1 Repository setup | Create branch `feat/windows-image-update`, run a baseline `dotnet build` and `dotnet test`, record warnings | The baseline build fails: report before you proceed |
| 2 Package update | Bump the package in `Directory.Packages.props` (fallback `Packages.props`), then fix build errors one at a time | None |
| 3 Config generation | Find and run the ConfigGen project, check `.pipelines` for the old image, compare warnings with the baseline | The image did not change: recheck the package and project |
| 4 PR and validation | Commit, push, open a draft PR, hand off to `pipeline-validator` | None |

Fix the first build error, rebuild, and repeat, because one fix often clears many downstream errors. Common first errors: `NU1605` and `NU1608` (bump the one named package), `NU1107` (pin the package), and `CS0246` (a dependent API changed).

Which project to run depends on the repository type. A repo whose name contains `.resources` uses its Topology project. A service repo uses its ConfigurationGeneration project. A combined repo may need both.

Defaults you can change: old image pattern `ltsc2019`, expected new image `ltsc2022`, package name, branch name, and props file. Do not hardcode the target image, because the next migration will differ.

The PR is always a draft until pipelines pass.

Rollback:

| Failed at | Action |
| --- | --- |
| Phase 1 or 2, not pushed | `git checkout main && git branch -D feat/windows-image-update` (this deletes unmerged local work on that branch; confirm you have nothing to keep) |
| Phase 3, not pushed | `git reset --hard origin/main` (first confirm you are on the update branch and have no uncommitted work to keep; this discards it) |
| Phase 4, pushed | Close the draft PR in Azure DevOps and delete the remote branch |

Read [`references/troubleshooting.md`](../../src/claude/skills/windows-image-updater/references/troubleshooting.md) for package and build errors.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`pipeline-validator`](pipeline-validator.md): validates and fixes pipelines after the PR exists.
- Source: [`SKILL.md`](../../src/claude/skills/windows-image-updater/SKILL.md)
- Troubleshooting: [`troubleshooting.md`](../../src/claude/skills/windows-image-updater/references/troubleshooting.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
