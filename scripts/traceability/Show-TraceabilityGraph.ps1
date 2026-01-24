param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if ($DryRun) {
    Write-Host "Dry-run test successful"
    exit 0
}

Write-Host "Script executed successfully"
exit 0
