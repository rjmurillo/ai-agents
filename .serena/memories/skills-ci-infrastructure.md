# CI Infrastructure Skills

**Extracted**: 2025-12-15
**Updated**: 2025-12-20 (added Skill-CI-Workflows-001)
**Source**: ai-agents install scripts session - CI/CD setup

## Skill-CI-Workflows-001: dorny/paths-filter Global Checkout Requirement

**Statement**: dorny/paths-filter requires checkout in ALL jobs, not just the job using the filter

**Context**: When using dorny/paths-filter action in GitHub Actions workflows with multiple jobs

**Evidence**: PR #121 in rjmurillo/ai-agents - Initially added docs-only filter to skip-tests job without checkout. rjmurillo correction: "dorny/paths-filter requires checkout in ALL jobs". Unused filter removed because checkout requirement made it redundant.

**Impact**: Without checkout, dorny/paths-filter cannot access git history to determine changed files, causing workflow to fail or produce incorrect results.

**Atomicity**: 98%

**Source**: Session 38 retrospective (2025-12-20)

**Pattern**:
```yaml
jobs:
  check-changes:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4  # REQUIRED
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          filters: |
            docs:
              - '**/*.md'
    outputs:
      docs-only: ${{ steps.filter.outputs.docs == 'true' }}

  skip-tests:
    needs: check-changes
    if: needs.check-changes.outputs.docs-only == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4  # STILL REQUIRED even though filter is in different job
      - run: echo "Skipping tests for docs-only change"
```

**Common Mistake**: Assuming only the job using dorny/paths-filter needs checkout.

**Related Skills**: None

---

## Skill-CI-TestRunner-001: Reusable Test Runner Pattern

**Statement**: Extract test runner to build/scripts/ with CI and local modes for consistent execution

**Context**: When creating CI/CD pipelines that developers can also run locally

**Evidence**: Invoke-PesterTests.ps1 with -CI switch used by workflow and developers

**Atomicity**: 88%

**Pattern**:

```powershell
# build/scripts/Invoke-PesterTests.ps1
[CmdletBinding()]
param(
    [string]$TestPath = "./scripts/tests",
    [string]$OutputPath = "./artifacts/pester-results.xml",
    [ValidateSet("NUnitXml", "JUnitXml")]
    [string]$OutputFormat = "NUnitXml",
    [ValidateSet("None", "Normal", "Detailed", "Diagnostic")]
    [string]$Verbosity = "Detailed",
    [switch]$CI,        # Exit with error code on failure
    [switch]$PassThru   # Return result object
)

# Configure Pester
$config = New-PesterConfiguration
$config.Run.Path = $TestPath
$config.Run.Exit = $CI.IsPresent  # Only exit on failure in CI mode
$config.Run.PassThru = $true
$config.TestResult.Enabled = $true
$config.TestResult.OutputFormat = $OutputFormat
$config.TestResult.OutputPath = $OutputPath

$result = Invoke-Pester -Configuration $config

# Local mode: return result for inspection
if ($PassThru) { return $result }
```

**Usage**:

```powershell
# Local development
.\build\scripts\Invoke-PesterTests.ps1 -Verbosity Detailed

# CI pipeline
.\build\scripts\Invoke-PesterTests.ps1 -CI
```

**Workflow Integration**:

```yaml
# .github/workflows/pester-tests.yml
- name: Run Pester Tests
  shell: pwsh
  run: ./build/scripts/Invoke-PesterTests.ps1 -CI
```

---

## Skill-CI-Artifacts-001: Artifact Path Convention

**Statement**: Use artifacts/ directory for all test outputs; configure in single location

**Context**: When standardizing build artifact locations

**Evidence**: Consolidated test output to artifacts/pester-results.xml

**Atomicity**: 85%

**Pattern**:

```text
project/
  artifacts/           # All build outputs
    pester-results.xml
    coverage/
    logs/
  build/
    scripts/           # Build automation
      Invoke-PesterTests.ps1
  .github/
    workflows/
      pester-tests.yml
```

**Benefits**:

- Single location for CI to upload artifacts
- Easy to add to .gitignore
- Consistent across different test frameworks
- Matches common CI/CD conventions

**Configuration**:

```yaml
# .github/workflows/pester-tests.yml
- uses: actions/upload-artifact@v4
  with:
    name: test-results
    path: ./artifacts/
    retention-days: 30
```

---

## Skill-CI-Runner-001: Prefer Linux Runners

