# push-pr

Commits your working tree, pushes the branch, and opens a pull request on GitHub or Azure DevOps. It is the one skill that creates PRs; [`ship`](ship.md) calls it. The PR body is written from the real diff, not copied from the template.

## When to use it

- You want to push your changes and open a PR in one step.
- You say `push and open a PR`, `open a pull request`, `push this branch`, or `commit and push`.

## When not to use it

- You want the pre-ship gates (pipeline, security, review marker, tests) to run first: use [`ship`](ship.md).
- You only need to validate PR metadata: use [`validate-pr-description`](validate-pr-description.md).

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:push-pr
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/push-pr`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /push-pr skill to ...`. The skill takes no argument. It reads `git status`, `git diff HEAD`, and the current branch.

It reads the `origin` URL first: `dev.azure.com` or `visualstudio.com` means Azure DevOps, and anything else means GitHub. Only the create step differs by host.

If you are on `main`, it creates a branch first. Branch names use a conventional type and a 3 to 5 word description, such as `fix/parser-log-enrichment`. It never pushes to `main`.

## What you get

- A new branch, if you started on `main`.
- A pushed branch on `origin`.
- A pull request on GitHub, or on Azure DevOps with its `pullRequestId` reported, whose title follows conventional commit format (for example `feat: Add feature` or `fix(auth): Resolve bug`) and whose body has every template section filled from the diff.

The body must include an `## Acceptance criteria` heading with `- [ ]` or `* [ ]` bullets. The Validate Spec Coverage job reads these from the PR body. Numbered criteria are not recognized. Check a box only once the criterion is met, because a FAIL from that job does not block the merge. The body should also carry an issue-linking keyword (`Closes #<number>`, `Fixes #<number>`, or `Resolves #<number>`). Use a closing keyword only when the diff delivers what the issue asks.

## Advanced use

**Process.** The skill first names `<target>`, the branch the PR merges into. It is the repository default branch unless you name another. The name may hold only letters, digits, `.`, `_`, `/`, and `-`. For any other name, the skill stops and asks you. Then it follows these steps:

1. Create a branch if on `main`.
2. Read [`.github/PULL_REQUEST_TEMPLATE.md`](../../.github/PULL_REQUEST_TEMPLATE.md).
3. Run the secure path allocator, `new_pr.py --prepare-body-file`. It returns a unique body file under `.project-toolkit/scratch/`. Copy the returned path exactly. Do not store it in a shell variable, because each tool call runs a fresh shell. Edit that file to fill the template, then delete the `<!-- replace with PR body -->` marker line. A body that still holds the marker is rejected.
4. Run `new_pr.py --preflight` with the title and body file. It checks the title format and the body file. It makes no network call and creates nothing.
5. Run `scripts/validation/pr_description.py --body-file ... --base origin/<target>` before pushing. Exit `1` means a CRITICAL finding, usually a file named in the body that the diff does not touch. Commit it or edit the body, then re-run. Exit `2` means the check could not run. Commit first, because local mode reads committed `HEAD` only. A plugin install does not ship this validator. In that case, say the step was not run and compare the paths in the body by hand to `git diff --name-only origin/<target>...HEAD`.
6. Push the branch to `origin`.
7. On GitHub, run `new_pr.py --title ... --body-file ...` to create the PR. Add `--base "<target>"` when `<target>` is not the default branch. Without it, `new_pr.py` opens the PR against the default branch. On Azure DevOps, see the next paragraph.

**Azure DevOps.** Steps 1 to 6 run the same. Step 7 first runs `validate_pr_description.py` on the same title and body file, then a dash check by eye, because that validator has none. Then it runs `az repos pr create --output json --title ... --description '@<body file>'`. `az` is not in `allowed-tools`, so you see and approve every flag. No other flag is allowed except `--target-branch` for a non-default target. In step 5, check the paths against the target branch. Use `--base origin/<branch>` if the local validator is available. Otherwise, use the manual comparison in step 5 against the same branch. If the returned `description` starts with `@`, Azure CLI sent the path instead of the file. The skill reports FAIL with the `pullRequestId` and asks you whether to fix or abandon that PR. On Windows, the Windows fallback below replaces steps 3 to 5 only. Use its `.project-toolkit/scratch/pr-body-windows.md` file as the body file for both the validator and `az repos pr create`, and keep the single quotes around `'@<path>'`, because PowerShell reads an unquoted `@name` as splatting.

The skill never applies the `description-validation-bypass` label. A human maintainer decides that.

**Worktrees.** If the branch is checked out in a worktree outside your clone and you run the command from another checkout, add `--head "<branch>"`. Push the branch first. `new_pr.py` exits `2` and prints the push command when `origin` lacks the branch.

**Windows.** The allocator refuses to run on Windows with `ERROR: secure PR body files are not supported on Windows`. In that case only, pass the body inline with `--body '<text>'` instead of `--body-file`. Use single quotes in bash and a single-quoted here-string in PowerShell, never double quotes. Do not add `--skip-validation`. Add `--base "<target>"` as in step 7 when `<target>` is not the default branch. The source file lists the full fallback steps.

**Security scope.** The skill's `allowed-tools` grant is scoped: specific `git` subcommands, `new_pr.py`, `pr_description.py`, and `validate_pr_description.py` run in isolated mode (`-I`), `mkdir -p .project-toolkit/scratch`, and edits to `.project-toolkit/scratch/pr-body-*.md`. The [`SKILL.md`](../../src/claude/skills/push-pr/SKILL.md) frontmatter is the full list. Do not widen it to bare `Bash`.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`ship`](ship.md): runs pre-flight gates, then calls this skill to open the PR.
- [`validate-pr-description`](validate-pr-description.md): validates PR metadata alone.
- [`takeover`](takeover.md): uses this skill to file a replacement PR.
- Source: [`SKILL.md`](../../src/claude/skills/push-pr/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
