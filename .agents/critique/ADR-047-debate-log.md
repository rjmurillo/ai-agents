# ADR-047 Debate Log: Plugin-Mode Hook Behavior

## Metadata

| Field | Value |
|-------|-------|
| ADR | ADR-047-plugin-mode-hook-behavior.md |
| Date | 2026-02-16 |
| Rounds | 1 |
| Consensus | CONCERNS (5/5 agents) |
| Outcome | ACCEPT with REQUIRED amendments |

## Summary

All 5 review agents returned a CONCERNS verdict. The decision itself is architecturally sound, but documentation gaps in security guidance and evidence accuracy require amendments before acceptance.

## Agent Verdicts

| Agent | Verdict | Key Finding | Blocking Issues |
|-------|---------|-------------|-----------------|
| architect | CONCERNS | MADR 4.0 template gaps (no YAML front matter, Decision Drivers) | None (documentation only) |
| critic | CONCERNS | P1 gaps in error handling, validation coverage, consumer docs | 0 P0, 4 P1 |
| independent-thinker | CONCERNS | Challenged 4 assumptions (bootstrap paradox, user count, etc.) | None (valid alternatives) |
| security | CONCERNS | HIGH findings: CWE-426 (untrusted search path), CWE-22 (path traversal) | 3 P0 amendments |
| analyst | ACCEPT with corrections | Evidence 92.5% accurate (37 files vs "40+"), 7-line boilerplate not 5 | None (minor corrections) |

## Consolidated Issues

### P0 (Blocking for Acceptance)

From security agent (SR-002):

1. **Add "Security Considerations" to Consequences section**
   - Document trust model for CLAUDE_PLUGIN_ROOT and CLAUDE_PROJECT_DIR
   - Mandate path normalization with `Path.resolve()`
   - Require containment validation before file operations
   - Reference canonical implementations

2. **Update Implementation Notes Checklist**
   - Add: "Validate all paths are within project boundary before file operations"
   - Add: "Test with malicious environment variables to verify rejection"

3. **Reference existing security patterns**
   - Add references to `.gemini/styleguide.md` (Path Traversal guidance)
   - Add references to `invoke_skill_learning.py` (`_validate_path_string` pattern)

### P1 (Should Address Before Merge)

From critic agent:

1. **Missing error handling patterns** (lines 58-59)
   - `os.makedirs()` permission errors not addressed
   - Recommendation: Wrap in try/except, exit with ADR-035 code 2

2. **Missing lib directory validation** (lines 40-46)
   - Resolved: Implementer agent added validation in commit bcd6951c
   - Pattern: `if not os.path.isdir(_lib_dir): sys.exit(2)`

3. **No test coverage verification** (lines 103-113)
   - Test `test_plugin_path_resolution_pattern()` proposed but not verified
   - Implement test BEFORE marking ADR as Accepted

4. **Consumer documentation gap** (line 78)
   - No reference to where `.agents/` documentation lives
   - Create task: Update plugin README.md with directory guidance

### P2 (Nice to Have)

From analyst agent:

1. **Evidence accuracy corrections**
   - "40+ files" claim: 37 actual (92.5% accurate)
   - "5-line boilerplate" claim: 7 lines actual
   - "Hundreds of engineers" claim: Target (ADR-045), not current adoption

2. **Boilerplate extraction** (from critic)
   - Consider `lib/plugin_bootstrap.py` to centralize pattern
   - Currently dismissed due to bootstrap paradox (acceptable)

## Security Findings Summary

From security report SR-002:

| Finding | Severity | CWE | Status |
|---------|----------|-----|--------|
| Missing trust boundary for CLAUDE_PLUGIN_ROOT | HIGH | CWE-426 | Requires ADR amendment |
| Missing path traversal guidance for CLAUDE_PROJECT_DIR | HIGH | CWE-22 | Requires ADR amendment |
| Directory creation outside project scope | MEDIUM | CWE-73 | Requires ADR amendment |
| Test coverage verifies presence, not security | MEDIUM | CWE-754 | Requires enhanced tests |
| Environment variable injection not documented | LOW | CWE-16 | P2 documentation |

## Resolution

### Required ADR Amendments

Before marking ADR-047 as Accepted:

1. [ ] Add "Security Considerations" subsection to Consequences
2. [ ] Update Implementation Notes checklist with security requirements
3. [ ] Reference canonical secure implementations
4. [ ] Implement test coverage for security properties
5. [ ] Correct minor evidence inaccuracies (7 lines, 37 files)

### Implementation Completed (PR #1186)

From implementer agent (commit bcd6951c):

1. [x] Path normalization in `get_project_directory()` using `Path.resolve()`
2. [x] Lib directory validation added to hooks with `os.path.isdir()` check
3. [x] Error context added to ADR lifecycle hook
4. [x] `warnings.warn()` added to `_get_repo_maintainers()`
5. [x] Permission error handling for `os.makedirs()`
6. [x] Exception type logging added to fail-open handlers

## Agent Reports

| Agent | Artifact |
|-------|----------|
| critic | `.agents/critique/ADR-047-plugin-mode-hook-behavior-critique.md` |
| security | `.agents/security/SR-002-ADR-047-plugin-mode-security-review.md` |
| analyst | `.agents/analysis/001-adr-047-plugin-mode-hook-behavior-analysis.md` |

## Consensus Decision

**Verdict**: ACCEPT ADR-047 with REQUIRED amendments (P0 items listed above)

**Rationale**: The technical decision is sound:
- Run all hooks in plugin mode
- Use CLAUDE_PLUGIN_ROOT for path resolution only
- Never gate behavior on environment variable presence

The security and documentation gaps are addressable and do not undermine the core decision. Once amendments are incorporated, the ADR will be ready for Accepted status.

**Next Steps**:
1. Apply security amendments to ADR-047
2. Verify test coverage includes security test cases
3. Update ADR status from "Proposed" to "Accepted"

---

*Debate Log Created: 2026-02-16*
*Protocol: adr-review skill (6-agent debate)*
*Max Rounds: 10 (completed in 1)*
