<#
.SYNOPSIS
    Shared functions for agent generation and testing.

.DESCRIPTION
    This module contains common functions used by both Generate-Agents.ps1
    and its test suite. Extracting these functions ensures tests validate
    the actual implementations, not stale copies.

.NOTES
    Import with: Import-Module ./build/Generate-Agents.Common.psm1
#>

function Test-PathWithinRoot {
    <#
    .SYNOPSIS
        Security check: Validates that a path is within the repository root.
    .DESCRIPTION
        Ensures path is a true descendant of root by appending directory separator
        to prevent prefix-matching attacks (e.g., C:\repo_evil matching C:\repo).
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Path,

        [Parameter(Mandatory)]
        [string]$Root
    )

    $resolvedPath = [System.IO.Path]::GetFullPath($Path)
    $resolvedRoot = [System.IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
    # Append directory separator to ensure only true descendants match
    $resolvedRoot += [System.IO.Path]::DirectorySeparatorChar

    # Path equals root (without trailing separator) is valid
    $pathWithoutTrailing = $resolvedPath.TrimEnd('\', '/')
    $rootWithoutTrailing = $resolvedRoot.TrimEnd('\', '/')
    if ($pathWithoutTrailing -eq $rootWithoutTrailing) {
        return $true
    }

    return $resolvedPath.StartsWith($resolvedRoot, [StringComparison]::OrdinalIgnoreCase)
}

function Read-YamlFrontmatter {
    <#
    .SYNOPSIS
        Extracts YAML frontmatter from a markdown file.
    .OUTPUTS
        PSCustomObject with FrontmatterRaw, Body properties.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Content
    )

    # Match YAML frontmatter between --- markers
    if ($Content -match '^---\r?\n([\s\S]*?)\r?\n---\r?\n([\s\S]*)$') {
        $frontmatterRaw = $Matches[1]
        $body = $Matches[2]

        return [PSCustomObject]@{
            FrontmatterRaw = $frontmatterRaw
            Body           = $body
        }
    }

    Write-Warning "No valid YAML frontmatter found"
    return $null
}

function ConvertFrom-SimpleFrontmatter {
    <#
    .SYNOPSIS
        Parses simple YAML frontmatter into a hashtable.
        Handles basic key: value pairs, inline arrays ['item1', 'item2'],
        and block-style arrays with indented list items.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [ValidateNotNullOrEmpty()]
        [string]$FrontmatterRaw
    )

    # Validate input is not just whitespace
    if ([string]::IsNullOrWhiteSpace($FrontmatterRaw)) {
        Write-Warning "ConvertFrom-SimpleFrontmatter: Input is empty or whitespace-only"
        return @{}
    }

    $result = @{}
    $lines = $FrontmatterRaw -split '\r?\n'
    $currentKey = $null
    $currentArray = $null

    for ($i = 0; $i -lt $lines.Count; $i++) {
        $line = $lines[$i]

        # Skip empty lines
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        # Check for block-style array item (indented with "  - ")
        if ($line -match '^\s+-\s*(.*)$') {
            if ($null -ne $currentKey -and $null -ne $currentArray) {
                $item = $Matches[1].Trim()
                # Remove surrounding quotes if present
                if ($item -match '^"(.*)"$' -or $item -match "^'(.*)'$") {
                    $item = $Matches[1]
                }
                $currentArray += $item
            }
            else {
                Write-Warning "ConvertFrom-SimpleFrontmatter: Orphaned array item on line $($i + 1) with no parent key: '$line'"
            }
            continue
        }

        # If we were collecting an array and hit a non-array line, save it
        if ($null -ne $currentKey -and $null -ne $currentArray) {
            # Convert array to inline format for compatibility
            $arrayItems = $currentArray | ForEach-Object { "'$_'" }
            $result[$currentKey] = "[" + ($arrayItems -join ", ") + "]"
            $currentKey = $null
            $currentArray = $null
        }

        # Match keys with letters, digits, underscores, and hyphens (for argument-hint etc.)
        if ($line -match '^([\w-]+):\s*(.*)$') {
            $key = $Matches[1]
            $value = $Matches[2].Trim()

            # Check if it's an inline array (starts with [ and ends with ])
            if ($value -match "^\[.*\]$") {
                # Keep the raw array string for now
                $result[$key] = $value
            }
            elseif ($value -eq '' -or $value -eq 'null') {
                # Empty value - might be start of block-style array
                # Check if next line is an array item
                if ($i + 1 -lt $lines.Count -and $lines[$i + 1] -match '^\s+-\s*') {
                    $currentKey = $key
                    $currentArray = @()
                }
                else {
                    $result[$key] = $null
                }
            }
            else {
                # Remove surrounding quotes if present
                if ($value -match '^"(.*)"$' -or $value -match "^'(.*)'$") {
                    $value = $Matches[1]
                }
                $result[$key] = $value
            }
        }
    }

    # Handle array at end of frontmatter
    if ($null -ne $currentKey -and $null -ne $currentArray) {
        $arrayItems = $currentArray | ForEach-Object { "'$_'" }
        $result[$currentKey] = "[" + ($arrayItems -join ", ") + "]"
    }

    return $result
}

