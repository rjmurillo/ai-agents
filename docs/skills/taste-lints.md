# taste-lints

Runs custom lints for file size, naming conventions, function complexity, and skill prompt size. Each error message is written as a remediation instruction an agent can follow, so the fix is in the report.

## When to use it

- You are writing or editing source files and want to catch taste violations early.
- You are preparing code for a pull request.
- You are adding new files and want the names checked.
- You say `run taste lints`, `check file size`, `check naming conventions`, `lint taste invariants`, or `taste lint report`.

## When not to use it

- Style rules from `.editorconfig` such as line endings and indentation: use [`style-enforcement`](style-enforcement.md) instead.
- A full pre-merge review: use [`review`](review.md). It runs this skill as one of its four local quality axes.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:taste-lints`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the taste-lints skill to lint the files I changed against origin/main.
```

The skill runs `taste_lints.py`, reads the `AGENT_REMEDIATION` blocks, applies the suggested fixes, and reruns to confirm. To run it yourself from the root of a checkout of this repository:

```bash
uv run python .claude/skills/taste-lints/scripts/taste_lints.py --git-staged
```

## What you get

A report that lists every scanned file count and violation count. Each violation has an `AGENT_REMEDIATION` block with an actionable fix.

| Exit code | Meaning |
| --- | --- |
| `0` | Clean |
| `1` | Script error (bad arguments, file not found) |
| `10` | Violations detected |

The four rules:

| Rule | Check | Severity |
| --- | --- | --- |
| `file-size` | 301 to 500 lines warns. 501 or more is an error. | warning, error |
| `naming` | `snake_case` for Python, `kebab-case` for skill directories and YAML files, `PascalCase` for PowerShell, `UPPER_CASE` for constants, `invoke_` prefix for hook scripts. | per violation |
| `complexity` | Functions over cyclomatic complexity 10 need decomposition. | per violation |
| `skill-size` | Skills over 500 lines need progressive disclosure. | per violation |

Naming exceptions: a YAML stem may hold dot-separated kebab-case segments (`ci.pr.yml`), a leading dot is valid ([`.coderabbit.yaml`](../../.coderabbit.yaml)), and `__init__.py` and `__main__.py` are exempt from `snake_case`. A suggested name that cannot start with a letter gets an `item` prefix, so `1config.yml` becomes `item-1config.yml`.

## Advanced use

```bash
uv run python .claude/skills/taste-lints/scripts/taste_lints.py --help
```

| Flag | Effect |
| --- | --- |
| `--git-staged` | Lint staged files. |
| `--diff-scope BASE_BRANCH` | Lint only files changed in `git diff --name-only BASE_BRANCH...HEAD`. |
| `--directory`, `-d` | Lint every scannable file in a directory. |
| `--format` | `text` (default) or `json`. |
| `--max-violations` | Text output lists at most this many violations, errors first (default 100, `0` lists all). The summary counts every violation. JSON is never cut. |
| `--rules` | Comma-separated rules to run: `file-size`, `naming`, `complexity`, `skill-size`. Default is all. |
| `files` | Positional list of files. |

Examples:

```bash
uv run python .claude/skills/taste-lints/scripts/taste_lints.py --diff-scope origin/main --format json
uv run python .claude/skills/taste-lints/scripts/taste_lints.py --rules file-size,naming --directory src/
```

To suppress one rule for a file, add a comment:

```python
# taste-lint: ignore file-size
```

Valid rule names for suppression: `file-size`, `naming`, `complexity`, `skill-size`.

The idea comes from OpenAI's harness engineering write-up, which uses custom lints so error messages carry remediation instructions into agent context. The [`review`](review.md) skill invokes this skill during Stage-2 review.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`style-enforcement`](style-enforcement.md): `.editorconfig` and StyleCop checks.
- [`review`](review.md): invokes taste lints as a review axis.
- [`code-qualities-assessment`](code-qualities-assessment.md): design quality scoring.
- Source: [`SKILL.md`](../../src/claude/skills/taste-lints/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
