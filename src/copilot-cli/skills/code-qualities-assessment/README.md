# Code Qualities Assessment Skill

Assess code maintainability through 5 foundational software engineering qualities.

## Quick Start

```python
# Assess a file
python3 scripts/assess.py --target src/services/auth.py

# Assess changed files (CI mode)
python3 scripts/assess.py --target . --changed-only --format json

# Generate HTML report
python3 scripts/assess.py --target src/ --format html --output report.html
```text

## The 5 Qualities

1. **Cohesion**: How strongly related are responsibilities within a boundary?
2. **Coupling**: How dependent is this code on other code?
3. **Encapsulation**: How well are implementation details hidden?
4. **Testability**: How easily can behavior be verified in isolation?
5. **Non-Redundancy**: How unique is each piece of knowledge?

## Files

```text
code-qualities-assessment/
├── SKILL.md                        # Main skill documentation
├── README.md                       # This file
├── scripts/
│   └── assess.py                   # Main assessment orchestrator
├── templates/
│   └── .qualityrc.json             # Configuration template
└── references/
    ├── calibration-examples.md     # Scoring examples for team calibration
    └── refactoring-patterns.md     # Remediation patterns
```text

## Configuration

Create `.qualityrc.json` in your project root:

```json
{
  "thresholds": {
    "cohesion": { "min": 7, "warn": 5 },
    "coupling": { "max": 3, "warn": 5 },
    "encapsulation": { "min": 7, "warn": 5 },
    "testability": { "min": 6, "warn": 4 },
    "nonRedundancy": { "min": 8, "warn": 6 }
  },
  "ignore": ["**/generated/**", "**/*.pb.py"]
}
```text

## Language Support

**Fully Supported**: Python, TypeScript/JavaScript, C#, Java, Go
**Partial Support**: Ruby, Rust, PHP, Kotlin

## Integration Examples

### CI/CD Pipeline

```python
# GitHub Actions
- name: Check code quality
  run: |
    python3 .claude/skills/code-qualities-assessment/scripts/assess.py \
      --target src/ \
      --changed-only \
      --format json \
      --output quality.json
```text

### Pre-commit Hook

```python
#!/bin/bash
python3 .claude/skills/code-qualities-assessment/scripts/assess.py \
  --target $(git diff --cached --name-only) \
  --format markdown
```text

## Timelessness: 9/10

These qualities are computer science fundamentals from the 1960s-1990s:

- Cohesion and coupling: Parnas (1972), Stevens (1974)
- Encapsulation: Core OOP principle (1960s)
- Testability: TDD movement (1990s-2000s)
- DRY: Hunt & Thomas, Pragmatic Programmer (1999)

Language-agnostic design ensures longevity.

## License

MIT
