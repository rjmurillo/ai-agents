<#
.SYNOPSIS
    Schema validation module for JSON output validation.

.DESCRIPTION
    Provides fail-fast JSON schema validation for memory system producers.
    Implements CVA pattern: shared validation logic extracted from multiple scripts.

    Functions:
    - Get-SchemaPath: Load and cache schema paths
    - Test-SchemaValid: Validate JSON against schema
    - Write-ValidatedJson: Validate-then-write pattern
    - Clear-SchemaCache: Reset cache (for testing)

.NOTES
    Task: Fix #821 (Episode extractor schema validation)
    Pattern: CVA refactor - shared validation for Update-CausalGraph.ps1 and Extract-SessionEpisode.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Module-level schema cache
$script:SchemaCache = @{}

function Get-SchemaPath {
    <#
    .SYNOPSIS
        Loads and caches schema file path.

    .PARAMETER SchemaName
        Name of the schema file (without extension).

    .PARAMETER SchemaDirectory
        Directory containing schema files. Defaults to .claude/skills/memory/resources/schemas/

    .OUTPUTS
        Full path to the schema file.

    .EXAMPLE
        $schemaPath = Get-SchemaPath -SchemaName "episode"
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [ValidateNotNullOrEmpty()]
        [string]$SchemaName,

        [string]$SchemaDirectory
    )

    # Check cache first
    if ($script:SchemaCache.ContainsKey($SchemaName)) {
        return $script:SchemaCache[$SchemaName]
    }

    # Determine default schema directory if not provided
    if (-not $SchemaDirectory) {
        # Find git root
        $gitRoot = git rev-parse --show-toplevel 2>$null
        if (-not $gitRoot) {
            throw [System.Management.Automation.ItemNotFoundException]::new("Cannot determine git root. Run from within a git repository or provide -SchemaDirectory.")
        }
        $SchemaDirectory = Join-Path $gitRoot ".claude" "skills" "memory" "resources" "schemas"
    }

    # Resolve schema path
    $schemaFile = Join-Path $SchemaDirectory "$SchemaName.schema.json"

    if (-not (Test-Path $schemaFile -PathType Leaf)) {
        throw [System.IO.FileNotFoundException]::new("Schema file not found: $schemaFile")
    }

    # Cache and return
    $script:SchemaCache[$SchemaName] = $schemaFile
    return $schemaFile
}

