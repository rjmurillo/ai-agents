---
name: golden-principles
version: 1.0.0
model: claude-sonnet-4-6
description: Scan repository for golden principle violations with agent-readable remediation. Enforces GP-001 through GP-008 from .agents/governance/golden-principles.md. Use when auditing compliance, preparing PRs, or running garbage collection scans.
license: MIT
---

# Golden Principles

Scan the repository for violations of mechanically enforced golden principles.
Produces remediation instructions that agents can act on directly.

Inspired by [OpenAI Harness Engineering](https://openai.com/index/harness-engineering/):

> "We started encoding what we call 'golden principles' directly into the repository
> and built a recurring cleanup process."

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `scan golden principles` | Full principle compliance scan |
| `check principle compliance` | Scan with summary report |
| `golden principle violations` | Scan and list violations |
| `run garbage collection` | Deep scan with fix-up recommendations |
| `audit principles` | Scan specific rules only |

## When to Use

Use this skill when:

- Preparing a PR for submission (catch violations early)
- Running periodic garbage collection scans
- Auditing a domain or directory for compliance
- Adding new files to the repository

Use `taste-lints` instead when:

- Checking code-level invariants only (file size, naming, complexity)
- Running pre-commit checks on staged files

Use `quality-grades` instead when:

- Grading domains across architectural layers
- Producing quality trend reports

## Process

1. Run `python3 .claude/skills/golden-principles/scripts/scan_principles.py` with target
2. Review AGENT_REMEDIATION blocks in output
3. Apply suggested fixes
4. Re-run to confirm compliance

## Usage

```bash
# Scan entire repository
python3 .claude/skills/golden-principles/scripts/scan_principles.py

# Scan specific directory
python3 .claude/skills/golden-principles/scripts/scan_principles.py --directory .claude/skills/

# Run specific rules only
python3 .claude/skills/golden-principles/scripts/scan_principles.py --rules script-language,skill-frontmatter

# JSON output for tooling
python3 .claude/skills/golden-principles/scripts/scan_principles.py --format json

# Write results to file
python3 .claude/skills/golden-principles/scripts/scan_principles.py --output scan-results.json --format json
```

## Rules

| Rule | Principle | What it checks |
|------|-----------|----------------|
| `script-language` | GP-001 | No new .sh/.bash files |
| `skill-frontmatter` | GP-003 | SKILL.md has required frontmatter fields |
| `agent-definition` | GP-004 | Agent .md files have required sections |
| `yaml-logic` | GP-005 | No inline logic in workflow YAML |
| `actions-pinned` | GP-006 | GitHub Actions pinned to SHA |

GP-002, GP-007, GP-008 are enforced by existing tools (git hooks, taste-lints).

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | No violations found |
| 1 | Script error (bad arguments, file not found) |
| 10 | Violations detected |

## Suppression

Add a comment in the file header to suppress a specific rule:

```python
# golden-principle: ignore script-language
```

Valid rules: `script-language`, `skill-frontmatter`, `agent-definition`, `yaml-logic`, `actions-pinned`

## Verification

After execution:

- [ ] Report lists scanned file count
- [ ] Each violation includes principle ID and remediation
- [ ] Exit code matches violation state
- [ ] Output format matches --format flag

## Cross-References

- [Golden Principles Document](.agents/governance/golden-principles.md)
- [Taste Lints](.claude/skills/taste-lints/SKILL.md) for GP-007, GP-008
- [Quality Grades](.claude/skills/quality-grades/SKILL.md) for domain-level grading
