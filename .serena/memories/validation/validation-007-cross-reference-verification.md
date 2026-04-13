# Validation Pattern: Cross-Reference Verification

**Source**: Issue #474 ADR numbering validation (Session 2025-12-28-01)
**Pattern**: When validating renumbering/refactoring, verify ALL cross-references, not just some

## The Gap

Implementer claimed commit d5f9afe "updated memory file cross-references" (plural) but only updated 1 of 2 files:

- ✅ Updated: `architecture-adr-compliance-documentation.md`
- ❌ Missed: `adr-reference-index.md`

Result: Memory index contains references to non-existent ADRs (ADR-014a/b, ADR-015a/b).

## Root Cause

**Incomplete search coverage**: Search found one file, implementer stopped searching after first update.

## Validation Protocol

When validating cross-references after renaming/renumbering:

### Step 1: List ALL Potential Reference Locations

```bash
# Not just code files - include ALL file types
grep -r "OLD-PATTERN" . --include="*.md" --include="*.yml" --include="*.yaml" --include="*.json"
```

### Step 2: Categorize by File Type

| Location | Risk Level | Verification Method |
|----------|-----------|---------------------|
| Memory files | HIGH | Manual review (hard to test) |
| Workflow files | MEDIUM | CI tests catch some issues |
| Documentation | MEDIUM | Manual review |
| Code files | LOW | Compiler/linter catches |

### Step 3: Verify Each Category Independently

Don't stop after first file. For memory files specifically:

```bash
# Check ALL memory files
find .serena/memories -name "*.md" -exec grep -l "PATTERN" {} \;

# Verify count matches commit message
# If commit says "files" (plural), expect 2+ results
```

### Step 4: Test Cross-References

After updates, verify targets exist:

```bash
# Extract all ADR references from index
grep "ADR-[0-9]" adr-reference-index.md | sed 's/.*ADR-\([0-9]*\).*/\1/' | sort -u

# Verify each ADR file exists
for num in $(grep "ADR-[0-9]" index.md | sed 's/.*ADR-\([0-9]*\).*/\1/'); do
  ls .agents/architecture/ADR-$num*.md || echo "MISSING: ADR-$num"
done
```

## Critic Verification Checklist

When reviewing renumbering/refactoring:

- [ ] Search output shows ALL occurrences found
- [ ] Commit message matches file count (singular vs plural)
- [ ] Each file type verified independently
- [ ] Cross-reference targets exist (no broken links)
- [ ] Index/catalog files updated (often missed)

## Anti-Pattern: Trust Commit Message

**Don't**: Assume "updated cross-references" means ALL files updated
**Do**: Independently verify by searching for old patterns

## Related Patterns

- [edit-002-unique-context-for-edit-matching](edit-002-unique-context-for-edit-matching.md): Finding unique strings for replacement
- [validation-skepticism](validation-skepticism.md): Don't trust, verify
- [documentation-verification-protocol](documentation-verification-protocol.md): Systematic doc validation

## Success Metrics

- Zero broken cross-references after refactoring
- Index files match actual file state
- Search finds NO occurrences of old patterns

## Related

- [validation-006-self-report-verification](validation-006-self-report-verification.md)
- [validation-007-frontmatter-validation-compliance](validation-007-frontmatter-validation-compliance.md)
- [validation-474-adr-numbering-qa-final](validation-474-adr-numbering-qa-final.md)
- [validation-anti-patterns](validation-anti-patterns.md)
- [validation-baseline-triage](validation-baseline-triage.md)
