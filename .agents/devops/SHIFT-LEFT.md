# Shift-Left Validation Strategy

**Status**: Active
**Version**: 1.0
**Last Updated**: 2025-12-23

## Overview

Shift-left validation catches issues early in development before PR creation.
This reduces review cycles, accelerates merge velocity, and improves code quality.

## Unified Validation Runner

Use `scripts/Validate-PrePR.ps1` as the single command to run all shift-left validations.

### Quick Start

```powershell
# Full validation (recommended before creating PR)
pwsh scripts/Validate-PrePR.ps1

# Quick validation (fast checks only, for rapid iteration)
pwsh scripts/Validate-PrePR.ps1 -Quick

# Verbose output (for troubleshooting)
pwsh scripts/Validate-PrePR.ps1 -Verbose
```

## Validation Sequence

The runner executes validations in optimized order (fast checks first):

| # | Validation | Purpose | Skip if -Quick | Typical Duration |
|---|------------|---------|----------------|------------------|
| 1 | Session End | Verify session protocol compliance | No | 2-5s |
| 2 | Pester Tests | Run all unit tests | No | 10-30s |
| 3 | Markdown Lint | Auto-fix and validate markdown | No | 5-10s |
| 3.5 | Workflow YAML | Validate GitHub Actions workflows | No | 2-5s |
| 3.9 | YAML Style | Check YAML style (non-blocking warnings) | Yes | 2-5s |
| 4 | Path Normalization | Check for absolute paths | Yes | 15-30s |
| 5 | Planning Artifacts | Validate planning consistency | Yes | 10-20s |
| 6 | Agent Drift | Detect semantic drift | Yes | 20-40s |

### Total Duration

- **Quick mode**: ~20-50s (validations 1-3.5)
- **Full mode**: ~60-120s (all validations)

## Exit Codes

| Code | Meaning | Action |
|------|---------|--------|
| 0 | PASS | All validations succeeded, ready for PR |
| 1 | FAIL | One or more validations failed, fix issues |
| 2 | ERROR | Environment or configuration issue |

## Validation Details

### 1. Session End Validation

**Script**: `scripts/Validate-Session.ps1`

**Checks**:

- Session log exists in `.agents/sessions/`
- Session End checklist complete (all MUST rows checked)
- Evidence provided for each checklist item
- HANDOFF.md updated with session link
- Markdown linting passed
- Git worktree clean (all changes committed)

**Fix suggestions**:

- Create session log if missing
- Complete Session End checklist in session log
- Run `npx markdownlint-cli2 --fix "**/*.md"`
- Commit all changes including `.agents/` files

### 2. Pester Unit Tests

**Script**: `build/scripts/Invoke-PesterTests.ps1`

**Checks**:

- All Pester tests pass
- Test coverage meets thresholds
- No test failures or errors

**Fix suggestions**:

- Review test failure output
- Run individual test file: `pwsh -File tests/MyTest.Tests.ps1`
- Use `Invoke-Pester -Output Diagnostic` for detailed output

### 3. Markdown Linting

**Tool**: `markdownlint-cli2`

**Checks**:

- No markdown linting violations
- Auto-fixable issues corrected
- Code blocks have language identifiers

**Fix suggestions**:

- Run `npx markdownlint-cli2 --fix "**/*.md"` to auto-fix
- Add language identifiers to code blocks (MD040)
- Wrap generic types like `ArrayPool<T>` in backticks (MD033)

### 3.5. Workflow YAML Validation

**Tool**: `actionlint`

**Checks**:

- GitHub Actions workflow syntax validation
- Invalid action inputs/outputs detection
- Expression type checking (`${{ }}` syntax)
- Runner label validation
- Cron syntax validation
- Security issues (script injection, credential exposure)
- Integrated shellcheck for shell scripts
- Integrated pyflakes for Python scripts

**Fix suggestions**:

- Review error messages for specific workflow file and line number
- Check action inputs against action's `action.yml` definition
- Verify runner labels exist (e.g., `ubuntu-latest`, `windows-latest`)
- Test cron expressions with online validators
- Fix expression syntax errors (missing spaces, incorrect property access)

**Installation**:

```bash
# macOS
brew install actionlint

# Linux (download binary)
bash <(curl -sSfL https://raw.githubusercontent.com/rhysd/actionlint/main/scripts/download-actionlint.bash)

# Go
go install github.com/rhysd/actionlint/cmd/actionlint@latest
```

