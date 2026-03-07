# ADR Artifact Count Verification

## Pattern

Run `git diff --stat` and compare artifact counts to ADR text before committing ADR amendments to prevent documentation drift.

## Problem

ADR amendments may reference file counts, commit SHAs, or other quantified artifacts that can become inaccurate if not verified against actual implementation results.

## Solution

**Before committing an ADR amendment**:

1. Run `git diff --stat` to get actual file change counts
2. Compare numbers in ADR text to git output
3. Verify commit SHAs are correct
4. Check file paths exist
5. Validate any quantified claims

## Evidence

**Session 826** (2026-01-13): ADR-040 amendment stated "18 generated files" but implementation actually updated 54 files across 3 platforms (`.github/agents/`, `src/vs-code-agents/`, `src/copilot-cli/`). PR review comment caught the discrepancy.

## Impact

- **Atomicity**: 92%
- **Domain**: adr-documentation
- **Failure Mode**: Documentation becomes misleading, developers trust incorrect counts
- **Detection**: PR review or later audit

## Implementation

Add to ADR checklist:
```markdown
- [ ] Run `git diff --stat` and verify file counts match ADR text
- [ ] Verify all commit SHAs are correct
- [ ] Check all referenced file paths exist
```

## Related

- [[protocol-template-enforcement]] - Template validation pattern
- [[adr-037-sync-evidence-gaps]] - Evidence-based verification
- [[retrospective-004-evidence-based-validation]] - Validation standards

## Source

- Session: 826 (2026-01-13)
- Retrospective: `.agents/retrospective/2026-01-13-fix-tools-frontmatter-retrospective.md`
- Learning: L1 (Phase 4, Lines 498-506)
