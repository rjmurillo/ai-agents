# Python for PowerShell Developers

**Reference**: ADR-042 Python Migration Strategy
**Audience**: Developers migrating scripts from PowerShell to Python
**Status**: Active

---

## Overview

This guide provides a side-by-side comparison of PowerShell and Python syntax to help developers migrate existing scripts. The examples follow the coding standards in `pyproject.toml`.

---

## Variables and Types

| PowerShell | Python |
|------------|--------|
| `$variable = "value"` | `variable = "value"` |
| `[string]$name = "Bob"` | `name: str = "Bob"` |
| `[int]$count = 42` | `count: int = 42` |
| `[bool]$flag = $true` | `flag: bool = True` |
| `[array]$items = @(1, 2, 3)` | `items: list[int] = [1, 2, 3]` |
| `[hashtable]$map = @{ a = 1 }` | `map: dict[str, int] = {"a": 1}` |
| `$null` | `None` |
| `$true` / `$false` | `True` / `False` |

---

## Functions

### PowerShell

```powershell
function Get-UserName {
    param(
        [Parameter(Mandatory)]
        [string]$UserId,

        [int]$Timeout = 30
    )

    return "user_$UserId"
}

# Call
$name = Get-UserName -UserId "123" -Timeout 60
```

### Python

```python
def get_user_name(user_id: str, timeout: int = 30) -> str:
    """Get the username for a given user ID.

    Args:
        user_id: The user identifier.
        timeout: Request timeout in seconds.

    Returns:
        The username string.
    """
    return f"user_{user_id}"


# Call
name = get_user_name("123", timeout=60)
```

---

## Control Flow

### If/Else

| PowerShell | Python |
|------------|--------|
| `if ($x -eq $y) { ... }` | `if x == y:` |
| `if ($x -ne $y) { ... }` | `if x != y:` |
| `if ($x -gt $y) { ... }` | `if x > y:` |
| `if ($x -lt $y) { ... }` | `if x < y:` |
| `if ($x -ge $y) { ... }` | `if x >= y:` |
| `if ($x -le $y) { ... }` | `if x <= y:` |
| `if ($x -and $y) { ... }` | `if x and y:` |
| `if ($x -or $y) { ... }` | `if x or y:` |
| `if (-not $x) { ... }` | `if not x:` |
| `elseif { ... }` | `elif:` |
| `else { ... }` | `else:` |

### PowerShell

```powershell
if ($status -eq "active") {
    Write-Host "Active"
}
elseif ($status -eq "pending") {
    Write-Host "Pending"
}
else {
    Write-Host "Unknown"
}
```

### Python

```python
if status == "active":
    print("Active")
elif status == "pending":
    print("Pending")
else:
    print("Unknown")
```

---

## Loops

### ForEach

| PowerShell | Python |
|------------|--------|
| `foreach ($item in $list) { ... }` | `for item in list:` |
| `$list \| ForEach-Object { $_ }` | `[f(x) for x in list]` |

### PowerShell

```powershell
foreach ($file in $files) {
    Write-Host $file.Name
}

# Pipeline style
$files | ForEach-Object { $_.Name }
```

### Python

```python
for file in files:
    print(file.name)

# List comprehension
names = [f.name for f in files]
```

### For (Index-based)

| PowerShell | Python |
|------------|--------|
| `for ($i = 0; $i -lt 10; $i++) { ... }` | `for i in range(10):` |

### While

| PowerShell | Python |
|------------|--------|
| `while ($condition) { ... }` | `while condition:` |

---

## Error Handling

### PowerShell

```powershell
try {
    $content = Get-Content $path -ErrorAction Stop
}
catch [System.IO.FileNotFoundException] {
    Write-Error "File not found: $path"
    exit 1
}
catch {
    Write-Error "Unexpected error: $_"
    exit 2
}
finally {
    Write-Host "Cleanup complete"
}
```

### Python

```python
try:
    content = path.read_text()
except FileNotFoundError:
    print(f"File not found: {path}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"Unexpected error: {e}", file=sys.stderr)
    sys.exit(2)
finally:
    print("Cleanup complete")
```

---

## File Operations

| PowerShell | Python |
|------------|--------|
| `Get-Content $file` | `Path(file).read_text()` |
| `Set-Content $file -Value $text` | `Path(file).write_text(text)` |
| `Get-ChildItem $dir` | `Path(dir).iterdir()` |
| `Get-ChildItem $dir -Recurse` | `Path(dir).rglob("*")` |
| `Test-Path $path` | `Path(path).exists()` |
| `Test-Path $path -PathType Leaf` | `Path(path).is_file()` |
| `Test-Path $path -PathType Container` | `Path(path).is_dir()` |
| `New-Item -ItemType Directory $dir` | `Path(dir).mkdir(parents=True)` |
| `Remove-Item $path` | `Path(path).unlink()` |
| `Join-Path $a $b` | `Path(a) / b` |
| `Split-Path $path -Leaf` | `Path(path).name` |
| `Split-Path $path -Parent` | `Path(path).parent` |

### PowerShell

```powershell
$content = Get-Content $configFile | ConvertFrom-Json
$content.version = "2.0"
$content | ConvertTo-Json | Set-Content $configFile
```

### Python

```python
from pathlib import Path
import json

config_file = Path(config_file)
content = json.loads(config_file.read_text())
content["version"] = "2.0"
config_file.write_text(json.dumps(content, indent=2))
```

---

## JSON Operations