**Statement**: Prefer ubuntu-latest over windows-latest for GitHub Actions runners - MUCH faster

**Context**: GitHub Actions workflow configuration

**Evidence**: User feedback on PR #47: "prefer 'linux-latest' runners. MUCH faster"

**Atomicity**: 95%

**Tag**: helpful

**Impact**: 8/10

**Exceptions**:

- PowerShell Desktop required (not pwsh/PowerShell Core)
- Windows-specific features or APIs needed
- Testing Windows-only behavior

**Pattern**:

```yaml
# Default: Use Linux
jobs:
  build:
    runs-on: ubuntu-latest
    
# Exception: Windows-specific testing
  windows-test:
    runs-on: windows-latest
    if: needs.check.outputs.windows-required == 'true'
```

---

---

## Skill-CI-ANSI-Disable-001: Disable ANSI in CI Mode

**Statement**: Disable ANSI codes in CI via NO_COLOR env var and PSStyle.OutputRendering PlainText

**Context**: When PowerShell scripts with console color output are used in CI pipelines that generate XML or structured reports

**Evidence**: CI run 20324607494: ANSI escape codes (0x1B) corrupted Pester XML report, causing test-reporter GitHub Action to fail

**Atomicity**: 90%

**Tag**: helpful

**Impact**: 9/10

**Pattern**:

```powershell
# In test runner (Invoke-PesterTests.ps1)
if ($CI) {
    $env:NO_COLOR = '1'
    $env:TERM = 'dumb'
    if ($PSVersionTable.PSVersion.Major -ge 7) {
        $PSStyle.OutputRendering = 'PlainText'
    }
}
```

```powershell
# In scripts that output colors (Validate-PathNormalization.ps1)
$NoColor = $env:NO_COLOR -or $env:TERM -eq 'dumb' -or $env:CI

if ($NoColor) {
    $ColorRed = ""
    $ColorGreen = ""
    $ColorReset = ""
} else {
    $ColorRed = "`e[31m"
    $ColorGreen = "`e[32m"
    $ColorReset = "`e[0m"
}

function Write-ColorOutput {
    param([string]$Message, [string]$Color = $ColorReset)
    
    if ($NoColor) {
        Write-Host $Message
    } else {
        Write-Host "$Color$Message$ColorReset"
    }
}
```

**Why it matters**:

- ANSI escape codes (0x1B) are invalid XML characters
- XML parsers reject files with control characters
- CI reporting infrastructure (test-reporter) requires valid XML
- NO_COLOR is a standard environment variable for disabling colors

**Standards Respected**:

- [NO_COLOR](https://no-color.org/): Standard environment variable
- TERM=dumb: Traditional Unix signal for non-interactive mode
- PSStyle.OutputRendering: PowerShell 7+ native plain text mode

---

## Skill-CI-Environment-Testing-001: Local CI Simulation

**Statement**: Test scripts locally with temp paths and no auth to catch CI environment failures

**Context**: Before pushing PowerShell scripts that will run in GitHub Actions or other CI environments

**Evidence**: CI run 20324607494: All 4 test failures passed locally but failed in CI due to Windows 8.3 paths, gh CLI unavailability, and XML output format

**Atomicity**: 88%

**Tag**: helpful

**Impact**: 8/10

**Pattern**:

```powershell
# Local CI simulation
function Test-InCIMode {
    # Simulate CI temp paths (Windows 8.3 short names)
    $originalTemp = $env:TEMP
    $env:TEMP = "C:\Users\RUNNER~1\AppData\Local\Temp"
    
    # Remove auth tokens
    $originalGH = $env:GH_TOKEN
    Remove-Item Env:\GH_TOKEN -ErrorAction SilentlyContinue
    
    try {
        # Run tests in CI mode
        Invoke-PesterTests -CI
    }
    finally {
        # Restore environment
        $env:TEMP = $originalTemp
        if ($originalGH) { $env:GH_TOKEN = $originalGH }
    }
}
```

**Environment Differences to Simulate**:

1. **Path normalization**: Windows 8.3 short names (RUNNER~1 vs full names)
2. **External auth**: gh CLI, git credentials unavailable
3. **Output format**: XML reports instead of console output
4. **Environment variables**: CI=true, NO_COLOR=1, TERM=dumb

**Pre-push Checklist**:

- [ ] Run tests with `-CI` flag
- [ ] Test with temp directory paths
- [ ] Test without gh CLI authentication
- [ ] Verify XML output is valid (no ANSI codes)

---

## Skill-CI-Heredoc-001: YAML Heredoc Indentation (95%)

**Statement**: In YAML run blocks, heredoc content must have consistent indentation; zero-indent lines are parsed as YAML

**Context**: GitHub Actions workflow `run: |` blocks with multi-line content

**Trigger**: Creating YAML workflow with embedded multi-line content

**Evidence**: Session 04 (2025-12-18): Run 20331947252 failed with "could not find expected ':'". Heredoc content with zero indentation (e.g., `## Task`) was parsed as YAML keys, not string content.

