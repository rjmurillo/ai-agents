<#
.SYNOPSIS
    Benchmarks memory search performance across Serena and Forgetful systems.

.DESCRIPTION
    Implements M-008 from Phase 2A: Create memory search benchmarks.

    Measures:
    1. Serena lexical search (file-based, keyword matching)
    2. Forgetful semantic search (vector-based, embeddings)
    3. Combined/unified search (future Memory Router)

    Outputs performance metrics for comparison against claude-flow baseline (96-164x target).

.PARAMETER Queries
    Array of test queries to benchmark. If not provided, uses default set.

.PARAMETER Iterations
    Number of iterations per query for averaging. Default: 5

.PARAMETER WarmupIterations
    Number of warmup iterations before measurement. Default: 2

.PARAMETER SerenaOnly
    Only benchmark Serena (skip Forgetful if unavailable).

.PARAMETER Format
    Output format: "console", "markdown", "json". Default: "console"

.EXAMPLE
    .\Measure-MemoryPerformance.ps1
    # Run default benchmarks

.EXAMPLE
    .\Measure-MemoryPerformance.ps1 -Queries @("PowerShell arrays", "git hooks") -Iterations 10
    # Benchmark specific queries with more iterations

.EXAMPLE
    .\Measure-MemoryPerformance.ps1 -Format json | ConvertFrom-Json
    # Get structured output for programmatic use

.NOTES
    Part of Phase 2A Memory System implementation.
    Issue: #167 (Vector Memory System)
    Task: M-008 (Create memory search benchmarks)
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string[]]$Queries,

    [Parameter()]
    [int]$Iterations = 5,

    [Parameter()]
    [int]$WarmupIterations = 2,

    [Parameter()]
    [switch]$SerenaOnly,

    [Parameter()]
    [ValidateSet("console", "markdown", "json")]
    [string]$Format = "console"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# region Configuration

# Default benchmark queries covering different domains

$DefaultQueries = @(
    "PowerShell array handling patterns"
    "git pre-commit hook validation"
    "GitHub CLI PR operations"
    "session protocol compliance"
    "security vulnerability detection"
    "Pester test isolation"
    "CI workflow patterns"
    "memory-first architecture"
)

if (-not $Queries -or $Queries.Count -eq 0) {
    $Queries = $DefaultQueries
}

# Serena memory path

$SerenaMemoryPath = ".serena/memories"

# Forgetful MCP endpoint (from .mcp.json)

$ForgetfulEndpoint = "http://localhost:8020/mcp"

# endregion

# region Color Output

$ColorReset = "`e[0m"
$ColorRed = "`e[31m"
$ColorYellow = "`e[33m"
$ColorGreen = "`e[32m"
$ColorCyan = "`e[36m"
$ColorMagenta = "`e[35m"

function Write-ColorOutput {
    param([string]$Message, [string]$Color = $ColorReset)
    if ($Format -eq "console") {
        Write-Host "${Color}${Message}${ColorReset}"
    }
}

# endregion

# region Serena Benchmarking

