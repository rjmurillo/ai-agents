# CI Environment Simulation

## Skill-CI-Environment-Testing-001: Local CI Simulation (88%)

**Statement**: Test scripts locally with temp paths and no auth to catch CI environment failures.

**Evidence**: CI run 20324607494 - All 4 test failures passed locally but failed in CI.

**Pattern**:

```powershell
function Test-InCIMode {
    # Simulate CI temp paths (Windows 8.3 short names)
    $originalTemp = $env:TEMP
    $env:TEMP = "C:\Users\RUNNER~1\AppData\Local\Temp"

    # Remove auth tokens
    $originalGH = $env:GH_TOKEN
    Remove-Item Env:\GH_TOKEN -ErrorAction SilentlyContinue

    try {
        Invoke-PesterTests -CI
    }
    finally {
        $env:TEMP = $originalTemp
        if ($originalGH) { $env:GH_TOKEN = $originalGH }
    }
}
```

**Environment Differences to Simulate**:

1. **Path normalization**: Windows 8.3 short names (RUNNER~1)
2. **External auth**: gh CLI, git credentials unavailable
3. **Output format**: XML reports instead of console
4. **Environment variables**: CI=true, NO_COLOR=1, TERM=dumb

**Pre-push Checklist**:

- [ ] Run tests with `-CI` flag
- [ ] Test with temp directory paths
- [ ] Test without gh CLI authentication
- [ ] Verify XML output is valid (no ANSI codes)
