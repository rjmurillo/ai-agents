---
paths:
  - "**/*.ps1"
  - "**/*.psm1"
  - "**/*.psd1"
description: PowerShell 7+ style (layout, naming, help), best practices (parameters, errors, output, security, performance), and cross-platform pitfalls. Applies when editing PowerShell scripts or modules.
---

# PowerShell Rules

These rules apply when you write or review PowerShell. Baseline is PowerShell 7+
(cross-platform `pwsh`), NOT Windows PowerShell 5.1. Write for Linux and macOS
runners as well as Windows. Style and practice follow the community
[PowerShell Practice and Style guide](https://github.com/PoshCode/PowerShellPracticeAndStyle),
adapted to that baseline. Precedence: the host repo's `PSScriptAnalyzer` settings,
then this file, then the upstream guide.

## Layout and Formatting

- Indent four spaces per level. No tab characters. Continuation lines may indent
  further to line up with the line above.
- Use One True Brace Style: the opening brace ends the line, the closing brace
  starts its own line, and `} else {` stays on one line. Exception: a short
  scriptblock argument may sit on one line (`Where-Object { $_.Length -gt 10mb }`).
- Keep lines at or under 115 characters where you can. Break long commands with
  splatting or with the implicit continuation inside `()`, `[]`, `{}`, or after
  `|` and `,`. Avoid backtick continuation: one trailing space after the backtick
  breaks the parse with an error that points somewhere else.
- Put one space around operators and parameter names, after commas and
  semicolons, and inside `{ }` and `$( )`. No space inside `()` or `[]`, after a
  unary operator (`$i++`, `-1`), or around the colon of `-Switch:$value`.
- No trailing whitespace. End each file with one newline. Put two blank lines
  around function and class definitions and one between class methods.
- Do not end lines with `;`, including in a multi-line hashtable.
- Reformat whitespace in its own commit, never mixed with a content change.

## Capitalization and Naming

- PascalCase every public identifier: functions, parameters, modules, classes,
  enums, properties, and script or global variables. camelCase is allowed for
  private locals. Capitalize both letters of a two-letter acronym (`Get-PSDrive`),
  but treat `Id` and `Ok` as words.
- Write language keywords (`foreach`, `param`, `process`) and operators (`-eq`,
  `-match`) in lowercase. Write comment-help keywords (`.SYNOPSIS`) in uppercase.
- Name commands `Verb-Noun` with an approved verb (`Get-Verb`) and a singular
  PascalCase noun. A function named `DoStuff` will not pass review.
- Reuse the built-in parameter names (`-Path`, `-Name`, `-ComputerName`,
  `-Credential`, `-Force`) instead of inventing `$Param_Computer` or `$InstanceName`.
- Use full command names, never aliases (`Get-ChildItem`, not `gci`, `ls`, or
  `dir`). Pass parameters by name, not position (`Get-Process -Name pwsh`).
- Prefix shared state with its scope (`$script:Cache`) so a reader can tell it
  from a local.

## Script and Function Structure

- Start every script and function from `[CmdletBinding()]` and a `param()`
  block, then `begin`, `process`, and `end` in execution order. Name the `end`
  block explicitly and do not use the `filter` keyword.
- Make every non-trivial function an advanced function with typed, attributed
  parameters (`[Parameter(Mandatory)]`, `[ValidateNotNullOrEmpty()]`,
  `[ValidateSet(...)]`).
- Validate input with attributes, not `if` checks in the body: `ValidateSet`,
  `ValidateRange`, `ValidateLength`, `ValidateCount`, `ValidatePattern`,
  `ValidateScript`, `ValidateNotNull`, `ValidateNotNullOrEmpty`, and the
  `AllowNull`, `AllowEmptyString`, `AllowEmptyCollection` opt-ins.
- Declare `[OutputType()]` when a command returns objects, one per parameter set
  when sets return different types. When any parameter names a
  `ParameterSetName`, set `DefaultParameterSetName` in `[CmdletBinding()]`.
- Type every parameter. Be careful with `[string]`, `[object]`, and `[psobject]`
  on `ValueFromPipeline` parameters or parameter-set discriminators: every value
  coerces to them, so binding picks the wrong set. Pass values on to another
  command with a type at least as strong as its parameter.
- `[switch]` parameters get no default and default to off. Turning one on moves
  the command to a less common mode. Treat a switch as two-state, and forward it
  with `-Other:$MySwitch` or splatting.
- Accept `ValueFromPipelineByPropertyName` wherever practical, with `[Alias()]`
  for common property names. Pipeline-bound values exist only in `process {}`.
- Emit each result from `process {}` as it is ready. Do not collect results and
  emit them in `end {}`, and do not write `return $obj` to produce output: every
  uncaptured value is output, so place the object on its own line.
- A command that changes state declares
  `[CmdletBinding(SupportsShouldProcess, ConfirmImpact = 'Medium')]`, gates each
  change with `$PSCmdlet.ShouldProcess(...)`, and forwards `-WhatIf:$WhatIfPreference`
  to the commands it calls. A `ShouldContinue` prompt needs a `-Force` bypass.

## Tools, Controllers, and Reuse

- Put reusable logic in advanced functions, ideally in a module. A tool takes
  input only through parameters and emits raw objects (bytes, not a formatted
  "12 GB" string). A controller script composes tools for one process and may
  format for people.
- Do not call `Format-*` inside a tool. Give module output a `PSTypeName` and a
  `.format.ps1xml` view listed in `FormatsToProcess`.
- Search for a built-in before writing one (`Test-Connection`, not a wrapper
  around `ping`). When you must call a native tool or a .NET API instead, wrap it
  in an advanced function and comment why the built-in did not fit.

## Output Streams

- Results go to the success stream (bare output or `Write-Output`); let the
  caller format.
- `Write-Verbose` carries detail for the person running the script,
  `Write-Debug` carries detail for the maintainer, `Write-Warning` and
  `Write-Error` carry problems. `Write-Progress` is ephemeral, so never put
  something the user needs only there.
- Use `Write-Host` only in a `Show-` or `Format-` command or an interactive
  prompt. Never use it for data.
- Emit one kind of object per command. Never mix strings into object output,
  which breaks table formatting. Internal helpers may return several types to a
  caller that assigns them (`$user, $group = Get-UserAndGroup`).

## Documentation and Comments

- Put comment-based help inside the function, at the top, above `param()`. It
  needs a `.SYNOPSIS` that says more than the name ("Gets LOB app users" fails),
  a `.DESCRIPTION`, one `.EXAMPLE` per major use case (code first, then what it
  does), and `.NOTES` for detail.
- Document each parameter with a comment directly above it inside `param()`
  rather than in `.PARAMETER` blocks, so the comment moves with the parameter.
- Put the `<#` and `#>` of a block comment on their own lines. Start each line
  comment with `#`. Keep inline comments at least two spaces from the code.
- Comment the why, not the what; a regex is the exception. A comment that
  contradicts the code is worse than none, so update comments with the code.

## Cross-Platform and Paths

- Build paths with `Join-Path` or `[IO.Path]::Combine`, never string
  concatenation with `\`. Use `[IO.Path]::DirectorySeparatorChar` when you must.
- Anchor paths on `$PSScriptRoot`, not `.` or `..`. .NET methods and native
  executables resolve relative paths against `[Environment]::CurrentDirectory`,
  which does not follow `$PWD`, so pass them full paths (`Convert-Path`).
- Use `$HOME`, not `~`, whose meaning depends on the current provider. Use
  `[IO.Path]::GetTempPath()`, not `$env:TEMP` or other Windows-only paths. Do not
  assume `C:\` or backslashes.
- Declare the minimum version: `#Requires -Version 7.0` (or higher when you use a
  newer feature) in scripts and `PowerShellVersion` in module manifests.
