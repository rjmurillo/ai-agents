---
name: style-enforcement
description: Validate code against style rules from .editorconfig, StyleCop.json, and Directory.Build.props. Detects line ending violations, naming convention issues, indentation problems, and charset mismatches across C#, Python, PowerShell, and JavaScript. Produces JSON reports for pre-commit hooks and CI pipelines.
license: MIT
metadata:
  version: 1.0.0
  model: claude-sonnet-4-5
---

# Style Enforcement

Validate code files against configured style rules from project configuration files.

## Triggers

- `check style compliance`
- `validate editorconfig rules`
- `run style enforcement`
- `check naming conventions`
- `validate line endings`

---

## Quick Start

```bash
# Check all files in current directory
python3 scripts/check_style.py --target .

# Check only changed files (CI mode)
python3 scripts/check_style.py --git-staged

# Check specific files
python3 scripts/check_style.py src/models/user.cs src/services/auth.cs

# JSON output for automation
python3 scripts/check_style.py --target . --format json --output violations.json
```

---

## Evidence

Created based on analysis of moq.analyzers closed PR reviewer patterns:

- **9.8% of human reviewer feedback** (11 of 112 comments) addressed naming/style conventions
- Common patterns: line endings (CRLF vs LF), naming conventions (FooAsync), style guide violations
- Examples: "Use lf not crlf", "Should be named FooAsync", "Conflicting style rules"

Source: `.agents/analysis/moq-analyzers-reviewer-patterns-2026-02-08.md`

---

## Configuration Sources

The skill reads style configuration from these files (in priority order):

| File | Purpose | Scope |
|------|---------|-------|
| `.editorconfig` | EditorConfig standard | All languages |
| `.stylecop.json` / `stylecop.json` | StyleCop Analyzers rules | C# |
| `Directory.Build.props` | MSBuild properties | .NET projects |

### .editorconfig Properties Checked

| Property | Values | Languages |
|----------|--------|-----------|
| `end_of_line` | lf, crlf, cr | All |
| `indent_style` | space, tab | All |
| `indent_size` | number | All |
| `charset` | utf-8, utf-8-bom, latin1 | All |
| `trim_trailing_whitespace` | true, false | All |
| `insert_final_newline` | true, false | All |

### .editorconfig Naming Conventions (C#)

```ini
# Example naming rules
dotnet_naming_rule.async_methods_should_end_with_async.symbols = async_methods
dotnet_naming_rule.async_methods_should_end_with_async.style = async_suffix_style
dotnet_naming_rule.async_methods_should_end_with_async.severity = warning

dotnet_naming_style.async_suffix_style.required_suffix = Async
```

---

## Detection Capabilities

### Line Ending Violations

Detects when file line endings differ from `.editorconfig` `end_of_line` setting.

```
Rule: STYLE-001
Severity: warning
Example: "File uses CRLF but editorconfig requires LF"
```

### Indentation Violations

Detects tabs vs spaces mismatches and incorrect indent sizes.

```
Rule: STYLE-002
Severity: warning
Example: "Line uses tabs but editorconfig requires spaces (indent_size=4)"
```

### Charset Violations

Detects incorrect file encoding (BOM presence/absence).

```
Rule: STYLE-003
Severity: warning
Example: "File has UTF-8 BOM but editorconfig requires utf-8 (no BOM)"
```

### Trailing Whitespace

Detects trailing whitespace when `trim_trailing_whitespace = true`.

```
Rule: STYLE-004
Severity: info
Example: "Line 42 has trailing whitespace"
```

### Final Newline

Detects missing final newline when `insert_final_newline = true`.

```
Rule: STYLE-005
Severity: info
Example: "File does not end with newline"
```

### Naming Convention Violations (C#)

Detects async method naming when `dotnet_naming_rule` configured.

```
Rule: STYLE-010
Severity: warning
Example: "Async method 'GetUser' should end with 'Async' suffix"
```

---

## Process

```
┌─────────────────────────────────────────┐
│ 1. Configuration Discovery              │
│    - Walk up from target to find root   │
│    - Parse .editorconfig hierarchy      │
│    - Parse .stylecop.json if present    │
│    - Parse Directory.Build.props        │
├─────────────────────────────────────────┤
│ 2. Rule Compilation                     │
│    - Match globs to file extensions     │
│    - Build per-file rule set            │
│    - Merge inherited properties         │
├─────────────────────────────────────────┤
│ 3. File Scanning                        │
│    - Check each file against its rules  │
│    - Detect violations with line info   │
│    - Apply suppression comments         │
├─────────────────────────────────────────┤
│ 4. Report Generation                    │
│    - Format: markdown, JSON, or SARIF   │
│    - Include violation counts           │
│    - Exit code based on findings        │
└─────────────────────────────────────────┘
```

---

## Command Reference

### Basic Usage