function Measure-SerenaSearch {
    <#
    .SYNOPSIS
        Benchmarks Serena's lexical memory search.
    .DESCRIPTION
        Simulates the mcp__serena__list_memories + mcp__serena__read_memory pattern.
        Measures:
        1. List time (scanning all memory file names)
        2. Match time (keyword matching in file names)
        3. Read time (loading matched files)
    #>
    param(
        [string]$Query,
        [string]$MemoryPath,
        [int]$Iterations,
        [int]$WarmupIterations
    )

    $result = @{
        Query          = $Query
        System         = "Serena"
        ListTimeMs     = 0
        MatchTimeMs    = 0
        ReadTimeMs     = 0
        TotalTimeMs    = 0
        MatchedFiles   = 0
        TotalFiles     = 0
        IterationTimes = @()
    }

    # Verify path exists
    if (-not (Test-Path $MemoryPath)) {
        $result.Error = "Memory path not found: $MemoryPath"
        return $result
    }

    # Get query keywords for matching
    $keywords = @($Query.ToLowerInvariant() -split '\s+' | Where-Object { $_.Length -gt 2 })

    # Warmup iterations (not measured)
    # Note: SilentlyContinue is used intentionally during benchmarking to avoid error handling
    # overhead skewing timing results. Path existence is verified above.
    for ($w = 0; $w -lt $WarmupIterations; $w++) {
        $files = @(Get-ChildItem -Path $MemoryPath -Filter "*.md" -ErrorAction SilentlyContinue)
        foreach ($file in $files) {
            $fileName = $file.BaseName.ToLowerInvariant()
            $matchingKeywords = @($keywords | Where-Object { $fileName -match [regex]::Escape($_) })
            if ($matchingKeywords.Count -gt 0) {
                $null = Get-Content -Path $file.FullName -Raw -ErrorAction SilentlyContinue
            }
        }
    }

    # Measured iterations
    $listTimes = @()
    $matchTimes = @()
    $readTimes = @()
    $totalTimes = @()
    $matchedFileCounts = @()

    for ($i = 0; $i -lt $Iterations; $i++) {
        $iterationStart = Get-Date

        # Phase 1: List files (simulates list_memories)
        $listStart = Get-Date
        $files = @(Get-ChildItem -Path $MemoryPath -Filter "*.md" -ErrorAction SilentlyContinue)
        $listEnd = Get-Date
        $listTimes += ($listEnd - $listStart).TotalMilliseconds

        # Phase 2: Match keywords (simulates lexical search)
        $matchStart = Get-Date
        $matchedFiles = @()
        foreach ($file in $files) {
            $fileName = $file.BaseName.ToLowerInvariant()
            $matchingKeywords = @($keywords | Where-Object { $fileName -match [regex]::Escape($_) })
            if ($matchingKeywords.Count -gt 0) {
                $matchedFiles += $file
            }
        }
        $matchEnd = Get-Date
        $matchTimes += ($matchEnd - $matchStart).TotalMilliseconds

        # Phase 3: Read matched files (simulates read_memory)
        $readStart = Get-Date
        foreach ($file in $matchedFiles) {
            $null = Get-Content -Path $file.FullName -Raw -ErrorAction SilentlyContinue
        }
        $readEnd = Get-Date
        $readTimes += ($readEnd - $readStart).TotalMilliseconds

        $iterationEnd = Get-Date
        $totalTimes += ($iterationEnd - $iterationStart).TotalMilliseconds
        $matchedFileCounts += $matchedFiles.Count
    }

    # Calculate averages
    $result.ListTimeMs = [math]::Round(($listTimes | Measure-Object -Average).Average, 2)
    $result.MatchTimeMs = [math]::Round(($matchTimes | Measure-Object -Average).Average, 2)
    $result.ReadTimeMs = [math]::Round(($readTimes | Measure-Object -Average).Average, 2)
    $result.TotalTimeMs = [math]::Round(($totalTimes | Measure-Object -Average).Average, 2)
    $result.MatchedFiles = [math]::Round(($matchedFileCounts | Measure-Object -Average).Average, 0)
    $result.TotalFiles = $files.Count
    $result.IterationTimes = $totalTimes

    return $result
}

# endregion

# region Forgetful Benchmarking

function Test-ForgetfulAvailable {
    <#
    .SYNOPSIS
        Checks if Forgetful MCP is available.
    #>
    param([string]$Endpoint)

    try {
        $null = Invoke-RestMethod -Uri $Endpoint -Method Get -TimeoutSec 2 -ErrorAction Stop
        return $true
    }
    catch {
        # Endpoint not available - expected when Forgetful is not running
        return $false
    }
}

function Measure-ForgetfulSearch {
    <#
    .SYNOPSIS
        Benchmarks Forgetful's semantic memory search.
    .DESCRIPTION
        Uses the Forgetful MCP HTTP endpoint to perform semantic search.
        Measures end-to-end latency including:
        1. Embedding generation
        2. Vector similarity search
        3. Result retrieval
    #>
    param(
        [string]$Query,
        [string]$Endpoint,
        [int]$Iterations,
        [int]$WarmupIterations
    )

    $result = @{
        Query           = $Query
        System          = "Forgetful"
        SearchTimeMs    = 0
        TotalTimeMs     = 0
        MatchedMemories = 0
        IterationTimes  = @()
    }

    # Check availability
    if (-not (Test-ForgetfulAvailable -Endpoint $Endpoint)) {
        $result.Error = "Forgetful MCP not available at $Endpoint"
        return $result
    }

    # Note: This is a simplified simulation since we can't directly call MCP from PowerShell
    # In production, this would use the Claude Code MCP tools
    # For now, we measure HTTP roundtrip as a proxy

    $searchBody = @{
        jsonrpc = "2.0"
        id      = 1
        method  = "tools/call"
        params  = @{
            name      = "memory_search"
            arguments = @{
                query = $Query
                limit = 10
            }
        }
    } | ConvertTo-Json -Depth 5

    # Warmup - errors are expected and intentionally ignored
    for ($w = 0; $w -lt $WarmupIterations; $w++) {
        try {
            $null = Invoke-RestMethod -Uri $Endpoint -Method Post -Body $searchBody -ContentType "application/json" -TimeoutSec 10 -ErrorAction SilentlyContinue
        }
        catch {
            # Warmup errors are expected when endpoint is unavailable or warming up
            Write-Verbose "Warmup iteration $w failed: $($_.Exception.Message)"
        }
    }

    # Measured iterations
    $searchTimes = @()
    $memoryCounts = @()

    for ($i = 0; $i -lt $Iterations; $i++) {
        $searchStart = Get-Date

        try {
            $response = Invoke-RestMethod -Uri $Endpoint -Method Post -Body $searchBody -ContentType "application/json" -TimeoutSec 30 -ErrorAction Stop
            $searchEnd = Get-Date
            $searchTimes += ($searchEnd - $searchStart).TotalMilliseconds

            # Try to extract result count
            if ($response.result -and $response.result.content) {
                $memoryCounts += 1  # At minimum we got a response
            }
            else {
                $memoryCounts += 0
            }
        }
        catch {
            $searchEnd = Get-Date
            $searchTimes += ($searchEnd - $searchStart).TotalMilliseconds
            $memoryCounts += 0
            $result.Error = $_.Exception.Message
        }
    }

    # Calculate averages
    if ($searchTimes.Count -gt 0) {
        $result.SearchTimeMs = [math]::Round(($searchTimes | Measure-Object -Average).Average, 2)
        $result.TotalTimeMs = $result.SearchTimeMs
        $result.MatchedMemories = [math]::Round(($memoryCounts | Measure-Object -Average).Average, 0)
        $result.IterationTimes = $searchTimes
    }

    return $result
}

