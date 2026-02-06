<#
.SYNOPSIS
    Unified memory access layer with Serena-first routing and Forgetful augmentation.

.DESCRIPTION
    Implements ADR-037 Memory Router Architecture for Phase 2A.
    Provides a unified interface for memory search across:
    - Serena (lexical, file-based, always available)
    - Forgetful (semantic, vector-based, optional augmentation)

    Routing strategy:
    1. Always query Serena first (canonical source)
    2. If Forgetful available and not LexicalOnly, augment with semantic results
    3. Deduplicate using SHA-256 content hashing
    4. Return merged results with source attribution

.NOTES
    ADR: .agents/architecture/ADR-037-memory-router-architecture.md
    Task: M-003 (Phase 2A Memory System)
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

#region Module State

# Health check cache to avoid repeated TCP connections
$script:HealthCache = @{
    Available   = $false
    LastChecked = [datetime]::MinValue
    CacheTTL    = [timespan]::FromSeconds(30)
}

# Default configuration
$script:Config = @{
    SerenaPath       = ".serena/memories"
    ForgetfulPort    = 8020
    ForgetfulTimeout = 500  # milliseconds
    MaxResults       = 10
}

# File list cache to avoid repeated Get-ChildItem calls
$script:FileListCache = @{
    Path        = ""
    Files       = @()
    LowerNames  = [string[]]@()  # Pre-computed lowercase basenames for fast matching
    LastChecked = [datetime]::MinValue
    CacheTTL    = [timespan]::FromSeconds(10)
}

#endregion

#region Private Functions

function Get-ContentHash {
    <#
    .SYNOPSIS
        Computes SHA-256 hash of content for deduplication.

    .PARAMETER Content
        String content to hash.

    .OUTPUTS
        [string] 64-character lowercase hex hash.
    #>
    [CmdletBinding()]
    [OutputType([string])]
    param(
        [Parameter(Mandatory)]
        [AllowEmptyString()]
        [string]$Content
    )

    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Content)
    $hashBytes = [System.Security.Cryptography.SHA256]::HashData($bytes)
    return [System.BitConverter]::ToString($hashBytes).Replace("-", "").ToLowerInvariant()
}

