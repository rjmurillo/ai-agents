# YAML Array Format Compatibility Pattern

## Summary

Block-style YAML arrays are universally compatible across YAML parsers. Inline arrays with single quotes can fail on Windows systems.

## Problem

Windows YAML parsers (specifically in GitHub Copilot CLI) fail to parse inline array syntax:

```yaml
# FAILS on Windows
tools: ['codebase', 'editFiles', 'search']
```

Error: "Unexpected scalar at node end"

## Solution

Use block-style arrays:

```yaml
# WORKS everywhere
tools:
  - codebase
  - editFiles
  - search
```

## Root Cause

Inline arrays with single quotes trigger parsing errors in some Windows YAML implementations. The exact parser version and configuration matters, but block-style is universally safe.

## Evidence

- Issue #893: Windows user reported parsing error
- ADR-040 amendment: Standardized on block-style arrays
- 72 files updated (18 templates + 54 generated)

## Related

- [[learnings-2026-01]] - Session 826 learnings
- Issue #896 - CRLF line endings investigation (deferred)