**Atomicity**: 95%

**Impact**: Critical - Workflow fails to parse

**Tag**: helpful

**Created**: 2025-12-18

**Fix**: Move large heredoc content to separate files and reference them, or ensure consistent indentation.

---

## Skill-CI-Auth-001: GH_TOKEN Auto-Authentication (92%)

**Statement**: When GH_TOKEN env var is set, gh CLI auto-authenticates; explicit `gh auth login` fails

**Context**: GitHub Actions workflows using gh CLI

**Trigger**: Configuring gh CLI authentication in workflows

**Evidence**: Session 04 (2025-12-18): `gh auth login --with-token` failed with exit code 1 because GH_TOKEN was already set. GitHub CLI automatically uses the env var.

**Atomicity**: 92%

**Impact**: 8/10 - Prevents workflow failures

**Tag**: helpful

**Created**: 2025-12-18

**Pattern**:

```yaml
# WRONG: Explicit login when token is already set
- name: Auth
  run: echo "${{ secrets.TOKEN }}" | gh auth login --with-token

# RIGHT: Just set the env var and use gh directly
- name: Use gh
  env:
    GH_TOKEN: ${{ secrets.TOKEN }}
  run: gh pr list
```

---

## Skill-CI-Regex-001: Fixed-Length Lookbehinds for Portability (90%)

**Statement**: GNU grep lookbehinds must be fixed-length; use sed for portable variable-length regex

**Context**: Shell scripts using regex in GitHub Actions

**Trigger**: Using `grep -oP` with lookbehind assertions

**Evidence**: Session 04 (2025-12-18): Pattern `(?<=VERDICT:\s*)` failed with "lookbehind assertion is not fixed length". Variable-length `\s*` not supported.

**Atomicity**: 90%

**Impact**: 8/10 - Cross-platform compatibility

**Tag**: helpful

**Created**: 2025-12-18

**Pattern**:

```bash
# WRONG: Variable-length lookbehind
grep -oP '(?<=VERDICT:\s*)\w+' file.txt

# RIGHT: Use sed
sed -n 's/.*VERDICT:\s*\(\w\+\).*/\1/p' file.txt
```

---

## Skill-CI-Output-001: Single-Line GitHub Actions Outputs (95%)

**Statement**: GitHub Actions outputs must be single-line; multi-line values break output format

**Context**: Setting GitHub Actions step outputs

**Trigger**: Capturing command output for use in subsequent steps

**Evidence**: Session 04 (2025-12-18): `copilot --version` outputs multiple lines (version + commit), breaking output format with "Invalid format 'Commit: 83653a1'".

**Atomicity**: 95%

**Impact**: 8/10 - Prevents workflow failures

**Tag**: helpful

**Created**: 2025-12-18

**Pattern**:

```bash
# WRONG: Multi-line output
VERSION=$(copilot --version)
echo "version=$VERSION" >> $GITHUB_OUTPUT

# RIGHT: Extract single line
VERSION=$(copilot --version | head -1)
echo "version=$VERSION" >> $GITHUB_OUTPUT
```

---

## Skill-CI-Matrix-Output-001: Matrix Jobs Use Artifacts for Data Passing (98%)

**Statement**: GitHub Actions matrix jobs only expose ONE leg's outputs; use artifacts for reliable data passing

**Context**: Matrix strategy jobs needing to pass data to downstream jobs

**Trigger**: Matrix job outputs needed in aggregate/summary job

**Evidence**: Session 07 (2025-12-18): Matrix jobs (security, qa, analyst) all wrote outputs but only ONE matrix leg's outputs were available to downstream job. GitHub Community Discussion #17245 confirms this limitation.

**Atomicity**: 98%

**Impact**: Critical - Matrix output behavior is non-deterministic

**Tag**: helpful

**Created**: 2025-12-18

**Pattern**:

