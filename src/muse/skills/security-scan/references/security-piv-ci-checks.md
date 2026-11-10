# PIV CI Environment Checks

Loaded by the `security` agent when it writes the CI check request in Post-Implementation Verification. The agent cannot run these commands: it asks the caller to run them and verifies the returned output. Take the security test command from the target repository first; these steps apply only when the target has the capability.

```powershell
# Set CI environment
$env:GITHUB_ACTIONS = 'true'
$env:CI = 'true'

# Verify Git hook manager configuration
uv run --frozen lefthook validate
if ($LASTEXITCODE -ne 0) {
    throw "[FAIL] Lefthook configuration validation failed"
}
Write-Host "[PASS] Hook payload syntax and Lefthook configuration validated"

# Check for hardcoded secrets in staged changes
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "[FAIL] git command not found. Install Git and ensure it's in PATH."
}

$diff = git diff --cached 2>&1
if ($LASTEXITCODE -ne 0) {
    $gitError = ($diff | Out-String).Trim()
    throw "[FAIL] git diff --cached failed (exit code: $LASTEXITCODE). Error: $gitError. Common causes: not in a git repository, corrupted index, or permission issues."
}

if ($diff -match '(api_key|password|secret|token)\s*[:=]\s*[''"][^''"]+[''"]') {
    throw "[FAIL] Hardcoded secret detected in staged changes. Remove credentials before committing."
}
Write-Host "[PASS] No hardcoded secrets detected in staged changes"

# Verify no environment variable leaks
$envPatterns = @('\$env:[A-Z0-9_]+\s*=\s*[''"][^''"]+[''"]')
try {
    $envMatches = Get-ChildItem -Recurse -Include *.ps1 -ErrorAction Stop |
        Select-String -Pattern $envPatterns

    if ($envMatches) {
        foreach ($match in $envMatches) {
            Write-Warning "[FAIL] Hardcoded env var found: $($match.Path):$($match.LineNumber)"
        }
        throw [System.Management.Automation.PSInvalidOperationException]::new("Hardcoded environment variable assignments detected. This is a security risk. Please remove them.")
    } else {
        Write-Host "[PASS] No hardcoded environment variables detected"
    }
}
catch {
    throw "Failed to scan for environment variable leaks: $_"
}
```
