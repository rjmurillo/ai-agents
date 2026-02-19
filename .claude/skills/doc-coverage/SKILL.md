---
name: doc-coverage
description: Detect missing documentation in code (XML docs, docstrings, JSDoc) and project files (CHANGELOG gaps). Produces coverage reports with specific gaps by file and symbol. Use for pre-PR validation, CI gates, or documentation audits.
license: MIT
metadata:
  version: 1.0.0
  model: claude-sonnet-4-5
---

# Documentation Coverage

Detect missing documentation across code and project files with coverage metrics.

## Triggers

- `check documentation coverage`
- `find missing docs`
- `validate API documentation`
- `check XML doc comments`
- `run doc coverage scan`

---

## Quick Start

```bash
# Check all files in current directory
python3 scripts/check_docs.py --target .

# Check only changed files (CI mode)
python3 scripts/check_docs.py --git-staged

# Check specific files
python3 scripts/check_docs.py src/models/user.cs src/services/auth.py

# JSON output for automation
python3 scripts/check_docs.py --target . --format json --output coverage.json

# Set minimum threshold
python3 scripts/check_docs.py --target . --min-coverage 80
```

---

## Evidence

Created based on analysis of moq.analyzers closed PR reviewer patterns:

- **8.9% of human reviewer feedback** (10 of 112 comments) addressed documentation gaps
- Common patterns: Missing XML doc comments, CHANGELOG not updated, undocumented public APIs
- Examples: "Missing XML doc comments", "Update CHANGELOG.md", "Public API needs documentation"

Source: `.agents/analysis/moq-analyzers-reviewer-patterns-2026-02-08.md`

---

## Documentation Types Checked

### C# XML Documentation

| Element | Check | Example |
|---------|-------|---------|
| `<summary>` | Required on public types, methods, properties | `/// <summary>Description</summary>` |
| `<param>` | Required for each parameter | `/// <param name="id">The ID</param>` |
| `<returns>` | Required for non-void methods | `/// <returns>Result description</returns>` |
| `<exception>` | Recommended for thrown exceptions | `/// <exception cref="ArgumentNullException">` |

### Python Docstrings

| Element | Check | Example |
|---------|-------|---------|
| Module docstring | Required at top of file | `"""Module description."""` |
| Function docstring | Required for public functions | `"""Function description."""` |
| Class docstring | Required for public classes | `"""Class description."""` |
| Args section | Recommended (Google style) | `Args:\n    param: Description` |

### JavaScript/TypeScript JSDoc

| Element | Check | Example |
|---------|-------|---------|
| Function JSDoc | Required for exported functions | `/** @description ... */` |
| Class JSDoc | Required for exported classes | `/** @class ... */` |
| `@param` | Required for each parameter | `@param {string} name` |
| `@returns` | Required for non-void functions | `@returns {number}` |

### CHANGELOG Coverage

| Check | Description |
|-------|-------------|
| Entry exists | PRs with breaking changes have CHANGELOG entry |
| Version section | Current version has section in CHANGELOG.md |
| Date format | Entries follow consistent date format |

---

## When to Use

Use this skill when:

- Preparing code for PR submission (catch documentation gaps before review)
- Setting up CI gates for documentation quality
- Auditing existing codebase documentation coverage
- Enforcing documentation standards on public APIs

Use **doc-sync** instead when:

- Syncing CLAUDE.md navigation files
- Updating architecture documentation in README files
- Not checking code-level documentation

---

## Output Formats

### Text (default)

```
Documentation Coverage Report
=============================

Overall Coverage: 73.2% (below 80% threshold)

Gaps Found: 12

src/services/auth.cs:45:AuthenticateUser
  - Missing: <summary> on public method
  - Missing: <param name="credentials">

src/models/user.py:12:User
  - Missing: class docstring

CHANGELOG.md
  - Missing: entry for breaking change in v2.1.0
```

### JSON

```json
{
  "coverage_percent": 73.2,
  "threshold": 80,
  "passed": false,
  "total_symbols": 156,
  "documented_symbols": 114,
  "gaps": [
    {
      "file": "src/services/auth.cs",
      "line": 45,
      "symbol": "AuthenticateUser",
      "type": "method",
      "missing": ["summary", "param:credentials"]
    }
  ]
}
```

### Markdown

Produces a markdown report suitable for PR comments or documentation.

---

## Configuration

Create `.doccoveragerc.json` in project root:

```json
{
  "min_coverage_percent": 80,
  "check_public_only": true,
  "check_changelog": true,
  "exclude_patterns": [
    "**/tests/**",
    "**/test_*.py",
    "**/*.Tests.cs",
    "**/dist/**",
    "**/node_modules/**"
  ],
  "languages": {
    "csharp": {
      "require_summary": true,
      "require_param": true,
      "require_returns": true,
      "require_exception": false
    },
    "python": {
      "style": "google",
      "require_module_docstring": true,
      "require_args_section": false
    },
    "javascript": {
      "require_jsdoc": true,
      "require_param": true,
      "require_returns": true
    }
  }
}
```

---

## Exit Codes

| Code | Meaning | Action |
|------|---------|--------|
| 0 | Coverage meets threshold | Proceed with PR |
| 10 | Coverage below threshold | Add documentation |
| 1 | Error (file not found, parse error) | Fix error |

---

## Integration

### Pre-commit Hook

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: doc-coverage
        name: Documentation Coverage
        entry: python3 .claude/skills/doc-coverage/scripts/check_docs.py --git-staged --min-coverage 80
        language: system
        pass_filenames: false
```

### GitHub Actions

```yaml
# .github/workflows/docs.yml
name: Documentation Coverage
on: [pull_request]

jobs:
  doc-coverage:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Check documentation coverage
        run: |
          python3 .claude/skills/doc-coverage/scripts/check_docs.py \
            --target . \
            --min-coverage 80 \
            --format json \
            --output coverage.json
      - name: Upload coverage report
        uses: actions/upload-artifact@v4
        with:
          name: doc-coverage
          path: coverage.json
```

---

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Requiring 100% coverage | Leads to low-quality filler docs | Set realistic threshold (80%) |
| Checking test files | Test docs are less critical | Exclude test patterns |
| Ignoring CHANGELOG | Breaking changes need documentation | Enable changelog checks |
| No configuration | One size doesn't fit all | Use .doccoveragerc.json |

---

## Verification

After running:

- [ ] Coverage percentage reported
- [ ] All gaps have file:line:symbol location
- [ ] Exit code matches coverage status
- [ ] Configuration file respected (if present)

---

## Scripts

| Script | Purpose | Exit Codes |
|--------|---------|------------|
| `scripts/check_docs.py` | Main documentation coverage scanner | 0=pass, 10=below threshold, 1=error |

---

## Extension Points

1. **New languages**: Add parser in `check_docs.py` for additional languages
2. **Custom checks**: Add project-specific documentation requirements
3. **Report formats**: Add SARIF or other CI-friendly formats
4. **Threshold by type**: Different thresholds for classes vs methods

---

## Related Skills

| Skill | Relationship |
|-------|--------------|
| style-enforcement | Complements with code style checks |
| code-qualities-assessment | Broader quality assessment including docs |
| analyze | Deep codebase analysis including doc patterns |
