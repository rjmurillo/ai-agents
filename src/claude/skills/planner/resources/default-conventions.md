# Default Conventions

These conventions apply when project documentation does not specify otherwise.

## Priority Hierarchy

Higher tiers override lower. Cite backing source when auditing.

| Tier | Source          | Action                           |
| ---- | --------------- | -------------------------------- |
| 1    | user-specified  | Explicit user instruction: apply |
| 2    | doc-derived     | CLAUDE.md / project docs: apply  |
| 3    | default-derived | This document: apply             |
| 4    | assumption      | No backing: CONFIRM WITH USER    |

## Severity Levels

| Level      | Meaning                          | Action          |
| ---------- | -------------------------------- | --------------- |
| SHOULD_FIX | Likely to cause maintenance debt | Flag for fixing |
| SUGGESTION | Improvement opportunity          | Note if time    |

---

## Structural Conventions

<default-conventions domain="god-object">
**God Object**: >15 public methods OR >10 dependencies OR mixed concerns (networking + UI + data)
Severity: SHOULD_FIX
</default-conventions>

<default-conventions domain="god-function">
**God Function**: >50 lines OR multiple abstraction levels OR >3 nesting levels
Severity: SHOULD_FIX
Exception: Inherently sequential algorithms or state machines
</default-conventions>

<default-conventions domain="duplicate-logic">
**Duplicate Logic**: Copy-pasted blocks, repeated error handling, parallel near-identical functions
Severity: SHOULD_FIX
</default-conventions>

<default-conventions domain="dead-code">
**Dead Code**: No callers, impossible branches, unread variables, unused imports
Severity: SUGGESTION
</default-conventions>

<default-conventions domain="inconsistent-error-handling">
**Inconsistent Error Handling**: Mixed exceptions/error codes, inconsistent types, swallowed errors
Severity: SUGGESTION
Exception: Project specifies different handling per error category
</default-conventions>

---

## File Organization Conventions

<default-conventions domain="test-organization">
**Test Organization**: Extend existing test files; create new only when:
- Distinct module boundary OR >500 lines OR different fixtures required
Severity: SHOULD_FIX (for unnecessary fragmentation)
</default-conventions>

<default-conventions domain="file-creation">
**File Creation**: Prefer extending existing files; create new only when:
- Clear module boundary OR >300-500 lines OR distinct responsibility
Severity: SUGGESTION
</default-conventions>

---

## Testing Conventions

<default-conventions domain="testing">
**Principle**: Maximize coverage through input variation, not test count.

**DO**:

- Property-based tests: verify invariants (`write(x) -> read() == x`) across many inputs
- Parameterized fixtures: compose layers that multiply test scenarios
- Integration tests: public API against real dependencies
- Minimal test bodies: complexity in fixtures, not test logic
- Cover: integration boundaries, invariants, behavior edges, error handling at system edges

**DON'T**:

- Test external library behavior (test YOUR code)
- One-test-per-variant when parametrization applies
- Mock owned dependencies (use real implementations)
- Test internals when public API covers them
- Verify trivial behavior with no regression risk

Severity: SHOULD_FIX (violations), SUGGESTION (missed opportunities)
</default-conventions>

---

## Modernization Conventions

<default-conventions domain="version-constraints">
**Version Constraint Violation**: Features unavailable in project's documented target version
Requires: Documented target version
Severity: SHOULD_FIX
</default-conventions>

<default-conventions domain="modernization">
**Modernization Opportunity**: Legacy APIs, verbose patterns, manual stdlib reimplementations
Severity: SUGGESTION
Exception: Project requires legacy pattern
</default-conventions>
