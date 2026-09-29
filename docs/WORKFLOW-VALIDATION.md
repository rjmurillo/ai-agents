# Workflow Validation Guide

This guide explains how to validate GitHub Actions workflows locally before pushing changes.

## Quick Start

### Validate All Workflows

```bash
uv run python scripts/validate_workflows.py
```

### Validate Only Changed Files

```bash
uv run python scripts/validate_workflows.py --changed
```

### Validate Specific File

```bash
uv run python scripts/validate_workflows.py .github/workflows/pytest.yml
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
uv run python scripts/validate_workflows.py --act
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

Workflow validation is integrated into the Lefthook pre-push jobs declared in
`lefthook.yml`. Lefthook filters changed workflow and action files, then runs
the named validators.

To enable the hooks:

```bash
uv run --frozen lefthook install --reset-hooks-path
uv run --frozen lefthook check-install
```

### Manual Validation

Run validation independently before pushing:

```bash
uv run python scripts/validate_workflows.py --changed
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
uv run python scripts/validate_workflows.py
```

## Examples

### Example 1: Clean Validation

```bash
$ uv run python scripts/validate_workflows.py .github/workflows/pytest.yml
Validating: .github/workflows/pytest.yml

✅ All validations passed
```

### Example 2: With Warnings

```bash
$ uv run python scripts/validate_workflows.py .github/workflows/large-workflow.yml
Validating: .github/workflows/large-workflow.yml

⚠️  Warnings:
  .github/workflows/large-workflow.yml: Workflow has 821 lines of code (ADR-006 recommends ≤100)

✅ All validations passed
```

### Example 3: With Errors

```bash
$ uv run python scripts/validate_workflows.py .github/workflows/bad-workflow.yml
Validating: .github/workflows/bad-workflow.yml

❌ Errors:
  .github/workflows/bad-workflow.yml: Action 'actions/checkout@v4' must use SHA pinning

