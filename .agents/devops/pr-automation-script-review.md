# DevOps Review: PR Automation Script

**Script**: `scripts/Invoke-PRMaintenance.ps1`
**Reviewer**: DevOps Agent
**Date**: 2025-12-22
**Status**: 🟢 READY FOR OPERATIONALIZATION

## Executive Summary

The PR maintenance script is production-ready with minor operational enhancements needed. The script demonstrates solid error handling, logging, and dry-run capability. This review provides operationalization strategy for hourly automated runs via GitHub Actions.

| Metric | Current State | Target | Gap |
|--------|---------------|--------|-----|
| **Runtime** | Unknown (no baseline) | <2min for 20 PRs | Needs instrumentation |
| **Error Handling** | Comprehensive | Production-grade | ✅ Met |
| **Logging** | File-based | Centralized + file | Enhancement needed |
| **Monitoring** | None | Failure alerts | Critical gap |
| **Concurrency** | No protection | Mutex/lock | High priority |
| **Resource Cleanup** | Partial | Full idempotency | Medium priority |

## 1. Scheduling Strategy

### Recommended Approach: GitHub Actions Scheduled Workflow

**Rationale**: Native integration with GitHub ecosystem, no external infrastructure, built-in secret management.

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| **GitHub Actions cron** | Native secrets, no infra, audit trail | 1hr min resolution | ✅ **RECOMMENDED** |
| Windows Task Scheduler | Precise timing | Requires hosted runner, Windows-only | ❌ Not portable |
| systemd timer | Linux-native | Requires self-hosted runner | ❌ Complexity |

**Implementation**: `.github/workflows/pr-maintenance.yml`

```yaml
on:
  schedule:
    - cron: '0 * * * *'  # Hourly at minute 0
  workflow_dispatch:     # Manual trigger for testing
```

**Timing Considerations**:

- GitHub Actions cron runs on UTC (not repository timezone)
- Minimum resolution: 1 hour
- Actual execution may lag 3-10 minutes (queue delays)
- For faster response, consider `pull_request` trigger with filters

## 2. CI/CD Integration

### GitHub Actions Workflow Design

**Architecture**: Thin workflow orchestrator + testable PowerShell module

```text
Workflow (YAML)
  |
  ├─ Pre-flight checks (gh CLI, git, pwsh version)
  ├─ Call Invoke-PRMaintenance.ps1
  ├─ Parse results (exit code + JSON output)
  ├─ Post summary comment (if blocked PRs)
  └─ Upload logs as artifact
```

**Workflow Requirements**:

| Requirement | Implementation | Validation |
|-------------|----------------|------------|
| GitHub token | `${{ secrets.GITHUB_TOKEN }}` | Scopes: `repo`, `workflow` |
| PowerShell Core | `ubuntu-latest` (pwsh 7.4+) | `pwsh --version` |
| gh CLI | Pre-installed on runners | `gh --version` |
| Git | Pre-installed | `git --version` |

### Workflow Metrics Targets

| Stage | Target | Maximum | Monitoring |
|-------|--------|---------|------------|
| Checkout | <5s | 10s | `actions/checkout` metrics |
| Pre-flight | <10s | 20s | Command timing |
| Script execution | <90s | 180s | Exit before 3min timeout |
| Log upload | <5s | 10s | Artifact size <1MB |
| **Total** | **<2min** | **3min** | Fail if >3min |

## 3. Monitoring and Alerting

### Current State: [FAIL] No Monitoring

**Critical Gaps**:

- No visibility into script failures
- No alerts for blocked PRs
- No performance metrics
- No API rate limit tracking

### Recommended Monitoring

#### GitHub Actions Workflow Status

**Built-in Monitoring** (Free):

- Workflow run history (GitHub UI)
- Email notifications on failure (repo settings)
- Status badge in README

```markdown
![PR Maintenance](https://github.com/OWNER/REPO/actions/workflows/pr-maintenance.yml/badge.svg)
```

**Alerting**:

```yaml
# In workflow
- name: Notify on failure
  if: failure()
  uses: actions/github-script@v7
  with:
    script: |
      github.rest.issues.create({
        owner: context.repo.owner,
        repo: context.repo.repo,
        title: '[ALERT] PR Maintenance Failed',
        body: 'Workflow run: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}',
        labels: ['automation', 'P1']
      })
```

#### Script-Level Metrics

**Instrument Script** (add to summary):

```powershell
# Export metrics as JSON
$metrics = @{
    Duration = $duration.TotalSeconds
    PRsProcessed = $results.Processed
    CommentsAcknowledged = $results.CommentsAcknowledged
    ConflictsResolved = $results.ConflictsResolved
    BlockedPRs = $results.Blocked.Count
    Errors = $results.Errors.Count
    Timestamp = Get-Date -Format 'o'
}

$metrics | ConvertTo-Json | Out-File '.agents/logs/pr-maintenance-metrics.json'
```

