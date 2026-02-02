# CodeQL Integration Rollout Checklist

This checklist provides a systematic approach to deploying and validating the CodeQL security analysis integration across all tiers.

## Pre-Rollout

Verify all prerequisites are met before beginning rollout:

- [ ] **Implementation Complete**: All phases of CodeQL integration implemented
  - [ ] CLI installation scripts (`Install-CodeQL.ps1`, `Install-CodeQLIntegration.ps1`)
  - [ ] Scanning scripts (`Invoke-CodeQLScan.ps1`, `Test-CodeQLConfig.ps1`, `Get-CodeQLDiagnostics.ps1`)
  - [ ] Shared configurations (`.github/codeql/codeql-config.yml`, `codeql-config-quick.yml`)
  - [ ] CI/CD workflows (`.github/workflows/codeql-analysis.yml`, `test-codeql-integration.yml`)
  - [ ] VSCode integration (`.vscode/tasks.json`, `.vscode/extensions.json`, `.vscode/settings.json`)
  - [ ] Claude Code skill (`.claude/skills/codeql-scan/`)
  - [ ] PostToolUse hook (`.claude/hooks/PostToolUse/Invoke-CodeQLQuickScan.ps1`)

- [ ] **All Pester Tests Passing**: Unit and integration tests verified
  - [ ] `tests/Install-CodeQL.Tests.ps1` passing
  - [ ] `tests/Invoke-CodeQLScan.Tests.ps1` passing
  - [ ] `tests/CodeQL-Integration.Tests.ps1` passing
  - [ ] `tests/Test-CodeQLRollout.Tests.ps1` passing
  - [ ] Run: `pwsh ./build/scripts/Invoke-PesterTests.ps1`

- [ ] **Documentation Reviewed**: All documentation complete and accurate
  - [ ] User guide: `docs/codeql-integration.md`
  - [ ] Architecture docs: `docs/codeql-architecture.md`
  - [ ] ADR-041: `.agents/architecture/ADR-041-codeql-integration.md`
  - [ ] AGENTS.md updated with CodeQL commands

- [ ] **ADR Approved**: ADR-041 reviewed and accepted
  - [ ] Multi-tier strategy rationale validated
  - [ ] Alternatives considered documented
  - [ ] Consequences understood and accepted
  - [ ] Related decisions linked

---

## Rollout Steps

### Step 1: Run Automated Validation

```bash
pwsh .codeql/scripts/Test-CodeQLRollout.ps1
```

**Expected Result**: All checks pass (45/45)

- [ ] **CLI Installation**:
  - [ ] CodeQL CLI exists at `.codeql/cli/codeql`
  - [ ] CLI version: v2.23.9 or later
  - [ ] CLI executable (Unix systems)

- [ ] **Configuration**:
  - [ ] Shared config exists (`.github/codeql/codeql-config.yml`)
  - [ ] Quick config exists (`.github/codeql/codeql-config-quick.yml`)
  - [ ] YAML syntax valid
  - [ ] Query packs resolvable

- [ ] **Scripts**:
  - [ ] All 5 required scripts exist
  - [ ] Scripts executable (Unix systems)
  - [ ] Pester tests exist (3 test files)

- [ ] **CI/CD Integration**:
  - [ ] CodeQL workflow exists (`.github/workflows/codeql-analysis.yml`)
  - [ ] Test workflow exists (`.github/workflows/test-codeql-integration.yml`)
  - [ ] SHA-pinned actions configured
  - [ ] Shared config referenced in workflow

- [ ] **Local Development**:
  - [ ] VSCode extensions configured
  - [ ] VSCode tasks configured
  - [ ] VSCode settings configured
  - [ ] Claude Code skill exists
  - [ ] Skill script executable

- [ ] **Automatic Scanning**:
  - [ ] PostToolUse hook exists
  - [ ] Hook script executable (Unix systems)
  - [ ] Quick config referenced by hook

- [ ] **Documentation**:
  - [ ] User docs exist
  - [ ] Developer docs exist
  - [ ] ADR exists
  - [ ] AGENTS.md updated

- [ ] **Tests**:
  - [ ] Unit tests discoverable
  - [ ] Integration tests exist

- [ ] **Gitignore**:
  - [ ] CodeQL directories excluded (`.codeql/cli/`, `.codeql/db/`, `.codeql/results/`, `.codeql/logs/`)

### Step 2: Verify CLI Installation

```bash
pwsh .codeql/scripts/Install-CodeQL.ps1 -AddToPath
.codeql/cli/codeql version
```

**Expected Output**:

```text
CodeQL command-line toolchain release 2.23.9.
```

- [ ] CLI downloaded successfully
- [ ] CLI version correct
- [ ] CLI executable works

### Step 3: Test Full Scan

Run a full repository scan on a sample repository:

```bash
pwsh .codeql/scripts/Invoke-CodeQLScan.ps1
```

**Expected Results**:

- [ ] Languages auto-detected (Python, GitHub Actions)
- [ ] Databases created for each language
- [ ] Analysis completed successfully
- [ ] SARIF output generated at `.codeql/results/codeql-results.sarif`
- [ ] Scan completed within 60 seconds
- [ ] Exit code 0 (success)

