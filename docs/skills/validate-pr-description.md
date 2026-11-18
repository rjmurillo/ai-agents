# validate-pr-description

Checks a PR title and body before you submit. It always checks the conventional-commit title. It checks the issue-linking keyword and the template sections only when the target repository has a tracking issue, a PR template, or a gate that requires them. You get a result per check, so you fix it with one edit instead of one CI round.

## When to use it

- You wrote a PR title and body and want to know if they pass.
- Trigger phrases: `validate my PR description`, `check my PR title`, `is this PR body compliant`, `validate PR metadata`.

## When not to use it

- You want to open, update, or push a PR: use [`github`](github.md) or [`push-pr`](push-pr.md).
- You want to review the code diff: use [`review`](review.md).

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:validate-pr-description "feat(auth): add token refresh" pr-body.md
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/validate-pr-description "feat(auth): add token refresh" pr-body.md`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /validate-pr-description skill to ...`.

The first argument is the title. The second is a path to the body file. If you give neither, the skill asks for both. It does not guess them from your branch or last commit.

## What you get

A report per check, not one verdict. Each failure shows the offending text and a corrected form.

| # | Check | Applies when | Rule |
| --- | --- | --- | --- |
| 1 | Conventional commit title | Always | `<type>(<scope>)?: <description>`. Type is one of `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`, `build`, `revert`. |
| 2 | Issue-linking keyword | A tracking issue exists, or the repository has an issue-link gate | The body has `Closes #N`, `Fixes #N`, `Resolves #N`, a past-tense variant, or `Refs #N`. Use `owner/repo#N` for an issue in another repository. |
| 3 | Template compliance | The repository has a PR template | Every section the template asks you to fill is populated. |

Before checks 2 and 3, the skill searches your checkout for a PR template and for workflows or scripts that enforce issue links or template sections. It learns of a tracking issue when you name one or when the title, body, or branch name references one. A check whose "Applies when" condition is not met reports `NOT APPLICABLE` with what was searched. The skill never asks you to open an issue just so a keyword has a target.

The report also says which path ran: the repository's validator, or a manual pass. They are different levels of evidence. In a repository other than this one, the plugin's validator script reflects this repository's template. The skill keeps its keyword warning when a tracking issue or an issue-link gate exists, and drops it otherwise. It discards the script's template warning and checks your own template's headings instead.

## Advanced use

### Validator script

When the plugin's `validate_pr_description.py` is present, the skill runs it. Run it yourself from the root of a checkout of this repository:

```bash
uv run python .claude/skills/github/scripts/pr/validate_pr_description.py --help
```

Flags: `--title` (required), `--body`, `--body-file`, `--fail-on-violation`. Exit `0` means all checks pass or warn. Exit `1` means a failure with `--fail-on-violation`. That flag also turns keyword and template warnings into failures, so in another repository exit `1` can come from checks the skill reports `NOT APPLICABLE`. Exit `2` is a usage or environment error.

### File mentions against the diff

In a checkout that ships [`scripts/validation/pr_description.py`](../../scripts/validation/pr_description.py), the skill also runs its local mode. This is the same file-mention check the required `Validate PR` check runs.

```bash
uv run python scripts/validation/pr_description.py --help
```

```bash
uv run --frozen python -I scripts/validation/pr_description.py --body-file pr-body.md --base origin/main
```

Local mode reads committed `HEAD`, so commit first. Exit `1` is a CRITICAL finding, usually `File mentioned but not in diff`. The fix is to remove the path, move it out of the change heading, or wrap it in a code fence. Exit `2` means the check could not run. With a pasted body and no file, the skill says the check was not run. It never suggests the `description-validation-bypass` label. A maintainer decides that.

This check does not cover the dash or closing-keyword checks.

### Closing keywords

A closing keyword claims the PR closes the issue. The skill checks that claim against the diff. If the diff does not deliver what the issue asks, it recommends `Refs #N` and says why.

### Other forges

The keyword list is GitHub and GitLab behavior. On Azure DevOps and Bitbucket the same keywords are traceability markers with no auto-close, so a missing keyword is a weaker finding there.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`push-pr`](push-pr.md): opens the PR after your description passes.
- [`ship`](ship.md): runs this skill before it pushes.
- [`review`](review.md): reviews the code diff.
- Source: [`SKILL.md`](../../src/claude/skills/validate-pr-description/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