- Normalize line endings when comparing multi-line output across platforms.

## Error Handling

- Set `$ErrorActionPreference = 'Stop'` at the top of scripts that must fail fast,
  or pass `-ErrorAction Stop` to each cmdlet whose error you trap.
  Non-terminating errors are silent by default and hide failures.
- Put the whole transaction in one `try` block instead of setting a success flag
  and testing it afterwards. Catch specific exception types where you can. Clean
  up in `finally`.
- In `catch`, copy the error first (`$err = $_`): the next command can replace
  `$_` and `$Error[0]`. Do not clear `$Error`.
- Do not diagnose failures with `$?`, which carries no detail, or with a `$null`
  result when the command can raise a terminating error instead.
- After calling an external (native) executable, check `$LASTEXITCODE` explicitly
  and reset it. A non-zero `$LASTEXITCODE` left over from one command makes a
  later step or the whole workflow look failed.
- Standardize process exit codes per ADR-035: `0` success, `1` logic or validation
  error, `2` usage or configuration error, `3` external or dependency failure,
  `4` authentication or authorization failure (`5`-`99` reserved, `100`+ documented
  script-specific). `exit` with the matching code so callers and CI branch on the
  cause, not just pass or fail.

## Security

- Take credentials as a `[pscredential]` parameter named `$Credential`. Never
  accept a password as a plain `[string]`, which lands in history and logs, and
  never call `Get-Credential` inside a function.
- When an API needs plain text, unwrap at the call site
  (`$api.SetPassword($Credential.GetNetworkCredential().Password)`). Do not store
  the plain text in a variable.
- Hold other secrets as `[securestring]`. If you must convert one with
  `[Runtime.InteropServices.Marshal]::SecureStringToBSTR`, call `ZeroFreeBSTR` in
  `finally`.
- `Export-Clixml` and `ConvertFrom-SecureString` encrypt with DPAPI on Windows
  only. On Linux and macOS the saved value is not encrypted, so persist secrets
  in a secret store or environment variables, never in a file.
- Never use `Invoke-Expression` on data you did not write. Call the command
  directly, or splat its arguments.

## Performance

- Measure before you optimize (`Measure-Command`), on the PowerShell version and
  hardware that matter. For small inputs, keep the more readable form.
- Rough cost order, cheapest first: language features, compiled .NET methods,
  plain script, then cmdlet and function calls. The `foreach` statement beats
  `ForEach-Object`.
- Stream large inputs through the pipeline, or through a `StreamReader` wrapped
  in a function, instead of loading a whole file into a variable.

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

- PowerShell Practice and Style: <https://github.com/PoshCode/PowerShellPracticeAndStyle>
- PowerShell docs: <https://learn.microsoft.com/powershell/>
- Cmdlet development guidelines: <https://learn.microsoft.com/powershell/scripting/developer/cmdlet/cmdlet-development-guidelines>
- Pester: <https://pester.dev/>
- PSScriptAnalyzer rules: <https://learn.microsoft.com/powershell/utility-modules/psscriptanalyzer/rules/readme>