```bash
python3 scripts/check_style.py [options] [files...]
```

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `--target` | No | . | Directory or file to scan |
| `--git-staged` | No | false | Check only git staged files |
| `--format` | No | text | Output format: text, json, sarif |
| `--output` | No | stdout | Output file path |
| `--config` | No | auto | Path to .editorconfig (auto-discovers) |
| `--severity` | No | warning | Minimum severity: error, warning, info |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All files compliant |
| 1 | Script error (invalid arguments, config parse failure) |
| 10 | Violations detected |

---

## Integration

### Pre-commit Hook

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: style-enforcement
        name: Style Enforcement
        entry: python3 .claude/skills/style-enforcement/scripts/check_style.py
        args: [--git-staged]
        language: python
        pass_filenames: false
```

### GitHub Actions

```yaml
# .github/workflows/style.yml
jobs:
  style:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Check style
        run: |
          python3 .claude/skills/style-enforcement/scripts/check_style.py \
            --target . \
            --format sarif \
            --output style-results.sarif
      - uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: style-results.sarif
```

### Agent Pre-Submission

Before creating a PR, run style enforcement:

```bash
python3 .claude/skills/style-enforcement/scripts/check_style.py --git-staged
```

If exit code is 10, fix violations before proceeding.

---

## Examples

### Example 1: Check Single File

```bash
python3 scripts/check_style.py src/models/User.cs
```

**Output:**

```
Style Enforcement Report
========================

Violations: 2

src/models/User.cs
  Line 1: [STYLE-001] File uses CRLF but editorconfig requires LF
  Line 45: [STYLE-010] Async method 'GetUser' should end with 'Async' suffix

Exit code: 10 (violations detected)
```

### Example 2: JSON Output for CI

```bash
python3 scripts/check_style.py --target . --format json
```

```json
{
  "scan_timestamp": "2026-02-08T10:30:00Z",
  "files_scanned": 42,
  "violations": [
    {
      "file": "src/models/User.cs",
      "line": 1,
      "column": 1,
      "rule": "STYLE-001",
      "message": "File uses CRLF but editorconfig requires LF",
      "severity": "warning"
    }
  ],
  "summary": {
    "total": 1,
    "by_severity": {"warning": 1}
  }
}
```

### Example 3: SARIF for GitHub Code Scanning

```bash
python3 scripts/check_style.py --target . --format sarif --output results.sarif
```

---

## Suppression

Suppress specific violations with inline comments:

```csharp
// style-enforcement: ignore STYLE-001
var data = GetData();  // CRLF line ending allowed here
```

```python
# style-enforcement: ignore STYLE-002
 pass  # Tab indentation allowed here
```

---

## When to Use

Use this skill when:

- Checking style compliance before commits
- Enforcing consistent code formatting in CI
- Validating editorconfig rules are applied correctly
- Detecting naming convention violations

Use existing linters instead when:

- Full ESLint/Prettier rules needed (JavaScript)
- Full StyleCop Analyzer output needed (C#, use `dotnet build`)
- Auto-formatting is desired (use `dotnet format`, `black`, `prettier`)

---

## Language Support

### Fully Supported

| Language | Extensions | Naming Rules |
|----------|------------|--------------|
| C# | .cs | Async suffix, interface prefix |
| Python | .py | snake_case validation |
| PowerShell | .ps1, .psm1 | Verb-Noun validation |
| JavaScript/TypeScript | .js, .ts, .jsx, .tsx | camelCase validation |

### Basic Support (line endings, indentation, charset)

- Go (.go)
- Rust (.rs)
- Java (.java)
- Ruby (.rb)
- Markdown (.md)
- YAML (.yml, .yaml)
- JSON (.json)

---

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Running without .editorconfig | No rules to enforce | Create .editorconfig first |
| Ignoring all violations | Defeats purpose | Fix root causes, suppress sparingly |
| Checking generated files | False positives | Add to .gitignore or ignore patterns |
| Mixing with auto-formatters | Conflicts | Run formatter first, then check |

---

## Verification

After running style check:

- [ ] .editorconfig parsed successfully
- [ ] Violations include file:line:rule format
- [ ] Exit code matches violation count (0 vs 10)
- [ ] Suppression comments honored
- [ ] SARIF output validates (if used)

---

## Related Skills

| Skill | Relationship |
|-------|--------------|
| [code-qualities-assessment](../code-qualities-assessment/SKILL.md) | Design quality vs style |
| [analyze](../analyze/SKILL.md) | Broad codebase investigation |
| [security-scan](../security-scan/SKILL.md) | Security vs style violations |

---

## Timelessness: 8/10

EditorConfig is an industry standard (2012+) supported by all major editors and IDEs.
Style conventions (naming, indentation, line endings) are fundamental to code quality.
The skill delegates language-specific rules to external analyzers when available.
