# style-enforcement

Checks your code against the style rules in `.editorconfig`, `StyleCop.json`, and `Directory.Build.props`. You get a list of violations with file, line, and rule ID. It covers line endings, indentation, charset, whitespace, and naming.

## When to use it

- You want to check style compliance before a commit or pull request.
- You want CI to enforce your `.editorconfig`.
- You say `check style compliance`, `validate editorconfig rules`, `run style enforcement`, `check naming conventions`, or `validate line endings`.

## When not to use it

- Taste invariants such as file size or structured logging: use [`taste-lints`](taste-lints.md) instead.
- Full ESLint or Prettier rules, full StyleCop analyzer output (`dotnet build`), or auto-formatting (`dotnet format`, `black`, `prettier`): use those tools directly.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:style-enforcement`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the style-enforcement skill to check my staged files against .editorconfig.
```

The skill runs `check_style.py` and reports violations. To run it yourself from the root of a checkout of this repository:

```bash
uv run python .claude/skills/style-enforcement/scripts/check_style.py --git-staged
```

## What you get

A report in text, JSON, or SARIF. Each violation has a file, line, rule ID, message, and severity.

| Rule | Severity | Detects |
| --- | --- | --- |
| `STYLE-001` | warning | Line endings that differ from `end_of_line` |
| `STYLE-002` | warning | Tabs versus spaces, or the wrong indent size |
| `STYLE-003` | warning | Wrong charset or BOM |
| `STYLE-004` | info | Trailing whitespace when `trim_trailing_whitespace = true` |
| `STYLE-005` | info | Missing final newline when `insert_final_newline = true` |
| `STYLE-010` | warning | C# async method without the `Async` suffix, when `dotnet_naming_rule` is configured |

| Exit code | Meaning |
| --- | --- |
| `0` | All files compliant |
| `1` | Script error (invalid arguments or config parse failure). Treat it as blocked, not as a pass. |
| `10` | Violations detected |

## Advanced use

```bash
uv run python .claude/skills/style-enforcement/scripts/check_style.py --help
```

| Flag | Effect |
| --- | --- |
| `--target` | Directory or file to scan (default: current directory). |
| `--git-staged` | Check only staged files. |
| `--format` | `text` (default), `json`, or `sarif`. |
| `--output` | Write to a file instead of stdout. |
| `--severity` | Minimum severity to report: `error`, `warning` (default), or `info`. |
| `files` | Positional list of specific files. |

Examples:

```bash
uv run python .claude/skills/style-enforcement/scripts/check_style.py src/models/User.cs src/services/Auth.cs
uv run python .claude/skills/style-enforcement/scripts/check_style.py --target . --format sarif --output results.sarif
```

SARIF output can go to GitHub code scanning with `github/codeql-action/upload-sarif`.

### Rule sources

The skill reads `.editorconfig` (all languages), `.stylecop.json` or `stylecop.json` (C#), and `Directory.Build.props` (.NET). It walks up from the target to find the root and merges inherited properties. It checks `end_of_line`, `indent_style`, `indent_size`, `charset`, `trim_trailing_whitespace`, and `insert_final_newline`.

### Language support

| Support | Languages |
| --- | --- |
| Full, with naming rules | C# (Async suffix, interface prefix), Python (snake_case), PowerShell (Verb-Noun), JavaScript and TypeScript (camelCase) |
| Basic (line endings, indentation, charset) | Go, Rust, Java, Ruby, Markdown, YAML, JSON |

### Suppression

Add an inline comment on the line before the code, or on the same line, to skip one rule. The scanner reads only `#` comments, so this works in languages such as Python, YAML, and PowerShell:

```text
# style-enforcement: ignore STYLE-001
```

Without an `.editorconfig` there are no rules to enforce. Run your formatter first, then run this check. Do not check generated files.

The skill is wired as a pre-commit hook with `--git-staged` and as a pre-PR check for agents. The [`doc-accuracy`](doc-accuracy.md) skill points here for complementary code style checks.

Reference: [`dotnet-monorepo-standards.md`](../../src/claude/skills/style-enforcement/references/dotnet-monorepo-standards.md).

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`taste-lints`](taste-lints.md): file size, naming, logging, and complexity invariants.
- [`code-qualities-assessment`](code-qualities-assessment.md): design quality rather than style.
- [`analyze`](analyze.md): broad codebase investigation.
- [`security-scan`](security-scan.md): security findings rather than style.
- Source: [`SKILL.md`](../../src/claude/skills/style-enforcement/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