**Workflow parses metrics**:

```yaml
- name: Parse metrics
  id: metrics
  shell: pwsh
  run: |
    $metrics = Get-Content .agents/logs/pr-maintenance-metrics.json | ConvertFrom-Json
    echo "duration=$($metrics.Duration)" >> $GITHUB_OUTPUT
    echo "blocked_prs=$($metrics.BlockedPRs)" >> $GITHUB_OUTPUT

- name: Post summary
  run: |
    echo "## PR Maintenance Summary" >> $GITHUB_STEP_SUMMARY
    echo "- Duration: ${{ steps.metrics.outputs.duration }}s" >> $GITHUB_STEP_SUMMARY
    echo "- Blocked PRs: ${{ steps.metrics.outputs.blocked_prs }}" >> $GITHUB_STEP_SUMMARY
```

#### API Rate Limit Monitoring

**Risk**: Script calls GitHub API extensively (20 PRs × N comments/PR).

**Mitigation**:

```yaml
- name: Check rate limit
  run: |
    REMAINING=$(gh api rate_limit --jq '.rate.remaining')
    if [ $REMAINING -lt 100 ]; then
      echo "::warning::GitHub API rate limit low: $REMAINING remaining"
    fi
```

**Limits**:

- GitHub Actions: 1000 requests/hour/repository
- GITHUB_TOKEN: Shared across all workflows

## 4. Logging and Observability

### Current State: [WARN] File-Based Logging

**Strengths**:

- Structured log format (timestamp, level, message)
- Color-coded console output
- Append-mode log file

**Gaps**:

- Log file grows unbounded
- No log rotation
- No centralized aggregation
- Difficult to query/analyze

### Enhanced Logging Strategy

#### Structured Logging (PowerShell)

**Current Format**:

```text
[2025-12-22 10:00:00] [INFO] Starting PR maintenance run
```

**Enhanced Format** (JSON):

```powershell
function Write-StructuredLog {
    param(
        [string]$Message,
        [string]$Level = 'INFO',
        [hashtable]$Context = @{}
    )

    $entry = @{
        timestamp = Get-Date -Format 'o'
        level = $Level
        message = $Message
        context = $Context
    } | ConvertTo-Json -Compress

    Add-Content -Path $LogPath -Value $entry
    Write-Host "[$Level] $Message"
}

# Usage
Write-StructuredLog -Message "Processing PR" -Level INFO -Context @{
    pr = $pr.number
    title = $pr.title
    mergeable = $pr.mergeable
}
```

**Benefits**:

- Queryable with `jq`
- Import to log analysis tools
- Correlation via context fields

#### Log Rotation

**Problem**: Unbounded log growth.

**Solution**: Rotate daily + keep 30 days.

```powershell
function Get-RotatedLogPath {
    $date = Get-Date -Format 'yyyy-MM-dd'
    $logDir = Join-Path $PSScriptRoot '..' '.agents' 'logs'
    return Join-Path $logDir "pr-maintenance-$date.log"
}

# Cleanup old logs (keep 30 days)
Get-ChildItem $logDir -Filter "pr-maintenance-*.log" |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
    Remove-Item
```

#### GitHub Actions Job Summary

**Current**: Logs buried in workflow output.

**Enhanced**: Post summary to `$GITHUB_STEP_SUMMARY`.

```yaml
- name: Generate summary
  shell: pwsh
  run: |
    $summary = @"
    ## PR Maintenance Run - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')

    | Metric | Value |
    |--------|-------|
    | PRs Processed | $env:PROCESSED |
    | Comments Acknowledged | $env:ACKNOWLEDGED |
    | Conflicts Resolved | $env:RESOLVED |
    | PRs Closed | $env:CLOSED |
    | Blocked PRs | $env:BLOCKED |

    ### Blocked PRs
    $env:BLOCKED_LIST
    "@

    $summary >> $env:GITHUB_STEP_SUMMARY
```

## 5. Configuration Management

### Current State: [WARN] Hardcoded Configuration

**Hardcoded Values**:

```powershell
$script:Config = @{
    ProtectedBranches = @('main', 'master', 'develop')
    BotAuthors = @('Copilot', 'coderabbitai[bot]', 'gemini-code-assist[bot]', 'cursor[bot]')
    AcknowledgeReaction = 'eyes'
    WorktreeBasePath = '..'
    CIWaitTimeout = 300
}
```

**Gaps**:

- No environment-specific config (dev/staging/prod)
- No override mechanism
- Bot list will grow stale

