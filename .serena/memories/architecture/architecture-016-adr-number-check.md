# Skill-Architecture-016: ADR Number Check

**Statement:** Before creating new ADR, run `ls .agents/architecture/ADR-*.md | sort -t- -k2 -n | tail -5` to check last 5 numbers, choose next available

**Context:** When architect agent prepares to create ADR file

**Evidence:** Session 92 / PR #466: ADR-021 collision (Session 86 in main, Session 91 in PR branch)

**Why:** Sequential numbering fails during parallel branch development. Branches can independently choose same "next" number.

**Impact:** 8/10 - Prevents rework from renumbering and reference updates

**Atomicity:** 92%

## Correct Pattern

```bash
# Before creating ADR-NNN-title.md
ls .agents/architecture/ADR-*.md | sort -t- -k2 -n | tail -5

# Output shows:
# ADR-019-model-routing-strategy.md
# ADR-020-architecture-governance.md
# ADR-021-quality-gate-improvements.md  ← Last in main
# ADR-022-cache-invalidation.md
# ADR-023-prompt-testing.md              ← Last in PR branch

# Choose ADR-024 for safety (or check main branch if in feature branch)
```

## Anti-Pattern

```text
❌ Assume next number is ADR-021 because you have ADR-020 locally
   (main branch may already have ADR-021)

❌ Create ADR without checking existing numbers
   (causes collision during rebase)
```

## Historical Collisions

- ADR-007 (required renumbering to ADR-011)
- ADR-014 (required renumbering to ADR-020)
- ADR-021 (required renumbering to ADR-023)

## Validation

After creating ADR, verify uniqueness:

```bash
git ls-files --others --exclude-standard | grep "ADR-$NUMBER" # Check local
git fetch origin main && git diff main --name-only | grep "ADR-$NUMBER" # Check main
```

## Integration Point

Add to architect agent handoff protocol:

```markdown
### Before Creating ADR

1. Check existing ADR numbers: `ls .agents/architecture/ADR-*.md | sort -t- -k2 -n | tail -5`
2. If in feature branch, check main branch: `git fetch origin main && git ls-tree -r --name-only origin/main .agents/architecture/ | grep ADR`
3. Choose next available number (highest + 1)
4. Verify uniqueness before committing
```

## Related

- [architecture-003-dry-exception-deployment](architecture-003-dry-exception-deployment.md)
- [architecture-015-deployment-path-validation](architecture-015-deployment-path-validation.md)
- [architecture-adr-compliance-documentation](architecture-adr-compliance-documentation.md)
- [architecture-composite-action](architecture-composite-action.md)
- [architecture-model-selection](architecture-model-selection.md)
