# CI Output Handling

## Skill-CI-ANSI-Disable-001: Disable ANSI in CI Mode (90%)

**Statement**: Disable ANSI codes in CI via NO_COLOR env var and PSStyle.OutputRendering PlainText.

**Evidence**: CI run 20324607494 - ANSI escape codes (0x1B) corrupted Pester XML report.

**Pattern**:

```powershell
# In test runner
if ($CI) {
    $env:NO_COLOR = '1'
    $env:TERM = 'dumb'
    if ($PSVersionTable.PSVersion.Major -ge 7) {
        $PSStyle.OutputRendering = 'PlainText'
    }
}
```

```powershell
# In scripts with color output
$NoColor = $env:NO_COLOR -or $env:TERM -eq 'dumb' -or $env:CI

if ($NoColor) {
    $ColorRed = ""
    $ColorGreen = ""
} else {
    $ColorRed = "`e[31m"
    $ColorGreen = "`e[32m"
}
```

**Standards**: [NO_COLOR](https://no-color.org/), TERM=dumb, PSStyle.OutputRendering

## Skill-CI-Output-001: Single-Line GitHub Actions Outputs (95%)

**Statement**: GitHub Actions outputs must be single-line; multi-line values break format.

**Evidence**: Session 04 - `copilot --version` outputs multiple lines, breaking "Invalid format".

```bash
# WRONG: Multi-line output
VERSION=$(copilot --version)
echo "version=$VERSION" >> $GITHUB_OUTPUT

# RIGHT: Extract single line
VERSION=$(copilot --version | head -1)
echo "version=$VERSION" >> $GITHUB_OUTPUT
```