### Recommended Configuration Strategy

#### Option 1: Environment Variables (Preferred for CI)

```powershell
# Read from env vars with defaults
$script:Config = @{
    ProtectedBranches = ($env:PR_PROTECTED_BRANCHES -split ',' -replace '^\s+|\s+$', '') ?? @('main', 'master')
    BotAuthors = ($env:PR_BOT_AUTHORS -split ',' -replace '^\s+|\s+$', '') ?? @('Copilot', 'coderabbitai[bot]')
    AcknowledgeReaction = $env:PR_ACK_REACTION ?? 'eyes'
    WorktreeBasePath = $env:PR_WORKTREE_PATH ?? '..'
    MaxPRs = [int]($env:PR_MAX_PRS ?? 20)
}
```

**Workflow configuration**:

```yaml
env:
  PR_PROTECTED_BRANCHES: "main,develop"
  PR_BOT_AUTHORS: "Copilot,coderabbitai[bot],gemini-code-assist[bot],cursor[bot]"
  PR_ACK_REACTION: "eyes"
  PR_MAX_PRS: "20"
```

#### Option 2: Config File (Better for complex settings)

**File**: `.agents/config/pr-maintenance.json`

```json
{
  "protectedBranches": ["main", "master", "develop"],
  "botAuthors": [
    "Copilot",
    "coderabbitai[bot]",
    "gemini-code-assist[bot]",
    "cursor[bot]"
  ],
  "acknowledgeReaction": "eyes",
  "worktreeBasePath": "..",
  "maxPRs": 20,
  "ciWaitTimeout": 300
}
```

**Load in script**:

```powershell
$configPath = Join-Path $PSScriptRoot '..' '.agents' 'config' 'pr-maintenance.json'
$script:Config = Get-Content $configPath | ConvertFrom-Json -AsHashtable
```

**Verdict**: Use **environment variables** for CI/CD flexibility, **config file** for local development.

## 6. Secrets Management

### Current State: [PASS] Uses GitHub CLI Authentication

**Security Analysis**:

| Aspect | Status | Evidence |
|--------|--------|----------|
| **Token storage** | ✅ SECURE | Uses `gh` CLI (auto-authenticated via `GH_TOKEN` env) |
| **Token scopes** | ✅ MINIMAL | `repo` scope only (via `GITHUB_TOKEN`) |
| **Token rotation** | ✅ AUTOMATIC | `GITHUB_TOKEN` rotates per workflow run |
| **Credential leak** | ✅ PROTECTED | No token in logs/output |

**How It Works**:

1. GitHub Actions sets `GITHUB_TOKEN` environment variable
2. `gh` CLI auto-authenticates when `GH_TOKEN` present
3. Script calls `gh` commands (no explicit auth)
4. Token expires after workflow run

**No Changes Needed**: Current approach follows security best practices.

### Best Practices Applied

| Practice | Implementation | Validation |
|----------|----------------|------------|
| Least privilege | `GITHUB_TOKEN` (repo scope only) | ✅ Built-in |
| No hardcoded secrets | Uses env var | ✅ Verified |
| Automatic rotation | Per-run token | ✅ GitHub Actions default |
| Audit trail | Workflow logs | ✅ Immutable |

### Additional Hardening (Optional)

**Restrict token permissions** (workflow-level):

```yaml
permissions:
  contents: read       # Checkout code
  pull-requests: write # Manage PRs
  issues: write        # Post alerts
```

**Benefit**: Reduces blast radius if token compromised.

## 7. Runner Requirements

### Environment Specification

| Requirement | Version | Validation Command |
|-------------|---------|-------------------|
| **OS** | Ubuntu 22.04+ | `lsb_release -a` |
| **PowerShell Core** | 7.4+ | `pwsh --version` |
| **gh CLI** | 2.40+ | `gh --version` |
| **Git** | 2.39+ | `git --version` |

**Recommended Runner**: `ubuntu-latest` (GitHub-hosted)

```yaml
jobs:
  pr-maintenance:
    runs-on: ubuntu-latest  # Free, fast, pwsh 7.4 pre-installed
```

### Pre-flight Checks

**Add to workflow**:

```yaml
- name: Validate environment
  run: |
    echo "Validating runner environment..."

    # PowerShell version
    PWSH_VERSION=$(pwsh --version | grep -oP '\d+\.\d+')
    if (( $(echo "$PWSH_VERSION < 7.4" | bc -l) )); then
      echo "::error::PowerShell $PWSH_VERSION < 7.4 (required)"
      exit 1
    fi
    echo "[PASS] PowerShell $PWSH_VERSION"

    # gh CLI version
    GH_VERSION=$(gh --version | head -1 | grep -oP '\d+\.\d+\.\d+')
    echo "[PASS] gh CLI $GH_VERSION"

    # Git version
    GIT_VERSION=$(git --version | grep -oP '\d+\.\d+')
    echo "[PASS] git $GIT_VERSION"
```