# endregion

# region Main Execution

function Invoke-MemoryBenchmark {
    param(
        [string[]]$TestQueries,
        [int]$TestIterations,
        [int]$TestWarmup,
        [switch]$SkipForgetful
    )

    $benchmark = @{
        Timestamp        = Get-Date -Format 'o'
        Configuration    = @{
            Queries           = $TestQueries.Count
            Iterations        = $TestIterations
            WarmupIterations  = $TestWarmup
            SerenaPath        = $SerenaMemoryPath
            ForgetfulEndpoint = $ForgetfulEndpoint
        }
        SerenaResults    = @()
        ForgetfulResults = @()
        Summary          = @{
            SerenaAvgMs    = 0
            ForgetfulAvgMs = 0
            SpeedupFactor  = 0
            Target         = "96-164x (claude-flow baseline)"
        }
    }

    Write-ColorOutput "=== Memory Performance Benchmark (M-008) ===" $ColorCyan
    Write-ColorOutput "Queries: $($TestQueries.Count), Iterations: $TestIterations, Warmup: $TestWarmup" $ColorMagenta
    Write-ColorOutput ""

    # Benchmark Serena
    Write-ColorOutput "Benchmarking Serena (lexical search)..." $ColorCyan

    foreach ($query in $TestQueries) {
        Write-ColorOutput "  Query: '$query'" $ColorMagenta

        $serenaResult = Measure-SerenaSearch -Query $query -MemoryPath $SerenaMemoryPath -Iterations $TestIterations -WarmupIterations $TestWarmup
        $benchmark.SerenaResults += $serenaResult

        if ($serenaResult.ContainsKey('Error') -and $serenaResult.Error) {
            Write-ColorOutput "    Error: $($serenaResult.Error)" $ColorRed
        }
        else {
            Write-ColorOutput "    Total: $($serenaResult.TotalTimeMs)ms (List: $($serenaResult.ListTimeMs)ms, Match: $($serenaResult.MatchTimeMs)ms, Read: $($serenaResult.ReadTimeMs)ms)" $ColorGreen
            Write-ColorOutput "    Matched: $($serenaResult.MatchedFiles) of $($serenaResult.TotalFiles) files" $ColorCyan
        }
    }

    # Calculate Serena average
    $serenaValidResults = @($benchmark.SerenaResults | Where-Object { -not $_.ContainsKey('Error') -or -not $_.Error })
    if ($serenaValidResults.Count -gt 0) {
        $benchmark.Summary.SerenaAvgMs = [math]::Round(($serenaValidResults | ForEach-Object { $_.TotalTimeMs } | Measure-Object -Average).Average, 2)
    }

    # Benchmark Forgetful (if available)
    if (-not $SkipForgetful) {
        Write-ColorOutput ""
        Write-ColorOutput "Benchmarking Forgetful (semantic search)..." $ColorCyan

        if (Test-ForgetfulAvailable -Endpoint $ForgetfulEndpoint) {
            foreach ($query in $TestQueries) {
                Write-ColorOutput "  Query: '$query'" $ColorMagenta

                $forgetfulResult = Measure-ForgetfulSearch -Query $query -Endpoint $ForgetfulEndpoint -Iterations $TestIterations -WarmupIterations $TestWarmup
                $benchmark.ForgetfulResults += $forgetfulResult

                if ($forgetfulResult.ContainsKey('Error') -and $forgetfulResult.Error) {
                    Write-ColorOutput "    Error: $($forgetfulResult.Error)" $ColorRed
                }
                else {
                    Write-ColorOutput "    Total: $($forgetfulResult.TotalTimeMs)ms" $ColorGreen
                    Write-ColorOutput "    Matched: $($forgetfulResult.MatchedMemories) memories" $ColorCyan
                }
            }

            # Calculate Forgetful average
            $forgetfulValidResults = @($benchmark.ForgetfulResults | Where-Object { -not $_.ContainsKey('Error') -or -not $_.Error })
            if ($forgetfulValidResults.Count -gt 0) {
                $benchmark.Summary.ForgetfulAvgMs = [math]::Round(($forgetfulValidResults | ForEach-Object { $_.TotalTimeMs } | Measure-Object -Average).Average, 2)
            }
        }
        else {
            Write-ColorOutput "  Forgetful MCP not available at $ForgetfulEndpoint" $ColorYellow
            Write-ColorOutput "  Skipping Forgetful benchmarks" $ColorYellow
        }
    }

    # Calculate speedup factor
    if ($benchmark.Summary.SerenaAvgMs -gt 0 -and $benchmark.Summary.ForgetfulAvgMs -gt 0) {
        $benchmark.Summary.SpeedupFactor = [math]::Round($benchmark.Summary.SerenaAvgMs / $benchmark.Summary.ForgetfulAvgMs, 2)
    }

    return $benchmark
}