**If Failures**:

- Check diagnostics: `pwsh .codeql/scripts/Get-CodeQLDiagnostics.ps1`
- Validate configuration: `pwsh .codeql/scripts/Test-CodeQLConfig.ps1`
- Review logs: `.codeql/logs/`

### Step 4: Test Quick Scan with Caching

Run a second scan to verify caching works:

```bash
pwsh .codeql/scripts/Invoke-CodeQLScan.ps1 -UseCache
```

**Expected Results**:

- [ ] Cached databases reused
- [ ] Scan completed within 20 seconds (much faster than first scan)
- [ ] Results consistent with full scan
- [ ] Exit code 0 (success)

### Step 5: Verify VSCode Integration

Open the repository in VSCode:

- [ ] **Extensions Recommended**:
  - [ ] VSCode prompts to install CodeQL extension
  - [ ] Extension can be installed from recommendations

- [ ] **Tasks Available**:
  - [ ] Run task: "CodeQL: Full Scan" (`Ctrl+Shift+P` -> "Tasks: Run Task")
  - [ ] Task executes successfully
  - [ ] Results appear in terminal

- [ ] **Settings Applied**:
  - [ ] CodeQL CLI path configured
  - [ ] CodeQL extension recognizes CLI

### Step 6: Test Claude Code Skill

In Claude Code session:

```bash
/codeql-scan
```

**Or direct invocation**:

```bash
pwsh .claude/skills/codeql-scan/scripts/Invoke-CodeQLScanSkill.ps1 -Operation full
```

**Expected Results**:

- [ ] Skill loads without errors
- [ ] Scan executes successfully
- [ ] Results presented clearly
- [ ] Exit code 0 (success)

### Step 7: Verify PostToolUse Hook

Trigger the hook by editing a Python or Actions file:

1. Edit a `.py` or `.github/workflows/*.yml` file
2. Observe console output after save

**Expected Results**:

- [ ] Hook triggers automatically after file edit
- [ ] Quick scan executes (within 30 seconds)
- [ ] Security warnings displayed (if any findings)
- [ ] Non-blocking (can continue working immediately)
- [ ] Graceful degradation if CLI unavailable

**Test Graceful Degradation**:

```bash
# Temporarily rename CLI to test fallback
mv .codeql/cli/codeql .codeql/cli/codeql.bak

# Edit a Python file - hook should gracefully skip scan

# Restore CLI
mv .codeql/cli/codeql.bak .codeql/cli/codeql
```

- [ ] Hook does not crash when CLI unavailable
- [ ] Workflow continues uninterrupted

### Step 8: Test CI/CD Workflow

Create a test PR to validate CI integration:

```bash
# Create test branch
git checkout -b test/codeql-validation

# Make a small change
echo "# Test comment" >> README.md
git add README.md
git commit -m "test: verify CodeQL CI integration"

# Push and create PR
git push -u origin test/codeql-validation
gh pr create --title "Test: CodeQL CI Integration" --body "Verify CodeQL workflow runs successfully"
```

**Expected Results**:

- [ ] **Workflow Triggers**:
  - [ ] CodeQL Analysis workflow runs automatically
  - [ ] Workflow completes within 5 minutes

- [ ] **Workflow Steps**:
  - [ ] Checkout step succeeds
  - [ ] Initialize CodeQL step succeeds
  - [ ] Autobuild step succeeds (or manual build)
  - [ ] Perform CodeQL Analysis step succeeds
  - [ ] Upload SARIF step succeeds

- [ ] **Results**:
  - [ ] PR check shows green (or red if findings detected)
  - [ ] SARIF uploaded to Security tab
  - [ ] Results viewable in GitHub UI

- [ ] **Blocking Behavior** (if critical findings):
  - [ ] PR cannot be merged until resolved
  - [ ] Clear error message shown

### Step 9: Review SARIF Output

Examine SARIF results:

```bash
cat .codeql/results/codeql-results.sarif | jq
```

**Verify**:

- [ ] Valid SARIF 2.1.0 format
- [ ] Contains runs for each scanned language
- [ ] Results include rule ID, message, location
- [ ] Severity levels populated (error, warning, note)
- [ ] No sensitive information leaked (credentials, secrets)

---

## Post-Rollout

### Monitor First PR

After rollout, monitor the next production PR:

- [ ] **CodeQL Analysis Runs**:
  - [ ] Workflow executes automatically
  - [ ] Completes successfully (no timeouts)
  - [ ] Results uploaded to Security tab

- [ ] **Blocking Behavior Verified**:
  - [ ] Critical findings block merge (if any found)
  - [ ] Warning/note findings allow merge

- [ ] **Developer Experience**:
  - [ ] Results clear and actionable
  - [ ] False positives minimal (< 10%)
  - [ ] Performance acceptable (< 5 minute PR delay)

### Verify SARIF Upload

Check GitHub Security tab:

- [ ] Navigate to repository -> Security -> Code scanning alerts
- [ ] Verify CodeQL results appear
- [ ] Check alert details are complete (location, recommendation, severity)
- [ ] Verify alerts can be dismissed with reason

### Validate Performance

Check scan times across all tiers:

| Tier | Target | Actual | Status |
|------|--------|--------|--------|
| **Full Scan (CI)** | < 60s | ______ | [ ] PASS |
| **Quick Scan (Local)** | < 20s | ______ | [ ] PASS |
| **Hook Scan (Auto)** | < 30s | ______ | [ ] PASS |

**If timeouts occur**:

- [ ] Check database cache is working
- [ ] Verify query pack selection (quick vs full)
- [ ] Consider excluding large paths
- [ ] Review `.codeql/logs/` for bottlenecks

### Collect Developer Feedback

Survey team members:

- [ ] **Ease of Use**:
  - [ ] Installation process clear?
  - [ ] Documentation sufficient?
  - [ ] VSCode integration helpful?

- [ ] **Value**:
  - [ ] Findings relevant?
  - [ ] False positive rate acceptable?
  - [ ] Caught real issues?

- [ ] **Performance**:
  - [ ] Scan times acceptable?
  - [ ] Hook intrusive or helpful?
  - [ ] CI delay tolerable?

---

## Success Criteria

Mark rollout as successful when ALL criteria met:

### Functional Criteria

- [x] **All Validation Checks Pass**: `Test-CodeQLRollout.ps1` returns 45/45 checks passed
- [ ] **CI/CD Workflow Completes**: First production PR shows green check for CodeQL
- [ ] **SARIF Upload Successful**: Results visible in GitHub Security tab
- [ ] **Local Development Works**: At least one developer successfully runs local scan
- [ ] **Hook Functions**: PostToolUse hook executes without errors (or gracefully degrades)

### Performance Criteria

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| **Full Scan Duration** | < 60s | ______ | [ ] |
| **Quick Scan Duration** | < 20s | ______ | [ ] |
| **Hook Scan Duration** | < 30s | ______ | [ ] |
| **Cache Hit Rate** | > 70% | ______ | [ ] |
| **False Positive Rate** | < 20% | ______ | [ ] |

### Adoption Criteria

- [ ] **Documentation Accessible**: At least 3 team members aware of CodeQL integration
- [ ] **Local Usage**: At least 3 developers run local scan within first week
- [ ] **Skill Adoption**: At least 1 developer uses `/codeql-scan` skill
- [ ] **Zero Incidents**: No blocked PRs due to integration errors (findings are expected)

### Quality Criteria

- [ ] **No False Positives in First 3 PRs**: Or < 10% of total findings are false positives
- [ ] **Real Issues Found**: At least 1 legitimate security issue caught (validates value)
- [ ] **Developer Satisfaction**: Feedback generally positive (no major complaints)

---

## Rollback Plan

If critical issues arise, follow this rollback procedure:

### Immediate Rollback (Emergency)

**If CI/CD blocking all PRs incorrectly**:

```bash
# Disable CodeQL workflow
gh workflow disable codeql-analysis.yml
```

**If PostToolUse hook causing crashes**:

```bash
# Temporarily disable hook
mv .claude/hooks/PostToolUse/Invoke-CodeQLQuickScan.ps1 .claude/hooks/PostToolUse/Invoke-CodeQLQuickScan.ps1.disabled
```

### Partial Rollback

**Keep Tier 2 (Local), disable Tier 1 (CI) and Tier 3 (Hook)**:

- [ ] Disable CodeQL workflow: `gh workflow disable codeql-analysis.yml`
- [ ] Disable PostToolUse hook: Rename or remove hook script
- [ ] Keep local development tools (VSCode tasks, skill) for opt-in usage

### Full Rollback

**Remove all CodeQL integration**:

```bash
# Remove workflows
rm .github/workflows/codeql-analysis.yml
rm .github/workflows/test-codeql-integration.yml

# Remove configurations
rm -r .github/codeql

# Remove scripts
rm -r .codeql/scripts

# Remove CLI
rm -r .codeql/cli

# Remove VSCode integration
# (Optional - doesn't hurt to keep)

# Remove Claude integration
rm -r .claude/skills/codeql-scan
rm .claude/hooks/PostToolUse/Invoke-CodeQLQuickScan.ps1

# Commit rollback
git add .
git commit -m "revert: remove CodeQL integration"
git push
```

---

## Related Documentation

- **User Guide**: [docs/codeql-integration.md](./codeql-integration.md)
- **Architecture**: [docs/codeql-architecture.md](./codeql-architecture.md)
- **ADR**: [.agents/architecture/ADR-041-codeql-integration.md](../.agents/architecture/ADR-041-codeql-integration.md)
- **Validation Script**: [.codeql/scripts/Test-CodeQLRollout.ps1](../.codeql/scripts/Test-CodeQLRollout.ps1)

---

## Notes

**Rollout Date**: _______________

**Performed By**: _______________

**Approver**: _______________

**Issues Encountered**:

---

**Final Status**: [ ] SUCCESS [ ] PARTIAL [ ] ROLLBACK

**Completion Date**: _______________