Validation failed with 1 error(s)
```

## Local versus CI duplication audit

Issue #5067 asked for a per-check audit of the local pre-PR sequence against CI.
This section replaces the pre-#5132 figures ("about 20 checks", "5 ratchets").
Measured 2026-09-29 against `origin/main` at `6d49acc33`, the base of the branch that
added this section.

Method: the 79 gates in `_SEQUENCE` (`scripts/validation/pre_pr_sequence.py`) were
listed by importing the module. Each gate's implementation was matched against
the script stems on non-comment lines of the 56 files in `.github/workflows/`
and against `lefthook.yml`. Every match below was confirmed by reading the
workflow step and the gate wrapper. No workflow invokes `pre_pr.py` itself.

Two rules decide the disposition:

- ADR-093: a local run clears a red remote check only when the checker, ruleset,
  flags, and version are identical. A different flag or tool is a different check.
- Both sides stay when the workflow says why. `pr-validation.yml` states the CI leg
  exists for routes that skip local hooks: `--no-verify`, a clone without
  `lefthook install`, the web editor, the API, and bot pushes.

Nothing is dropped in this change. Dropping the local side moves a known failure
to a CI round trip. Dropping the CI side reopens the hook-skipping routes.

### Checks in `pr-validation.yml` (14)

| Check | Runs locally | Runs in CI | Duplicate | Disposition |
|---|---|---|---|---|
| PR description vs diff (`map_pr_description_result.py`) | Not in `_SEQUENCE` | `validate-pr` step | No | Keep CI. It reads the PR body, which does not exist before the PR opens. |
| PR description standards (`parse_pr_standards.py`) | Not in `_SEQUENCE` | `validate-pr` step | No | Keep CI. Same reason. |
| Workflow YAML (`scripts/validate_workflows.py`) | pre-commit `workflow-validation`, staged files only | `Validate workflow YAML`, whole tree | Yes, same script | Keep both. The `Workflow YAML Validation` pre-PR gate runs actionlint, a different checker. |
| Bare-python3 entrypoints (`check_python3_entrypoints.py`) | None | `Check bare-python3 documentation entrypoints` | No | Keep CI. The `Documented Interpreter Portability` gate is a different script. |
| Rule scope declarations (`check_rule_scope_keys.py`) | pre-PR gate `Rule Scope Declarations (paths:)` | `Check rule scope declarations (paths:)` | Yes, same script | Keep both. |
| ADR-006 run-block ratchet (`adr006_run_block_scanner.py`) | None | `Run ADR-006 run-block ratchet` | No | Keep CI. |
| Taste-lint count ratchet | pre-push `count-ratchets`, pre-PR `Count Ratchets` | `Run taste-lint error-count ratchet` | Yes, same script | Keep both. |
| Type-ignore count ratchet | same | `Run type-ignore count ratchet` | Yes, same script | Keep both. |
| Unindexed-memory count ratchet | same | `Run unindexed-memory count ratchet` | Yes, same script | Keep both. |
| Memory-index token ratchet | same | `Run memory-index token ratchet` | Yes, same script | Keep both. |
| Merge-tree ratchet | same | `Run merge-tree ratchet` | Yes, same script | Keep both. |
| CLI exit contract ratchet | same | `Run CLI exit contract ratchet` | Yes, same script | Keep both. |
| Conflict markers | pre-commit `conflict-marker-policy`, staged files | `Check for conflict markers`, tracked tree | Partial: same script, different subcommand and scope | Keep both. |
| Model pin policy (`check_model_pins.py`) | pre-PR gate `Model Pin Governance (warn)`, `--mode warn` | `Enforce model pin policy`, `--mode enforce` | No: different flags | Keep both. Only CI enforces. |

Result: 8 same-script duplicates, 1 partial duplicate, 1 different-flag pair, 4
CI-only checks.

### Pre-PR gates that a dedicated workflow also runs

| Pre-PR gate | Runs in CI at | Duplicate | Disposition |
|---|---|---|---|
| Python Syntax (compile gate) | `pytest.yml` | Yes, same script | Keep both. |
| Index Line Endings | `pytest.yml` | Yes, same script | Keep both. |
| Legacy .agents Write Targets | `validate-vendor-portability.yml` (also pre-commit `agents-write-targets`) | Yes, same script | Keep both. |
| Spec ID Uniqueness | `validate-spec-id-uniqueness.yml` | Yes, same script | Keep both. |
| Vendor Portability, Skill Script Portability, Skill Markdown Portability, Skill Markdown Exec Portability, Skill Resolver Anchoring, Plugin-Root Interpreter, Skill Contract Tests (7 gates) | `validate-vendor-portability.yml` | Yes, same scripts | Keep both. `test_pre_pr_covers_vendor_portability.py` pins the parity. |
| Rule Activation Coverage | `validate-rule-activation-coverage.yml` | Yes, same script | Keep both. |
| Path Normalization | `validate-paths.yml`; pre-push fast stage runs it once | Yes, same script | Keep both. The `already_run_by` field prevents a second local run. |
| Planning Artifacts | `validate-planning-artifacts.yml`; pre-push fast stage runs it once | Yes, same script | Keep both. |
| Plugin Version Bump | `validate-plugin-version-bump.yml` through `run_plugin_version_bump_ci.py` | Yes, same underlying script | Keep both. |
| Hook Anchoring (Claude + Copilot) | `validate-plugin-manifests.yml` | Yes, same script | Keep both. |
| Copilot Agent Frontmatter | `validate-generated-agents.yml` | Yes, same script | Keep both. |
| Argument-Hint Frontmatter | `validate-generated-agents.yml` | Yes, same script | Keep both. |
| Generated Artifact Staleness | `validate-generated-agents.yml` (`build_all.py --check`) | Yes, same command | Keep both. |
| Instruction Budget (always-on) | `instruction-budget.yml` (`--ci`) | Yes, same command | Keep both. |
| Count Ratchets: `ruff_ratchet.py`, `ruff_count_ratchet.py`, `subprocess_encoding_count_ratchet.py` (3 of the 9 registered ratchets) | `pytest.yml` | Yes, same scripts | Keep both. |
| YAML Style Validation | `yaml-lint.yml` | Same tool and `.yamllint.yml`; the CI version comes from an action pin, so ADR-093 cannot call it identical | Keep both. Local is advisory. |

Result: 24 same-script duplicates (21 gates and 3 ratchets), 1 same-tool pair.

The 79 rows are registered gates. A pre-push run defers 5 of them to separate hook
jobs (`already_run_by`), and `--quick` skips 4.

The other 54 gates have no workflow step that runs the same script (79 gates,
minus 25 with one: `Count Ratchets`, `Rule Scope Declarations`, `Model Pin
Governance`, `YAML Style Validation`, and the 21 gates in the table above). Two of
the 54 sit beside a CI check that uses a different tool: `Workflow YAML
Validation` (actionlint locally, `validate_workflows.py` in CI) and `Documented
Interpreter Portability` (a different script from `check_python3_entrypoints.py`).
Examples are `Nested Test Detection`, `Sync Registry Provenance`, and `Agent
Drift Detection`. They run only through `pre_pr.py`, so a hook-skipping push
reaches CI without them.

Total: 32 same-script duplicate check pairs across both tables (8 plus 24; the
workflow YAML pair is a pre-commit hook, not a `_SEQUENCE` gate), against the
"about 20 plus 5 ratchets" figure the issue carried from before #5132. Six of the
nine registered ratchets run in both pre-push and `pr-validation.yml`, not five.

## See Also

- [ADR-006: Thin Workflows, Testable Modules](../.project-toolkit/architecture/ADR-006-thin-workflows-testable-modules.md)
- [PROJECT-CONSTRAINTS.md](../.agents/governance/PROJECT-CONSTRAINTS.md)
- [nektos/act GitHub Repository](https://github.com/nektos/act)