**Local validation**:

```bash
# Validate all workflow files
actionlint

# Validate specific workflow
actionlint .github/workflows/pester-tests.yml

# JSON output for parsing
actionlint -format json
```

**Integration points**:

- Pre-commit hook: `.githooks/pre-commit` (blocking)
- Unified runner: `scripts/Validate-PrePR.ps1` (blocking)
- Worktrunk pre-merge: `.config/wt.toml` (blocking)

**Common errors**:

| Error | Cause | Fix |
|-------|-------|-----|
| `property "foo" is not defined in object type` | Typo in action input name | Check action's `action.yml` |
| `undefined variable "FOO"` | Using undefined output/env | Verify variable is set earlier |
| `invalid CRON format` | Bad schedule syntax | Use `0 0 * * *` format |
| `runner label "foo" is unknown` | Invalid runs-on value | Use official runner labels |
| `shellcheck reported issue` | Shell script error | Fix script syntax |

### 3.9. YAML Style Validation

**Tool**: `yamllint`

**Purpose**: Validates YAML files for style consistency across the repository. Complements actionlint (which focuses on GitHub Actions semantics) by checking general YAML formatting.

**Checks**:

- Line length limits (120 characters max)
- Consistent 2-space indentation
- Trailing spaces
- Comment formatting (space after `#`)
- Unix line endings
- New line at end of file

**Configuration**: `.yamllint.yml` in repository root

**Installation**:

```bash
# macOS
brew install yamllint

# Linux/Windows (via pip)
pip install yamllint

# Verify installation
yamllint --version
```

**Local validation**:

```bash
# Validate all YAML files
yamllint .

# Validate specific file
yamllint .github/workflows/pester-tests.yml

# Parsable format (for CI)
yamllint -f parsable .
```

**Integration points**:

- Pre-commit hook: `.githooks/pre-commit` (non-blocking warnings)
- Unified runner: `scripts/Validate-PrePR.ps1` (skipped if -Quick, non-blocking)

**Behavior**:

- **Non-blocking**: yamllint failures show warnings but don't fail commits
- **Rationale**: Style issues are cosmetic and shouldn't block development velocity
- **Recommendation**: Fix yamllint warnings during code cleanup or refactoring

**Common warnings**:

| Warning | Cause | Fix |
|---------|-------|-----|
| `line too long` | Line exceeds 120 chars | Split long lines or shorten URLs |
| `trailing-spaces` | Spaces at end of line | Remove trailing spaces |
| `indentation` | Inconsistent spacing | Use 2 spaces for indentation |
| `comments` | Missing space after # | Add space: `# comment` not `#comment` |
| `new-line-at-end-of-file` | No newline at EOF | Add blank line at end |

**Relationship to actionlint**:

| Tool | Focus | When to Use |
|------|-------|-------------|
| actionlint | GitHub Actions semantics | Always for workflow files (blocking) |
| yamllint | General YAML style | All YAML files (non-blocking warnings) |

Both tools should be used together: actionlint catches functional errors, yamllint enforces style consistency.

### 4. Path Normalization

**Script**: `build/scripts/Validate-PathNormalization.ps1`

**Checks**:

- No absolute paths in documentation files
- All paths use relative format
- Cross-platform path separators (forward slashes)

**Fix suggestions**:

- Replace absolute paths with relative paths
- Use forward slashes (/) for cross-platform compatibility
- Examples: `docs/guide.md`, `../architecture/design.md`

### 5. Planning Artifacts

**Script**: `build/scripts/Validate-PlanningArtifacts.ps1`

**Checks**:

- Effort estimate consistency (within 20% threshold)
- No orphan conditions (all conditions linked to tasks)
- Requirement coverage complete

**Fix suggestions**:

- Add Estimate Reconciliation section to task breakdown
- Link specialist conditions to specific tasks
- Add Conditions column to Work Breakdown table

### 6. Agent Drift Detection

**Script**: `build/scripts/Detect-AgentDrift.ps1`

**Checks**:

- Semantic alignment between Claude and VS Code agents
- Core sections consistent (>80% similarity)
- No unintended divergence in responsibilities

**Fix suggestions**:

- Review drifting sections in output
- Sync content between agent variants
- Document intentional platform-specific differences

## Integration with Workflows

### Pre-Commit Hook

The pre-commit hook (`.githooks/pre-commit`) runs a subset of validations automatically:

- Markdown linting (auto-fix enabled)
- PowerShell script analysis
- Session End validation (if `.agents/` files staged)

