# PowerShell Security Review

When reviewing PowerShell scripts (.ps1, .psm1), verify:

## Input Validation

- [ ] Parameters have `[ValidatePattern]`, `[ValidateSet]`, or `[ValidateScript]` attributes
- [ ] User input never passed directly to `Invoke-Expression` or `iex`
- [ ] File paths validated with `[ValidateScript({Test-Path $_ -PathType Leaf})]` or equivalent
- [ ] Numeric inputs have `[ValidateRange]` to prevent overflow or negative values
- [ ] String inputs have length limits via `[ValidateLength]`

## Command Injection Prevention (CWE-77, CWE-78)

**WHY**: Unquoted variables in external commands can be exploited when those programs invoke shells or interpret special characters. PowerShell passes unquoted `$Query` as a single argument to npx, but if the external program (or a shell it invokes) interprets metacharacters (`;|&><`), unintended commands execute. Quoting in PowerShell ensures the full string is passed as a single literal argument.

**UNSAFE**:

```powershell
# VULNERABLE - Special characters in $Query can inject commands
npx tsx $PluginScript $Query $OutputFile
```

**SAFE**:

```powershell
# SECURE - Variables quoted, metacharacters treated as literals
npx tsx "$PluginScript" "$Query" "$OutputFile"

# RECOMMENDED for 5+ parameters - Use array for readability
$Args = @("$PluginScript", "$Query", "$OutputFile")
& npx tsx $Args
```

**Checklist**:

- [ ] All variables in external commands are quoted (`"$Variable"` not `$Variable`)
- [ ] Check for unquoted variables in: `npx`, `node`, `python`, `git`, `gh`, `pwsh`, `bash`
- [ ] Avoid string concatenation for commands: `& "cmd $UserInput"` is UNSAFE
- [ ] For commands with 5+ parameters, use array variable with quoted elements

## Path Traversal Prevention (CWE-22, CWE-23, CWE-36)

**WHY**: `StartsWith()` performs string comparison on the raw path string BEFORE filesystem resolution. Attack: Constructed path contains `..` sequences that pass string comparison (because the string DOES start with the base directory), but when the filesystem later resolves `..` sequences, the path escapes to parent directories. `GetFullPath()` resolves `..` sequences BEFORE validation, revealing the true target path.

**UNSAFE**:

```powershell
# VULNERABLE - Path constructed before validation
$MemoriesDir = "C:\Users\App\Memories"
$UserInput = "..\..\..\Windows\System32\config"
$OutputFile = Join-Path $MemoriesDir $UserInput
# $OutputFile is now "C:\Users\App\Memories\..\..\..\Windows\System32\config"

if (-not $OutputFile.StartsWith($MemoriesDir)) {
    throw "Path traversal detected"
}
# DOES NOT THROW - String comparison passes: "C:\Users\App\Memories\..\..\..." DOES start with "C:\Users\App\Memories"
# When this path is later used by filesystem operations, ".." sequences resolve to C:\Windows\System32\config
```

**SAFE**:

```powershell
# SECURE - Normalize and validate with error handling
try {
    # Validate base directory
    if (-not $MemoriesDir) {
        throw "Base directory parameter is required"
    }

    $MemoriesDirFull = [System.IO.Path]::GetFullPath($MemoriesDir)
    $memoriesRoot = [System.IO.Path]::GetPathRoot($MemoriesDirFull)
    if ($MemoriesDirFull.Length -gt $memoriesRoot.Length) {
        $MemoriesDirFull = $MemoriesDirFull.TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
    }

    if (-not (Test-Path $MemoriesDirFull -PathType Container)) {
        throw "Base directory does not exist: $MemoriesDirFull"
    }

    # Validate user input
    if (-not $UserInput) {
        throw "User input path is required"
    }

    # Normalize output path
    $OutputFile = [System.IO.Path]::GetFullPath((Join-Path $MemoriesDirFull $UserInput))
    # $OutputFile is now "C:\Windows\System32\config" (normalized)

    # Check for path traversal
    if (-not $OutputFile.StartsWith($MemoriesDirFull + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Path traversal attempt detected. Path '$UserInput' resolves to '$OutputFile' which is outside allowed directory '$MemoriesDirFull'."
    }
    # THROWS - Normalized path "C:\Windows\System32\config" does not start with "C:\Users\App\Memories"

    Write-Host "[PASS] Path validated: $OutputFile"
}
catch [System.ArgumentException] {
    throw "Invalid path format: $_"
}
catch [System.IO.PathTooLongException] {
    throw "Path exceeds maximum length: $_"
}
catch [System.Security.SecurityException] {
    throw "Access denied to path: $_"
}
catch {
    throw "Path validation failed: $_"
}
```

**Checklist**:

- [ ] Use `[System.IO.Path]::GetFullPath()` to normalize paths before validation
- [ ] Never trust `StartsWith()` for path containment without normalization
- [ ] Validate resolved path within allowed directory AFTER normalization
- [ ] Check for symlinks with `$_.Attributes -band [IO.FileAttributes]::ReparsePoint`
- [ ] Use `Join-Path` instead of string concatenation for path building

## Secrets and Credentials

- [ ] No hardcoded passwords, API keys, tokens, or connection strings
- [ ] Use `Read-Host -AsSecureString` for password input
- [ ] Use `ConvertTo-SecureString` and `PSCredential` for credential handling
- [ ] Avoid `Write-Host` or logging for sensitive data (check `Write-Verbose`, `Write-Debug`)
- [ ] Environment variables for secrets use `$env:` prefix, not hardcoded values

## Error Handling

- [ ] `Set-StrictMode -Version Latest` at script top to catch uninitialized variables
- [ ] `$ErrorActionPreference = 'Stop'` for production scripts (fail-fast)
- [ ] Try-catch blocks do not expose sensitive data in error messages
- [ ] Exit codes checked after external commands: `if ($LASTEXITCODE -ne 0) { throw }`
- [ ] Error messages do not reveal internal paths, stack traces, or implementation details

## Code Execution (CWE-94, CWE-95)

**WHY**: `Invoke-Expression` executes strings as PowerShell code. No sanitization. Attack: User input passed directly to interpreter. Solution: Hashtable restricts to predefined commands, user selects KEY not syntax.

**UNSAFE**:

```powershell
# VULNERABLE - User input executed as PowerShell code
$UserCommand = Read-Host "Enter command"
Invoke-Expression $UserCommand
```

**SAFE**:

```powershell
# SECURE - Predefined commands, user selects option
$AllowedCommands = @{
    'status' = { git status }
    'log'    = { git log -n 10 }
}
$Choice = Read-Host "Choose: status, log"
if ($AllowedCommands.ContainsKey($Choice)) {
    & $AllowedCommands[$Choice]
}
```

**Checklist**:

- [ ] No use of `Invoke-Expression` unless absolutely required with sanitized input
- [ ] No `$ExecutionContext.InvokeCommand.ExpandString()` with external input
- [ ] No `Add-Type` with user-controlled C# code
- [ ] No `.Invoke()` on user-provided script blocks
- [ ] No dynamic module imports from untrusted paths

## References

- [OWASP PowerShell Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/PowerShell_Security_Cheat_Sheet.html)
- [CWE-77 Command Injection](https://cwe.mitre.org/data/definitions/77.html)
- [CWE-22 Path Traversal](https://cwe.mitre.org/data/definitions/22.html)
- [PowerShell Security Best Practices](https://learn.microsoft.com/en-us/powershell/scripting/dev-cross-plat/security/securing-powershell)