### Resource Limits

**Current State**: No limits defined.

| Resource | Expected Usage | Limit | Monitoring |
|----------|---------------|-------|------------|
| **Memory** | <256MB | 1GB | Workflow timeout |
| **Disk** | <100MB (worktrees) | 500MB | Cleanup enforcement |
| **CPU** | <10% (I/O bound) | N/A | Runtime duration |
| **Network** | 20 PRs × 5 API calls = 100 requests | 1000/hr | Rate limit check |

**Disk Cleanup**:

```yaml
- name: Cleanup worktrees
  if: always()
  run: |
    # Remove all worktrees (safety net)
    git worktree list --porcelain | grep '^worktree' | cut -d' ' -f2 |
      grep -E 'ai-agents-pr-[0-9]+' |
      xargs -I {} git worktree remove {} --force || true
```

## 8. Failure Recovery

### Current State: [WARN] Partial Recovery

**Implemented**:

- ✅ Try-catch blocks around PR processing
- ✅ Worktree cleanup in `finally` block
- ✅ Continue on PR-level errors
- ✅ Exit codes (0/1/2)

**Gaps**:

- ❌ Worktree cleanup may fail if script crashes
- ❌ No retry logic for transient errors
- ❌ No circuit breaker for API failures

### Enhanced Recovery Strategy

#### Idempotency

**Current**: Script can be re-run safely (acknowledgments use reactions, conflicts use git merge).

**Enhancement**: Track processed PRs to avoid duplicate work.

```powershell
# State file: .agents/logs/pr-maintenance-state.json
$stateFile = '.agents/logs/pr-maintenance-state.json'
$state = if (Test-Path $stateFile) {
    Get-Content $stateFile | ConvertFrom-Json -AsHashtable
} else {
    @{ ProcessedPRs = @{} }
}

# Skip recently processed PRs (within 1 hour)
foreach ($pr in $prs) {
    $lastProcessed = $state.ProcessedPRs[$pr.number]
    if ($lastProcessed -and ((Get-Date) - [datetime]$lastProcessed).TotalHours -lt 1) {
        Write-Log "Skipping PR #$($pr.number) (processed $lastProcessed)" -Level INFO
        continue
    }

    # Process PR...

    # Update state
    $state.ProcessedPRs[$pr.number] = Get-Date -Format 'o'
}

# Save state
$state | ConvertTo-Json | Out-File $stateFile
```

#### Retry Logic for Transient Failures

**Pattern**: Exponential backoff for API calls.

```powershell
function Invoke-WithRetry {
    param(
        [ScriptBlock]$Action,
        [int]$MaxRetries = 3,
        [int]$InitialDelay = 1
    )

    $attempt = 0
    while ($attempt -lt $MaxRetries) {
        try {
            return & $Action
        }
        catch {
            $attempt++
            if ($attempt -ge $MaxRetries) { throw }

            $delay = $InitialDelay * [Math]::Pow(2, $attempt - 1)
            Write-Log "Retry $attempt/$MaxRetries after ${delay}s: $_" -Level WARN
            Start-Sleep -Seconds $delay
        }
    }
}

# Usage
$comments = Invoke-WithRetry {
    Get-PRComments -Owner $Owner -Repo $Repo -PRNumber $pr.number
}
```

#### Worktree Cleanup Enforcement

**Problem**: If script crashes, worktrees persist.

**Solution**: Cleanup script + workflow step.

```powershell
# scripts/Cleanup-Worktrees.ps1
git worktree list --porcelain |
    Select-String -Pattern '^worktree (.+ai-agents-pr-\d+)' |
    ForEach-Object { $_.Matches.Groups[1].Value } |
    ForEach-Object {
        Write-Host "Removing stale worktree: $_"
        git worktree remove $_ --force
    }
```

**Workflow**:

```yaml
- name: Cleanup stale worktrees
  if: always()
  shell: pwsh
  run: ./scripts/Cleanup-Worktrees.ps1
```

#### Circuit Breaker for API Failures

**Pattern**: Stop processing if error rate exceeds threshold.

```powershell
$errorRate = $results.Errors.Count / [Math]::Max($results.Processed, 1)
if ($errorRate -gt 0.5) {
    Write-Log "ERROR: High error rate ($errorRate) - stopping" -Level ERROR
    throw "Circuit breaker triggered: $($results.Errors.Count) errors in $($results.Processed) PRs"
}
```

## 9. Concurrency Control

### Current State: [FAIL] No Concurrency Protection

