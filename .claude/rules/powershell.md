---
paths:
  - "**/*.ps1"
  - "**/*.psm1"
  - "**/*.psd1"
description: PowerShell 7+ idioms, error handling, and cross-platform pitfalls. Applies when editing PowerShell scripts or modules.
---

# PowerShell Rules

These rules apply when you write or review PowerShell. Baseline is PowerShell 7+
(cross-platform `pwsh`), NOT Windows PowerShell 5.1. Write for Linux and macOS
runners as well as Windows. Defer to `PSScriptAnalyzer` settings in the repo.

## Structure

- Make every non-trivial function an advanced function: `[CmdletBinding()]` plus
  a `param()` block with typed, attributed parameters
  (`[Parameter(Mandatory)]`, `[ValidateNotNullOrEmpty()]`, `[ValidateSet(...)]`).
- Use approved verbs (`Get-Verb`) and `Verb-Noun` names. `Get-`, `Set-`,
  `New-`, `Remove-`, `Test-`. A function named `DoStuff` will not pass review.
- Emit objects to the pipeline; let the caller format. Do not `Write-Host` data.
  Use `Write-Output` (or bare output) for results, `Write-Verbose`/`Write-Warning`/
  `Write-Error` for diagnostics, and `Write-Host` only for genuine console UX.
- Support the pipeline with `process {}` blocks and `ValueFromPipeline` when a
  function operates on a stream of inputs.

## Cross-Platform

- Build paths with `Join-Path` or `[IO.Path]::Combine`, never string
  concatenation with `\`. Use `[IO.Path]::DirectorySeparatorChar` when you must.
- Use `$env:TEMP` via `[IO.Path]::GetTempPath()` and `$HOME`, not Windows-only
  paths. Do not assume `C:\` or backslashes.
- Prefer `[Environment]::NewLine` awareness in tests; normalize line endings when
  comparing multi-line output across platforms.

## Error Handling

- Set `$ErrorActionPreference = 'Stop'` at the top of scripts that must fail fast,
  or pass `-ErrorAction Stop` per call. Non-terminating errors are silent by
  default and hide failures.
- Wrap risky calls in `try/catch/finally`. Catch specific exception types where
  you can. Clean up in `finally`.
- After calling an external (native) executable, check `$LASTEXITCODE` explicitly
  and reset it. A non-zero `$LASTEXITCODE` left over from one command makes a
  later step or the whole workflow look failed.
- Standardize process exit codes per ADR-035: `0` success, `1` logic or validation
  error, `2` usage or configuration error, `3` external or dependency failure,
  `4` authentication or authorization failure (`5`-`99` reserved, `100`+ documented
  script-specific). `exit` with the matching code so callers and CI branch on the
  cause, not just pass or fail.

## Testing

- Pester 5+ for tests, with `Describe`/`Context`/`It` describing behavior. Keep
  discovery-phase and run-phase code separate (Pester 5 runs `Describe` blocks
  twice). Initialize shared state in `BeforeAll`, not at script scope.
- Run `PSScriptAnalyzer` in CI and fix findings. Do not suppress a rule without a
  justifying comment.

## Anti-Patterns to Reject

These are repeat offenders observed in this codebase. They pass on one platform or
one input shape and fail on another.

- **Assuming a command returns an array.** A pipeline that yields one item returns
  a scalar, so `$result.Count` is missing and indexing breaks. Force an array:
  `@(Get-Thing)` or `[array]$result`.
- **Case-insensitive matching when you need case-sensitive.** `-match`, `-eq`,
  `-contains`, and `-replace` are case-INsensitive by default. Use the `c`-prefixed
  operators (`-cmatch`, `-ceq`, `-creplace`) when case matters, especially when
  parsing AI or tool output where token case is the signal.
- **`-contains` with a possibly-null left operand.** `$null -contains $x` and a
  null collection silently return `$false`. Guard the collection, or put the
  known-non-null collection on the left and the candidate on the right.
- **`Import-Module` of a relative path without `./`.** `Import-Module foo.psm1`
  searches `$env:PSModulePath`, not the current directory. Use
  `Import-Module ./foo.psm1` (or an absolute path via `$PSScriptRoot`).
- **Relying on case to distinguish variables.** PowerShell variable names are
  case-INsensitive: `$Result` and `$result` are the same variable. Do not let two
  "different" names alias each other.
- **An indented here-string terminator.** The closing `"@` / `'@` MUST sit at
  column 0 with no leading whitespace, or the string never closes and the parser
  fails with a confusing error.

## References

- PowerShell docs: <https://learn.microsoft.com/powershell/>
- Cmdlet development guidelines: <https://learn.microsoft.com/powershell/scripting/developer/cmdlet/cmdlet-development-guidelines>
- Pester: <https://pester.dev/>
- PSScriptAnalyzer rules: <https://learn.microsoft.com/powershell/utility-modules/psscriptanalyzer/rules/readme>