function Invoke-SerenaSearch {
    <#
    .SYNOPSIS
        Performs lexical search across Serena memory files.

    .DESCRIPTION
        Searches .serena/memories/ for files matching query keywords.
        Scoring: based on percentage of query keywords matching in filename.
        Use -SkipContent to avoid file I/O and hashing for search-only queries.

    .PARAMETER Query
        Search query string.

    .PARAMETER MemoryPath
        Path to Serena memories directory.

    .PARAMETER MaxResults
        Maximum results to return.

    .PARAMETER SkipContent
        When set, skips file content reading and SHA-256 hashing.
        Content and Hash properties will be $null on returned objects.
        Use this for search-only queries where content is not needed.

    .OUTPUTS
        Array of [PSCustomObject] with: Name, Content, Source, Score, Path, Hash
    #>
    [CmdletBinding()]
    [OutputType([PSCustomObject[]])]
    param(
        [Parameter(Mandatory)]
        [string]$Query,

        [Parameter()]
        [string]$MemoryPath = ".serena/memories",

        [Parameter()]
        [int]$MaxResults = 10,

        [Parameter()]
        [switch]$SkipContent
    )

    $results = [System.Collections.Generic.List[PSCustomObject]]::new()

    # Verify path exists
    if (-not (Test-Path $MemoryPath)) {
        Write-Verbose "Memory path not found: $MemoryPath"
        return @()
    }

    # Extract keywords (>2 chars), avoid pipeline overhead
    $lowerQuery = $Query.ToLowerInvariant()
    $allTokens = $lowerQuery.Split(' ', [System.StringSplitOptions]::RemoveEmptyEntries)
    $keywords = [System.Collections.Generic.List[string]]::new()
    foreach ($token in $allTokens) {
        if ($token.Length -gt 2) { $keywords.Add($token) }
    }
    if ($keywords.Count -eq 0) {
        Write-Verbose "No valid keywords extracted from query"
        return @()
    }
    $keywordCount = $keywords.Count

    # Get memory files (cached for 10s to avoid repeated filesystem scans)
    $now = [datetime]::UtcNow
    $cacheValid = ($script:FileListCache.Path -eq $MemoryPath) -and
                  ($script:FileListCache.LastChecked -gt [datetime]::MinValue) -and
                  (($now - $script:FileListCache.LastChecked) -lt $script:FileListCache.CacheTTL)

    if ($cacheValid) {
        $files = $script:FileListCache.Files
        $lowerNames = $script:FileListCache.LowerNames
        Write-Verbose "Using cached file list ($($files.Count) files)"
    }
    else {
        try {
            $files = @(Get-ChildItem -Path $MemoryPath -Filter "*.md" -ErrorAction Stop)
        }
        catch {
            Write-Warning "Failed to enumerate memory files in '$MemoryPath': $($_.Exception.Message)"
            return @()
        }
        # Pre-compute lowercase basenames to avoid per-iteration string allocation
        $lowerNames = [string[]]::new($files.Count)
        for ($j = 0; $j -lt $files.Count; $j++) {
            $lowerNames[$j] = $files[$j].BaseName.ToLowerInvariant()
        }
        $script:FileListCache.Path = $MemoryPath
        $script:FileListCache.Files = $files
        $script:FileListCache.LowerNames = $lowerNames
        $script:FileListCache.LastChecked = $now
        Write-Verbose "Refreshed file list cache ($($files.Count) files)"
    }

    # Score each file by keyword matches using string Contains (faster than regex)
    $fileCount = $files.Count
    for ($idx = 0; $idx -lt $fileCount; $idx++) {
        $fileName = $lowerNames[$idx]
        $matchCount = 0
        foreach ($kw in $keywords) {
            if ($fileName.Contains($kw)) { $matchCount++ }
        }

        if ($matchCount -gt 0) {
            $score = [math]::Round(($matchCount / $keywordCount) * 100, 2)
            $currentFile = $files[$idx]

            if ($SkipContent) {
                $results.Add([PSCustomObject]@{
                    Name    = $currentFile.BaseName
                    Content = $null
                    Source  = "Serena"
                    Score   = $score
                    Path    = $currentFile.FullName
                    Hash    = $null
                })
            }
            else {
                try {
                    $content = Get-Content -Path $currentFile.FullName -Raw -ErrorAction Stop
                }
                catch {
                    Write-Warning "Failed to read memory file '$($currentFile.FullName)': $($_.Exception.Message)"
                    continue
                }

                $results.Add([PSCustomObject]@{
                    Name    = $currentFile.BaseName
                    Content = $content
                    Source  = "Serena"
                    Score   = $score
                    Path    = $currentFile.FullName
                    Hash    = Get-ContentHash -Content ($content ?? "")
                })
            }
        }
    }

    # Sort by score descending, limit results
    $sorted = @($results | Sort-Object -Property Score -Descending | Select-Object -First $MaxResults)

    Write-Verbose "Serena search returned $($sorted.Count) results"
    return $sorted
}