**Risk**: Two workflow runs execute simultaneously.

**Scenario**:

1. Hourly workflow starts at 10:00
2. Manual `workflow_dispatch` triggered at 10:01
3. Both runs process same PRs
4. Duplicate reactions, conflicting worktrees, race conditions

**Impact**: High (worktree conflicts, duplicate work, API rate limit exhaustion)

### Recommended Concurrency Strategy

#### GitHub Actions Concurrency Groups

**Implementation**:

```yaml
concurrency:
  group: pr-maintenance
  cancel-in-progress: false  # Queue new runs, don't cancel
```

**Behavior**:

- Only one `pr-maintenance` workflow runs at a time
- Subsequent runs queue (wait for previous to complete)
- No cancellation (preserve work)

**Alternative** (Cancel previous runs):

```yaml
concurrency:
  group: pr-maintenance
  cancel-in-progress: true  # Cancel old runs
```

**Verdict**: Use `cancel-in-progress: false` to preserve work.

#### File-Based Lock (Defense in Depth)

**Script-level lock**:

```powershell
$lockFile = '.agents/logs/pr-maintenance.lock'

# Acquire lock
if (Test-Path $lockFile) {
    $lockAge = (Get-Date) - (Get-Item $lockFile).LastWriteTime
    if ($lockAge.TotalMinutes -lt 10) {
        Write-Log "Another instance is running (lock file age: $($lockAge.TotalMinutes)m)" -Level WARN
        exit 0
    }
    else {
        Write-Log "Stale lock file detected (age: $($lockAge.TotalMinutes)m) - removing" -Level WARN
        Remove-Item $lockFile -Force
    }
}

New-Item $lockFile -ItemType File -Force | Out-Null
Write-Log "Lock acquired: $lockFile" -Level INFO

try {
    # Run maintenance...
}
finally {
    Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
    Write-Log "Lock released" -Level INFO
}
```

**Stale Lock Timeout**: 10 minutes (2× expected runtime).

## 10. Resource Limits and API Rate Limiting

### API Rate Limit Analysis

**GitHub API Limits**:

- **Primary rate limit**: 1000 requests/hour/repository (GitHub Actions)
- **Secondary limits**: 100 concurrent requests

**Script API Consumption** (per PR):

| Operation | Endpoint | Calls | Notes |
|-----------|----------|-------|-------|
| List PRs | `GET /repos/{owner}/{repo}/pulls` | 1 | Batched (20 PRs) |
| Get PR comments | `GET /repos/{owner}/{repo}/pulls/{pr}/comments` | 1 | Per PR |
| Add reaction | `POST /repos/{owner}/{repo}/pulls/comments/{id}/reactions` | N | Per unacked comment |
| Check mergeable | `gh pr view` | 1 | Per PR |
| Resolve conflicts | `gh` operations | 5-10 | Git operations (no API) |
| Close PR | `gh pr close` + comment | 2 | Per superseded PR |

**Maximum Consumption** (20 PRs, 5 comments/PR, all unacked):

```text
1 (list) + 20 (comments) + 100 (reactions) + 20 (mergeable) + 40 (close 2 PRs) = 181 requests
```

**Safety Margin**: 181 / 1000 = 18% of hourly budget.

**Verdict**: [PASS] Well within limits for hourly runs.

### Rate Limit Monitoring

**Pre-flight check**:

```yaml
- name: Check API rate limit
  id: ratelimit
  run: |
    REMAINING=$(gh api rate_limit --jq '.rate.remaining')
    LIMIT=$(gh api rate_limit --jq '.rate.limit')
    echo "remaining=$REMAINING" >> $GITHUB_OUTPUT
    echo "limit=$LIMIT" >> $GITHUB_OUTPUT

    if [ $REMAINING -lt 200 ]; then
      echo "::error::GitHub API rate limit low: $REMAINING/$LIMIT remaining"
      exit 1
    fi
    echo "[PASS] Rate limit: $REMAINING/$LIMIT"
```

**Post-run reporting**:

```yaml
- name: Report rate limit usage
  if: always()
  run: |
    REMAINING=$(gh api rate_limit --jq '.rate.remaining')
    USED=$((LIMIT - REMAINING))
    echo "API calls used: $USED" >> $GITHUB_STEP_SUMMARY
```

### Disk Space Management

**Risk**: Worktrees consume disk space.

**Mitigation**:

1. **Cleanup in finally block** (already implemented)
2. **Pre-run cleanup** (catch stale worktrees)
3. **Monitor disk usage**

```yaml
- name: Check disk space
  run: |
    AVAILABLE=$(df -h . | tail -1 | awk '{print $4}')
    echo "Disk available: $AVAILABLE"
```