**Recommendation**: Run `Validate-PrePR.ps1` before committing to catch issues earlier.

### CI Pipeline

The full validation suite runs in CI via GitHub Actions workflow:

- Workflow: `.github/workflows/shift-left-validation.yml`
- Trigger: On push to feature branches
- Mode: Full validation (no -Quick flag)

### Developer Workflow

Recommended workflow for feature development:

```text
1. Make changes
2. Run: pwsh scripts/Validate-PrePR.ps1 -Quick
3. Fix any issues
4. Commit changes (pre-commit hook runs subset)
5. Before PR: pwsh scripts/Validate-PrePR.ps1 (full validation)
6. Create PR (CI runs full validation)
```

## Performance Optimization

### Quick Mode

Use `-Quick` flag during rapid iteration to skip slow validations:

```powershell
pwsh scripts/Validate-PrePR.ps1 -Quick
```

**Skipped validations**:

- Path Normalization (15-30s saved)
- Planning Artifacts (10-20s saved)
- Agent Drift (20-40s saved)

**Total time saved**: ~50-90s per run

### Parallel Execution

Validations run sequentially by design to:

- Provide clear progress feedback
- Fail fast on blocking issues
- Simplify error diagnosis

Future enhancement: Add `-Parallel` flag for independent validations.

## Local Workflow Testing with act

### Overview

The `act` tool (nektos/act) enables local testing of GitHub Actions workflows using Docker containers. This reduces the expensive push-check-tweak cycle by catching workflow errors before CI runs.

### Supported Workflows

Workflows compatible with local testing (PowerShell-only, no AI dependencies):

| Workflow | Description | Test Viability |
|----------|-------------|----------------|
| `pester-tests.yml` | Run Pester unit tests | ✅ Full support |
| `validate-paths.yml` | Path normalization validation | ✅ Full support |
| `memory-validation.yml` | Memory index validation | ✅ Full support |

Workflows **not** compatible with local testing:

| Workflow | Reason |
|----------|--------|
| `ai-session-protocol.yml` | Requires Copilot CLI and BOT_PAT |
| `ai-pr-quality-gate.yml` | Requires Copilot CLI and BOT_PAT |
| `ai-spec-validation.yml` | Requires Copilot CLI and BOT_PAT |

### Prerequisites

```bash
# Install act
brew install act                    # macOS
choco install act-cli               # Windows
gh extension install https://github.com/nektos/gh-act  # GitHub CLI extension
# Linux: Download from https://github.com/nektos/act/releases

# Install Docker (required by act)
# macOS/Windows: https://www.docker.com/products/docker-desktop
# Linux: https://docs.docker.com/engine/install/

# Verify installation
act --version
docker info
```

### Configuration

The repository includes `.actrc` with optimized defaults:

- Uses `catthehacker/ubuntu:full-latest` images for maximum production parity (~18GB)
- Enables artifact storage in `.artifacts/`
- Enables caching in `.cache/`
- Uses linux/amd64 architecture for compatibility
- Maps `windows-latest` to `-self-hosted` (runs on host, not container)

**Note**: Full images are large (~18GB) but provide complete tool parity with GitHub-hosted runners, optimizing for "no surprises" - if it works locally, it works in production.

### Usage

#### PowerShell Wrapper (Recommended)

Use `scripts/Test-WorkflowLocally.ps1` for simplified workflow testing:

```powershell
# Run pester-tests workflow
pwsh scripts/Test-WorkflowLocally.ps1 -Workflow pester-tests

# Dry-run to validate syntax only
pwsh scripts/Test-WorkflowLocally.ps1 -Workflow validate-paths -DryRun

# Run specific job with verbose output
pwsh scripts/Test-WorkflowLocally.ps1 -Workflow pester-tests -Job test -Verbose

# Pass secrets
pwsh scripts/Test-WorkflowLocally.ps1 -Workflow pester-tests -Secrets @{ GITHUB_TOKEN = $env:GITHUB_TOKEN }
```

#### Direct act Commands

```bash
# Run workflow
act pull_request -W .github/workflows/pester-tests.yml

# Dry-run (validate only)
act pull_request -W .github/workflows/validate-paths.yml -n

# Run specific job
act pull_request -j test -W .github/workflows/pester-tests.yml

# Pass secret
act pull_request -W .github/workflows/pester-tests.yml -s GITHUB_TOKEN="$(gh auth token)"

# List available workflows
act -l
```

