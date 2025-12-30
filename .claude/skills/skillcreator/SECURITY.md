# Security Review - SkillCreator Scripts

## Overview

The Python scripts in `scripts/` accept user-provided file paths as arguments. This document explains the security mitigations in place.

## Path Traversal Mitigation (CWE-22)

All scripts implement `sanitize_path()` function that provides defense-in-depth path validation:

### Pre-validation Checks (String Level)

1. **Empty path rejection** - Prevents null input
2. **Null byte detection** - Blocks `\x00` injection attacks
3. **Newline rejection** - Blocks `\r` and `\n` injection
4. **Tilde expansion** - `~` expanded before path operations

### Path Resolution

1. **os.path.realpath()** - Resolves all symlinks and normalizes path
2. **Post-resolution traversal check** - Verifies no `..` components remain
3. **Directory containment** (optional) - Can restrict to current directory

### Defense-in-Depth

Even if an attacker bypasses string validation, the resolved path:

- Is always absolute (no relative path confusion)
- Has symlinks resolved (no symlink attacks)
- Is checked for `..` after resolution

## CodeQL Analysis Notes

CodeQL Advanced Security flags these scripts because it cannot recognize custom sanitization functions. The `sanitize_path()` function IS a valid sanitizer, but CodeQL's dataflow analysis doesn't have a model for it.

### Why Alerts Are False Positives

1. All user input goes through `sanitize_path()` before any path operation
2. Path is converted to absolute using `os.path.realpath()`
3. Post-resolution validation ensures no traversal
4. Path is only passed to `Path()` AFTER full validation

### Suppression Documentation

`# lgtm[py/path-injection]` comments mark validated code paths. These are:

- **package_skill.py**: Lines 98-145 (all use sanitized skill_path or output_path)
- **quick_validate.py**: Lines 95-102, 196 (all use sanitized path)
- **validate-skill.py**: Line 93 (uses sanitized self.skill_path)

## Recommendations for Users

1. **Install PyYAML** - The fallback YAML parser has limitations
   ```bash
   pip install pyyaml
   ```

2. **Review paths before execution** - These scripts operate on user-specified directories

3. **Run in sandboxed environment** - For untrusted skill validation, use containers

## Third-Party Skill Exception

This skill is classified as third-party under ADR-005 (PowerShell-only policy). Python is permitted for third-party skills that are:

1. Self-contained (no system dependencies beyond Python stdlib)
2. Security-reviewed (this document)
3. Documented with explicit security considerations

## Security Contact

For security issues, please file an issue on the repository.