### Memory Limits

**Current**: No explicit limit.

**Expected Usage**: <256MB (PowerShell + git operations).

**Safety**: GitHub Actions runners have 7GB RAM, ample headroom.

## Complete GitHub Actions Workflow

```yaml
name: PR Maintenance

on:
  schedule:
    - cron: '0 * * * *'  # Hourly at minute 0 (UTC)
  workflow_dispatch:     # Manual trigger
    inputs:
      dry_run:
        description: 'Dry run (no changes)'
        type: boolean
        default: false
      max_prs:
        description: 'Max PRs to process'
        type: number
        default: 20

permissions:
  contents: read
  pull-requests: write
  issues: write

concurrency:
  group: pr-maintenance
  cancel-in-progress: false  # Queue runs, don't cancel

env:
  PR_PROTECTED_BRANCHES: "main,master,develop"
  PR_BOT_AUTHORS: "Copilot,coderabbitai[bot],gemini-code-assist[bot],cursor[bot]"
  PR_ACK_REACTION: "eyes"
  PR_MAX_PRS: ${{ inputs.max_prs || 20 }}

jobs:
  pr-maintenance:
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Full history for git operations

      - name: Validate environment
        run: |
          echo "### Environment Validation" >> $GITHUB_STEP_SUMMARY
          echo "" >> $GITHUB_STEP_SUMMARY

          PWSH_VERSION=$(pwsh --version | grep -oP '\d+\.\d+')
          echo "- PowerShell: $PWSH_VERSION" >> $GITHUB_STEP_SUMMARY

          GH_VERSION=$(gh --version | head -1 | grep -oP '\d+\.\d+\.\d+')
          echo "- gh CLI: $GH_VERSION" >> $GITHUB_STEP_SUMMARY

          GIT_VERSION=$(git --version | grep -oP '\d+\.\d+')
          echo "- git: $GIT_VERSION" >> $GITHUB_STEP_SUMMARY

      - name: Check API rate limit
        id: ratelimit
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          REMAINING=$(gh api rate_limit --jq '.rate.remaining')
          LIMIT=$(gh api rate_limit --jq '.rate.limit')
          RESET=$(gh api rate_limit --jq '.rate.reset')

          echo "remaining=$REMAINING" >> $GITHUB_OUTPUT
          echo "limit=$LIMIT" >> $GITHUB_OUTPUT

          echo "### API Rate Limit" >> $GITHUB_STEP_SUMMARY
          echo "- Remaining: $REMAINING / $LIMIT" >> $GITHUB_STEP_SUMMARY
          echo "- Reset: $(date -d @$RESET)" >> $GITHUB_STEP_SUMMARY

          if [ $REMAINING -lt 200 ]; then
            echo "::error::GitHub API rate limit low: $REMAINING/$LIMIT remaining"
            exit 1
          fi

      - name: Cleanup stale worktrees
        run: |
          # Remove stale worktrees from previous runs
          git worktree list --porcelain |
            grep '^worktree' |
            awk '{print $2}' |
            grep -E 'ai-agents-pr-[0-9]+' |
            xargs -I {} git worktree remove {} --force || true

      - name: Run PR maintenance
        id: maintenance
        env:
          GH_TOKEN: ${{ github.token }}
        shell: pwsh
        run: |
          $dryRun = if ('${{ inputs.dry_run }}' -eq 'true') { $true } else { $false }
          $maxPRs = [int]'${{ env.PR_MAX_PRS }}'

          Write-Host "Running PR maintenance (DryRun: $dryRun, MaxPRs: $maxPRs)"

          $params = @{
            MaxPRs = $maxPRs
            LogPath = '.agents/logs/pr-maintenance.log'
          }

          if ($dryRun) {
            $params['DryRun'] = $true
          }

          ./scripts/Invoke-PRMaintenance.ps1 @params

      - name: Parse results
        id: results
        if: always()
        shell: pwsh
        run: |
          # Extract summary from log
          $log = Get-Content .agents/logs/pr-maintenance.log -Raw

          # Parse metrics
          if ($log -match 'PRs Processed: (\d+)') {
            $processed = $Matches[1]
            echo "processed=$processed" >> $env:GITHUB_OUTPUT
          }

          if ($log -match 'Comments Acknowledged: (\d+)') {
            $acknowledged = $Matches[1]
            echo "acknowledged=$acknowledged" >> $env:GITHUB_OUTPUT
          }

          if ($log -match 'Conflicts Resolved: (\d+)') {
            $resolved = $Matches[1]
            echo "resolved=$resolved" >> $env:GITHUB_OUTPUT
          }

          if ($log -match 'PRs Closed \(Superseded\): (\d+)') {
            $closed = $Matches[1]
            echo "closed=$closed" >> $env:GITHUB_OUTPUT
          }

          # Extract blocked PRs
          $blockedSection = $log -split 'Blocked PRs \(require human action\):' | Select-Object -Last 1
          $blockedList = $blockedSection -split '\n' |
            Where-Object { $_ -match 'PR #' } |
            ForEach-Object { $_.Trim() } |
            Out-String

          if ($blockedList) {
            # Save to file (multi-line output)
            $blockedList | Out-File -FilePath blocked-prs.txt
            echo "has_blocked=true" >> $env:GITHUB_OUTPUT
          } else {
            echo "has_blocked=false" >> $env:GITHUB_OUTPUT
          }

      - name: Post summary
        if: always()
        shell: pwsh
        run: |
          $summary = @"
          ## PR Maintenance Summary

          **Run Time**: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss UTC')
          **Dry Run**: ${{ inputs.dry_run }}

          | Metric | Value |
          |--------|-------|
          | PRs Processed | ${{ steps.results.outputs.processed || 'N/A' }} |
          | Comments Acknowledged | ${{ steps.results.outputs.acknowledged || '0' }} |
          | Conflicts Resolved | ${{ steps.results.outputs.resolved || '0' }} |
          | PRs Closed (Superseded) | ${{ steps.results.outputs.closed || '0' }} |

          "@

          if ('${{ steps.results.outputs.has_blocked }}' -eq 'true') {
            $blockedList = Get-Content blocked-prs.txt -Raw
            $summary += @"

          ### Blocked PRs (Require Human Action)

          ``````
          $blockedList
          ``````
          "@
          }

          $summary += @"

          ### Rate Limit After Run

          - Remaining: $(gh api rate_limit --jq '.rate.remaining') / ${{ steps.ratelimit.outputs.limit }}

          ---
          [View Logs](${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }})
          "@

          $summary | Out-File -FilePath $env:GITHUB_STEP_SUMMARY -Append

      - name: Create alert issue for blocked PRs
        if: steps.results.outputs.has_blocked == 'true'
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          BLOCKED_LIST=$(cat blocked-prs.txt)

          gh issue create \
            --title "[PR Maintenance] Blocked PRs Require Human Action" \
            --label "automation,needs-triage" \
            --body "## Blocked PRs

          The automated PR maintenance workflow encountered PRs that require human action:

          \`\`\`
          $BLOCKED_LIST
          \`\`\`

          **Action Required**: Review the listed PRs and address blocking issues.

          **Workflow Run**: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}

          ---
          🤖 Auto-generated by PR Maintenance workflow"

      - name: Cleanup worktrees (final)
        if: always()
        run: |
          git worktree list --porcelain |
            grep '^worktree' |
            awk '{print $2}' |
            grep -E 'ai-agents-pr-[0-9]+' |
            xargs -I {} git worktree remove {} --force || true

      - name: Upload logs
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: pr-maintenance-logs
          path: .agents/logs/pr-maintenance*.log
          retention-days: 30

      - name: Notify on failure
        if: failure()
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          gh issue create \
            --title "[ALERT] PR Maintenance Workflow Failed" \
            --label "automation,P1" \
            --body "## Workflow Failure

          The PR maintenance workflow failed during execution.

          **Run**: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
          **Trigger**: ${{ github.event_name }}
          **Time**: $(date -u)

          **Action Required**: Investigate workflow logs and resolve the issue.

          ---
          🤖 Auto-generated by PR Maintenance workflow"
```

