# golden-principles

Scans your repository for violations of the mechanically enforced golden principles. Each violation comes with remediation instructions that an agent can act on directly.

## When to use it

- You are preparing a PR and want to catch violations early.
- You run periodic garbage collection scans.
- You are auditing a domain or directory for compliance.
- You are adding new files to the repository.
- You say `scan golden principles`, `check principle compliance`, `golden principle violations`, `run garbage collection`, or `audit principles`.

## When not to use it

- You only need code-level invariants such as file size, naming, or complexity, or you are running pre-commit checks on staged files: use [`taste-lints`](taste-lints.md) instead.
- You want to grade domains across architectural layers or produce quality trend reports: use [`quality-grades`](quality-grades.md) instead.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:golden-principles`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the golden-principles skill to scan the .claude/skills directory and fix any violations.
```

The agent runs the scanner, reads the `AGENT_REMEDIATION` blocks in the output, applies the suggested fixes, and re-runs the scan to confirm.

## What you get

The scanner prints violations with the principle ID and an `AGENT_REMEDIATION` block for each one. The report lists the scanned file count.

| Exit code | Meaning |
| --- | --- |
| `0` | No violations found. |
| `1` | Script error (bad arguments, file not found). Treat it as blocked, not as a pass. |
| `10` | Violations detected. Report each with its principle ID and remediation. |

## Advanced use

### Rules

| Rule | Principle | What it checks |
| --- | --- | --- |
| `script-language` | GP-001 | No new `.sh` or `.bash` files. |
| `skill-frontmatter` | GP-003 | `SKILL.md` has the required frontmatter fields. |
| `agent-definition` | GP-004 | Agent `.md` files have the required sections. |
| `yaml-logic` | GP-005 | No inline logic in workflow YAML. |
| `actions-pinned` | GP-006 | GitHub Actions are pinned to a SHA. |

GP-002, GP-007, and GP-008 are enforced by existing tools (git hooks and [`taste-lints`](taste-lints.md)), not by this scanner.

### Run the scanner

Run it from the root of a checkout of this repository:

```bash
uv run python .claude/skills/golden-principles/scripts/scan_principles.py --help
```

The script takes optional file paths plus these flags:

| Flag | Meaning |
| --- | --- |
| `--directory`, `-d` | Scan all files in a directory. Defaults to the repo root. |
| `--diff-scope BASE_BRANCH` | Scan only files changed in `git diff --name-only BASE_BRANCH...HEAD`. |
| `--format {text,json}` | Output format. Defaults to `text`. |
| `--rules` | Comma-separated rules to run. Defaults to all. |
| `--output`, `-o` | Write output to a file instead of stdout. |

Examples:

```bash
uv run python .claude/skills/golden-principles/scripts/scan_principles.py --directory .claude/skills/
uv run python .claude/skills/golden-principles/scripts/scan_principles.py --diff-scope origin/main --format json
uv run python .claude/skills/golden-principles/scripts/scan_principles.py --rules script-language,skill-frontmatter
uv run python .claude/skills/golden-principles/scripts/scan_principles.py --output scan-results.json --format json
```

### Suppress a rule

Add a comment in the file header to suppress one rule:

```python
# golden-principle: ignore script-language
```

Valid rule names are `script-language`, `skill-frontmatter`, `agent-definition`, `yaml-logic`, and `actions-pinned`.

### Chaining and configuration

[`review`](review.md) invokes this skill as one of its four local quality axes. The principle text lives in `.agents/governance/golden-principles.md`. A vendored install without that file loses the canonical text, but the bundled scanner still applies its built-in checks for GP-001 and GP-003 through GP-006 to your files.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`taste-lints`](taste-lints.md): enforces GP-007 and GP-008 and other code-level invariants.
- [`quality-grades`](quality-grades.md): domain-level grading and trend reports.
- [`review`](review.md): invokes this skill as a quality axis.
- Source: [`SKILL.md`](../../src/claude/skills/golden-principles/SKILL.md)
- Reference: [Code qualities](../../src/claude/skills/golden-principles/references/design-code-qualities.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
