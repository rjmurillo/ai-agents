# Skill-Refactoring-001: Delete > Refactor Principle

**Statement**: When refactoring, first ask "Can I delete this and use something standard?" before asking "How do I make this reusable?"

**Context**: Code refactoring decisions, particularly when facing complex custom implementations

**Evidence**: Session 67 (2025-12-22): Generate-Skills.ps1 refactoring (script deleted in commit d7f2e08, replaced by validate-skill.py)
- Original plan: Extract 112-line custom YAML parser into reusable module
- Better approach: Delete it, use `powershell-yaml` from PSGallery
- Result: 96% code reduction (112 lines → 4 lines), zero maintenance burden

**Atomicity**: 94%

**Tag**: helpful (refactoring strategy)

**Impact**: 10/10 (eliminates maintenance, uses battle-tested code)

**Created**: 2025-12-22

**Validated**: 1 (Session 67)

**Pattern**:

When facing custom code that could be "made reusable":

1. Search PSGallery / package manager for existing solutions
2. Evaluate: Is the standard module good enough?
3. If yes → **delete** custom code, use standard module
4. If no → document why standard isn't sufficient before building custom

**Benefits**:
- Zero maintenance burden
- Community-tested edge cases
- Standard tools developers recognize
- Often massive code reduction

**Anti-Pattern**: "Not Invented Here" syndrome - building custom solutions when standards exist

**Example** (Session 67):

```powershell
# BEFORE: 112 lines of custom YAML parser
function Parse-YamlScalar { ... 27 lines ... }
function Parse-YamlFrontmatter { ... 85 lines ... }

# AFTER: 4 lines using standard module
#Requires -Modules @{ ModuleName='powershell-yaml'; ModuleVersion='0.4.0' }
Import-Module powershell-yaml

function Parse-YamlFrontmatter {
    param([string] $YamlText)
    return ConvertFrom-Yaml $YamlText -Ordered
}
```

**Decision Tree**:

```
Custom code exists
  ├─ Can it be deleted?
  │   ├─ Yes, standard module exists → DELETE ✅
  │   └─ No, unique requirement → Keep or refactor
  └─ Should it be "made reusable"?
      ├─ Check: Can standard module do this?
      │   ├─ Yes → DELETE, use standard ✅
      │   └─ No → Proceed with refactoring
      └─ Document: Why standard isn't sufficient
```

**Related**: 
- Less is more (code minimalism)
- Standing on shoulders of giants
- YAGNI (You Aren't Gonna Need It)
