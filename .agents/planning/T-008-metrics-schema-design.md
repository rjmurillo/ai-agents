# T-008: Design Metrics Collection Schema

**Phase**: 2 (Traceability + Metrics)
**Complexity**: Medium
**Scope**: Design only (governance documents, no code implementation)
**Dependencies**: Phase 2 Traceability (T-001 to T-007) COMPLETE
**Related**: [Issue #169](https://github.com/rjmurillo/ai-agents/issues/169), [PROJECT-PLAN.md Phase 2](.agents/planning/enhancement-PROJECT-PLAN.md)

---

## Overview

Design the metrics collection schema following the established three-document governance pattern from Phase 2 traceability work. This task creates the foundational schema that T-009 (implementation) and T-010 (dashboard) will build upon.

**Reference Architecture**: `.agents/analysis/claude-flow-architecture-analysis.md`

**Storage Strategy**: Dual storage (YAML frontmatter in session logs + JSON cache for CI)

**Metric Priority**:
- **P0** (blocking): M-001, M-002, M-003, M-004 (core agent effectiveness)
- **P1** (important): M-005, M-006, M-007, M-008 (operational insights)
- **Performance**: P-001, P-002, P-003 (PROJECT-PLAN targets)

---

## Deliverables

### 1. Governance Documents (3 files)

#### `.agents/governance/metrics-schema.md` (~300 lines)

**Purpose**: Define metric categories, YAML structure, validation rules, validation algorithm

**Sections**:
1. **Header**: Version 1.0.0, created date, status Active, related docs
2. **Overview**: Purpose, scope, relation to Issue #169 and PROJECT-PLAN Phase 2
3. **Metric Categories**: 4 categories (Activity, Quality, Performance, Infrastructure)
4. **Metric Definitions**: All 11 metrics (M-001 to M-008, P-001 to P-003) with:
   - ID, category, name, description
   - Collection point (where captured)
   - Calculation method (sum, avg, percentage, ratio)
   - Baseline value (from baseline-report.md)
   - Target value (from Issue #169 and PROJECT-PLAN)
   - Unit (count, percentage, seconds, ratio)
   - Frequency (real-time, session, daily, weekly)
   - Related metrics (dependencies)
   - Status (active, deprecated)
5. **YAML Front Matter Schema**: Full schema with all fields and value options
6. **Validation Rules**: 5 rules with examples
   - Rule 1: Baseline Exists
   - Rule 2: Target Defined
   - Rule 3: Collection Point Valid
   - Rule 4: Unit Consistency
   - Rule 5: Related References Valid
7. **Validation Algorithm**: Pseudocode (language-agnostic)
8. **Validation Levels**: Error/Warning/Info with exit codes (0, 1, 2)
9. **Integration Points**: Table of where schema is enforced (pre-commit, CI, agents)
10. **Examples**: Valid and invalid metric definitions

**Pattern to Follow**: `.agents/governance/traceability-schema.md` (structure, tables, YAML examples, pseudocode)

---

#### `.agents/governance/metrics-protocol.md` (~350 lines)

**Purpose**: Define collection workflow, roles, enforcement points, integration with session protocol

**Sections**:
1. **Header**: Version, created, status, phase
2. **Purpose**: Why this protocol exists
3. **Scope**: What it applies to (session logs, retrospectives, CI, skills)
4. **Quick Reference**: Links to metrics-schema.md and metrics-report-format.md
5. **Roles and Responsibilities**: Which agents do what
   - orchestrator: Records M-001 (invocation rate)
   - retrospective: Extracts M-006 (turnaround time), M-003 (shift-left)
   - qa: Contributes to M-003
   - security: Tags M-004 (infrastructure review)
   - implementer: Tracks P-001 (token efficiency)
   - devops: Runs collect-metrics.ps1 weekly
   - pre-commit hook: Validates metric definitions
6. **Collection Points**: 6 points with triggers, captures, location, format
   - session_start: After Serena init
   - agent_dispatch: orchestrator invokes subagent
   - git_commit: Before each commit
   - session_end: After QA validation
   - pr_create: PR created
   - ci_run: Weekly cron
7. **Data Flow Diagram**: ASCII diagram showing collection flow
8. **Enforcement Points**: Where protocol is enforced (session gates, hooks, CI)
9. **Common Violations and Fixes**: Problem-solution pairs with YAML examples
10. **YAML Front Matter Requirements**: Complete examples for:
    - Metric definitions
    - Session metrics
    - Agent invocations
    - Commit metrics
11. **Integration with Workflows**: Feature development flow, weekly reporting flow
12. **Troubleshooting**: Common issues and fixes

**Pattern to Follow**: `.agents/governance/traceability-protocol.md` (roles, enforcement, workflows, violations)

---

#### `.agents/governance/metrics-report-format.md` (~250 lines)

**Purpose**: Define dashboard structure, remediation actions, exit codes

**Sections**:
1. **Header**: Version, created, status, related Issue #169
2. **Overview**: Purpose of standardized reporting
3. **Report Structure**:
   - Header (period, generated date, sessions analyzed)
   - Executive Summary (table: metric, current, target, status, trend)
   - Metric Details (11 sections, one per metric)
   - Remediation Actions (Critical/Important/Informational)
   - Trend Analysis (weekly trends table)
   - Recommendations (immediate/process improvements/consolidation)
4. **Metric Detail Template**: Standard format for each of 11 metrics
   - Category, status
   - Distribution table (if applicable)
   - Observations
   - Remediation checklist
5. **Remediation Actions Format**: YAML structure for tracking fixes
6. **Exit Codes**: 0 (on track), 1 (critical behind), 2 (warning behind)
7. **Integration with Reports**: How session logs, retrospectives, ADRs connect
8. **References**: Links to metrics-schema.md, metrics-protocol.md, baseline-report.md

**Pattern to Follow**: `.agents/governance/orphan-report-format.md` (report structure, remediation actions, integration)

---

## Metric Taxonomy (11 Total Metrics)

### Activity Metrics (3)
- **M-001**: Invocation Rate by Agent (Issue #169 metric 1)
  - Collection: agent_dispatch, git_commit
  - Calculation: COUNT(agent_invocations) GROUP BY agent_type
  - Baseline: Unmeasured
  - Target: Orchestrator >= 50% multi-domain tasks
  - Unit: count

- **M-005**: Usage Distribution by Agent (Issue #169 metric 5)
  - Collection: agent_dispatch
  - Calculation: (agent_invocations / total_invocations) * 100
  - Baseline: 0% (unmeasured)
  - Target: Balanced distribution
  - Unit: percentage

- **M-008**: Policy Compliance (Issue #169 metric 8)
  - Collection: session_end
  - Calculation: (compliant_sessions / total_sessions) * 100
  - Baseline: 0%
  - Target: 100%
  - Unit: percentage

### Quality Metrics (3)
- **M-002**: Agent Coverage (Issue #169 metric 2)
  - Collection: git_commit
  - Calculation: (commits_with_agent / total_commits) * 100
  - Baseline: ~30%
  - Target: >= 50%
  - Unit: percentage

- **M-003**: Shift-Left Effectiveness (Issue #169 metric 3)
  - Collection: pr_create, retrospective
  - Calculation: (issues_caught_agent / total_issues) * 100
  - Baseline: 0%
  - Target: >= 80%
  - Unit: percentage

- **M-007**: Vulnerability Discovery Timeline (Issue #169 metric 7)
  - Collection: security agent, retrospective
  - Calculation: Timestamp of first detection
  - Baseline: 0 (not tracked)
  - Target: N/A (tracking only)
  - Unit: timestamp

### Performance Metrics (4)
- **M-006**: Agent Review Turnaround Time (Issue #169 metric 6)
  - Collection: session_start, session_end
  - Calculation: end_time - start_time
  - Baseline: Unmeasured
  - Target: Quick (<5 min), Standard (<30 min), Comprehensive (<120 min)
  - Unit: minutes

- **P-001**: Token Efficiency (PROJECT-PLAN target)
  - Collection: session_start, session_end
  - Calculation: (baseline_tokens - actual_tokens) / baseline_tokens * 100
  - Baseline: 0%
  - Target: >= 30% reduction
  - Unit: percentage

- **P-002**: Parallel Execution Speed (PROJECT-PLAN target)
  - Collection: agent_dispatch (parallel tasks)
  - Calculation: sequential_time / parallel_time
  - Baseline: 1.0x (no parallelism)
  - Target: 2.8-4.4x speedup
  - Unit: ratio

- **P-003**: Memory Search Speed (PROJECT-PLAN target)
  - Collection: memory agent, Serena/Forgetful logs
  - Calculation: baseline_latency / vector_latency
  - Baseline: 1.0x (sequential search)
  - Target: 96-164x faster
  - Unit: ratio

### Infrastructure Metrics (1)
- **M-004**: Infrastructure Code Review Rate (Issue #169 metric 4)
  - Collection: git_commit, security agent
  - Calculation: (infra_commits_reviewed / total_infra_commits) * 100
  - Baseline: 0%
  - Target: 100%
  - Unit: percentage

---

## YAML Schema Examples

### Metric Definition (in governance docs)

```yaml
---
type: metric_definition
id: M-002
category: quality
name: Agent Coverage
description: Percentage of commits with explicit agent involvement (detected via commit message patterns)
collection_point: git_commit
calculation: percentage
baseline: 30
target: 50
unit: percentage
frequency: daily
related:
  - M-001  # Agent invocations feed into coverage calculation
status: active
---
```

### Session Metrics (in session logs)

```yaml
---
session_metrics:
  session_id: 2025-12-31-session-115
  start_time: 2025-12-31 10:00:00
  end_time: 2025-12-31 11:30:00
  duration_minutes: 90
  branch: feat/metrics-schema
  memories_loaded: 8
  agents_invoked:
    - orchestrator: 1
    - planner: 1
    - implementer: 3
    - qa: 1
  commits: 2
  files_changed: 15
  errors: 0
  qa_verdict: PASS
  infrastructure_files: false
---
```

### Agent Invocation (in session logs, Work Log section)

```yaml
---
agent_invocation:
  agent: implementer
  timestamp: 2025-12-31 10:15:00
  task: Implement feature X per plan
  parent: orchestrator
---
```

### Commit Metrics (in session logs, Commits This Session section)

```yaml
---
commit_metrics:
  sha: abc123def456
  files_changed: 5
  agent_involved: true
  agent_type: implementer
  infrastructure: false
---
```

---

## Collection Point Mapping

| Collection Point | When Triggered | Captured By | Metrics Fed | Location |
|------------------|----------------|-------------|-------------|----------|
| session_start | After Serena init, before work | Session log header | M-006 (start time), P-001 (baseline tokens) | Session log YAML frontmatter |
| agent_dispatch | orchestrator invokes subagent | Session log Work Log | M-001 (invocations), M-005 (distribution) | Session log inline YAML |
| git_commit | Before each commit | Session log Commits | M-002 (coverage), M-004 (infrastructure) | Session log inline YAML |
| session_end | After QA, before close | Session log Session End | M-006 (end time), M-008 (policy compliance) | Session log final section |
| pr_create | PR created via skill/gh | Session log or CI | M-003 (shift-left contribution) | Session log or CI workflow |
| ci_run | Weekly cron job | agent-metrics.yml workflow | All metrics (aggregation) | `.agents/metrics/YYYY-MM-DD-report.md` |

**Data Flow**:
```
session_start → session_metrics.yaml → session log header
     ↓
agent_dispatch → agent_invocation.yaml → session log Work Log
     ↓
git_commit → commit_metrics.yaml → session log Commits
     ↓
session_end → session_summary.yaml → session log Session End
     ↓
ci_run → collect-metrics.ps1 → dashboard markdown
```

---

## Enforcement Strategy (Design for T-009 Implementation)

**T-008 Scope**: Document the enforcement approach (what, when, where)
**T-009 Scope**: Implement the enforcement (hooks, automation, validation scripts)

**CRITICAL PRINCIPLE**: Enforcement must be **mechanized and unskippable**. No reliance on agent memory or prompts. Scripts and hooks automatically inject, validate, and block.

### Enforcement Philosophy

**Anti-Pattern**: "Agent prompts remind you to add YAML" ← Agents will skip if expedient
**Correct Pattern**: "Script auto-generates YAML, pre-commit blocks if missing" ← Mechanized, unskippable

**Enforcement Hierarchy**:
1. **Auto-injection**: Scripts generate YAML automatically (no agent involvement)
2. **Validation gates**: Pre-commit hooks block if YAML missing or invalid
3. **Blocking exit codes**: Session can't close without passing validation

### Enforcement Mechanisms

#### 1. Session Log Auto-Generation (MECHANIZED, BLOCKING)

**Problem**: Relying on agents to manually create session logs with YAML frontmatter
**Solution**: Script auto-generates session log with pre-populated YAML

**T-009 Implementation**: Create `New-SessionLog.ps1`

```powershell
# scripts/New-SessionLog.ps1

param(
    [Parameter(Mandatory=$false)]
    [string]$SessionNumber
)

# Auto-detect next session number
if (-not $SessionNumber) {
    $existingLogs = Get-ChildItem ".agents/sessions" -Filter "*.md"
    $lastNumber = ($existingLogs | ForEach-Object {
        if ($_.Name -match "session-(\d+)") { [int]$matches[1] }
    } | Measure-Object -Maximum).Maximum
    $SessionNumber = $lastNumber + 1
}

# Auto-populate YAML
$date = Get-Date -Format "yyyy-MM-DD"
$timestamp = Get-Date -Format "yyyy-MM-DD HH:mm:ss"
$branch = git branch --show-current
$sessionId = "$date-session-$SessionNumber"

# Generate session log with YAML template
$template = @"
---
session_metrics:
  session_id: $sessionId
  start_time: $timestamp
  end_time: __REQUIRED__  # Validation blocks if not filled
  duration_minutes: __REQUIRED__  # Auto-calculated at end
  branch: $branch
  memories_loaded: __REQUIRED__  # Must update after Serena init
  agents_invoked: {}  # Auto-populated by orchestrator hook
  commits: 0  # Auto-incremented by git hook
  files_changed: 0  # Auto-calculated at end
  errors: 0  # Manual tracking
  qa_verdict: __REQUIRED__  # Validation blocks if not filled
  infrastructure_files: false  # Auto-detected at end
---

# Session $SessionNumber: [BRIEF TITLE]

[Session content...]
"@

$filePath = ".agents/sessions/$sessionId.md"
Set-Content -Path $filePath -Value $template

Write-Output "Session log created: $filePath"
Write-Output "REQUIRED fields must be updated before session end validation"
```

**Enforcement**:
- `__REQUIRED__` placeholders fail validation if not replaced
- Pre-commit hook blocks commit if placeholders remain
- No manual YAML writing required

**SESSION-PROTOCOL Integration**:
```markdown
Phase 1 (Session Start):
- [x] Run: pwsh scripts/New-SessionLog.ps1
- [x] Verify: Session log exists with YAML header
```

#### 2. Pre-Commit Hook Validation (MECHANIZED, BLOCKING)

**Problem**: Commits can succeed even if session logs missing metrics or have placeholders
**Solution**: Pre-commit hook blocks until all validation passes

**T-009 Implementation**: Enhance `.githooks/pre-commit`

```powershell
# .githooks/pre-commit (enhanced for metrics)

# Existing: Validate traceability
pwsh scripts/Validate-Traceability.ps1
if ($LASTEXITCODE -ne 0) {
    Write-Error "Traceability validation failed. Commit blocked."
    exit 1
}

# NEW: Validate metric definitions (if metrics files staged)
$metricsChanged = git diff --cached --name-only | Select-String ".agents/metrics/.*\.md"
if ($metricsChanged) {
    pwsh scripts/Validate-Metrics.ps1  # T-009 deliverable
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Metric definition validation failed. Commit blocked."
        exit 1
    }
}

# NEW: Validate session log completeness (if session log staged)
$sessionLogChanged = git diff --cached --name-only | Select-String ".agents/sessions/.*\.md"
if ($sessionLogChanged) {
    pwsh scripts/Validate-SessionLog.ps1  # T-009 deliverable
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Session log incomplete. Run: pwsh scripts/Complete-SessionLog.ps1"
        exit 1
    }
}
```

**Validation Checks** (T-009 scripts):

`Validate-Metrics.ps1`:
- All 5 rules enforced (baseline, target, collection point, unit, references)
- Exit 1 if errors, exit 2 if warnings, exit 0 if pass
- Blocks commit on exit 1

`Validate-SessionLog.ps1`:
- YAML frontmatter exists
- No `__REQUIRED__` placeholders remain
- `end_time` filled in
- `qa_verdict` is PASS or FAIL (not placeholder)
- `agents_invoked` is populated (not empty {})
- Exit 1 if incomplete, exit 0 if complete

**Enforcement Level**: BLOCKING - Commit cannot succeed if validation fails

#### 3. Git Commit Hook Auto-Injection (MECHANIZED, UNSKIPPABLE)

**Problem**: Agents might forget to write commit_metrics YAML
**Solution**: Git hook auto-injects commit metadata into session log

**T-009 Implementation**: Create `post-commit` hook

```powershell
# .githooks/post-commit (new file, T-009)

# Auto-inject commit metrics into current session log
$sessionLog = Get-ChildItem ".agents/sessions" -Filter "*session-*.md" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $sessionLog) {
    Write-Warning "No session log found. Skipping commit metrics."
    exit 0
}

# Get commit details
$commitSha = git rev-parse HEAD
$filesChanged = git diff-tree --no-commit-id --name-only -r HEAD
$infraPattern = "\.github/|\.githooks/|Dockerfile|docker-compose|\.tf$|scripts/"
$hasInfra = $filesChanged | Where-Object { $_ -match $infraPattern }

# Auto-inject commit metrics
$commitMetrics = @"

## Commit: $($commitSha.Substring(0,7))

File(s) changed: $($filesChanged.Count)
Infrastructure files: $(if ($hasInfra) { 'YES' } else { 'NO' })

---
commit_metrics:
  sha: $commitSha
  files_changed: $($filesChanged.Count)
  infrastructure: $(if ($hasInfra) { 'true' } else { 'false' })
  timestamp: $(Get-Date -Format "yyyy-MM-DD HH:mm:ss")
---
"@

Add-Content -Path $sessionLog.FullName -Value $commitMetrics

# Auto-increment commits counter in YAML frontmatter
$content = Get-Content $sessionLog.FullName
$newContent = $content -replace "commits: (\d+)", {
    "commits: $([int]$matches[1] + 1)"
}
Set-Content -Path $sessionLog.FullName -Value $newContent
```

**Enforcement**:
- Runs AUTOMATICALLY after every commit
- No agent involvement required
- Updates session log without manual intervention

**Metrics Captured**:
- Commit SHA
- Files changed count
- Infrastructure file detection (auto)
- Timestamp
- Increments `commits` counter in YAML

#### 4. Session End Validation Script (MECHANIZED, BLOCKING)

**Problem**: Sessions can end without completing required metrics
**Solution**: Validation script blocks session close until metrics complete

**T-009 Implementation**: Enhance `scripts/Validate-SessionEnd.ps1`

```powershell
# scripts/Validate-SessionEnd.ps1 (enhancement for T-009)

param(
    [Parameter(Mandatory=$true)]
    [string]$SessionLogPath
)

# Existing validation (from SESSION-PROTOCOL)
# ... session protocol checks ...

# NEW: Metrics validation
Write-Output "Validating session metrics..."

$content = Get-Content $SessionLogPath -Raw
$yamlMatch = $content -match "(?s)---\s*session_metrics:(.*?)---"

if (-not $yamlMatch) {
    Write-Error "BLOCKING: Session log missing metrics YAML frontmatter"
    exit 1
}

$yaml = $matches[1]

# Check for required placeholders
if ($yaml -match "__REQUIRED__") {
    Write-Error "BLOCKING: Session log has unfilled __REQUIRED__ fields"
    Write-Output "Fields to fill: $(($yaml | Select-String '__REQUIRED__' -AllMatches).Matches.Count)"
    exit 1
}

# Check end_time filled
if ($yaml -notmatch "end_time:\s+\d{4}-\d{2}-\d{2}") {
    Write-Error "BLOCKING: end_time not filled. Run: pwsh scripts/Complete-SessionLog.ps1"
    exit 1
}

# Check qa_verdict filled
if ($yaml -match "qa_verdict:\s+(__|REQUIRED)") {
    Write-Error "BLOCKING: qa_verdict not filled. Must be PASS, FAIL, or SKIPPED"
    exit 1
}

# Check agents_invoked populated
if ($yaml -match "agents_invoked:\s+\{\}") {
    Write-Warning "WARNING: No agents were invoked this session (unusual)"
}

Write-Output "✓ Session metrics validation passed"
exit 0
```

**Enforcement**:
- SESSION-PROTOCOL Phase 7 MUST run this before final commit
- Exit 1 blocks session close
- Clear error messages guide fixes

**Helper Script**: Create `Complete-SessionLog.ps1` to auto-fill calculable fields

```powershell
# scripts/Complete-SessionLog.ps1 (T-009 deliverable)

param(
    [string]$SessionLogPath
)

if (-not $SessionLogPath) {
    $SessionLogPath = Get-ChildItem ".agents/sessions" -Filter "*session-*.md" |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}

$content = Get-Content $SessionLogPath -Raw

# Auto-fill end_time
$endTime = Get-Date -Format "yyyy-MM-DD HH:mm:ss"
$content = $content -replace "end_time: __REQUIRED__", "end_time: $endTime"

# Auto-calculate duration
if ($content -match "start_time:\s+(.+)") {
    $startTime = [datetime]::ParseExact($matches[1], "yyyy-MM-DD HH:mm:ss", $null)
    $duration = ([datetime]$endTime - $startTime).TotalMinutes
    $content = $content -replace "duration_minutes: __REQUIRED__", "duration_minutes: $([int]$duration)"
}

# Auto-calculate files_changed
$filesChanged = (git diff --name-only HEAD~1..HEAD | Measure-Object).Count
$content = $content -replace "files_changed: 0", "files_changed: $filesChanged"

# Auto-detect infrastructure files
$infraFiles = git diff --name-only HEAD~1..HEAD | Where-Object { $_ -match "\.github/|\.githooks/" }
if ($infraFiles) {
    $content = $content -replace "infrastructure_files: false", "infrastructure_files: true"
}

Set-Content -Path $SessionLogPath -Value $content

Write-Output "✓ Session log auto-completed. Review qa_verdict and memories_loaded manually."
```

#### 5. CI Workflow Aggregation (MECHANIZED, AUTOMATED)

**Problem**: Manual metrics aggregation is error-prone
**Solution**: Weekly CI cron auto-aggregates and generates dashboard

**T-009 Implementation**: Enhance `collect-metrics.ps1`

```powershell
# .claude/skills/metrics/collect-metrics.ps1 (enhanced)

function Get-Metrics {
    param([int]$Days = 7)

    # Existing: Git log analysis (commits, agent patterns)
    $gitMetrics = Get-CommitsSince -Days $Days

    # NEW: Session log YAML parsing
    $sessionLogs = Get-ChildItem ".agents/sessions/*.md" |
        Where-Object { $_.LastWriteTime -gt (Get-Date).AddDays(-$Days) }

    $sessionMetrics = @()
    foreach ($log in $sessionLogs) {
        $content = Get-Content $log.FullName -Raw

        # Extract YAML frontmatter
        if ($content -match "(?s)---\s*session_metrics:(.*?)---") {
            $yaml = $matches[1]

            # Parse YAML fields (simple regex-based parsing)
            $metrics = @{}
            if ($yaml -match "duration_minutes:\s+(\d+)") { $metrics.duration = [int]$matches[1] }
            if ($yaml -match "commits:\s+(\d+)") { $metrics.commits = [int]$matches[1] }
            if ($yaml -match "qa_verdict:\s+(\w+)") { $metrics.qa_verdict = $matches[1] }
            # ... parse other fields ...

            $sessionMetrics += $metrics
        }
    }

    # Merge git + session metrics
    $combined = @{
        git = $gitMetrics
        sessions = $sessionMetrics
        period_days = $Days
    }

    return $combined
}
```

**Enforcement**:
- Weekly cron: `0 0 * * 0` (Sundays at midnight)
- Auto-commits dashboard to `.agents/metrics/YYYY-MM-DD-report.md`
- No manual intervention

---

## Enforcement Summary (MECHANIZED, UNSKIPPABLE)

| Enforcement Point | Type | Trigger | Blocks? | Implementation (T-009) |
|-------------------|------|---------|---------|------------------------|
| **1. Session log auto-generation** | Script | Session start | Yes (can't start without) | `scripts/New-SessionLog.ps1` |
| **2. Pre-commit validation** | Hook | git commit | Yes (commit fails if invalid) | `.githooks/pre-commit` enhancement |
| **3. Post-commit auto-injection** | Hook | git commit | No (auto-captures) | `.githooks/post-commit` (new) |
| **4. Session end validation** | Script | Session close | Yes (can't close if incomplete) | `scripts/Validate-SessionEnd.ps1` enhancement |
| **5. CI weekly aggregation** | Cron | Sundays 00:00 | No (reporting only) | `.github/workflows/agent-metrics.yml` |

**Key Differences from Original Proposal**:

| Original (Weak) | New (Strong) |
|-----------------|--------------|
| "Agent prompt reminds to add YAML" | Script auto-generates YAML with placeholders |
| "orchestrator writes agent_invocation" | Post-commit hook auto-injects commit metrics |
| "Pre-commit validates format" | Pre-commit blocks on missing/incomplete metrics |
| "Manual session end checklist" | Validation script with exit codes blocks close |
| "Retrospective extracts metrics" | Metrics already present via automation |

**Philosophy**:
- **No trust, only verify**: Scripts enforce, not agent memory
- **Fail closed**: Missing metrics = blocked commit/session
- **Auto-capture where possible**: Hooks inject data without agent involvement
- **Clear error messages**: Validation failures guide fixes with script names

---

## T-008 Deliverables: Document ALL Enforcement

For T-008 (design phase), `metrics-protocol.md` must document:

### 1. Enforcement Overview Section
```markdown
## Enforcement Strategy

Metrics collection uses **mechanized, unskippable enforcement**:

1. Auto-generation (scripts create YAML templates)
2. Auto-injection (hooks capture commit data)
3. Validation gates (scripts block on incomplete/invalid)
4. Exit codes (0=pass, 1=error/block)

NO reliance on agent memory or prompts.
```

### 2. Script Specifications (5 scripts)
- `New-SessionLog.ps1`: Auto-generates session log with YAML template
- `Validate-SessionLog.ps1`: Checks completeness, blocks if `__REQUIRED__` remains
- `Complete-SessionLog.ps1`: Auto-fills calculable fields (end_time, duration, files_changed)
- `Validate-Metrics.ps1`: Validates metric definitions (5 rules)
- Enhanced `Validate-SessionEnd.ps1`: Adds metrics checks to existing validation

### 3. Hook Specifications (2 hooks)
- `.githooks/pre-commit` enhancement: Add metrics and session log validation
- `.githooks/post-commit` (new): Auto-inject commit metrics into session log

### 4. Collection Point Mapping
- session_start: Run `New-SessionLog.ps1` (auto-generates YAML)
- git_commit: `post-commit` hook auto-injects commit_metrics
- session_end: Run `Complete-SessionLog.ps1` then `Validate-SessionEnd.ps1`
- ci_run: Weekly cron aggregates session YAML

### 5. Error Messages and Fixes
```markdown
## Common Errors

**Error**: "Session log has unfilled __REQUIRED__ fields"
**Fix**: Run `pwsh scripts/Complete-SessionLog.ps1` to auto-fill

**Error**: "qa_verdict not filled"
**Fix**: Manually set `qa_verdict: PASS` or `FAIL` or `SKIPPED` in session log YAML

**Error**: "Metric definition validation failed"
**Fix**: Run `pwsh scripts/Validate-Metrics.ps1 -Verbose` to see which rule failed
```

### 6. Migration Strategy
```markdown
## Adopting Metrics (Gradual Rollout)

### Phase 1: Scripts Only (Week 1)
- Deploy `New-SessionLog.ps1`, `Complete-SessionLog.ps1`
- Optional use (no enforcement)
- Agents test workflow

### Phase 2: Validation Gates (Week 2)
- Enable `Validate-SessionEnd.ps1` metrics checks
- Blocking enforcement begins
- Session-PROTOCOL updated

### Phase 3: Full Automation (Week 3)
- Enable `post-commit` hook
- Pre-commit validation active
- Weekly CI reports live
```

T-009 will implement these scripts and hooks with test coverage ≥1.5:1 ratio.

---

## Integration with Existing Infrastructure

### `.claude/skills/metrics/collect-metrics.ps1`
**Current**: Parses git logs, detects agent patterns, outputs Summary/Markdown/JSON

**Future Enhancement (T-009)**: Add session log YAML parsing, aggregate session metrics

**Design Consideration**: Ensure YAML schema is parseable by PowerShell (no complex nesting)

### `.agents/metrics/baseline-report.md`
**Current**: Established 2025-12-13, pre-Phase 2 baseline measurements

**Usage**: Baseline values for all 11 metrics

**Design Consideration**: Reference baseline values in metric definitions

### `.agents/metrics/dashboard-template.md`
**Current**: Template with 8 metrics placeholders

**Future Enhancement (T-010)**: Extend with P-001, P-002, P-003 and trend analysis

**Design Consideration**: Ensure report format aligns with template structure

### `.agents/SESSION-PROTOCOL.md`
**Current**: 7-phase session protocol with blocking gates

**Enhancement Required**: Add metrics YAML to Phase 1 (Session Start) and Phase 7 (Session End)

**Design Consideration**: Metrics collection must not add friction to session protocol

---

## Validation Rules (5 Rules)

### Rule 1: Baseline Exists
Every metric MUST have a documented baseline value (numeric or "unmeasured").

**Rationale**: Baseline enables trend analysis and target tracking.

**Validation**: `IF metric.baseline IS NULL OR metric.baseline == "" THEN ERROR`

**Example**:
- ✅ Valid: `baseline: 30`
- ✅ Valid: `baseline: 0` (for new metrics)
- ❌ Invalid: `baseline:` (empty)

### Rule 2: Target Defined
Every metric MUST have a numeric target or "N/A" with justification.

**Rationale**: Targets define success criteria and drive improvement.

**Validation**: `IF metric.target IS NULL OR metric.target == "" THEN ERROR`

**Example**:
- ✅ Valid: `target: 50`
- ✅ Valid: `target: N/A  # Tracking-only metric`
- ❌ Invalid: `target:` (empty)

### Rule 3: Collection Point Valid
Collection point MUST be one of 6 allowed values.

**Allowed**: session_start, session_end, agent_dispatch, git_commit, pr_create, ci_run

**Rationale**: Ensures metrics can be captured automatically.

**Validation**: `IF metric.collection_point NOT IN [session_start, ...] THEN ERROR`

**Example**:
- ✅ Valid: `collection_point: git_commit`
- ❌ Invalid: `collection_point: manual` (not automated)

### Rule 4: Unit Consistency
Calculation type MUST match unit (percentage → %, count → count, etc.)

**Rationale**: Prevents data type errors in calculations.

**Validation**: `IF metric.calculation == "percentage" AND metric.unit != "percentage" THEN WARNING`

**Example**:
- ✅ Valid: `calculation: percentage, unit: percentage`
- ⚠️ Warning: `calculation: percentage, unit: count`

### Rule 5: Related References Valid
All related metric IDs MUST exist.

**Rationale**: Prevents broken dependency chains.

**Validation**: `FOR each related_id: IF NOT MetricExists(related_id) THEN ERROR`

**Example**:
- ✅ Valid: `related: [M-001]` (M-001 exists)
- ❌ Invalid: `related: [M-999]` (M-999 doesn't exist)

---

## Validation Algorithm (Pseudocode)

```text
FUNCTION ValidateMetricDefinitions(metrics_dir):
    errors = []
    warnings = []
    info = []

    # Load all metric definition files
    metric_files = FindFiles(metrics_dir, "*.md")
    metrics = {}

    FOR EACH file IN metric_files:
        # Parse YAML front matter
        yaml = ExtractYAML(file)

        IF yaml.type != "metric_definition":
            CONTINUE  # Not a metric definition

        metric_id = yaml.id
        metrics[metric_id] = yaml

        # Rule 1: Baseline Exists
        IF yaml.baseline IS NULL OR yaml.baseline == "":
            errors.append({
                file: file,
                rule: "Rule 1: Baseline Exists",
                message: "Missing baseline value for " + metric_id
            })

        # Rule 2: Target Defined
        IF yaml.target IS NULL OR yaml.target == "":
            errors.append({
                file: file,
                rule: "Rule 2: Target Defined",
                message: "Missing target value for " + metric_id
            })

        # Rule 3: Collection Point Valid
        valid_points = [session_start, session_end, agent_dispatch, git_commit, pr_create, ci_run]
        IF yaml.collection_point NOT IN valid_points:
            errors.append({
                file: file,
                rule: "Rule 3: Collection Point Valid",
                message: "Invalid collection point: " + yaml.collection_point
            })

        # Rule 4: Unit Consistency
        IF yaml.calculation == "percentage" AND yaml.unit != "percentage":
            warnings.append({
                file: file,
                rule: "Rule 4: Unit Consistency",
                message: "Unit mismatch: percentage calculation with " + yaml.unit + " unit"
            })

    # Rule 5: Related References Valid
    FOR EACH metric IN metrics.values():
        FOR EACH related_id IN metric.related:
            IF related_id NOT IN metrics:
                errors.append({
                    file: metric.file,
                    rule: "Rule 5: Related References Valid",
                    message: "Broken reference: " + metric.id + " → " + related_id
                })

    # Generate validation report
    report = {
        total_metrics: metrics.count,
        errors: errors,
        warnings: warnings,
        info: info
    }

    # Determine exit code
    exit_code = 0
    IF errors.count > 0:
        exit_code = 1  # Errors are blocking
    ELIF warnings.count > 0:
        exit_code = 2  # Warnings are non-blocking (unless -Strict)

    RETURN {report, exit_code}
```

---

## Success Criteria

T-008 is complete and ready for T-009 when:

### Governance Documents
- [ ] `.agents/governance/metrics-schema.md` exists (~300 lines)
- [ ] `.agents/governance/metrics-protocol.md` exists (~350 lines)
- [ ] `.agents/governance/metrics-report-format.md` exists (~250 lines)
- [ ] All 3 docs follow traceability governance pattern (metadata, sections, tables, YAML)

### Metric Definitions
- [ ] All 11 metrics defined (M-001 to M-008, P-001 to P-003)
- [ ] Each metric has: ID, category, name, description, collection_point, calculation, baseline, target, unit, frequency, related, status
- [ ] P0 metrics (M-001 to M-004) marked as critical
- [ ] P1 metrics (M-005 to M-008) marked as important
- [ ] Performance metrics (P-001 to P-003) linked to PROJECT-PLAN targets

### YAML Schema
- [ ] Metric definition schema documented with all fields
- [ ] Session metrics schema documented
- [ ] Agent invocation schema documented
- [ ] Commit metrics schema documented
- [ ] Valid and invalid examples provided for each schema

### Collection Points
- [ ] All 6 collection points documented (when, what, where, who)
- [ ] Data flow diagram created (ASCII)
- [ ] Integration with SESSION-PROTOCOL defined

### Validation
- [ ] 5 validation rules documented with examples
- [ ] Validation algorithm provided (pseudocode, language-agnostic)
- [ ] Exit codes defined (0=success, 1=error, 2=warning)
- [ ] Validation levels specified (Error/Warning/Info)

### Integration
- [ ] Integration with collect-metrics.ps1 documented
- [ ] Integration with SESSION-PROTOCOL.md documented
- [ ] Integration with baseline-report.md documented
- [ ] Integration with dashboard-template.md documented

### Handoff to T-009
- [ ] T-009 requirements clearly specified (YAML schemas, collection points)
- [ ] No ambiguities in metric definitions
- [ ] Storage strategy documented (dual: YAML + JSON)

### Quality Gates
- [ ] Critic agent validates schema consistency
- [ ] No broken cross-references between governance docs
- [ ] Follows PROJECT-CONSTRAINTS.md (PowerShell-only for future scripts)

---

## Critical Files for Reference

### Patterns to Follow
| File | Purpose | What to Learn |
|------|---------|---------------|
| `.agents/governance/traceability-schema.md` | Schema doc structure | Metadata blocks, tables, YAML examples, pseudocode, validation levels |
| `.agents/governance/traceability-protocol.md` | Protocol doc structure | Roles, enforcement points, workflows, violations/fixes, YAML requirements |
| `.agents/governance/orphan-report-format.md` | Report format structure | Report sections, remediation actions, exit codes, integration |

### Architectural Reference
| File | Purpose | What to Learn |
|------|---------|---------------|
| `.agents/analysis/claude-flow-architecture-analysis.md` | Reference architecture | System metrics (memory/CPU), task metrics (duration/status), performance metrics (activity) |
| `.agents/planning/enhancement-PROJECT-PLAN.md` | Performance targets | Parallel execution (2.8-4.4x), memory search (96-164x), token efficiency (30%) |

### Existing Infrastructure
| File | Purpose | What to Learn |
|------|---------|---------------|
| `.claude/skills/metrics/collect-metrics.ps1` | Current metrics collection | Git log parsing, agent detection patterns, output formats (Summary/Markdown/JSON) |
| `.agents/metrics/baseline-report.md` | Baseline values | Current state for all 8 Issue #169 metrics |
| `.agents/metrics/dashboard-template.md` | Dashboard structure | Sections, table formats, recommendations |
| `.agents/SESSION-PROTOCOL.md` | Session lifecycle | 7 phases, blocking gates, YAML frontmatter usage |

### Examples of Metrics in Practice
| File | Purpose | What to Learn |
|------|---------|---------------|
| `.agents/retrospective/2025-12-24-pr-monitoring-session-retrospective.md` | Execution traces | Time-indexed agent actions, energy levels, outcome classification |
| `.agents/retrospective/2026-01-01-pr-715-phase2-traceability.md` | Code metrics | Files changed, test count, review comments, resolution time |

---

## Constraints and Considerations

### ADR-005: PowerShell-Only Scripting
- **Applies to**: Future validation scripts (T-009)
- **Does NOT apply to**: T-008 (documentation only)
- **Consideration**: Ensure YAML schemas are PowerShell-parseable (avoid complex nesting)

### ADR-007: Memory-First Architecture
- **Applies to**: Metrics should be queryable via Serena/Forgetful
- **Consideration**: Document how metrics are stored in Serena memory for cross-session retrieval

### ADR-014: Distributed Handoff Architecture
- **Applies to**: Session logs are authoritative source for metrics
- **Consideration**: HANDOFF.md should NOT contain metrics (keep it read-only)

### Dual Storage Strategy
- **Primary**: YAML frontmatter in session logs (human-readable, single source of truth)
- **Secondary**: JSON cache (for efficient CI aggregation)
- **Rationale**: Balance context richness (YAML) with processing speed (JSON)

### Test Coverage Standard
- **From Phase 2 traceability**: 1.7:1 test-to-code ratio
- **Applies to**: T-009 implementation (not T-008)
- **Consideration**: Document test expectations in metrics-protocol.md

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Schema ambiguity causes bugs** (like traceability regex pattern) | High | Provide comprehensive YAML examples (valid + invalid). Test with PowerShell YAML parser. |
| **Metrics YAML adds friction to session protocol** | Medium | Keep YAML minimal. Pre-populate templates. Make collection automatic where possible. |
| **11 metrics too many, creating maintenance burden** | Medium | Use P0/P1 prioritization. Document deprecation workflow. Plan quarterly review. |
| **Collection points unclear, inconsistent capture** | High | Explicit mapping table. ASCII data flow diagram. Integration with SESSION-PROTOCOL. |
| **YAML parsing complexity in PowerShell** | Medium | Use simple structures (no deep nesting). Document PowerShell-Yaml module requirement for T-009. |

---

## Next Steps (T-009 and T-010)

### T-009: Implement Session Metrics Capture
**Dependencies from T-008**:
- Finalized YAML schemas (metric_definition, session_metrics, agent_invocation, commit_metrics)
- Collection point definitions (when to capture, what to capture, where to store)
- Validation rules (for pre-commit hook implementation)

**Expected Deliverables (T-009)**:
- `scripts/Validate-Metrics.ps1` (validates metric definitions)
- `tests/Validate-Metrics.Tests.ps1` (unit tests, ≥1.5:1 ratio)
- Session log template updates (YAML frontmatter sections)
- orchestrator updates (write agent_invocation YAML)
- Pre-commit hook updates (capture commit_metrics YAML)
- SESSION-PROTOCOL.md updates (metrics requirements)

### T-010: Create Performance Monitoring Dashboard
**Dependencies from T-008**:
- Finalized report format (Executive Summary, Metric Details, Remediation, Trends)
- Metric definitions (11 total with baselines/targets)
- Validation algorithm (for data integrity checks)

**Dependencies from T-009**:
- Session logs populating metrics YAML
- Historical data for trend analysis (at least 4 weeks)

**Expected Deliverables (T-010)**:
- Enhanced `collect-metrics.ps1` (session log YAML parsing)
- Weekly dashboard generation (`.agents/metrics/YYYY-MM-DD-report.md`)
- CI workflow automation (weekly cron)
- Remediation action tracking

---

## Implementation Notes

### Document Writing Tips
1. **Use traceability docs as templates**: Copy structure, adapt content
2. **Tables for structured data**: Easier to scan than prose
3. **YAML examples in code blocks**: Syntax-highlighted for clarity
4. **Pseudocode for algorithms**: Language-agnostic, focuses on logic
5. **Cross-references**: Link between the 3 governance docs extensively

### YAML Design Tips
1. **Keep it simple**: No deep nesting (PowerShell YAML parsing is basic)
2. **Use enums**: `category: activity | quality | performance | infrastructure`
3. **Make fields optional**: Not every metric needs all fields
4. **Default values**: Document defaults (e.g., `status: active` if omitted)
5. **Validation-friendly**: Easy to check with IF statements

### Integration Tips
1. **Minimal disruption**: Don't force retroactive changes to existing session logs
2. **Opt-in initially**: Make metrics YAML optional in Phase 1, required in Phase 2
3. **Pre-populated templates**: Auto-generate session log headers with placeholder YAML
4. **Clear error messages**: If validation fails, explain exactly what's wrong and how to fix

---

## Estimated Effort

**T-008 Total**: ~6-8 hours

| Task | Time Estimate | Notes |
|------|---------------|-------|
| metrics-schema.md | 2-3 hours | Most complex doc. 11 metric definitions, validation algorithm. |
| metrics-protocol.md | 2-3 hours | Roles, collection points, integration. Reference traceability-protocol.md. |
| metrics-report-format.md | 1-2 hours | Dashboard structure, remediation format. Extend dashboard-template.md. |
| Cross-references and examples | 1 hour | Ensure all 3 docs link correctly, valid/invalid YAML examples. |

**Deliverables**: ~900 lines of documentation (3 files)

---

## Definition of Done

- [ ] All 3 governance documents written and committed
- [ ] All 11 metrics defined with complete YAML frontmatter
- [ ] YAML schemas documented with valid/invalid examples
- [ ] 5 validation rules documented with pseudocode algorithm
- [ ] 6 collection points mapped with data flow diagram
- [ ] Integration points documented (SESSION-PROTOCOL, collect-metrics.ps1, etc.)
- [ ] Critic agent validates schema (no broken refs, follows pattern)
- [ ] Markdownlint passes on all docs
- [ ] Handoff to T-009 is clear (no ambiguities, all requirements specified)
- [ ] PRD clarifying questions answered in documentation
- [ ] Issue #169 comment updated with link to completed governance docs