## Deployment Checklist

### Pre-Deployment

- [ ] Create `.agents/config/pr-maintenance.json` (if using config file approach)
- [ ] Test workflow locally with `act` or manual trigger
- [ ] Verify `GITHUB_TOKEN` has required permissions (`repo`, `workflow`)
- [ ] Review cron schedule (adjust for timezone if needed)
- [ ] Set up failure notifications (email, Slack, etc.)

### Deployment

- [ ] Create workflow file: `.github/workflows/pr-maintenance.yml`
- [ ] Commit and push to main branch
- [ ] Trigger manual run via `workflow_dispatch`
- [ ] Verify workflow executes successfully
- [ ] Monitor first hourly run

### Post-Deployment

- [ ] Instrument baseline metrics (runtime, API usage)
- [ ] Monitor for 1 week
- [ ] Adjust `MaxPRs` if needed (based on runtime)
- [ ] Add README badge: `![PR Maintenance](https://github.com/OWNER/REPO/actions/workflows/pr-maintenance.yml/badge.svg)`
- [ ] Document alerting runbook

## Performance Baseline Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Workflow Duration** | <2min (20 PRs) | GitHub Actions metrics |
| **Script Duration** | <90s | Log file timestamp delta |
| **API Calls/Run** | <200 | Rate limit delta |
| **Success Rate** | >95% | Workflow run history |
| **Blocked PR Detection** | 100% | Manual validation |

