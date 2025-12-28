<#
.SYNOPSIS
  Generate *.skill files from canonical SKILL.md files.

.DESCRIPTION
  Generates *.skill from SKILL.md using:
    - YAML frontmatter: name, description, allowed-tools
    - Generator config: metadata.generator.keep_headings (list of headings to extract)
    - Body extraction: keeps only the headings listed in keep_headings
    - Adds generated metadata and a banner
    - Deterministic output and optional verify mode for CI

  The keep_headings directive MUST be under metadata.generator to comply with
  Anthropic skill-creator validation (allowed root keys: name, description,
  license, allowed-tools, metadata, compatibility).

.NOTES
  Requires: powershell-yaml module (Install-Module -Name powershell-yaml)
#>

#Requires -Modules @{ ModuleName='powershell-yaml'; ModuleVersion='0.4.0' }

[CmdletBinding()]
param(
  [Parameter(Mandatory = $false)]
  [string] $Root = ".",

  [Parameter(Mandatory = $false)]
  [string] $CanonicalName = "SKILL.md",

  [Parameter(Mandatory = $false)]
  [string] $OutputExtension = ".skill",

  # If set, generate <FolderName>.skill; otherwise prefer <frontmatter.name>.skill
  [switch] $UseFolderName,

  [switch] $DryRun,
  [switch] $Verify,
  [switch] $ForceLf,
  [switch] $IncludeHash,

  [switch] $VerboseLog
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Import YAML module
Import-Module powershell-yaml -ErrorAction Stop

function Write-Log { param([string] $Message) if ($VerboseLog) { Write-Host "[gen-skill] $Message" } }

function Normalize-Newlines {
  param([Parameter(Mandatory)][string] $Text, [switch] $Lf)
  $t = $Text -replace "`r`n", "`n"
  $t = $t -replace "`r", "`n"
  if ($Lf) { return $t }
  return ($t -replace "`n", "`r`n")
}

function Get-ContentUtf8([string] $Path) {
  [System.IO.File]::ReadAllText((Resolve-Path $Path), [System.Text.Encoding]::UTF8)
}

function Set-ContentUtf8([string] $Path, [string] $Text) {
  $utf8NoBom = New-Object System.Text.UTF8Encoding $false
  [System.IO.File]::WriteAllText($Path, $Text, $utf8NoBom)
}

function Compute-Sha256Hex([string] $Text) {
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
  $sha = [System.Security.Cryptography.SHA256]::Create()
  try {
    $hash = $sha.ComputeHash($bytes)
    return ($hash | ForEach-Object { $_.ToString("x2") }) -join ""
  } finally { $sha.Dispose() }
}

function Split-Frontmatter([string] $Markdown) {
  $md = Normalize-Newlines -Text $Markdown -Lf
  if (-not $md.StartsWith("---`n")) {
    return @{ Frontmatter = [ordered]@{}; Body = $Markdown; HadFrontmatter = $false }
  }
  $end = $md.IndexOf("`n---`n", 4)
  if ($end -lt 0) { throw "Frontmatter begins with '---' but no closing '---' found." }

  $yaml = $md.Substring(4, $end - 4)
  $body = $md.Substring($end + 5)

  # Use ConvertFrom-Yaml to parse frontmatter
  $frontmatter = ConvertFrom-Yaml $yaml -Ordered
  return @{ Frontmatter = $frontmatter; Body = $body; HadFrontmatter = $true }
}

function Extract-Sections([string] $Body, [string[]] $AllowedHeadings) {
  $allowed = New-Object 'System.Collections.Generic.HashSet[string]'
  foreach ($h in $AllowedHeadings) { [void]$allowed.Add($h) }

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

      if ($allowed.Contains($title)) {
        $keep = $true
        $keepLevel = $level
        $out.Add($line)
        continue
      }

      if ($keep -and $level -le $keepLevel) {
        $keep = $false
        $keepLevel = 0
      }

      if ($keep) { $out.Add($line) }
      continue
    }

    if ($keep) { $out.Add($line) }
  }

  $text = ($out -join "`n").Trim()
  if ($text.Length -eq 0) { return "" }
  return $text + "`n"
}

function Serialize-YamlValue($v, [int] $indent = 0) {
  $pad = (" " * $indent)

  if ($null -eq $v) { return @("$pad" + "null") }

  if ($v -is [bool]) { return @("$pad" + ($(if ($v) { "true" } else { "false" }))) }

  if ($v -is [int] -or $v -is [int64] -or $v -is [double]) { return @("$pad" + $v.ToString()) }

  if ($v -is [System.Collections.IList]) {
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($item in $v) {
      $itemStrs = Serialize-YamlValue $item ($indent + 2)
      # first line as "- x", rest as indented
      $lines.Add($pad + "- " + $itemStrs[0].TrimStart())
      for ($i = 1; $i -lt $itemStrs.Count; $i++) { $lines.Add($itemStrs[$i]) }
    }
    return $lines
  }

  if ($v -is [System.Collections.IDictionary]) {
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($k in $v.Keys) {
      $child = $v[$k]
      if ($child -is [System.Collections.IList] -or $child -is [System.Collections.IDictionary]) {
        $lines.Add("$pad${k}:")
        $lines.AddRange((Serialize-YamlValue $child ($indent + 2)))
      } else {
        $scalarLines = Serialize-YamlValue $child 0
        # quote strings here if needed
        $raw = $scalarLines[0]
        if ($child -is [string]) {
          $escaped = $child.Replace('"','\"')
          $raw = '"' + $escaped + '"'
        }
        $lines.Add("$pad${k}: $raw")
      }
    }
    return $lines
  }

  # string default, quoted
  $s = [string]$v
  $escaped = $s.Replace('"','\"')
  return @("$pad" + '"' + $escaped + '"')
}