function Invoke-ForgetfulSearch {
    <#
    .SYNOPSIS
        Performs semantic search via Forgetful MCP HTTP endpoint.

    .DESCRIPTION
        Uses JSON-RPC 2.0 protocol via MCP (Model Context Protocol) tool invocation
        to call Forgetful's memory_search tool.
        Requires Forgetful MCP server running on configured port.

    .PARAMETER Query
        Search query string.

    .PARAMETER Endpoint
        HTTP endpoint URL (default: http://localhost:8020/mcp).

    .PARAMETER MaxResults
        Maximum results to return.

    .OUTPUTS
        Array of [PSCustomObject] with: Id, Name, Content, Source, Score, Hash
    #>
    [CmdletBinding()]
    [OutputType([PSCustomObject[]])]
    param(
        [Parameter(Mandatory)]
        [string]$Query,

        [Parameter()]
        [string]$Endpoint = "http://localhost:8020/mcp",

        [Parameter()]
        [int]$MaxResults = 10
    )

    $results = @()

    # Build JSON-RPC 2.0 request
    $requestBody = @{
        jsonrpc = "2.0"
        id      = 1
        method  = "tools/call"
        params  = @{
            name      = "memory_search"
            arguments = @{
                query = $Query
                limit = $MaxResults
            }
        }
    } | ConvertTo-Json -Depth 5

    try {
        $response = Invoke-RestMethod -Uri $Endpoint -Method Post `
            -Body $requestBody -ContentType "application/json" `
            -TimeoutSec 10 -ErrorAction Stop

        # Parse response - Forgetful returns results in specific format
        if ($response.result -and $response.result.content) {
            # MCP tool responses have content array
            foreach ($item in $response.result.content) {
                if ($item.type -eq "text" -and $item.text) {
                    # Parse the text content as JSON if it contains memories
                    try {
                        $memories = $item.text | ConvertFrom-Json -ErrorAction Stop
                        if ($memories -is [array]) {
                            foreach ($memory in $memories) {
                                $content = $memory.content ?? $memory.text ?? ""
                                $results += [PSCustomObject]@{
                                    Id      = $memory.id ?? 0
                                    Name    = $memory.title ?? "Unknown"
                                    Content = $content
                                    Source  = "Forgetful"
                                    Score   = $memory.score ?? $memory.similarity ?? 0
                                    Hash    = Get-ContentHash -Content $content
                                }
                            }
                        }
                    }
                    catch {
                        Write-Warning "Forgetful returned unparseable response: $($_.Exception.Message)"
                    }
                }
            }
        }
    }
    catch {
        Write-Warning "Forgetful search unavailable: $($_.Exception.Message)"
        return @()
    }

    Write-Verbose "Forgetful search returned $($results.Count) results"
    return $results
}

function Merge-MemoryResults {
    <#
    .SYNOPSIS
        Merges and deduplicates results from multiple sources.

    .DESCRIPTION
        Uses SHA-256 content hashing to identify duplicates.
        Serena results take priority (appear first, are the canonical source).

    .PARAMETER SerenaResults
        Results from Serena search.

    .PARAMETER ForgetfulResults
        Results from Forgetful search.

    .PARAMETER MaxResults
        Maximum total results to return.

    .OUTPUTS
        Array of merged, deduplicated results.
    #>
    [CmdletBinding()]
    [OutputType([PSCustomObject[]])]
    param(
        [Parameter()]
        [PSCustomObject[]]$SerenaResults = @(),

        [Parameter()]
        [PSCustomObject[]]$ForgetfulResults = @(),

        [Parameter()]
        [int]$MaxResults = 10
    )

    $merged = [System.Collections.Generic.List[PSCustomObject]]::new()
    $seenHashes = [System.Collections.Generic.HashSet[string]]::new()

    # Add Serena results first (canonical)
    foreach ($result in $SerenaResults) {
        if ($seenHashes.Add($result.Hash)) {
            $merged.Add($result)
        }
    }

    # Add unique Forgetful results
    foreach ($result in $ForgetfulResults) {
        if ($seenHashes.Add($result.Hash)) {
            $merged.Add($result)
        }
    }

    # Limit to max results
    return @($merged | Select-Object -First $MaxResults)
}

#endregion

#region Public Functions

function Test-ForgetfulAvailable {
    <#
    .SYNOPSIS
        Checks if Forgetful MCP is available with 30s caching.

    .DESCRIPTION
        Performs TCP health check to Forgetful port.
        Caches result for 30 seconds to minimize overhead.

    .PARAMETER Port
        Forgetful server port (default: 8020).

    .PARAMETER Force
        Skip cache and force fresh check.

    .OUTPUTS
        [bool] True if Forgetful is available.
    #>
    [CmdletBinding()]
    [OutputType([bool])]
    param(
        [Parameter()]
        [int]$Port = 8020,

        [Parameter()]
        [switch]$Force
    )

    # Check cache unless forced
    $now = [datetime]::UtcNow
    if (-not $Force -and $script:HealthCache.LastChecked -gt [datetime]::MinValue) {
        $cacheAge = $now - $script:HealthCache.LastChecked
        if ($cacheAge -lt $script:HealthCache.CacheTTL) {
            Write-Verbose "Using cached Forgetful availability: $($script:HealthCache.Available)"
            return $script:HealthCache.Available
        }
    }

    # Perform TCP check
    $available = $false
    $tcpClient = $null
    try {
        $tcpClient = New-Object System.Net.Sockets.TcpClient
        $connectTask = $tcpClient.ConnectAsync("localhost", $Port)
        if ($connectTask.Wait($script:Config.ForgetfulTimeout) -and $tcpClient.Connected) {
            $available = $true
        }
    }
    catch [System.Net.Sockets.SocketException] {
        Write-Debug "Forgetful not listening on port $Port"
    }
    catch {
        Write-Warning "Unexpected error checking Forgetful availability: $($_.Exception.Message)"
    }
    finally {
        if ($tcpClient) {
            $tcpClient.Close()
        }
    }

    # Update cache
    $script:HealthCache.Available = $available
    $script:HealthCache.LastChecked = $now

    Write-Verbose "Forgetful availability: $available (fresh check)"
    return $available
}

function Get-MemoryRouterStatus {
    <#
    .SYNOPSIS
        Returns diagnostic information about the Memory Router.

    .DESCRIPTION
        Reports on Serena and Forgetful availability, cache state,
        and configuration.

    .OUTPUTS
        [PSCustomObject] Status object with diagnostic info.
    #>
    [CmdletBinding()]
    [OutputType([PSCustomObject])]
    param()

    $serenaAvailable = Test-Path $script:Config.SerenaPath
    $forgetfulAvailable = Test-ForgetfulAvailable

    $cacheAge = if ($script:HealthCache.LastChecked -gt [datetime]::MinValue) {
        [math]::Round(([datetime]::UtcNow - $script:HealthCache.LastChecked).TotalSeconds, 2)
    }
    else { -1 }

    return [PSCustomObject]@{
        Serena          = @{
            Available = $serenaAvailable
            Path      = $script:Config.SerenaPath
        }
        Forgetful       = @{
            Available = $forgetfulAvailable
            Endpoint  = "http://localhost:$($script:Config.ForgetfulPort)/mcp"
        }
        Cache           = @{
            AgeSeconds = $cacheAge
            TTLSeconds = $script:HealthCache.CacheTTL.TotalSeconds
        }
        Configuration   = $script:Config
    }
}

function Search-Memory {
    <#
    .SYNOPSIS
        Unified memory search across Serena and Forgetful.

    .DESCRIPTION
        Main entry point for memory search per ADR-037.
        Routes queries through Serena-first, optionally augments with Forgetful.

    .PARAMETER Query
        Search query. Validated for safe characters only.

    .PARAMETER MaxResults
        Maximum results to return (1-100, default 10).

    .PARAMETER SemanticOnly
        Force Forgetful-only search (fails if unavailable).

    .PARAMETER LexicalOnly
        Force Serena-only search (skip Forgetful).

    .OUTPUTS
        Array of [PSCustomObject] with search results.
    #>
    [CmdletBinding()]
    [OutputType([PSCustomObject[]])]
    param(
        [Parameter(Mandatory, Position = 0)]
        [ValidatePattern('^[a-zA-Z0-9\s\-.,_()&:]+$')]
        [ValidateLength(1, 500)]
        [string]$Query,

        [Parameter()]
        [ValidateRange(1, 100)]
        [int]$MaxResults = 10,

        [Parameter()]
        [switch]$SemanticOnly,

        [Parameter()]
        [switch]$LexicalOnly
    )

    # Validate mutually exclusive switches
    if ($SemanticOnly -and $LexicalOnly) {
        throw "Cannot specify both -SemanticOnly and -LexicalOnly"
    }

    Write-Verbose "Search-Memory: Query='$Query', MaxResults=$MaxResults"

    $serenaResults = @()
    $forgetfulResults = @()

    # Semantic-only mode
    if ($SemanticOnly) {
        if (-not (Test-ForgetfulAvailable)) {
            throw "Forgetful is not available and -SemanticOnly was specified"
        }
        $forgetfulResults = Invoke-ForgetfulSearch -Query $Query -MaxResults $MaxResults
        return $forgetfulResults
    }

    # LexicalOnly: skip content reading and hashing entirely
    if ($LexicalOnly) {
        return Invoke-SerenaSearch -Query $Query -MaxResults $MaxResults -SkipContent
    }

    # Augmented mode: check Forgetful availability before deciding on content loading
    $forgetfulAvailable = Test-ForgetfulAvailable
    if (-not $forgetfulAvailable) {
        Write-Verbose "Forgetful unavailable, returning Serena-only results (fast path)"
        return Invoke-SerenaSearch -Query $Query -MaxResults $MaxResults -SkipContent
    }

    # Forgetful is available: need content/hashes for dedup during merge
    $serenaResults = Invoke-SerenaSearch -Query $Query -MaxResults $MaxResults
    $forgetfulResults = Invoke-ForgetfulSearch -Query $Query -MaxResults $MaxResults

    # Merge and deduplicate
    return Merge-MemoryResults -SerenaResults $serenaResults -ForgetfulResults $forgetfulResults -MaxResults $MaxResults
}

#endregion

# Export public functions
Export-ModuleMember -Function @(
    'Search-Memory',
    'Test-ForgetfulAvailable',
    'Get-MemoryRouterStatus'
)