function Convert-FrontmatterForPlatform {
    <#
    .SYNOPSIS
        Transforms frontmatter for a specific platform.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [hashtable]$Frontmatter,

        [Parameter(Mandatory)]
        [hashtable]$PlatformConfig,

        [Parameter(Mandatory)]
        [string]$AgentName
    )

    $result = @{}
    $platformName = $PlatformConfig['platform']

    # Copy existing fields (excluding placeholders and platform-specific tools)
    foreach ($key in $Frontmatter.Keys) {
        $value = $Frontmatter[$key]
        # Skip placeholder values
        if ($value -match '^\{\{PLATFORM_') { continue }
        # Skip platform-specific tools fields (tools_vscode, tools_copilot)
        if ($key -match '^tools_') { continue }
        # Skip the generic tools field if we have platform-specific ones
        if ($key -eq 'tools' -and ($Frontmatter.ContainsKey('tools_vscode') -or $Frontmatter.ContainsKey('tools_copilot'))) { continue }

        $result[$key] = $value
    }

    # Apply platform-specific transformations
    $fm = $PlatformConfig['frontmatter']

    # Handle name field
    if ($fm -and $fm['includeNameField'] -eq $true) {
        $result['name'] = $AgentName
    }
    else {
        $result.Remove('name')
    }

    # Handle model field
    if ($fm -and $fm['model']) {
        $result['model'] = $fm['model']
    }
    else {
        $result.Remove('model')
    }

    # Handle platform-specific tools array
    $toolsKey = "tools_$($platformName -replace '-', '')"  # tools_vscode, tools_copilotcli
    # Also try with hyphen for copilot-cli -> tools_copilot
    $toolsKeyAlt = "tools_$($platformName -replace '-cli$', '')"  # tools_copilot

    if ($Frontmatter.ContainsKey($toolsKey)) {
        $result['tools'] = $Frontmatter[$toolsKey]
    }
    elseif ($Frontmatter.ContainsKey($toolsKeyAlt)) {
        $result['tools'] = $Frontmatter[$toolsKeyAlt]
    }
    elseif ($Frontmatter.ContainsKey('tools')) {
        # Fallback to generic tools if no platform-specific one exists
        # But don't use placeholder values
        $toolsValue = $Frontmatter['tools']
        if ($toolsValue -notmatch '^\{\{PLATFORM_') {
            $result['tools'] = $toolsValue
        }
    }

    return $result
}