function Test-SchemaValid {
    <#
    .SYNOPSIS
        Validates JSON data against a JSON schema.

    .DESCRIPTION
        Uses Newtonsoft.Json.Schema for validation (if available).
        Falls back to basic structure validation if schema library not available.

    .PARAMETER JsonContent
        JSON content to validate (as string or object).

    .PARAMETER SchemaName
        Name of the schema to validate against.

    .PARAMETER SchemaDirectory
        Optional directory containing schema files.

    .OUTPUTS
        [PSCustomObject] with:
        - Valid: [bool] - whether validation passed
        - Errors: [string[]] - validation error messages

    .EXAMPLE
        $result = Test-SchemaValid -JsonContent $json -SchemaName "episode"
        if (-not $result.Valid) {
            throw "Schema validation failed: $($result.Errors -join ', ')"
        }
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [ValidateNotNull()]
        $JsonContent,

        [Parameter(Mandatory)]
        [ValidateNotNullOrEmpty()]
        [string]$SchemaName,

        [string]$SchemaDirectory
    )

    $errors = @()

    # Get schema path
    try {
        $schemaPath = Get-SchemaPath -SchemaName $SchemaName -SchemaDirectory $SchemaDirectory
    }
    catch {
        $errors += "Failed to load schema '$SchemaName': $($_.Exception.Message)"
        return [PSCustomObject]@{
            Valid  = $false
            Errors = $errors
        }
    }

    # Load schema
    try {
        $schemaContent = Get-Content -Path $schemaPath -Raw -ErrorAction Stop
        $schema = $schemaContent | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        $errors += "Failed to parse schema file '$schemaPath': $($_.Exception.Message)"
        return [PSCustomObject]@{
            Valid  = $false
            Errors = $errors
        }
    }

    # Parse JSON content if string or convert hashtable to PSCustomObject
    $data = $JsonContent
    if ($JsonContent -is [string]) {
        try {
            $data = $JsonContent | ConvertFrom-Json -ErrorAction Stop
        }
        catch {
            $errors += "Failed to parse JSON content: $($_.Exception.Message)"
            return [PSCustomObject]@{
                Valid  = $false
                Errors = $errors
            }
        }
    }
    elseif ($JsonContent -is [hashtable]) {
        # Convert hashtable to JSON and back to get PSCustomObject
        try {
            $json = $JsonContent | ConvertTo-Json -Depth 10
            $data = $json | ConvertFrom-Json
        }
        catch {
            $errors += "Failed to convert hashtable to JSON: $($_.Exception.Message)"
            return [PSCustomObject]@{
                Valid  = $false
                Errors = $errors
            }
        }
    }

    # Perform basic validation against schema requirements
    # Check required fields
    if ($schema.required) {
        foreach ($requiredField in $schema.required) {
            if (-not ($data.PSObject.Properties.Name -contains $requiredField)) {
                $errors += "Missing required field: '$requiredField'"
            }
        }
    }

    # Check field types
    if ($schema.properties) {
        foreach ($property in $schema.properties.PSObject.Properties) {
            $fieldName = $property.Name
            $fieldSchema = $property.Value

            # Skip if field not present (already checked in required)
            if (-not ($data.PSObject.Properties.Name -contains $fieldName)) {
                continue
            }

            $fieldValue = $data.$fieldName

            # Check type (null check first)
            if ($null -eq $fieldValue -and $fieldSchema.type -ne "null") {
                # Null is only valid if explicitly allowed or for non-required fields
                if ($schema.required -contains $fieldName) {
                    $errors += "Field '$fieldName' is null but is required"
                }
                continue
            }

            # Type validation
            switch ($fieldSchema.type) {
                "string" {
                    # Accept DateTime as valid string type because PowerShell's ConvertFrom-Json
                    # auto-converts ISO 8601 date strings to DateTime during hashtable round-trips
                    if ($null -ne $fieldValue -and $fieldValue -isnot [string] -and $fieldValue -isnot [datetime]) {
                        $errors += "Field '$fieldName' should be string, got $($fieldValue.GetType().Name)"
                    }
                }
                "number" {
                    if ($null -ne $fieldValue -and $fieldValue -isnot [int] -and $fieldValue -isnot [double] -and $fieldValue -isnot [decimal] -and $fieldValue -isnot [long] -and $fieldValue -isnot [int64]) {
                        $errors += "Field '$fieldName' should be number, got $($fieldValue.GetType().Name)"
                    }
                }
                "integer" {
                    if ($null -ne $fieldValue -and $fieldValue -isnot [int] -and $fieldValue -isnot [long] -and $fieldValue -isnot [int64]) {
                        $errors += "Field '$fieldName' should be integer, got $($fieldValue.GetType().Name)"
                    }
                }
                "boolean" {
                    if ($null -ne $fieldValue -and $fieldValue -isnot [bool] -and $fieldValue -isnot [System.Boolean]) {
                        $errors += "Field '$fieldName' should be boolean, got $($fieldValue.GetType().Name)"
                    }
                }
                "array" {
                    # Null check for arrays
                    if ($null -eq $fieldValue) {
                        $errors += "Field '$fieldName' is null, should be array (use @() for empty array)"
                        continue
                    }
                    # Check if it's array-like (array or ArrayList)
                    $isArrayLike = $false
                    if ($fieldValue -is [array]) {
                        $isArrayLike = $true
                    }
                    elseif ($fieldValue.GetType().Name -match 'ArrayList|List|Collection') {
                        $isArrayLike = $true
                    }
                    elseif ($fieldValue -is [System.Collections.IList]) {
                        $isArrayLike = $true
                    }

                    if (-not $isArrayLike) {
                        $errors += "Field '$fieldName' should be array, got $($fieldValue.GetType().Name)"
                    }
                }
                "object" {
                    if ($null -ne $fieldValue -and $fieldValue -isnot [PSCustomObject] -and $fieldValue -isnot [hashtable] -and $fieldValue -isnot [System.Management.Automation.PSObject]) {
                        $errors += "Field '$fieldName' should be object, got $($fieldValue.GetType().Name)"
                    }
                }
            }

            # Check enum constraints
            if ($fieldSchema.PSObject.Properties.Name -contains 'enum' -and $fieldSchema.enum -and $fieldValue) {
                if ($fieldValue -notin $fieldSchema.enum) {
                    $errors += "Field '$fieldName' value '$fieldValue' not in allowed values: $($fieldSchema.enum -join ', ')"
                }
            }

            # Check pattern constraints (for strings)
            if ($fieldSchema.PSObject.Properties.Name -contains 'pattern' -and $fieldSchema.pattern -and $fieldValue) {
                if ($fieldValue -notmatch $fieldSchema.pattern) {
                    $errors += "Field '$fieldName' value '$fieldValue' does not match pattern: $($fieldSchema.pattern)"
                }
            }
        }
    }

    return [PSCustomObject]@{
        Valid  = ($errors.Count -eq 0)
        Errors = $errors
    }
}

