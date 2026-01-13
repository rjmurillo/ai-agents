# Analysis: Install Script CI Workflow Requirements

## 1. Objective and Scope

**Objective**: Research requirements for creating a GitHub Actions workflow to verify the PowerShell install script (`scripts/install.ps1`) works correctly on Windows, macOS, and Linux.

**Scope**:

- CLI installation methods for Claude Code, GitHub Copilot CLI, and VS Code
- Verification commands for each CLI
- GitHub Actions runner capabilities and preinstalled software
- Authentication requirements and blockers
- Recommended workflow structure

**Out of Scope**:

- Actual workflow implementation
- Full end-to-end integration tests requiring API access

## 2. Context

The ai-agents repository provides a unified PowerShell installer that installs agent definitions to three environments:

| Environment | Global Path | Repo Path |
|-------------|-------------|-----------|
| Claude Code | `$HOME/.claude/agents` | `.claude/agents` |
| GitHub Copilot CLI | `$HOME/.copilot/agents` | `.github/agents` |
| VS Code | `$env:APPDATA/Code/User/prompts` | `.github/agents` |

The install script supports:

- Interactive and non-interactive modes
- Remote execution via `iex` (Invoke-Expression)
- Local execution with explicit parameters
- Force overwrite and version selection

Existing Pester tests (`scripts/tests/install.Tests.ps1` and `scripts/tests/Install-Common.Tests.ps1`) validate script structure and module functions but do not test actual cross-platform installation.

## 3. Approach

**Methodology**:

1. Web search for current CLI installation documentation
2. Review GitHub Actions runner-images for preinstalled software
3. Analyze existing repository workflow patterns
4. Investigate authentication requirements for headless verification

**Tools Used**:

- WebSearch/WebFetch for CLI documentation
- GitHub runner-images repository analysis
- Code review of existing install.ps1 and test files
- Repository workflow pattern analysis

**Limitations**:

- Cannot verify actual CLI authentication behavior without live testing
- Runner image documentation may not reflect latest updates

## 4. Data and Analysis

### Evidence Gathered