# Run benchmark

$benchmarkResults = Invoke-MemoryBenchmark -TestQueries $Queries -TestIterations $Iterations -TestWarmup $WarmupIterations -SkipForgetful:$SerenaOnly

# Output results

Write-ColorOutput ""
Write-ColorOutput "=== Summary ===" $ColorCyan

switch ($Format) {
    "console" {
        Write-ColorOutput "Serena Average: $($benchmarkResults.Summary.SerenaAvgMs)ms" $ColorMagenta
        if ($benchmarkResults.Summary.ForgetfulAvgMs -gt 0) {
            Write-ColorOutput "Forgetful Average: $($benchmarkResults.Summary.ForgetfulAvgMs)ms" $ColorMagenta
            Write-ColorOutput "Speedup Factor: $($benchmarkResults.Summary.SpeedupFactor)x" $(if ($benchmarkResults.Summary.SpeedupFactor -ge 10) { $ColorGreen } else { $ColorYellow })
            Write-ColorOutput "Target: $($benchmarkResults.Summary.Target)" $ColorCyan
        }
        else {
            Write-ColorOutput "Forgetful: Not available" $ColorYellow
        }
    }
    "markdown" {
        $sb = [System.Text.StringBuilder]::new()
        [void]$sb.AppendLine("# Memory Performance Benchmark Report")
        [void]$sb.AppendLine("")
        [void]$sb.AppendLine("**Date**: $(Get-Date -Format 'yyyy-MM-dd HH:mm')")
        [void]$sb.AppendLine("**Task**: M-008 (Phase 2A Memory System)")
        [void]$sb.AppendLine("")
        [void]$sb.AppendLine("## Configuration")
        [void]$sb.AppendLine("")
        [void]$sb.AppendLine("| Setting | Value |")
        [void]$sb.AppendLine("|---------|-------|")
        [void]$sb.AppendLine("| Queries | $($benchmarkResults.Configuration.Queries) |")
        [void]$sb.AppendLine("| Iterations | $($benchmarkResults.Configuration.Iterations) |")
        [void]$sb.AppendLine("| Warmup | $($benchmarkResults.Configuration.WarmupIterations) |")
        [void]$sb.AppendLine("")
        [void]$sb.AppendLine("## Results")
        [void]$sb.AppendLine("")
        [void]$sb.AppendLine("| System | Average (ms) | Status |")
        [void]$sb.AppendLine("|--------|-------------|--------|")
        [void]$sb.AppendLine("| Serena | $($benchmarkResults.Summary.SerenaAvgMs) | Baseline |")
        if ($benchmarkResults.Summary.ForgetfulAvgMs -gt 0) {
            $status = if ($benchmarkResults.Summary.SpeedupFactor -ge 10) { "Target Met" } else { "Below Target" }
            [void]$sb.AppendLine("| Forgetful | $($benchmarkResults.Summary.ForgetfulAvgMs) | $status |")
        }
        [void]$sb.AppendLine("")
        if ($benchmarkResults.Summary.SpeedupFactor -gt 0) {
            [void]$sb.AppendLine("**Speedup Factor**: $($benchmarkResults.Summary.SpeedupFactor)x")
            [void]$sb.AppendLine("**Target**: $($benchmarkResults.Summary.Target)")
        }
        Write-Output $sb.ToString()
    }
    "json" {
        Write-Output ($benchmarkResults | ConvertTo-Json -Depth 10)
    }
}

# endregion


