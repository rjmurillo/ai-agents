# Test parent shell impact on pwsh spawn time
# This script should be run from different parent shells to compare

param(
    [string]$ShellContext = "unknown"
)

Write-Host "`n=== Parent Shell Impact Test ===" -ForegroundColor Cyan
Write-Host "Context: $ShellContext" -ForegroundColor Yellow
Write-Host "Testing 20 iterations...`n" -ForegroundColor Gray

# Get environment stats
$envVarCount = (Get-ChildItem Env:).Count
$pathLength = $env:PATH.Length
$pathEntries = ($env:PATH -split ';').Count

Write-Host "Environment Profile:" -ForegroundColor White
Write-Host "  Variables: $envVarCount" -ForegroundColor Gray
Write-Host "  PATH length: $pathLength chars" -ForegroundColor Gray
Write-Host "  PATH entries: $pathEntries" -ForegroundColor Gray
Write-Host ""

# Test pwsh spawn with -NoProfile
$times = @()
for ($i = 1; $i -le 20; $i++) {
    $time = Measure-Command {
        pwsh -NoProfile -Command 'exit 0'
    } | Select-Object -ExpandProperty TotalMilliseconds
    $times += $time
}

$avg = ($times | Measure-Object -Average).Average
$min = ($times | Measure-Object -Minimum).Minimum
$max = ($times | Measure-Object -Maximum).Maximum
$stdDev = [math]::Sqrt((($times | ForEach-Object { ($_ - $avg) * ($_ - $avg) } | Measure-Object -Sum).Sum) / $times.Count)

Write-Host "=== Results (20 iterations) ===" -ForegroundColor Cyan
[PSCustomObject]@{
    'Context' = $ShellContext
    'Average (ms)' = [math]::Round($avg, 2)
    'Min (ms)' = [math]::Round($min, 2)
    'Max (ms)' = [math]::Round($max, 2)
    'Std Dev' = [math]::Round($stdDev, 2)
} | Format-Table -AutoSize

Write-Host "=== Impact on Claude Sessions ===" -ForegroundColor Cyan
Write-Host "50 pwsh calls (typical session):" -ForegroundColor White
Write-Host "  Total time: $([math]::Round($avg * 50 / 1000, 1))s" -ForegroundColor Yellow
Write-Host "  Per call: $([math]::Round($avg, 0))ms" -ForegroundColor Gray

# Export for comparison
$result = @{
    Context = $ShellContext
    Average = $avg
    Min = $min
    Max = $max
    StdDev = $stdDev
    EnvVars = $envVarCount
    PathLength = $pathLength
    PathEntries = $pathEntries
    Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
}

$result | ConvertTo-Json | Out-File -FilePath "shell-benchmark-$ShellContext.json" -Encoding UTF8
Write-Host "`nResults saved to: shell-benchmark-$ShellContext.json" -ForegroundColor Green
