# Skill: Path Containment Three-Layer Validation

## Statement

Validate path containment with three layers: case-insensitive comparison, trailing separator, path normalization.

## Trigger

When reviewing or implementing path validation code (especially CWE-22 prevention).

## Action

1. **Case-insensitive**: Use OrdinalIgnoreCase for Windows compatibility
2. **Trailing separator**: Enforce trailing separator to prevent prefix bypass
3. **Path normalization**: Convert to canonical form before comparison

## Benefit

Prevents path traversal attacks that bypass single-layer validation.

## Code Pattern

```powershell
# Three-layer path containment check
$normalizedPath = [System.IO.Path]::GetFullPath($inputPath)
$normalizedBase = [System.IO.Path]::GetFullPath($basePath)

# Ensure trailing separator for prefix comparison
if (-not $normalizedBase.EndsWith([System.IO.Path]::DirectorySeparatorChar)) {
    $normalizedBase += [System.IO.Path]::DirectorySeparatorChar
}

# Case-insensitive comparison
$isContained = $normalizedPath.StartsWith($normalizedBase, [StringComparison]::OrdinalIgnoreCase)
```

## Evidence

- PR #488: Required TWO fixes to fully harden CWE-22 protection
- gemini-code-assist: Caught case-sensitivity bypass on Windows
- Copilot: Caught `.agents/sessions-evil` prefix bypass

## Atomicity

**Score**: 92%

**Justification**: Single concept (path containment). Three layers are inseparable for complete protection.

## Category

pr-comment-responder

## Created

2025-12-29

## Related

- [pr-156-review-findings](pr-156-review-findings.md)
- [pr-320c2b3-refactoring-analysis](pr-320c2b3-refactoring-analysis.md)
- [pr-52-retrospective-learnings](pr-52-retrospective-learnings.md)
- [pr-52-symlink-retrospective](pr-52-symlink-retrospective.md)
- [pr-753-remediation-learnings](pr-753-remediation-learnings.md)
