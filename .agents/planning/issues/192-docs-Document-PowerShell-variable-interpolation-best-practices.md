---
number: 192
title: "docs: Document PowerShell variable interpolation best practices"
state: OPEN
created_at: 12/20/2025 12:39:29
author: rjmurillo-bot
labels: ["documentation", "priority:P2"]
assignees: []
milestone: null
url: https://github.com/rjmurillo/ai-agents/issues/192
---

# docs: Document PowerShell variable interpolation best practices

## Context

From Session 36 retrospective:

**Root Cause**: Variable interpolation bug (`$PullRequest:` instead of `$($PullRequest):`) caused syntax error in Get-PRContext.ps1.

**Knowledge Gap**: PowerShell variable interpolation best practices not documented, leading to repeated mistakes.

## Objective

Document PowerShell variable interpolation best practices to prevent syntax errors and improve code quality.

## Acceptance Criteria

- [ ] Documentation created explaining variable interpolation rules
- [ ] Examples of correct and incorrect patterns provided
- [ ] Special cases documented (colons, scopes, special characters)
- [ ] Best practices for string building documented
- [ ] Integration with .gemini/styleguide.md or separate doc
- [ ] Referenced in code review checklists

## Content to Document

### Variable Interpolation Rules

**Basic Interpolation**:
```powershell
# Correct
"Hello $Name"
"Path: $Path\file.txt"

# Incorrect (adjacent special chars)
"Error: $Variable:"  # Colon interpreted as scope operator
```

**Subexpression Syntax** (REQUIRED for special cases):
```powershell
# When variable is followed by colon
"Error: $($Variable):"

# When variable is followed by method/property call
"Length: $($Text.Length)"

# When using array indexing
"First: $($Array[0])"
```

### Common Pitfalls

1. **Scope Qualifiers**: `$PullRequest:` attempts to access `:` variable in `$PullRequest` scope
2. **Property Access**: `$Obj.Property` works, but `$Obj.Property:` needs `$($Obj.Property):`
3. **Array Elements**: `$Array[0]` works in assignments, needs `$($Array[0])` in strings

### Alternatives to Interpolation

```powershell
# String format operator (preferred for complex scenarios)
"Error on line {0}: {1}" -f $LineNumber, $Message

# StringBuilder for performance (large strings)
$Sb = [System.Text.StringBuilder]::new()
$Sb.Append("Text")

# Join for arrays
$Array -join ", "
```

## Integration Options

**Option A**: Add section to `.gemini/styleguide.md` under PowerShell Standards
**Option B**: Create standalone `docs/powershell-best-practices.md`
**Option C**: Add to existing governance documentation

Recommended: **Option A** (keeps style guide comprehensive)

## References

- Session 36 retrospective
- Skill-PowerShell-001: Variable interpolation safety (95% atomicity)
- Microsoft Docs: [about_Quoting_Rules](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_quoting_rules)

## Priority

P2 (MEDIUM) - Knowledge documentation to prevent future errors

## Effort Estimate

30 minutes