### Limitations

#### Windows-Specific Code

act uses Linux containers, so Windows-specific behaviors may differ:

- File paths (backslashes vs. forward slashes)
- Line endings (CRLF vs. LF)
- Hidden file detection
- Case sensitivity

**Workaround**: Use `-P windows-latest=-self-hosted` to run on host machine (see `.actrc`).

#### Missing Pre-installed Tools

GitHub-hosted runners have many pre-installed tools. The default `.actrc` configuration uses full images for maximum compatibility:

- **Default**: Full images (18GB+) via `.actrc` - complete tool parity with GitHub-hosted runners
- **Alternative**: Medium images for faster iteration: `-P ubuntu-latest=catthehacker/ubuntu:act-latest`
- **Custom**: Use custom Dockerfile with specific required tools

#### AI-Dependent Workflows

Workflows requiring Copilot CLI or BOT_PAT cannot run locally:

- Infrastructure-dependent (no local alternative)
- Shift-left not possible for these workflows
- Must rely on CI feedback

**ROI**: Medium - Reduces iteration time for 30% of workflows (PowerShell-only). Highest-failure workflows (Session Protocol, AI Quality Gate) still require CI.

### Troubleshooting

#### act Issues

| Problem | Cause | Solution |
|---------|-------|----------|
| `act: command not found` | act not installed | Install via brew/choco or download binary |
| `Cannot connect to Docker daemon` | Docker not running | Start Docker Desktop |
| `Error: image not found` | Missing Docker image | Pull image: `docker pull catthehacker/ubuntu:act-latest` |
| `Permission denied` | Docker socket permissions | Add user to docker group or use sudo |
| `Workflow validation failed` | Syntax error in workflow | Fix YAML syntax, run actionlint first |
| `Action not found` | Typo in action name | Check action exists on GitHub Marketplace |
| `Unknown runner label` | Invalid runs-on value | Use official labels: ubuntu-latest, windows-latest |

#### PowerShell Issues in act

| Problem | Cause | Solution |
|---------|-------|----------|
| `$ErrorActionPreference` not respected | act's PowerShell handling | act automatically prepends `$ErrorActionPreference = 'stop'` |
| `Write-Host` output missing | PowerShell stream redirection | Use `Write-Output` or check act's stdout |
| Module not found | Missing from Docker image | Install module in workflow: `Install-Module -Name Pester` |

## Troubleshooting

### Environment Issues

**Symptom**: Script exits with code 2

**Common causes**:

- PowerShell not installed: Install PowerShell Core 7+
- Node.js not installed: Install Node.js 18+ for markdownlint
- Git repository not initialized: Run in git repository root

### Validation Failures

**Symptom**: Script exits with code 1

**Steps**:

1. Review error messages in output
2. Run individual validation script for details
3. Fix issues based on fix suggestions above
4. Re-run `Validate-PrePR.ps1`

### Performance Issues

**Symptom**: Validation takes >2 minutes

**Optimization**:

- Use `-Quick` flag for rapid iteration
- Skip tests during markdown-only changes: `-SkipTests`
- Run individual validations: `pwsh scripts/Validate-Session.ps1`

## Metrics

Target validation times (as of 2025-12-23):

| Metric | Target | Maximum |
|--------|--------|---------|
| Quick mode | <30s | 60s |
| Full mode | <90s | 120s |
| Session End | <5s | 10s |
| Pester Tests | <20s | 60s |
| Markdown Lint | <10s | 20s |

**Current baseline**: Measured on Ubuntu 22.04, Intel i7, 16GB RAM

## Future Enhancements

Planned improvements:

- **Parallel execution**: Add `-Parallel` flag for independent validations
- **Incremental validation**: Skip unchanged files
- **Watch mode**: Auto-run on file changes
- **IDE integration**: VS Code task definitions
- **Metrics dashboard**: Track validation trends over time

## Related Documentation

- **Session Protocol**: `.agents/SESSION-PROTOCOL.md`
- **Pre-commit Hook**: `.githooks/pre-commit`
- **CI Pipeline**: `.github/workflows/shift-left-validation.yml`
- **DevOps Patterns**: `.agents/devops/validation-runner-pattern.md`

## References

- **Issue #325**: Unified shift-left validation runner
- **ADR-017**: Tiered memory index architecture
- **ADR-014**: Distributed handoff architecture
- **ADR-005**: PowerShell-only scripting standard