| PowerShell | Python |
|------------|--------|
| `ConvertFrom-Json $text` | `json.loads(text)` |
| `ConvertTo-Json $obj` | `json.dumps(obj)` |
| `ConvertTo-Json $obj -Depth 10` | `json.dumps(obj)` (no depth limit) |

---

## String Operations

| PowerShell | Python |
|------------|--------|
| `"Hello $name"` | `f"Hello {name}"` |
| `$text.Split(",")` | `text.split(",")` |
| `$text.Trim()` | `text.strip()` |
| `$text.ToLower()` | `text.lower()` |
| `$text.ToUpper()` | `text.upper()` |
| `$text.Replace("a", "b")` | `text.replace("a", "b")` |
| `$text -match "pattern"` | `re.search("pattern", text)` |
| `$text -replace "old", "new"` | `re.sub("old", "new", text)` |
| `$text.StartsWith("prefix")` | `text.startswith("prefix")` |
| `$text.EndsWith("suffix")` | `text.endswith("suffix")` |
| `$text.Contains("sub")` | `"sub" in text` |
| `[string]::IsNullOrEmpty($s)` | `not s` |

---

## Collections

### Arrays/Lists

| PowerShell | Python |
|------------|--------|
| `@()` | `[]` |
| `@(1, 2, 3)` | `[1, 2, 3]` |
| `$arr += $item` | `arr.append(item)` |
| `$arr.Count` | `len(arr)` |
| `$arr[0]` | `arr[0]` |
| `$arr[-1]` | `arr[-1]` |
| `$arr[1..3]` | `arr[1:4]` |
| `$arr -contains $x` | `x in arr` |
| `$arr \| Where-Object { $_ -gt 5 }` | `[x for x in arr if x > 5]` |
| `$arr \| Select-Object -First 5` | `arr[:5]` |
| `$arr \| Sort-Object` | `sorted(arr)` |

### Hashtables/Dictionaries

| PowerShell | Python |
|------------|--------|
| `@{}` | `{}` |
| `@{ key = "value" }` | `{"key": "value"}` |
| `$hash.key` | `hash["key"]` |
| `$hash["key"]` | `hash["key"]` |
| `$hash.Keys` | `hash.keys()` |
| `$hash.Values` | `hash.values()` |
| `$hash.ContainsKey("k")` | `"k" in hash` |

---

## Running External Commands

### PowerShell

```powershell
$result = git status 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "Git failed: $result"
    exit $LASTEXITCODE
}
```

### Python

```python
import subprocess

result = subprocess.run(
    ["git", "status"],
    capture_output=True,
    text=True,
    check=False
)

if result.returncode != 0:
    print(f"Git failed: {result.stderr}", file=sys.stderr)
    sys.exit(result.returncode)
```

---

## Command-Line Arguments

### PowerShell

```powershell
param(
    [Parameter(Mandatory)]
    [string]$SessionPath,

    [switch]$Strict,

    [int]$Timeout = 30
)
```

### Python

```python
import argparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process session")
    parser.add_argument(
        "--session-path",
        required=True,
        help="Path to session file"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Enable strict mode"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout in seconds"
    )
    return parser.parse_args()
```

---

## Testing

### Pester (PowerShell)

```powershell
Describe "Get-UserName" {
    It "Returns formatted username" {
        $result = Get-UserName -UserId "123"
        $result | Should -Be "user_123"
    }

    It "Throws on empty input" {
        { Get-UserName -UserId "" } | Should -Throw
    }
}
```

### pytest (Python)

```python
import pytest


def test_get_user_name_returns_formatted():
    """Returns formatted username."""
    result = get_user_name("123")

    assert result == "user_123"


def test_get_user_name_raises_on_empty():
    """Raises on empty input."""
    with pytest.raises(ValueError):
        get_user_name("")
```

---

## Common Patterns

### Null Coalescing

| PowerShell | Python |
|------------|--------|
| `$x ?? "default"` | `x or "default"` |
| `$x ??= "default"` | `x = x or "default"` |

### Ternary Operator

| PowerShell | Python |
|------------|--------|
| `$x ? "yes" : "no"` | `"yes" if x else "no"` |

### Pipeline to Comprehension

| PowerShell | Python |
|------------|--------|
| `$arr \| ForEach-Object { $_.Name }` | `[x.name for x in arr]` |
| `$arr \| Where-Object { $_.Active }` | `[x for x in arr if x.active]` |
| `$arr \| Select-Object Name, Age` | `[{"name": x.name, "age": x.age} for x in arr]` |

---

## Script Template

### PowerShell

```powershell
#Requires -Version 7.0

param(
    [Parameter(Mandatory)]
    [string]$InputPath
)

$ErrorActionPreference = "Stop"

try {
    # Business logic
    $data = Get-Content $InputPath | ConvertFrom-Json
    Write-Output "Processed: $($data.Count) items"
    exit 0
}
catch {
    Write-Error "Failed: $_"
    exit 1
}
```

### Python

```python
#!/usr/bin/env python3
"""Process input data file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-path",
        type=Path,
        required=True,
        help="Path to input file"
    )
    return parser.parse_args()


def main() -> int:
    """Main entry point. Returns exit code."""
    args = parse_args()

    try:
        data = json.loads(args.input_path.read_text())
        print(f"Processed: {len(data)} items")
        return 0
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

---

## References

- [ADR-042: Python Migration Strategy](../architecture/ADR-042-python-migration-strategy.md)
- [Python CI/CD Patterns](./python-cicd-patterns.md)
- [Python Security Checklist](../security/python-security-checklist.md)
- [pyproject.toml](../../pyproject.toml) (coding standards)