| Finding | Source | Confidence |
|---------|--------|------------|
| Claude Code installs via npm or native binary | [Anthropic docs](https://code.claude.com/docs/en/setup) | High |
| Claude Code requires Node.js 18+ | [npm package](https://www.npmjs.com/package/@anthropic-ai/claude-code) | High |
| gh-copilot extension deprecated Oct 2025 | [GitHub Changelog](https://github.blog/changelog/2025-09-25-upcoming-deprecation-of-gh-copilot-cli-extension/) | High |
| New Copilot CLI requires paid subscription | [GitHub Docs](https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli) | High |
| VS Code NOT preinstalled on runners | [runner-images](https://github.com/actions/runner-images) | High |
| PowerShell Core preinstalled all runners | runner-images documentation | High |
| Claude Code headless auth has known issues | [Issue #7100](https://github.com/anthropics/claude-code/issues/7100) | High |
| Copilot CLI GH_TOKEN auth has issues | [Discussion #167158](https://github.com/orgs/community/discussions/167158) | Medium |

### Facts (Verified)

1. **PowerShell Availability**: PowerShell Core (pwsh) is preinstalled on all GitHub-hosted runners (Windows, macOS, Linux).

2. **VS Code Not Preinstalled**: Visual Studio Code and the `code` CLI command are NOT preinstalled on any GitHub-hosted runner (Ubuntu, Windows, macOS). Installation would add significant workflow time.

3. **Claude Code Installation**:
   - Native binary: `curl -fsSL https://claude.ai/install.sh | bash` (macOS/Linux)
   - npm: `npm install -g @anthropic-ai/claude-code` (all platforms)
   - Requires Node.js 18+
   - Verification: `claude --version`, `claude doctor`

4. **GitHub Copilot CLI Installation** (new CLI, replaces deprecated gh-copilot):
   - Windows: `winget install GitHub.Copilot`
   - macOS/Linux: `brew install copilot-cli` or `npm install -g @github/copilot`
   - Install script: `curl -fsSL https://gh.io/copilot-install | bash`
   - Requires active paid Copilot subscription

5. **Authentication Blockers**:
   - Claude Code: `ANTHROPIC_API_KEY` environment variable required for actual CLI operations. Installation verification (`claude --version`) works without auth.
   - Copilot CLI: Requires GitHub PAT with "Copilot Requests" permission AND active Copilot subscription. Default `GITHUB_TOKEN` does NOT work.
   - VS Code: No CLI auth needed for file-based verification.

### Hypotheses (Unverified)

1. Claude Code `claude --version` command may prompt for login on first run, blocking CI.
2. Copilot CLI installation without subscription may fail silently or produce warnings.

## 5. Results

### CLI Installation Commands by Platform

#### Claude Code CLI

| Platform | Installation Command | Verification |
|----------|---------------------|--------------|
| Windows | `npm install -g @anthropic-ai/claude-code` | `claude --version` |
| macOS | `curl -fsSL https://claude.ai/install.sh \| bash` | `claude --version` |
| Linux | `curl -fsSL https://claude.ai/install.sh \| bash` | `claude --version` |

**Prerequisites**: Node.js 18+ (npm method) or none (native binary method)

#### GitHub Copilot CLI

| Platform | Installation Command | Verification |
|----------|---------------------|--------------|
| Windows | `winget install GitHub.Copilot` | `copilot --version` |
| macOS | `brew install copilot-cli` | `copilot --version` |
| Linux | `curl -fsSL https://gh.io/copilot-install \| bash` | `copilot --version` |

**Prerequisites**: Active GitHub Copilot paid subscription, GitHub authentication

#### VS Code CLI

| Platform | Installation Command | Verification |
|----------|---------------------|--------------|
| All | Not preinstalled, requires full VS Code install | `code --version` |

**Impact**: VS Code installation adds 1-3 minutes per platform. Not recommended for CI.

### GitHub Actions Runner Preinstalled Software (Relevant)

| Software | Windows | macOS | Ubuntu |
|----------|---------|-------|--------|
| PowerShell Core | 7.4+ | 7.4+ | 7.4+ |
| Node.js | 18/20/22 | 18/20/22 | 18/20/22 |
| npm | Yes | Yes | Yes |
| Git | Yes | Yes | Yes |
| VS Code | No | No | No |
| Claude Code CLI | No | No | No |
| Copilot CLI | No | No | No |

### Verification Strategy Options

| Option | Description | Auth Required | Feasibility |
|--------|-------------|---------------|-------------|
| **File-only** | Verify files created in correct locations | No | High |
| **CLI install** | Install CLI, verify with `--version` | Partial | Medium |
| **Full e2e** | Install CLI + authenticate + verify agents loaded | Yes | Low |

## 6. Discussion

### Recommended Approach: File-Based Verification

Given authentication blockers, the most practical CI workflow should focus on:

1. **Script Execution**: Run `install.ps1` with explicit parameters (non-interactive)
2. **File Verification**: Verify expected files exist in target directories
3. **Content Validation**: Check file content matches source
4. **Exit Code Check**: Verify script exits cleanly (exit code 0)

This approach tests 90% of the script functionality without requiring CLI authentication.

### Authentication Complexity

| CLI | Auth Blocker | Workaround |
|-----|--------------|------------|
| Claude Code | API key + possible login prompt | Skip CLI verification, file-only |
| Copilot CLI | Paid subscription + PAT with special permission | Skip CLI verification, file-only |
| VS Code | None (file-based) | Full verification possible if VS Code installed |

### Cost/Time Considerations

| Runner | Cost (per minute) | Estimated Time |
|--------|-------------------|----------------|
| ubuntu-latest | $0.008 | 1-2 min |
| windows-latest | $0.016 | 2-3 min |
| macos-latest | $0.08 | 2-3 min |

**Total estimated cost per run**: $0.15-0.25 for matrix across all 3 platforms.

### Workflow Design Recommendation

**Single workflow with matrix strategy** (preferred):

- Pros: Single YAML file, consistent test logic, parallel execution
- Cons: Longer total wall-clock time (but parallel reduces actual wait)

```yaml
strategy:
  matrix:
    os: [ubuntu-latest, windows-latest, macos-latest]
    environment: [Claude, Copilot, VSCode]
```

**Separate workflows per OS** (not recommended):

- Pros: Independent failure isolation
- Cons: 3x YAML maintenance, harder to ensure consistency

## 7. Recommendations

| Priority | Recommendation | Rationale | Effort |
|----------|----------------|-----------|--------|
| P0 | Implement file-based verification only | No auth blockers, tests actual installer behavior | Low |
| P1 | Add matrix strategy (3 OS x 3 env) | Comprehensive cross-platform coverage | Low |
| P2 | Skip CLI verification in initial release | Auth complexity blocks full e2e testing | N/A |
| P3 | Add optional CLI verification with secrets | Future enhancement when auth is available | Medium |

### Proposed Workflow Structure

```yaml
name: Install Script Verification

on:
  push:
    paths:
      - 'scripts/install.ps1'
      - 'scripts/lib/**'
  pull_request:
    paths:
      - 'scripts/install.ps1'
      - 'scripts/lib/**'

jobs:
  test-install:
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        environment: [Claude, Copilot, VSCode]
        scope: [Global, Repo]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - name: Run Install Script
        shell: pwsh
        run: |
          ./scripts/install.ps1 `
            -Environment ${{ matrix.environment }} `
            -${{ matrix.scope == 'Global' && 'Global' || 'RepoPath .' }} `
            -Force
      - name: Verify Installation
        shell: pwsh
        run: |
          # Verify files exist in expected locations
          # (PowerShell script to check paths based on environment/scope)
```

### Acceptance Criteria for GitHub Issue

1. [MUST] Workflow runs on push/PR when `scripts/install.ps1` or `scripts/lib/**` change
2. [MUST] Tests all 3 environments (Claude, Copilot, VSCode)
3. [MUST] Tests both Global and Repo scopes
4. [MUST] Runs on Windows, macOS, and Linux runners
5. [MUST] Verifies correct files created in expected directories
6. [MUST] Reports clear pass/fail status for each matrix combination
7. [SHOULD] Use paths-filter to skip when no relevant files changed
8. [SHOULD] Follow existing pester-tests.yml patterns for consistency
9. [SHOULD NOT] Require API keys or authentication secrets
10. [WILL NOT] Verify CLI loads agents (auth blocker)

## 8. Conclusion

**Verdict**: Proceed with file-based verification workflow

**Confidence**: High

**Rationale**: File-based verification tests the core installer functionality without authentication blockers. CLI verification is blocked by API key requirements (Claude Code) and paid subscription requirements (Copilot CLI).

### User Impact

- **What changes for you**: New CI workflow validates installer works cross-platform before merge
- **Effort required**: 4-8 hours to implement and test workflow
- **Risk if ignored**: Installer bugs on non-Windows platforms go undetected

## 9. Appendices

### Sources Consulted

- [Set up Claude Code - Claude Code Docs](https://code.claude.com/docs/en/setup)
- [@anthropic-ai/claude-code - npm](https://www.npmjs.com/package/@anthropic-ai/claude-code)
- [Installing GitHub Copilot CLI - GitHub Docs](https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli)
- [Upcoming deprecation of gh-copilot CLI extension - GitHub Changelog](https://github.blog/changelog/2025-09-25-upcoming-deprecation-of-gh-copilot-cli-extension/)
- [GitHub-hosted runners - GitHub Docs](https://docs.github.com/actions/using-github-hosted-runners/about-github-hosted-runners)
- [actions/runner-images - GitHub](https://github.com/actions/runner-images)
- [Run Claude Code programmatically - Claude Code Docs](https://code.claude.com/docs/en/headless)
- [Claude Code headless auth issue #7100](https://github.com/anthropics/claude-code/issues/7100)
- [Copilot CLI GH_TOKEN discussion #167158](https://github.com/orgs/community/discussions/167158)

### Data Transparency

- **Found**: Installation commands, runner preinstalled software, auth requirements
- **Not Found**: Exact behavior of CLI version commands in headless CI (requires live testing)

### Related Files in Repository

- `/home/richard/src/GitHub/rjmurillo/ai-agents2/scripts/install.ps1` - Main installer
- `/home/richard/src/GitHub/rjmurillo/ai-agents2/scripts/lib/Install-Common.psm1` - Shared module
- `/home/richard/src/GitHub/rjmurillo/ai-agents2/scripts/lib/Config.psd1` - Configuration data
- `/home/richard/src/GitHub/rjmurillo/ai-agents2/scripts/tests/install.Tests.ps1` - Existing tests
- `/home/richard/src/GitHub/rjmurillo/ai-agents2/.github/workflows/pester-tests.yml` - Reference workflow pattern