## Operational Runbook

### Daily Operations

**Monitoring Cadence**: Check once/day (morning)

1. Review GitHub Actions workflow status (green/red)
2. Check for blocked PR alert issues
3. Review logs for errors (`.agents/logs/pr-maintenance.log`)

### Troubleshooting

| Issue | Symptoms | Resolution |
|-------|----------|------------|
| **High failure rate** | Workflow status red | Check logs for API errors, rate limits |
| **Blocked PRs accumulating** | Multiple alert issues | Manual PR review, adjust bot list |
| **Slow execution** | Duration >3min | Reduce `MaxPRs`, investigate API latency |
| **Stale worktrees** | Disk space warnings | Run cleanup script manually |
| **API rate limit** | 429 errors | Reduce frequency, check concurrent workflows |

### Maintenance

**Monthly**:

- Review bot author list (add new bots)
- Check log rotation (ensure <1GB total)
- Validate alert issue creation (test manual trigger)

**Quarterly**:

- Audit workflow permissions (least privilege)
- Review performance metrics (adjust targets)
- Update PowerShell/gh CLI versions

## Security Considerations

| Risk | Mitigation | Status |
|------|------------|--------|
| **Token leak** | Use `GITHUB_TOKEN` (auto-rotated) | ✅ Implemented |
| **Arbitrary code execution** | No user input execution | ✅ Safe |
| **Branch protection bypass** | Check protected branches | ✅ Implemented (line 521) |
| **Malicious PR content** | No dynamic code eval | ✅ Safe |
| **Worktree path traversal** | Validate worktree paths | ⚠️ Add validation |

**Recommendation**: Add worktree path validation:

```powershell
$worktreePath = Join-Path $script:Config.WorktreeBasePath "ai-agents-pr-$PRNumber"

# Validate path is within allowed directory
$allowedBase = Resolve-Path $script:Config.WorktreeBasePath
$resolvedPath = Resolve-Path $worktreePath -ErrorAction SilentlyContinue

if (-not $resolvedPath -or -not $resolvedPath.Path.StartsWith($allowedBase.Path)) {
    throw "Invalid worktree path: $worktreePath"
}
```

## Recommendations Summary

### Critical (P0)

1. **Implement concurrency control** (GitHub Actions `concurrency` group)
2. **Add pre-flight rate limit check** (prevent API exhaustion)
3. **Deploy GitHub Actions workflow** (hourly automation)

### High Priority (P1)

4. **Add structured logging** (JSON format for queryability)
5. **Implement retry logic** (exponential backoff for transient errors)
6. **Configure failure alerts** (create issue on workflow failure)
7. **Add worktree path validation** (security hardening)

### Medium Priority (P2)

8. **Instrument metrics** (export JSON summary)
9. **Implement log rotation** (daily logs, 30-day retention)
10. **Add circuit breaker** (stop on high error rate)
11. **Track processed PRs** (avoid duplicate work within 1 hour)

### Low Priority (P3)

12. **Externalize configuration** (environment variables + config file)
13. **Add performance monitoring** (baseline metrics dashboard)
14. **Create operational runbook** (embed in repository docs)

## Appendix: 12-Factor App Compliance

| Factor | Compliance | Evidence |
|--------|------------|----------|
| **I. Codebase** | ✅ PASS | Single repo, version-controlled |
| **II. Dependencies** | ✅ PASS | Explicit (pwsh 7.4+, gh CLI 2.40+) |
| **III. Config** | ⚠️ PARTIAL | Hardcoded (recommend env vars) |
| **IV. Backing services** | ✅ PASS | GitHub API treated as attached resource |
| **V. Build/release/run** | ✅ PASS | Workflow (build) + env (config) + execution separate |
| **VI. Processes** | ✅ PASS | Stateless (state in API, not memory) |
| **VII. Port binding** | N/A | Not a service |
| **VIII. Concurrency** | ⚠️ NEEDS WORK | No concurrency control (add mutex) |
| **IX. Disposability** | ✅ PASS | Fast startup (<5s), cleanup in finally |
| **X. Dev/prod parity** | ✅ PASS | Identical execution (local DryRun = CI) |
| **XI. Logs** | ⚠️ PARTIAL | File-based (recommend stdout + aggregation) |
| **XII. Admin processes** | ✅ PASS | One-off script execution |

**Overall Grade**: B+ (Strong foundation, minor enhancements needed)

---

**Review Complete**: 2025-12-22
**Next Steps**: Deploy workflow, instrument baseline metrics, monitor for 1 week