function Format-FrontmatterYaml {
    <#
    .SYNOPSIS
        Converts frontmatter hashtable back to YAML string.
        Maintains specific field order for consistency.
        Outputs arrays in block-style format for cross-platform compatibility.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [hashtable]$Frontmatter
    )

    $lines = @()

    # Define field order for frontmatter output
    $fieldOrder = @('name', 'description', 'argument-hint', 'tools', 'model')

    # Helper to format a value (handles arrays specially)
    $formatValue = {
        param([string]$key, $value)

        # Handle null or non-string values
        if ($null -eq $value) {
            Write-Verbose "Format-FrontmatterYaml: Null value for key '$key' - skipping"
            return @()
        }

        if ($value -isnot [string]) {
            Write-Verbose "Format-FrontmatterYaml: Non-string value for key '$key' (type: $($value.GetType().Name)) - converting to string"
            $value = [string]$value
        }

        # Check if value is an inline array
        if ($value -match "^\[(.*)\]$") {
            $arrayContent = $Matches[1]
            # Parse array items (handle both 'item' and "item" formats)
            $items = @()
            # Split by comma, handling quoted items
            # Note: This regex does not handle commas inside quoted values.
            # For our use case (tool names), this is acceptable as tool names do not contain commas.
            $pattern = "'([^']+)'|""([^""]+)""|([^,\s]+)"
            $itemMatches = [regex]::Matches($arrayContent, $pattern)
            foreach ($match in $itemMatches) {
                if ($match.Groups[1].Success) {
                    $items += $match.Groups[1].Value
                }
                elseif ($match.Groups[2].Success) {
                    $items += $match.Groups[2].Value
                }
                elseif ($match.Groups[3].Success) {
                    $items += $match.Groups[3].Value
                }
            }

            # Validate parsing: if we expected items but got none, warn and fallback
            if ($items.Count -eq 0 -and $arrayContent.Trim().Length -gt 0) {
                Write-Warning "Format-FrontmatterYaml: Failed to parse array items for key '$key': '$arrayContent' - preserving as inline"
                return @("${key}: $value")
            }

            # Output as block-style array
            $result = @("${key}:")
            foreach ($item in $items) {
                $result += "  - $item"
            }
            return $result
        }
        else {
            return @("${key}: $value")
        }
    }

    # Output fields in order
    foreach ($field in $fieldOrder) {
        if ($Frontmatter.ContainsKey($field) -and $null -ne $Frontmatter[$field]) {
            $value = $Frontmatter[$field]
            $lines += & $formatValue $field $value
        }
    }

    # Output any remaining fields
    foreach ($key in $Frontmatter.Keys) {
        if ($key -notin $fieldOrder -and $null -ne $Frontmatter[$key]) {
            $lines += & $formatValue $key $Frontmatter[$key]
        }
    }

    return $lines -join "`n"
}

function Convert-HandoffSyntax {
    <#
    .SYNOPSIS
        Transforms handoff syntax in markdown body.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Body,

        [Parameter(Mandatory)]
        [string]$TargetSyntax
    )

    $result = $Body

    switch ($TargetSyntax) {
        "#runSubagent" {
            # Convert /agent to #runSubagent
            $result = $result -replace '`/agent\s+(\w+)`', '`#runSubagent with subagentType=$1`'
            $result = $result -replace '/agent\s+\[agent_name\]', '#runSubagent with subagentType={agent_name}'
        }
        "/agent" {
            # Convert #runSubagent to /agent
            $result = $result -replace '`#runSubagent with subagentType=(\w+)`', '`/agent $1`'
            $result = $result -replace '#runSubagent with subagentType=\{agent_name\}', '/agent [agent_name]'
        }
    }

    return $result
}

function Convert-MemoryPrefix {
    <#
    .SYNOPSIS
        Replaces {{MEMORY_PREFIX}} placeholder with platform-specific prefix.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [string]$Body,

        [Parameter(Mandatory)]
        [string]$MemoryPrefix
    )

    return $Body -replace '\{\{MEMORY_PREFIX\}\}', $MemoryPrefix
}

# Export all functions
Export-ModuleMember -Function @(
    'Test-PathWithinRoot'
    'Read-YamlFrontmatter'
    'ConvertFrom-SimpleFrontmatter'
    'Convert-FrontmatterForPlatform'
    'Format-FrontmatterYaml'
    'Convert-HandoffSyntax'
    'Convert-MemoryPrefix'
)
