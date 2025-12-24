# Skill-Documentation-002: Reference Type Taxonomy

**Statement**: Categorize references as instructive (update), informational (skip), or operational (skip) before migration.

**Evidence**: Session 26: Type distinction prevented inappropriate updates.

**Atomicity**: 95% | **Impact**: 9/10

| Type | Definition | Action | Example |
|------|------------|--------|---------|
| **Instructive** | Instructions telling agents what to do | UPDATE | "MUST read .serena/memories/..." |
| **Informational** | Descriptive text about locations | SKIP | "Memories found in `.serena/memories/`" |
| **Operational** | Commands requiring file paths | SKIP | "git add .serena/memories/" |
