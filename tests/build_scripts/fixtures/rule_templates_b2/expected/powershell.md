---
paths:
  - "**/*.ps1"
  - "**/*.psm1"
  - "**/*.psd1"
description: PowerShell 7+ style (layout, naming, help), best practices (parameters, errors, output, security, performance), and cross-platform pitfalls. Applies when editing PowerShell scripts or modules.
---

# PowerShell Rules

Baseline is PowerShell 7+ (`pwsh`) on Linux, macOS, and Windows, NOT Windows
PowerShell 5.1. Style follows the [PowerShell Practice and Style guide](https://github.com/PoshCode/PowerShellPracticeAndStyle),
adapted to that baseline. The repo's `PSScriptAnalyzer` settings win over this file.

## Layout

- Four spaces per indent, no tabs. One True Brace Style: `{` ends the line, `}`
  starts one, `} else {`. A short scriptblock argument may stay on one line.
- Lines at most 115 characters. Break with splatting or inside `()`, `[]`, `{}`,
  or after `|` and `,`. Avoid backtick continuation: a trailing space breaks it.
- One space around operators and parameter names, after `,` and `;`, and inside
  `{ }` and `$( )`. None inside `()` or `[]`, after a unary operator (`$i++`),
  in `-Switch:$value`, or in `${Var}`. Never change string output for spacing.
- No trailing whitespace, no `;` line endings. One final newline. Two blank lines
  around functions and classes. Reformat whitespace in its own commit.

## Naming

- PascalCase public names: functions, parameters, classes, properties, script
  variables. camelCase is fine for locals. `PSDrive`, but `Id` and `Ok`.
- Lowercase keywords and operators (`foreach`, `-eq`). Uppercase help keywords.
- `Verb-Noun` with an approved verb (`Get-Verb`) and a singular noun. Reuse
  built-in parameter names (`-Path`, `-ComputerName`, `-Credential`, `-Force`).
- Full command names, never aliases (`Get-ChildItem`, not `gci` or `ls`). Named
  parameters, not positional. Scope-prefix shared state (`$script:Cache`).

## Functions

- Start from `[CmdletBinding()]` and typed `param()`, then `begin`, `process`,
  `end` in order. Name `end` explicitly. No `filter` keyword.
- Take `ValueFromPipelineByPropertyName` where practical, with `[Alias()]`.
- Validate with attributes (`ValidateSet`, `ValidateRange`, `ValidatePattern`,
  `ValidateScript`, `ValidateNotNullOrEmpty`, `AllowNull`, ...), not body `if`s.
- Declare `[OutputType()]`, one per parameter set when types differ. Any
  `ParameterSetName` requires `DefaultParameterSetName`.
- Avoid `[string]` or `[object]` on pipeline or set-choosing parameters:
  everything coerces to them. Forward values with at least the callee's type.
- `[switch]`: no default, off means the common mode, two states only. Forward as
  `-Other:$MySwitch`.
- Emit each per-input result in `process {}`; do not collect them for `end`.
  Only output that needs all input (a sort, a total) belongs in `end {}`. No
  `return $obj`.
- State changes need `SupportsShouldProcess` and `ConfirmImpact`, a
  `$PSCmdlet.ShouldProcess()` gate, and `-WhatIf:$WhatIfPreference` passed down.
  `ShouldContinue` needs a `-Force` bypass.
- Tools take input only from parameters and emit raw objects (bytes, not
  "12 GB"). Controller scripts compose tools and may format. Never `Format-*`
  in a tool; ship a `.format.ps1xml` view. Prefer a built-in (`Test-Connection`)
  over wrapping a native tool; if you wrap one, comment why.

## Output

- Results go to the success stream. `Write-Verbose` for users, `Write-Debug`
  for maintainers, `Write-Warning` and `Write-Error` for problems,
  `Write-Progress` only for ephemeral status.
- `Write-Host` only in a `Show-` command or an interactive prompt. Where the
  analyzer enforces `PSAvoidUsingWriteHost`, justify any suppression. Never
  for data.
- One object type per command. No strings mixed into object output.

## Help and Comments

- Help sits inside the function, above `param()`: a `.SYNOPSIS` that says more
  than the name, `.DESCRIPTION`, one `.EXAMPLE` per use case, `.NOTES`.
- Document each parameter with a comment right above it in `param()`.
- `<#` and `#>` on their own lines. Comment the why. Fix stale comments.

## Paths

- `Join-Path` or `[IO.Path]::Combine`, never `\` concatenation. No `C:\`.
- Anchor on `$PSScriptRoot`, not `.`. .NET methods resolve relative paths
  against `[Environment]::CurrentDirectory`, not `$PWD`; pass full paths.
- `$HOME`, not `~`. `[IO.Path]::GetTempPath()`, not `$env:TEMP`.
- `#Requires -Version 7.0` or higher; `PowerShellVersion` in manifests.
- Normalize line endings when comparing multi-line output.

## Errors

- `$ErrorActionPreference = 'Stop'`, or `-ErrorAction Stop` on each trapped call:
  non-terminating errors let execution continue past a failure.
- One `try` around the whole transaction, no success flags. Catch specific
  types. Clean up in `finally`. In `catch`, copy `$_` first.
- Do not diagnose with `$?` or a `$null` result.
- After a native executable, check `$LASTEXITCODE` and reset it; a stale
  non-zero value fails a later step.
- Exit codes per ADR-035: `0` success, `1` logic, `2` config, `3` external,
  `4` auth (`5`-`99` reserved, `100`+ script-specific).

## Security

- Credentials: a `[pscredential]` parameter named `$Credential`. No plain-text
  password parameter; no `Get-Credential` inside a function.
- Unwrap at the call site (`$Credential.GetNetworkCredential().Password`) or
  with `ConvertFrom-SecureString -AsPlainText`; never keep plain text.
- `Export-Clixml`, and `ConvertFrom-SecureString` without `-Key`, encrypt on
  Windows only. Elsewhere use a secret store (SecretManagement or CI secrets).
- No `Invoke-Expression` on data. Call the command or splat.

## Performance

- Measure (`Measure-Command`) first; small inputs favor readability.
- Cost order: language, .NET methods, script, then cmdlet calls. `foreach`
  beats `ForEach-Object`. Stream large files; do not load them into a variable.

## Testing

- Pester 5+, `Describe`/`Context`/`It`. Pester 5 runs discovery separately, so
  set shared state in `BeforeAll`, not at script scope.
- Run `PSScriptAnalyzer` in CI. Justify every suppression.

## Pitfalls

- **Scalar results.** One result is a scalar: a string indexes to a char and
  strict mode fails `.Count`. Wrap in `@()`; `[array]$null` stays `$null`.
- **Case.** `-match`, `-eq`, `-contains`, `-replace` ignore case; use `-cmatch`,
  `-ceq`, `-creplace` when case is the signal. Variable names ignore case too.
- **`$null` comparisons.** Put `$null` on the left (`$null -eq $x`); on the
  right, a collection filters instead of comparing. Guard `$null` collections.
- **`Import-Module foo.psm1`** searches `$env:PSModulePath`. Use `./foo.psm1`
  or `$PSScriptRoot`.
- **Here-strings.** The closing `"@` or `'@` must sit at column 0.

## References

<https://learn.microsoft.com/powershell/>, <https://pester.dev/>,
[PSScriptAnalyzer rules](https://learn.microsoft.com/powershell/utility-modules/psscriptanalyzer/rules/readme).