```yaml
# Matrix job: Save to file and upload artifact
review:
  strategy:
    matrix:
      agent: [security, qa, analyst]
  steps:
    - run: echo "$FINDINGS" > ${{ matrix.agent }}-findings.txt
    - uses: actions/upload-artifact@v4
      with:
        name: ${{ matrix.agent }}-findings
        path: ${{ matrix.agent }}-findings.txt

# Aggregate job: Download all artifacts
aggregate:
  needs: review
  steps:
    - uses: actions/download-artifact@v4
      with:
        pattern: '*-findings'
        merge-multiple: true
    - run: cat security-findings.txt qa-findings.txt analyst-findings.txt
```

---

## Skill-CI-Shell-Interpolation-001: Use Env Vars for Shell Variables (95%)

**Statement**: Never use `${{ }}` directly in shell strings; use env vars for safe interpolation

**Context**: GitHub Actions shell scripts with dynamic content

**Trigger**: Passing GitHub Actions expressions to shell scripts

**Evidence**: Session 07 (2025-12-18): Direct interpolation `if [ -n "${{ steps.x.outputs.findings }}" ]` broke when output contained quotes or special characters.

**Atomicity**: 95%

**Impact**: Critical - Special characters break shell

**Tag**: helpful

**Created**: 2025-12-18

**Pattern**:

```yaml
# WRONG: Direct interpolation
- run: |
    if [ -n "${{ steps.review.outputs.findings }}" ]; then
      echo "Found findings"
    fi

# RIGHT: Use env var
- run: |
    if [ -n "$FINDINGS" ]; then
      echo "Found findings"
    fi
  env:
    FINDINGS: ${{ steps.review.outputs.findings }}
```

---

## Skill-CI-Structured-Output-001: Verdict Tokens for AI Automation (98%)

**Statement**: AI automation in CI/CD requires verdict tokens (PASS/WARN/CRITICAL_FAIL) for deterministic bash parsing

**Context**: AI-driven quality gates in CI/CD pipelines

**Trigger**: Designing AI review prompts for CI automation

**Evidence**: Session 03 (2025-12-18): Structured verdict format enabled clean bash parsing without AI interpretation. Exit code logic: CRITICAL_FAIL → exit 1, else → exit 0.

**Atomicity**: 98%

**Impact**: Critical - Enables AI-driven CI gates

**Tag**: helpful

**Created**: 2025-12-18

**Pattern**:

```markdown
## Output Format

End your response with:
VERDICT: [PASS|WARN|CRITICAL_FAIL]
MESSAGE: [One sentence summary]
```

```bash
# Parse verdict
VERDICT=$(grep -oP '^VERDICT:\s*\K\w+' response.txt || echo "WARN")
if [ "$VERDICT" = "CRITICAL_FAIL" ]; then
  exit 1
fi
```

---

## Skill-CI-Comment-Formatting-001: CodeRabbit-Style PR Comments (85%)

**Statement**: Use emoji headers, verdict badges, and collapsible sections for vibrant PR comments

**Context**: AI-generated PR review comments

**Trigger**: Formatting PR comments for AI workflows

**Evidence**: Session 08 (2025-12-18): Enhanced AI workflow comments with CodeRabbit-style formatting (emoji headers, verdict badges, walkthrough sections, branded footer).

**Atomicity**: 85%

**Impact**: 7/10 - Improved developer experience

**Tag**: helpful

**Created**: 2025-12-18

**Pattern**:

```markdown
## 🤖 AI Quality Gate Review

### Summary

| Agent | Verdict |
|-------|---------|
| 🔒 Security | ✅ PASS |
| 🧪 QA | ⚠️ WARN |

<details>
<summary>📋 Walkthrough</summary>

What this workflow does...

</details>

---
🤖 Generated by AI Quality Gate • [Run Details](link)
```

---

## Skill-CI-Research-002: Research Platform Before Implementation (92%)

**Statement**: Before implementing CI/CD features, read platform documentation for known limitations, authentication behaviors, and compatibility requirements

**Context**: Starting GitHub Actions, Azure Pipelines, or similar work

**Trigger**: Any new CI/CD workflow, GitHub Action, or build script

