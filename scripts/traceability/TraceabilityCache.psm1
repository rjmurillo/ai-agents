<#
.SYNOPSIS
    Caching module for traceability graph operations.

.DESCRIPTION
    Provides file-based caching for parsed spec data with automatic invalidation
    based on file modification times. Optimizes performance by avoiding repeated
    YAML parsing of unchanged spec files.

.NOTES
    Cache Strategy:
    - Per-file caching with modification time tracking
    - Automatic invalidation on file changes
    - In-memory cache for current session
    - Disk-based cache (.agents/.cache/traceability/) for cross-session persistence

    Performance Targets:
    - First run: Full parse (baseline)
    - Subsequent runs (no changes): <100ms for 100 specs
    - Partial changes: Only re-parse changed files
#>

$script:MemoryCache = @{}
$script:CacheDir = Join-Path $PSScriptRoot "../../.agents/.cache/traceability"

function Initialize-TraceabilityCache {
    <#
    .SYNOPSIS
        Initializes the cache directory structure.
    #>
    [CmdletBinding()]
    param()

    if (-not (Test-Path $script:CacheDir)) {
        New-Item -Path $script:CacheDir -ItemType Directory -Force | Out-Null
    }
}

function Get-CacheKey {
    <#
    .SYNOPSIS
        Generates a cache key from a file path.
    #>
    [CmdletBinding()]
    param([string]$FilePath)

    $relativePath = $FilePath -replace [regex]::Escape($PWD.Path), ''
    return $relativePath -replace '[\\/:*?"<>|]', '_'
}

function Get-TraceabilityFileHash {
    <#
    .SYNOPSIS
        Gets a fast hash of file metadata for cache validation.
    #>
    [CmdletBinding()]
    param([string]$FilePath)

    if (-not (Test-Path $FilePath)) {
        return $null
    }

    $file = Get-Item $FilePath
    # Use LastWriteTimeUtc + Length as a fast change detector
    return "$($file.LastWriteTimeUtc.Ticks)_$($file.Length)"
}

function Get-CachedSpec {
    <#
    .SYNOPSIS
        Retrieves a cached spec if valid, otherwise returns null.
    #>
    [CmdletBinding()]
    param(
        [string]$FilePath,
        [string]$CurrentHash
    )

    $cacheKey = Get-CacheKey -FilePath $FilePath

    # Check memory cache first
    if ($script:MemoryCache.ContainsKey($cacheKey)) {
        $cached = $script:MemoryCache[$cacheKey]
        if ($cached.hash -eq $CurrentHash) {
            return $cached.spec
        }
    }

    # Check disk cache
    $cacheFile = Join-Path $script:CacheDir "$cacheKey.json"
    if (Test-Path $cacheFile) {
        try {
            $cached = Get-Content -Path $cacheFile -Raw | ConvertFrom-Json
            if ($cached.hash -eq $CurrentHash) {
                $spec = @{
                    type = $cached.type
                    id = $cached.id
                    status = $cached.status
                    related = @($cached.related)
                    filePath = $FilePath
                }
                # Store in memory for faster subsequent access
                $script:MemoryCache[$cacheKey] = @{
                    hash = $CurrentHash
                    spec = $spec
                }
                return $spec
            }
        }
        catch {
            # Cache file corrupted, will re-parse
            Write-Verbose "Cache file corrupted for $FilePath, will re-parse"
        }
    }

    return $null
}

function Set-CachedSpec {
    <#
    .SYNOPSIS
        Caches a parsed spec to both memory and disk.
    #>
    [CmdletBinding(SupportsShouldProcess)]
    param(
        [string]$FilePath,
        [string]$FileHash,
        [hashtable]$Spec
    )

    Initialize-TraceabilityCache

    $cacheKey = Get-CacheKey -FilePath $FilePath

    # Store in memory
    $script:MemoryCache[$cacheKey] = @{
        hash = $FileHash
        spec = $Spec
    }

    # Store on disk (async write to avoid blocking)
    $cacheFile = Join-Path $script:CacheDir "$cacheKey.json"
    $cacheData = @{
        hash = $FileHash
        type = $Spec.type
        id = $Spec.id
        status = $Spec.status
        related = $Spec.related
    }

    try {
        $cacheData | ConvertTo-Json -Depth 3 | Out-File -FilePath $cacheFile -Encoding UTF8 -Force
    }
    catch {
        Write-Verbose "Failed to write cache file for $FilePath : $_"
    }
}

function Clear-TraceabilityCache {
    <#
    .SYNOPSIS
        Clears all cached data (memory and disk).
    #>
    [CmdletBinding()]
    param()

    # Clear memory cache
    $script:MemoryCache.Clear()

    # Clear disk cache
    if (Test-Path $script:CacheDir) {
        Remove-Item -Path (Join-Path $script:CacheDir "*.json") -Force -ErrorAction SilentlyContinue
    }
}

function Get-CacheStat {
    <#
    .SYNOPSIS
        Returns cache statistics for monitoring and debugging.
    #>
    [CmdletBinding()]
    param()

    $diskCacheFiles = @()
    if (Test-Path $script:CacheDir) {
        $diskCacheFiles = Get-ChildItem -Path $script:CacheDir -Filter "*.json"
    }

    return @{
        MemoryCacheEntries = $script:MemoryCache.Count
        DiskCacheEntries = $diskCacheFiles.Count
        CacheDirectory = $script:CacheDir
    }
}

Export-ModuleMember -Function @(
    'Initialize-TraceabilityCache',
    'Get-TraceabilityFileHash',
    'Get-CachedSpec',
    'Set-CachedSpec',
    'Clear-TraceabilityCache',
    'Get-CacheStat'
)
