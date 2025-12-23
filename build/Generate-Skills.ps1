<#
.SYNOPSIS
  Generate *.skill files from canonical SKILL.md files.

.DESCRIPTION
  "Maximal" generator:
   - Finds SKILL.md files under a root directory
   - Parses YAML frontmatter using powershell-yaml module
   - Extracts allowed sections from the markdown body
   - Builds condensed frontmatter for *.skill (mapping rules are configurable)
   - Adds a GENERATED banner + source pointer
   - Normalizes line endings and ensures deterministic output
   - Supports dry-run, verify (CI), per-skill output naming, and multi-skill runs

.NOTES
  Requires powershell-yaml module (Install-Module -Name powershell-yaml)
#>

#Requires -Modules @{ ModuleName='powershell-yaml'; ModuleVersion='0.4.0' }

[CmdletBinding()]
param(
  # Root directory that contains skills
  [Parameter(Mandatory = $false)]
  [string] $Root = ".",

  # Glob/pattern for canonical skill files
  [Parameter(Mandatory = $false)]
  [string] $CanonicalName = "SKILL.md",

  # Output extension for generated files
  [Parameter(Mandatory = $false)]
  [string] $OutputExtension = ".skill",

  # Output file name (default uses folder name or overrides via frontmatter "name")
  [Parameter(Mandatory = $false)]
  [string] $OutputName = "",

  # If set, do not write files; print what would change
  [switch] $DryRun,

  # If set, fail (exit 1) when output differs from repo state (CI drift check)
  [switch] $Verify,

  # Allowed section headings to include in generated body (exact match)
  [Parameter(Mandatory = $false)]
  [string[]] $KeepHeadings = @(
    "Activation",
    "When to use",
    "When not to use",
    "Inputs",
    "Outputs",
    "Tooling",
    "Constraints",
    "Examples"
  ),

  # Drop everything under these headings even if KeepHeadings includes parent (exact match)
  [Parameter(Mandatory = $false)]
  [string[]] $DropHeadings = @(),

  # If set, include a content hash in the generated file
  [switch] $IncludeHash,

  # If set, force LF endings in generated file
  [switch] $ForceLf,

  # If set, process only the first SKILL.md found (useful for local testing)
  [switch] $Single,

  # Extra: print verbose diagnostics
  [switch] $VerboseLog
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Import required module
Import-Module powershell-yaml

# ---------------------------
# Utilities
# ---------------------------

function Write-Log {
  param([string] $Message)
  if ($VerboseLog) { Write-Host "[gen-skills] $Message" }
}

function Normalize-Newlines {
  param(
    [Parameter(Mandatory)] [string] $Text,
    [switch] $Lf
  )
  # Normalize to \n first
  $t = $Text -replace "`r`n", "`n"
  $t = $t -replace "`r", "`n"
  if ($Lf) { return $t }
  # Default back to Windows CRLF
  return ($t -replace "`n", "`r`n")
}

function Get-ContentUtf8 {
  param([Parameter(Mandatory)][string] $Path)
  return [System.IO.File]::ReadAllText((Resolve-Path $Path), [System.Text.Encoding]::UTF8)
}

function Set-ContentUtf8 {
  param(
    [Parameter(Mandatory)][string] $Path,
    [Parameter(Mandatory)][string] $Text
  )
  # Use UTF-8 without BOM
  $utf8NoBom = New-Object System.Text.UTF8Encoding $false
  [System.IO.File]::WriteAllText($Path, $Text, $utf8NoBom)
}

function Compute-Sha256Hex {
  param([Parameter(Mandatory)][string] $Text)
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
  $sha = [System.Security.Cryptography.SHA256]::Create()
  try {
    $hash = $sha.ComputeHash($bytes)
    return ($hash | ForEach-Object { $_.ToString("x2") }) -join ""
  } finally {
    $sha.Dispose()
  }
}

# ---------------------------
# YAML Frontmatter Parser
# Uses powershell-yaml module for robust parsing
# ---------------------------

function Parse-YamlFrontmatter {
  param([Parameter(Mandatory)][string] $YamlText)

  # Use powershell-yaml module's ConvertFrom-Yaml
  # Returns a hashtable/ordered dictionary
  return ConvertFrom-Yaml $YamlText -Ordered
}

# ---------------------------
# Markdown frontmatter split
# ---------------------------

function Split-Frontmatter {
  param([Parameter(Mandatory)][string] $Markdown)

  $md = Normalize-Newlines -Text $Markdown -Lf
  if (-not $md.StartsWith("---`n")) {
    return @{
      Frontmatter = [ordered]@{}
      Body = $Markdown
      HadFrontmatter = $false
    }
  }

  $end = $md.IndexOf("`n---`n", 4)
  if ($end -lt 0) {
    throw "Frontmatter begins with '---' but no closing '---' found."
  }

  $yaml = $md.Substring(4, $end - 4)
  $body = $md.Substring($end + 5) # length of "`n---`n" is 5
  $fm = Parse-YamlFrontmatter $yaml

  return @{
    Frontmatter = $fm
    Body = $body
    HadFrontmatter = $true
  }
}

# ---------------------------
# Section extraction
# Keep headings by title (exact match). Keeps heading line and its content until next heading of same or higher level.
# ---------------------------

function Extract-Sections {
  param(
    [Parameter(Mandatory)][string] $Body,
    [Parameter(Mandatory)][string[]] $AllowedHeadings,
    [Parameter(Mandatory=$false)][string[]] $DeniedHeadings = @()
  )

  $allowed = New-Object 'System.Collections.Generic.HashSet[string]'
  foreach ($h in $AllowedHeadings) { [void]$allowed.Add($h) }

  $denied = New-Object 'System.Collections.Generic.HashSet[string]'
  foreach ($h in $DeniedHeadings) { [void]$denied.Add($h) }

  $lines = (Normalize-Newlines -Text $Body -Lf) -split "`n"
  $out = New-Object System.Collections.Generic.List[string]

  $keep = $false
  $keepLevel = 0

  for ($i = 0; $i -lt $lines.Length; $i++) {
    $line = $lines[$i]
    $m = [regex]::Match($line, '^(#{1,6})\s+(.*)\s*$')
    if ($m.Success) {
      $level = $m.Groups[1].Value.Length
      $title = $m.Groups[2].Value.Trim()

      if ($denied.Contains($title)) {
        $keep = $false
        $keepLevel = 0
        continue
      }

      if ($allowed.Contains($title)) {
        $keep = $true
        $keepLevel = $level
        $out.Add($line)
        continue
      }

      # stop when a new section starts at same or higher level than current kept section
      if ($keep -and $level -le $keepLevel) {
        $keep = $false
        $keepLevel = 0
      }

      if ($keep) { $out.Add($line) }
      continue
    }

    if ($keep) { $out.Add($line) }
  }

  # Trim leading/trailing blank lines
  $text = ($out -join "`n").Trim()
  if ($text.Length -eq 0) { return "" }
  return ($text + "`n")
}

# ---------------------------
# Frontmatter mapping: SKILL.md -> *.skill
# Customize as needed for your schema.
# ---------------------------

function Build-SkillFrontmatter {
  param(
    [Parameter(Mandatory)][hashtable] $Fm,
    [Parameter(Mandatory)][string] $SourceRelPath,
    [Parameter(Mandatory)][string] $NameFallback,
    [switch] $GeneratedHash,
    [string] $HashValue
  )

  # Resolve a name in priority order
  $name = $null
  if ($Fm.ContainsKey("name")) { $name = [string]$Fm["name"] }
  elseif ($Fm.ContainsKey("title")) { $name = [string]$Fm["title"] }
  elseif ($Fm.ContainsKey("skill")) { $name = [string]$Fm["skill"] }
  else { $name = $NameFallback }

  $desc = ""
  if ($Fm.ContainsKey("description")) { $desc = [string]$Fm["description"] }

  $version = ""
  if ($Fm.ContainsKey("version")) { $version = [string]$Fm["version"] }

  # Deterministic ordered map
  $mapped = [ordered]@{
    name = $name
    description = $desc
  }

  if ($version) { $mapped["version"] = $version }

  # Add "generated" metadata
  $mapped["generated"] = $true
  $mapped["generated_from"] = $SourceRelPath

  if ($GeneratedHash) {
    $mapped["generated_hash_sha256"] = $HashValue
  }

  # Serialize as YAML (simple)
  $lines = New-Object System.Collections.Generic.List[string]
  $lines.Add("---")
  foreach ($k in $mapped.Keys) {
    $v = $mapped[$k]
    if ($null -eq $v) { continue }

    if ($v -is [bool]) {
      $lines.Add(("{0}: {1}" -f $k, ($(if ($v) { "true" } else { "false" }))))
      continue
    }

    if ($v -is [int] -or $v -is [int64] -or $v -is [double]) {
      $lines.Add(("{0}: {1}" -f $k, $v))
      continue
    }

    # Quote strings safely
    $sv = [string]$v
    $escaped = $sv.Replace('"', '\"')
    $lines.Add(("{0}: ""{1}""" -f $k, $escaped))
  }
  $lines.Add("---")

  return ($lines -join "`n") + "`n"
}

# ---------------------------
# File naming
# ---------------------------

function Get-OutputPath {
  param(
    [Parameter(Mandatory)][string] $CanonicalPath,
    [Parameter(Mandatory)][hashtable] $Fm,
    [string] $OutputNameOverride,
    [Parameter(Mandatory)][string] $OutputExt
  )

  $dir = Split-Path -Parent $CanonicalPath

  $baseName = $null
  if ($OutputNameOverride -and $OutputNameOverride.Trim().Length -gt 0) {
    $baseName = $OutputNameOverride.Trim()
  } elseif ($Fm.ContainsKey("name")) {
    $baseName = [string]$Fm["name"]
  } elseif ($Fm.ContainsKey("title")) {
    $baseName = [string]$Fm["title"]
  } else {
    # Use directory name
    $baseName = Split-Path -Leaf $dir
  }

  # Sanitize a bit for file system
  $safe = ($baseName -replace '[\\/:*?"<>|]', "_").Trim()
  if ($safe.Length -eq 0) { $safe = "Skill" }

  return Join-Path $dir ($safe + $OutputExt)
}

# ---------------------------
# Main
# ---------------------------

$rootPath = Resolve-Path $Root
Write-Log "Root: $rootPath"

$canonicalFiles = Get-ChildItem -Path $rootPath -Recurse -File -Filter $CanonicalName
if (-not $canonicalFiles -or $canonicalFiles.Count -eq 0) {
  Write-Error "No $CanonicalName found under $rootPath"
}

if ($Single) { $canonicalFiles = @($canonicalFiles | Select-Object -First 1) }

$anyDiff = $false
$processed = 0

foreach ($file in $canonicalFiles) {
  $processed++

  $canonicalPath = $file.FullName
  Write-Log "Processing: $canonicalPath"

  $md = Get-ContentUtf8 -Path $canonicalPath
  $split = Split-Frontmatter -Markdown $md
  $fm = $split.Frontmatter
  $body = $split.Body

  $rel = [System.IO.Path]::GetRelativePath($rootPath, $canonicalPath)

  $nameFallback = Split-Path -Leaf (Split-Path -Parent $canonicalPath)
  $extracted = Extract-Sections -Body $body -AllowedHeadings $KeepHeadings -DeniedHeadings $DropHeadings

  $bannerLines = @(
    "# GENERATED FILE",
    "# Source of truth: SKILL.md",
    "# Do not edit manually",
    "#",
    "# Regenerate: pwsh ./scripts/gen-skills.ps1",
    ""
  )
  $banner = ($bannerLines -join "`n") + "`n"

  # Hash can be based on extracted content + mapped frontmatter inputs, or entire source.
  $hashInput = ($split.HadFrontmatter ? (Normalize-Newlines -Text $md -Lf) : (Normalize-Newlines -Text $body -Lf))
  $hash = Compute-Sha256Hex -Text $hashInput

  $front = Build-SkillFrontmatter -Fm $fm -SourceRelPath $rel -NameFallback $nameFallback -GeneratedHash:$IncludeHash -HashValue $hash
  $out = $front + $banner + $extracted

  # Normalize newlines and ensure trailing newline
  $out = Normalize-Newlines -Text $out -Lf:$ForceLf
  if (-not $out.EndsWith("`n")) { $out += "`n" }

  $outPath = Get-OutputPath -CanonicalPath $canonicalPath -Fm $fm -OutputNameOverride $OutputName -OutputExt $OutputExtension

  $existing = $null
  if (Test-Path $outPath) {
    $existing = Normalize-Newlines -Text (Get-ContentUtf8 -Path $outPath) -Lf:$ForceLf
  }

  $differs = ($null -eq $existing) -or ($existing -ne $out)
  if ($differs) {
    $anyDiff = $true
    Write-Host "DIFF: $([System.IO.Path]::GetRelativePath($rootPath, $outPath)) <= $rel"

    if (-not $DryRun) {
      Set-ContentUtf8 -Path $outPath -Text $out
      Write-Host "WROTE: $([System.IO.Path]::GetRelativePath($rootPath, $outPath))"
    }
  } else {
    Write-Log "No change: $([System.IO.Path]::GetRelativePath($rootPath, $outPath))"
  }
}

Write-Host "Processed $processed canonical file(s)."

if ($Verify -and $anyDiff) {
  Write-Error "Verification failed: generated output differs. Run generator and commit changes."
  exit 1
}

exit 0
