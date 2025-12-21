# Session Protocol Compliance Analysis Script
# Analyzes all 2025-12-20 sessions for protocol compliance

$sessions = Get-ChildItem -Path ".agents/sessions" -Filter "2025-12-20-session-*.md"

$results = foreach ($session in $sessions) {
    $content = Get-Content $session.FullName -Raw

    # Check for Session End section
    $hasSessionEnd = $content -match "## Session End"

    # Check for HANDOFF.md update checkbox
    $hasHandoffUpdate = $content -match "\[x\].*Update.*HANDOFF\.md" -or $content -match "Update.*HANDOFF\.md.*\[x\]"

    # Check for markdown lint checkbox
    $hasLint = $content -match "\[x\].*markdown lint" -or $content -match "markdown lint.*\[x\]"

    # Check for commit checkbox
    $hasCommit = $content -match "\[x\].*Commit.*changes" -or $content -match "Commit SHA:.*[a-f0-9]{7}"

    # Check for Serena initialization
    $hasSerenaActivate = $content -match "\[x\].*mcp__serena__activate_project" -or $content -match "Serena Initialization - N/A"

    [PSCustomObject]@{
        Session = $session.Name
        HasSessionEnd = $hasSessionEnd
        HandoffUpdated = $hasHandoffUpdate
        LintRan = $hasLint
        ChangesCommitted = $hasCommit
        SerenaInitialized = $hasSerenaActivate
        PassedSessionEnd = $hasSessionEnd -and $hasHandoffUpdate -and $hasLint -and $hasCommit
    }
}

# Summary stats
$total = $results.Count
$passedSessionEnd = ($results | Where-Object PassedSessionEnd).Count
$failedSessionEnd = $total - $passedSessionEnd

$handoffFailures = ($results | Where-Object { -not $_.HandoffUpdated }).Count
$lintFailures = ($results | Where-Object { -not $_.LintRan }).Count
$commitFailures = ($results | Where-Object { -not $_.ChangesCommitted }).Count
$serenaFailures = ($results | Where-Object { -not $_.SerenaInitialized }).Count

Write-Host "`n=== SESSION PROTOCOL COMPLIANCE REPORT ===" -ForegroundColor Cyan
Write-Host "`nTotal Sessions: $total"
Write-Host "Passed Session End Protocol: $passedSessionEnd ($([math]::Round($passedSessionEnd/$total*100,1))%)" -ForegroundColor Green
Write-Host "Failed Session End Protocol: $failedSessionEnd ($([math]::Round($failedSessionEnd/$total*100,1))%)" -ForegroundColor Red

Write-Host "`n=== FAILURE BREAKDOWN ===" -ForegroundColor Yellow
Write-Host "HANDOFF.md not updated: $handoffFailures sessions"
Write-Host "Markdown lint not run: $lintFailures sessions"
Write-Host "Changes not committed: $commitFailures sessions"
Write-Host "Serena not initialized: $serenaFailures sessions"

Write-Host "`n=== DETAILED RESULTS ===" -ForegroundColor Cyan
$results | Format-Table -AutoSize

Write-Host "`n=== FAILED SESSIONS ===" -ForegroundColor Red
$results | Where-Object { -not $_.PassedSessionEnd } | Select-Object Session | Format-Table

Write-Host "`n=== PASSED SESSIONS ===" -ForegroundColor Green
$results | Where-Object PassedSessionEnd | Select-Object Session | Format-Table
