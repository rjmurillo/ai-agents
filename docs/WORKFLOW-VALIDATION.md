# Workflow Validation Guide

This guide explains how to validate GitHub Actions workflows locally before pushing changes.

## Quick Start

### Validate All Workflows

```bash
python3 scripts/validate_workflows.py
```

### Validate Only Changed Files

```bash
python3 scripts/validate_workflows.py --changed
```

### Validate Specific File

```bash
python3 scripts/validate_workflows.py .github/workflows/pytest.yml
```

## What Gets Validated

The validation script checks:

1. **YAML Syntax**: Valid YAML structure
2. **Workflow Structure**: Required fields (`name`, `on`, `jobs`)
3. **Action Pinning**: All actions use SHA pinning (security requirement)
4. **Workflow Size**: Warns if >100 lines (ADR-006: thin orchestration)
5. **Concurrency**: Validates concurrency configuration
6. **Permissions**: Warns if missing explicit permissions (security best practice)

## Validation Results

### Exit Codes

- `0`: All validations passed (warnings are OK)
- `1`: Validation errors found (must fix)
- `2`: Script error (missing dependencies, etc.)

### Warnings vs Errors

**Warnings** are informational and don't block commits:

- Workflow exceeds 100 lines (ADR-006 recommendation)
- Missing explicit permissions field
- Other best practice violations

**Errors** must be fixed before committing:

- Invalid YAML syntax
- Missing required fields
- Actions not SHA-pinned
- Structural issues

## Advanced Usage

### Run with act (GitHub Actions Local Runner)

If you have `act` installed, you can test workflow execution locally:

```bash
python3 scripts/validate_workflows.py --act
```

This will:

1. Run all standard validations
2. Use `act` to dry-run each workflow
3. Catch runtime issues before pushing

### Install act

**Linux (Homebrew)**:

```bash
brew install act
```

**Linux (Manual)**:

```bash
curl -s https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash
```

**Note**: `act` requires Docker to be installed and running.

## Integration with Git Hooks

### Automatic Pre-Push Validation

Workflow validation is **automatically integrated** into the pre-push hook at `.githooks/pre-push`.

When you push changes to workflow files (`.github/workflows/*.yml` or `.github/actions/*/action.yml`), the hook will:

1. Run `actionlint` for workflow-specific validation
2. Run `validate_workflows.py` for security and structure validation
3. Block the push if either validation fails

To enable the hooks:

```bash
git config core.hooksPath .githooks
```

The validation runs as **Phase 2, Check 8a** in the pre-push sequence, immediately after actionlint.

### Manual Validation

Run validation independently before pushing:

```bash
python3 scripts/validate_workflows.py --changed
git push
```

## ADR-006 Compliance

The validation script enforces ADR-006 (Thin Workflows, Testable Modules):

- **Warns** when workflows exceed 100 lines
- Encourages extracting logic to PowerShell modules
- Promotes local testing with Pester

If your workflow triggers size warnings:

1. Extract business logic to `.psm1` modules
2. Add Pester tests for the modules
3. Keep workflow YAML as thin orchestration

## Security Compliance

The script enforces security best practices:

### SHA Pinning (REQUIRED)

All external actions must use SHA pinning:

**Correct**:

```yaml
- uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5 # v4.3.1
```

**Incorrect**:

```yaml
- uses: actions/checkout@v4.3.1
- uses: actions/checkout@v4
- uses: actions/checkout@main
```

### Explicit Permissions (RECOMMENDED)

Workflows should declare permissions explicitly:

```yaml
name: My Workflow
on: push
permissions:
  contents: read
  pull-requests: write
jobs:
  # ...
```

## Troubleshooting

### PyYAML Not Found

```bash
# Install with uv
uv pip install PyYAML

# Or with pip
pip install PyYAML
```

### YAML 1.1 'on' Keyword Issue

The script handles the YAML 1.1 quirk where `on:` is parsed as boolean `True`.

If you see false positives about missing 'on' triggers, this is a bug in the validation script.

### Git Commands Fail

Ensure you're running the script from within a git repository:

```bash
cd /path/to/repo
python3 scripts/validate_workflows.py
```

## Examples

### Example 1: Clean Validation

```bash
$ python3 scripts/validate_workflows.py .github/workflows/pytest.yml
Validating: .github/workflows/pytest.yml

✅ All validations passed
```

### Example 2: With Warnings

```bash
$ python3 scripts/validate_workflows.py .github/workflows/large-workflow.yml
Validating: .github/workflows/large-workflow.yml

⚠️  Warnings:
  .github/workflows/large-workflow.yml: Workflow has 821 lines of code (ADR-006 recommends ≤100)

✅ All validations passed
```

### Example 3: With Errors

```bash
$ python3 scripts/validate_workflows.py .github/workflows/bad-workflow.yml
Validating: .github/workflows/bad-workflow.yml

❌ Errors:
  .github/workflows/bad-workflow.yml: Action 'actions/checkout@v4' must use SHA pinning

Validation failed with 1 error(s)
```

## See Also

- [ADR-006: Thin Workflows, Testable Modules](../.agents/architecture/ADR-006-thin-workflows-testable-modules.md)
- [PROJECT-CONSTRAINTS.md](../.agents/governance/PROJECT-CONSTRAINTS.md)
- [nektos/act GitHub Repository](https://github.com/nektos/act)
