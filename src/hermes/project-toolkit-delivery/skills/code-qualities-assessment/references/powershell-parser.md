# PowerShell Parser

PowerShell dependency counting uses PowerShell's own parser, not line matching.
The scanner runs `pwsh` and reads the syntax tree it returns.
It adds no Python package, so the scanner stays standard-library only.

## What counts

Each of these statements is one dependency:

- An `Import-Module` or `ipmo` call, including `& Import-Module` and `Microsoft.PowerShell.Core\Import-Module`.
- A `using module`, `using namespace`, or `using assembly` statement.
- A `#Requires` line that names `-Modules`.

Strings, here-strings, and ordinary comments do not count.
Other `#Requires` lines, such as `-Version` or `-PSEdition`, do not count.
PowerShell files get coupling and non-redundancy scores.
Cohesion, encapsulation, and testability are not scored for PowerShell.

## Requirement

Install PowerShell 7 or later and put `pwsh` on PATH.
Windows PowerShell 5.1 (`powershell.exe`) is not used.

## How it runs

The scanner starts one `pwsh` process per PowerShell file, with a 60 second timeout.
Each call costs about 0.65 seconds on a warm Linux machine.
The source goes to `pwsh` on stdin as base64 text, never on the command line.
`pwsh` runs in an empty temporary directory.
So a relative `using module ./X.psm1` or `using assembly ./X.dll` path resolves nowhere.

PowerShell resolves `using module` and `using assembly` while it parses.
A module or assembly this machine lacks is not an error, and the statement still counts.
Parsing does not run the code of a referenced module or assembly.

## Failures

These stop the scan with exit 1 and no report:

- `pwsh` is not on PATH, or it cannot start.
- `pwsh` times out, exits non-zero, or returns output the scanner cannot read.
- PowerShell reports a syntax error in the file. The message names the file and line.

The scanner never guesses a count and never falls back to regex.

## Limits

- A module manifest's `RequiredModules` and `NestedModules` keys in a `.psd1` file are not counted.
- The scanner reads files as UTF-8. A UTF-16 file cannot be read, as for every other language.

## Why not Tree-sitter

Issue rjmurillo/ai-agents#7437 first chose `tree-sitter-powershell==0.26.4`.
On 2026-11-18 that grammar marked 8 of 63 valid files with error nodes.
The files were the deduplicated modules shipped with pwsh 7.6.10.
`Export-ModuleMember -Function Get-A, Set-B` is one form it rejects.
The grammar also has no node for `using` statements or `#Requires`.
The maintainer then chose PowerShell's own parser, which reported 0 errors on the same files.
