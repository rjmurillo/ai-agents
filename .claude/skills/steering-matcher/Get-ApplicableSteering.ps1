<#
.SYNOPSIS
    Matches file paths against steering file glob patterns.

.DESCRIPTION
    Analyzes file paths and returns applicable steering files based on glob pattern matching.
    Steering files are sorted by priority (higher priority first).

.PARAMETER Files
    Array of file paths to analyze.

.PARAMETER SteeringPath
    Path to the steering directory. Defaults to ".agents/steering".

.EXAMPLE
    $files = @("src/Auth/Controllers/TokenController.cs")
    Get-ApplicableSteering -Files $files

.OUTPUTS
    Array of PSCustomObjects with steering file information (Name, Path, ApplyTo, Priority).
#>

function Get-ApplicableSteering {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyCollection()]
        [string[]]$Files,

        [Parameter(Mandatory = $false)]
        [string]$SteeringPath = ".agents/steering"
    )

    # Helper function to convert glob pattern to regex
    function ConvertTo-GlobRegex {
        param([string]$Pattern)

        $regexPattern = $Pattern -replace '\\', '/'
        $regexPattern = $regexPattern -replace '\*\*/', '<!GLOBSTAR_SLASH!>'
        $regexPattern = $regexPattern -replace '/\*\*', '<!SLASH_GLOBSTAR!>'
        $regexPattern = $regexPattern -replace '^\*\*', '<!START_GLOBSTAR!>'
        $regexPattern = $regexPattern -replace '\*\*$', '<!END_GLOBSTAR!>'
        $regexPattern = $regexPattern -replace '\?', '<!QUESTION_WILDCARD!>'
        $regexPattern = $regexPattern -replace '\*', '[^/]*'
        $regexPattern = $regexPattern -replace '\.', '\.'
        # Replace placeholders with actual regex
        $regexPattern = $regexPattern -replace '<!GLOBSTAR_SLASH!>', '(?:.+/|)'
        $regexPattern = $regexPattern -replace '<!SLASH_GLOBSTAR!>', '/.*'
        $regexPattern = $regexPattern -replace '<!START_GLOBSTAR!>', '.*'
        $regexPattern = $regexPattern -replace '<!END_GLOBSTAR!>', '.*'
        $regexPattern = $regexPattern -replace '<!QUESTION_WILDCARD!>', '.'

        return "^$regexPattern$"
    }

    # Helper function to test if file matches any pattern
    function Test-FileMatchesPattern {
        param(
            [string]$File,
            [string[]]$Patterns
        )

        $normalizedFile = $File -replace '\\', '/'
        foreach ($pattern in $Patterns) {
            $normalizedPattern = $pattern -replace '\\', '/'
            $regexPattern = ConvertTo-GlobRegex -Pattern $normalizedPattern
            if ($normalizedFile -match $regexPattern) {
                return $true
            }
        }
        return $false
    }

    # Return empty array if no files provided
    if ($Files.Count -eq 0) {
        return @()
    }

    # Get all steering files
    $steeringFiles = Get-ChildItem -Path $SteeringPath -Filter "*.md" -File |
        Where-Object { $_.Name -ne "README.md" -and $_.Name -ne "SKILL.md" }

    $applicableSteering = @()

    foreach ($steeringFile in $steeringFiles) {
        # Read front matter to get applyTo and priority
        $content = Get-Content -Path $steeringFile.FullName -Raw
        
        # Extract YAML front matter
        if ($content -match '(?s)^---\s*\n(.*?)\n---') {
            $frontMatter = $matches[1]
            
            # Parse applyTo, excludeFrom, and priority
            $applyTo = if ($frontMatter -match 'applyTo:\s*"([^"]+)"') { $matches[1] } else { $null }
            $excludeFrom = if ($frontMatter -match 'excludeFrom:\s*"([^"]+)"') { $matches[1] } else { $null }
            $priority = if ($frontMatter -match 'priority:\s*(\d+)') { [int]$matches[1] } else { 5 }

            if ($applyTo) {
                # Split patterns
                $includePatterns = $applyTo -split ',' | ForEach-Object { $_.Trim() }
                $excludePatterns = if ($excludeFrom) {
                    $excludeFrom -split ',' | ForEach-Object { $_.Trim() }
                } else {
                    @()
                }

                # Check if any file matches include patterns but not exclude patterns
                foreach ($file in $Files) {
                    $matchesInclude = Test-FileMatchesPattern -File $file -Patterns $includePatterns
                    $matchesExclude = if ($excludePatterns.Count -gt 0) {
                        Test-FileMatchesPattern -File $file -Patterns $excludePatterns
                    } else {
                        $false
                    }

                    if ($matchesInclude -and -not $matchesExclude) {
                        $applicableSteering += [PSCustomObject]@{
                            Name        = $steeringFile.BaseName
                            Path        = $steeringFile.FullName
                            ApplyTo     = $applyTo
                            ExcludeFrom = $excludeFrom
                            Priority    = $priority
                        }
                        break  # Only need one file to match to include this steering file
                    }
                }
            }
        }
    }

    # Sort by priority (descending) and return
    return $applicableSteering | Sort-Object -Property Priority -Descending
}

# Example usage (commented out)
<#
$files = @(
    "src/Auth/Controllers/TokenController.cs",
    "src/Auth/Services/TokenService.cs"
)

$steering = Get-ApplicableSteering -Files $files -SteeringPath ".agents/steering"

foreach ($s in $steering) {
    Write-Host "Matched: $($s.Name) (Priority: $($s.Priority))"
    Write-Host "  ApplyTo: $($s.ApplyTo)"
}
#>
