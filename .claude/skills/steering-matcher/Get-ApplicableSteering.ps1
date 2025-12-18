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
            
            # Parse applyTo and priority
            $applyTo = if ($frontMatter -match 'applyTo:\s*"([^"]+)"') { $matches[1] } else { $null }
            $priority = if ($frontMatter -match 'priority:\s*(\d+)') { [int]$matches[1] } else { 5 }

            if ($applyTo) {
                # Split applyTo if it contains multiple patterns
                $patterns = $applyTo -split ',' | ForEach-Object { $_.Trim() }

                # Check if any file matches any pattern
                $matched = $false
                foreach ($pattern in $patterns) {
                    foreach ($file in $Files) {
                        # Normalize paths
                        $normalizedFile = $file -replace '\\', '/'
                        $normalizedPattern = $pattern -replace '\\', '/'
                        
                        # Convert glob pattern to regex (use placeholders to avoid interference)
                        $regexPattern = $normalizedPattern
                        $regexPattern = $regexPattern -replace '\*\*/', '<!GLOBSTAR_SLASH!>'
                        $regexPattern = $regexPattern -replace '/\*\*', '<!SLASH_GLOBSTAR!>'
                        $regexPattern = $regexPattern -replace '^\*\*', '<!START_GLOBSTAR!>'
                        $regexPattern = $regexPattern -replace '\*\*$', '<!END_GLOBSTAR!>'
                        $regexPattern = $regexPattern -replace '\*', '[^/]*'
                        $regexPattern = $regexPattern -replace '\?', '.'
                        $regexPattern = $regexPattern -replace '\.', '\.'
                        # Replace placeholders with actual regex
                        $regexPattern = $regexPattern -replace '<!GLOBSTAR_SLASH!>', '(?:.+/|)'
                        $regexPattern = $regexPattern -replace '<!SLASH_GLOBSTAR!>', '/.*'
                        $regexPattern = $regexPattern -replace '<!START_GLOBSTAR!>', '.*'
                        $regexPattern = $regexPattern -replace '<!END_GLOBSTAR!>', '.*'
                        $regexPattern = "^$regexPattern$"

                        if ($normalizedFile -match $regexPattern) {
                            $matched = $true
                            break
                        }
                    }
                    if ($matched) { break }
                }

                if ($matched) {
                    $applicableSteering += [PSCustomObject]@{
                        Name     = $steeringFile.BaseName
                        Path     = $steeringFile.FullName
                        ApplyTo  = $applyTo
                        Priority = $priority
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
