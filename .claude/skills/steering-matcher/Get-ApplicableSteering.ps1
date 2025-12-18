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
    Array of hashtables with steering file information (Name, Path, Scope, Priority).
#>

function Get-ApplicableSteering {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Files,

        [Parameter(Mandatory = $false)]
        [string]$SteeringPath = ".agents/steering"
    )

    # Get all steering files
    $steeringFiles = Get-ChildItem -Path $SteeringPath -Filter "*.md" -File | 
        Where-Object { $_.Name -ne "README.md" }

    $applicableSteering = @()

    foreach ($steeringFile in $steeringFiles) {
        # Read front matter to get scope and priority
        $content = Get-Content -Path $steeringFile.FullName -Raw
        
        # Extract YAML front matter
        if ($content -match '(?s)^---\s*\n(.*?)\n---') {
            $frontMatter = $matches[1]
            
            # Parse scope and priority
            $scope = if ($frontMatter -match 'scope:\s*"([^"]+)"') { $matches[1] } else { $null }
            $priority = if ($frontMatter -match 'priority:\s*(\d+)') { [int]$matches[1] } else { 5 }

            if ($scope) {
                # Split scope if it contains multiple patterns
                $patterns = $scope -split ',' | ForEach-Object { $_.Trim() }

                # Check if any file matches any pattern
                $matched = $false
                foreach ($pattern in $patterns) {
                    foreach ($file in $Files) {
                        # Convert glob pattern to regex
                        $regexPattern = $pattern -replace '\*\*/', '.*/' -replace '\*', '[^/]*' -replace '\?', '.'
                        $regexPattern = "^$regexPattern$"

                        if ($file -match $regexPattern) {
                            $matched = $true
                            break
                        }
                    }
                    if ($matched) { break }
                }

                if ($matched) {
                    $applicableSteering += @{
                        Name     = $steeringFile.BaseName
                        Path     = $steeringFile.FullName
                        Scope    = $scope
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
    Write-Host "  Scope: $($s.Scope)"
}
#>
