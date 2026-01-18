# Skill: Explicit Verb-Object Requirement Phrasing

**Skill ID**: Skill-Requirements-Language-001

**Statement**: Requirements use explicit verb-object pairs to prevent ambiguity (e.g., 'Display X in Y' not 'Add X to Y')

**Context**: When writing requirements for implementation

**Evidence**: OODA-001 'add indicator TO classification' ambiguous led to wrong interpretation (static table instead of dynamic output)

**Atomicity Score**: 88%

**Tag**: helpful

**Impact**: 8/10

**Category**: requirements, language, clarity

**Created**: 2025-12-19

**Source**: `.agents/retrospective/2025-12-19-personality-integration-gaps.md`

## Pattern

### Good (Explicit)

- "Display current OODA phase in routing output"
- "Add checklist with 4 items to Code Quality Gates section"
- "Insert table showing prohibited phrases in Section 3"

### Bad (Ambiguous)

- "Add OODA phase indicator to classification"
- "Add code quality gates verification"
- "Include style guide content"

## Rule

Use: **verb** + **direct object** + **location/context**

## When to Apply

- Writing any requirement that will be implemented by another agent
- Planning documents with action items
- Analysis recommendations

## Benefit

- Reduces interpretation ambiguity
- Prevents approximately 50% of interpretation errors
- Clarifies exact location and format expected