function Build-SkillFrontmatter([hashtable] $Fm, [string] $SourceRelPath, [switch] $GeneratedHash, [string] $HashValue) {
  # Keep the keys Claude cares about. Drop keep_headings from generated output.
  $mapped = [ordered]@{}

  if ($Fm.Contains("name")) { $mapped["name"] = $Fm["name"] }
  if ($Fm.Contains("description")) { $mapped["description"] = $Fm["description"] }
  if ($Fm.Contains("allowed-tools")) { $mapped["allowed-tools"] = $Fm["allowed-tools"] }

  $mapped["generated"] = $true
  $mapped["generated-from"] = $SourceRelPath

  if ($GeneratedHash) { $mapped["generated-hash-sha256"] = $HashValue }

  $lines = New-Object System.Collections.Generic.List[string]
  $lines.Add("---")
  foreach ($k in $mapped.Keys) {
    $v = $mapped[$k]
    if ($v -is [System.Collections.IList] -or $v -is [System.Collections.IDictionary]) {
      $lines.Add("${k}:")
      $lines.AddRange((Serialize-YamlValue $v 2))
    } else {
      if ($v -is [string] -and $v.Contains("`n")) {
        # block scalar for multiline description
        # TrimEnd removes trailing newlines to avoid empty lines in output
        $lines.Add("${k}: |")
        foreach ($ln in (Normalize-Newlines -Text $v -Lf).TrimEnd("`n").Split("`n")) {
          $lines.Add("  " + $ln)
        }
      } elseif ($v -is [string]) {
        $escaped = $v.Replace('"','\"')
        $lines.Add("${k}: ""$escaped""")
      } elseif ($v -is [bool]) {
        $lines.Add("${k}: " + ($(if ($v) { "true" } else { "false" })))
      } else {
        $lines.Add("${k}: $v")
      }
    }
  }
  $lines.Add("---")
  return ($lines -join "`n") + "`n"
}

# Main
$rootPath = Resolve-Path $Root
# -Force includes hidden directories (like .claude/)
$canonicalFiles = @(Get-ChildItem -Path $rootPath -Recurse -Force -File -Filter $CanonicalName)
if ($canonicalFiles.Count -eq 0) { throw "No $CanonicalName found under $rootPath" }

$anyDiff = $false
foreach ($file in $canonicalFiles) {
  $canonicalPath = $file.FullName
  $dir = Split-Path -Parent $canonicalPath

  $md = Get-ContentUtf8 $canonicalPath
  $split = Split-Frontmatter $md
  $fm = $split.Frontmatter
  $body = $split.Body
  $rel = [System.IO.Path]::GetRelativePath($rootPath, $canonicalPath)

  # Extract keep_headings from metadata.generator.keep_headings
  # This path complies with Anthropic skill-creator validation rules
  # Skills without this config don't need .skill file generation
  $keep = $null
  if ($fm.Contains("metadata") -and
      $fm["metadata"] -is [System.Collections.IDictionary] -and
      $fm["metadata"].Contains("generator") -and
      $fm["metadata"]["generator"] -is [System.Collections.IDictionary] -and
      $fm["metadata"]["generator"].Contains("keep_headings")) {
    $keep = $fm["metadata"]["generator"]["keep_headings"]
  }

  if ($null -eq $keep) {
    Write-Log "Skipping (no metadata.generator.keep_headings): $rel"
    continue
  }

  if ($keep -isnot [System.Collections.IList]) {
    throw "'metadata.generator.keep_headings' must be a YAML list in $canonicalPath"
  }

  $hashInput = Normalize-Newlines -Text $md -Lf
  $hash = Compute-Sha256Hex $hashInput

  $front = Build-SkillFrontmatter -Fm $fm -SourceRelPath $rel -GeneratedHash:$IncludeHash -HashValue $hash
  $banner = @(
    "# GENERATED FILE",
    "# Source of truth: SKILL.md",
    "# Do not edit manually",
    "# Regenerate: pwsh ./scripts/gen-skills.ps1",
    ""
  ) -join "`n"

  $extracted = Extract-Sections -Body $body -AllowedHeadings ($keep | ForEach-Object { [string]$_ })

  $out = $front + $banner + "`n" + $extracted
  $out = Normalize-Newlines -Text $out -Lf:$ForceLf
  if (-not $out.EndsWith("`n")) { $out += "`n" }

  $baseName =
    if ($UseFolderName) { Split-Path -Leaf $dir }
    elseif ($fm.Contains("name")) { [string]$fm["name"] }
    else { Split-Path -Leaf $dir }

  $safe = ($baseName -replace '[\\/:*?"<>|]', "_").Trim()
  if ($safe.Length -eq 0) { $safe = "Skill" }

  $outPath = Join-Path $dir ($safe + $OutputExtension)

  $existing = $null
  if (Test-Path $outPath) {
    $existing = Normalize-Newlines -Text (Get-ContentUtf8 $outPath) -Lf:$ForceLf
  }

  $differs = ($null -eq $existing) -or ($existing -ne $out)
  if ($differs) {
    $anyDiff = $true
    Write-Host "DIFF: $([System.IO.Path]::GetRelativePath($rootPath, $outPath)) <= $rel"
    if (-not $DryRun) {
      Set-ContentUtf8 $outPath $out
      Write-Host "WROTE: $([System.IO.Path]::GetRelativePath($rootPath, $outPath))"
    }
  } else {
    Write-Log "No change: $([System.IO.Path]::GetRelativePath($rootPath, $outPath))"
  }
}

if ($Verify -and $anyDiff) {
  Write-Error "Verification failed: generated output differs. Run generator and commit changes."
  exit 1
}

exit 0