**Evidence**: Session 03-07 (2025-12-18): All these issues were documented behaviors that could have been researched:
- Matrix output limitation (GitHub Community Discussion #17245)
- GH_TOKEN auto-authentication (GitHub CLI docs)
- grep lookbehind requirements (GNU grep documentation)
- YAML heredoc parsing rules (YAML spec)

**Atomicity**: 92%

**Impact**: 9/10 - Prevents debugging sessions

**Tag**: helpful

**Created**: 2025-12-18

**Pre-Implementation Research Checklist**:

| Platform | Key Documentation |
|----------|-------------------|
| GitHub Actions | [Contexts](https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/accessing-contextual-information-about-workflow-runs), [Outputs](https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/passing-information-between-jobs), [Matrix](https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/running-variations-of-jobs-in-a-workflow) |
| GitHub CLI | [Authentication](https://cli.github.com/manual/gh_auth) |
| Shell | Regex compatibility (grep vs sed vs awk) |
| YAML | Heredoc/multi-line string handling |

**Known Limitations to Research**:

1. **Matrix outputs**: Only ONE leg's outputs exposed to downstream jobs - use artifacts
2. **GH_TOKEN**: Auto-authenticates when env var set - don't call `gh auth login`
3. **Lookbehinds**: GNU grep requires fixed-length - use sed for variable patterns
4. **YAML heredocs**: Zero-indent lines parsed as YAML keys - use consistent indentation

---

## Skill-CI-PathsFilter-001: dorny/paths-filter Checkout Requirement (98%)

**Statement**: dorny/paths-filter requires checkout step in ALL jobs, not just the job using the filter

**Context**: GitHub Actions workflows using dorny/paths-filter for conditional job execution

**Trigger**: Using dorny/paths-filter to skip jobs based on file changes

**Evidence**: PR #121 in rjmurillo/ai-agents (2025-12-20): rjmurillo corrected Claude's assumption that only the filter-using job needed checkout. The filter compares HEAD against base branch, requiring git history in all consuming jobs.

**Atomicity**: 98%

**Impact**: Critical - Jobs fail silently or return incorrect results without checkout

**Tag**: helpful

**Created**: 2025-12-20

**Pattern**:

```yaml
# WRONG: Checkout only in filter job
check-changes:
  runs-on: ubuntu-latest
  outputs:
    relevant: ${{ steps.filter.outputs.relevant }}
  steps:
    - uses: actions/checkout@v4  # ✓ Has checkout
    - uses: dorny/paths-filter@v3
      id: filter
      with:
        filters: |
          relevant:
            - 'src/**'

# Consuming job WITHOUT checkout - will fail or return wrong results
build:
  needs: check-changes
  if: needs.check-changes.outputs.relevant == 'true'
  runs-on: ubuntu-latest
  steps:
    # Missing checkout! Will have empty working directory
    - run: npm install  # Fails: no package.json
```

```yaml
# RIGHT: Checkout in ALL jobs that need repo context
check-changes:
  runs-on: ubuntu-latest
  outputs:
    relevant: ${{ steps.filter.outputs.relevant }}
  steps:
    - uses: actions/checkout@v4
    - uses: dorny/paths-filter@v3
      id: filter
      with:
        filters: |
          relevant:
            - 'src/**'

build:
  needs: check-changes
  if: needs.check-changes.outputs.relevant == 'true'
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4  # ✓ Required even though filter ran in previous job
    - run: npm install
```

**Why this matters**: The filter action examines git history to determine what files changed. Downstream jobs that use the filter outputs still need the repository files to do their actual work. Each job starts with an empty workspace.

**Related**: Skill-CI-Matrix-Output-001 (data passing between jobs)

---

## Related Files

- Test Runner: `build/scripts/Invoke-PesterTests.ps1`
- Pester Workflow: `.github/workflows/pester-tests.yml`
- Copilot Setup: `.github/workflows/copilot-setup-steps.yml`
- AI Review Action: `.github/actions/ai-review/action.yml`
- AI Quality Gate: `.github/workflows/ai-pr-quality-gate.yml`
- Retrospective: `.agents/retrospective/2025-12-17-ci-test-failures-xml-corruption.md`
- Session 03: `.agents/sessions/2025-12-18-session-03-ai-workflow-implementation.md`
- Session 04: `.agents/sessions/2025-12-18-session-04-ai-workflow-debugging.md`
- Session 07: `.agents/sessions/2025-12-18-session-07-qa-output-debug.md`
- Session 08: `.agents/sessions/2025-12-18-session-08-vibrant-comments.md`
- Session 38 Retrospective: `.agents/retrospective/2025-12-20-session-38-comprehensive.md`
- Source: `.agents/retrospective/pr-feedback-remediation.md`