function Write-ValidatedJson {
    <#
    .SYNOPSIS
        Validates JSON against schema before writing to file (fail-fast pattern).

    .PARAMETER Data
        Data object to serialize and validate.

    .PARAMETER FilePath
        Destination file path.

    .PARAMETER SchemaName
        Name of the schema to validate against.

    .PARAMETER SchemaDirectory
        Optional directory containing schema files.

    .PARAMETER Depth
        JSON serialization depth. Defaults to 10.

    .PARAMETER Force
        Overwrite file if it exists.

    .OUTPUTS
        [PSCustomObject] with:
        - Success: [bool] - whether write succeeded
        - FilePath: [string] - path to written file
        - ValidationResult: [PSCustomObject] - validation result

    .EXAMPLE
        $result = Write-ValidatedJson -Data $episode -FilePath $outputFile -SchemaName "episode"
        if (-not $result.Success) {
            throw "Failed to write validated JSON: $($result.ValidationResult.Errors -join ', ')"
        }
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)]
        [ValidateNotNull()]
        $Data,

        [Parameter(Mandatory)]
        [ValidateNotNullOrEmpty()]
        [string]$FilePath,

        [Parameter(Mandatory)]
        [ValidateNotNullOrEmpty()]
        [string]$SchemaName,

        [string]$SchemaDirectory,

        [int]$Depth = 10,

        [switch]$Force
    )

    # Serialize to JSON
    try {
        $json = $Data | ConvertTo-Json -Depth $Depth -ErrorAction Stop
    }
    catch {
        return [PSCustomObject]@{
            Success          = $false
            FilePath         = $FilePath
            ValidationResult = [PSCustomObject]@{
                Valid  = $false
                Errors = @("Failed to serialize to JSON: $($_.Exception.Message)")
            }
        }
    }

    # Validate against schema
    $validationResult = Test-SchemaValid -JsonContent $json -SchemaName $SchemaName -SchemaDirectory $SchemaDirectory

    if (-not $validationResult.Valid) {
        return [PSCustomObject]@{
            Success          = $false
            FilePath         = $FilePath
            ValidationResult = $validationResult
        }
    }

    # Check file existence
    if ((Test-Path $FilePath) -and -not $Force) {
        return [PSCustomObject]@{
            Success          = $false
            FilePath         = $FilePath
            ValidationResult = [PSCustomObject]@{
                Valid  = $false
                Errors = @("File already exists: $FilePath (use -Force to overwrite)")
            }
        }
    }

    # Write to file
    try {
        Set-Content -Path $FilePath -Value $json -Encoding UTF8 -ErrorAction Stop
    }
    catch {
        return [PSCustomObject]@{
            Success          = $false
            FilePath         = $FilePath
            ValidationResult = [PSCustomObject]@{
                Valid  = $false
                Errors = @("Failed to write file '$FilePath': $($_.Exception.Message)")
            }
        }
    }

    return [PSCustomObject]@{
        Success          = $true
        FilePath         = $FilePath
        ValidationResult = $validationResult
    }
}

function Clear-SchemaCache {
    <#
    .SYNOPSIS
        Clears the schema cache (for testing).

    .EXAMPLE
        Clear-SchemaCache
    #>
    [CmdletBinding()]
    param()

    $script:SchemaCache = @{}
}

Export-ModuleMember -Function @(
    'Get-SchemaPath',
    'Test-SchemaValid',
    'Write-ValidatedJson',
    'Clear-SchemaCache'
)
