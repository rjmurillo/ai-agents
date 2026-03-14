# ADR-048: Local Security Scanning

## Status

Accepted

## Date

2026-02-19

## Context

PR #908 demonstrated that security findings discovered in CI (CodeQL CWE-22 path traversal) create significant overhead:

1. **Late feedback**: Findings appear after PR creation, not during development
2. **Review noise**: Security comments pollute PR threads
3. **Wasted cycles**: Reviewers spend time on issues that could be caught locally
4. **Slower iteration**: Developers must context-switch back to fix security issues

The existing pre-push hook (`.githooks/pre-push`) runs 18 checks across 5 phases, including lint, type checks, tests, and governance validation. However, it lacks security scanning for actual vulnerabilities.

ADR-041 established CodeQL integration with a multi-tier strategy. Tier 1 (CI/CD) provides enforcement. Tier 2 (local) and Tier 3 (automatic PostToolUse) are optional developer conveniences. Neither tier runs in the pre-push hook.

**Key Question**: Should all PRs with code changes run local security scans before push?

## Decision

Extend the pre-push hook to run lightweight security scanning on changed code files.

**Tool choice**: semgrep (preferred) or bandit as fallback.

**Rationale for tool selection**:
- **semgrep**: Fast (1-5 seconds), cross-language, excellent Python/PowerShell support, simple CLI
- **bandit**: Python-only but zero dependencies, well-established
- **CodeQL CLI**: Too slow for pre-push (30-60 seconds minimum), requires database build

**Scope**: Changed files only (consistent with existing pre-push patterns).

**Threshold**: Fail on HIGH/CRITICAL findings. Warn on MEDIUM.

**Bypass**: Standard `--no-verify` with documented justification requirement.

### Implementation

Add to Phase 5 (Security & Governance) of `.githooks/pre-push`:

```bash
# 15.5. Security scan (semgrep)
if [ -n "$CHANGED_PY" ] || [ -n "$CHANGED_PS" ]; then
    if command -v semgrep &> /dev/null; then
        # Build file list
        SCAN_FILES=()
        while IFS= read -r file; do
            [ -z "$file" ] && continue
            [ -L "$file" ] && continue
            [ -f "$file" ] && SCAN_FILES+=("$file")
        done <<< "$CHANGED_PY"$'\n'"$CHANGED_PS"

        if [ ${#SCAN_FILES[@]} -gt 0 ]; then
            SCAN_OUTPUT=$(mktemp)
            TEMP_FILES+=("$SCAN_OUTPUT")
            if semgrep scan --config auto --severity ERROR --severity WARNING \
                    --quiet --no-git-ignore \
                    "${SCAN_FILES[@]}" > "$SCAN_OUTPUT" 2>&1; then
                record_pass "Security scan/semgrep (${#SCAN_FILES[@]} files)"
            else
                echo_info "  Security findings:"
                head -30 "$SCAN_OUTPUT"
                record_fail "Security scan found vulnerabilities"
                echo_info "  Fix: Address security findings or document exception."
            fi
            rm -f "$SCAN_OUTPUT"
        else
            record_skip "Security scan (no accessible files)"
        fi
    else
        record_skip "Security scan (semgrep not installed)"
    fi
else
    record_skip "Security scan (no code files changed)"
fi
```

### Installation

Add semgrep to developer setup in `docs/installation.md`:

```bash
# macOS
brew install semgrep

# Linux/Windows (via pip)
pip install semgrep

# Verify installation
semgrep --version
```

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Status quo (CI-only) | No local setup | PR #908 proves late feedback is costly | Delays feedback loop |
| CodeQL CLI in pre-push | Comprehensive coverage | 30-60s minimum, requires database | Too slow for pre-push |
| bandit only | Zero dependencies | Python-only, misses PowerShell | Incomplete coverage |
| semgrep + bandit | Defense in depth | Redundant for Python, slower | Diminishing returns |
| IDE-only (extensions) | No hook friction | Not enforced, inconsistent | Optional = often skipped |

### Trade-offs

**Speed vs. Coverage**: semgrep scans 10-100x faster than CodeQL at the cost of fewer rules. CI retains comprehensive CodeQL scanning for defense in depth.

**Optional Tool vs. Required**: semgrep installation is recommended but not required. The hook skips gracefully if unavailable, matching existing patterns (ruff, mypy, actionlint).

**Changed Files vs. Full Repo**: Scanning only changed files trades completeness for speed. New vulnerabilities in unchanged code remain CI's responsibility.

## Consequences

### Positive

1. **Shift-left security**: Catch CWE-22, CWE-78, CWE-079 in 1-5 seconds
2. **Cleaner PRs**: Security findings fixed before PR creation
3. **Faster iteration**: Local feedback loop
4. **Developer education**: Immediate exposure to secure coding patterns
5. **Reduced review noise**: Fewer security comments in PR threads

### Negative

1. **Tool installation**: Requires semgrep (pip or brew)
   - **Mitigation**: Clear installation docs, graceful skip if missing
2. **False positives**: May flag safe patterns
   - **Mitigation**: `# nosemgrep` suppression with justification
3. **Push friction**: Adds 1-5 seconds to push workflow
   - **Mitigation**: Only scans changed files, async display

### Neutral

1. **CI redundancy**: CodeQL continues running in CI
   - **Rationale**: Defense in depth, different rule sets
2. **Bypass available**: `--no-verify` remains an escape hatch
   - **Mitigation**: Document justification requirement in CONTRIBUTING.md

## Implementation Notes

### Performance Budget

| Check | Target | Actual |
|-------|--------|--------|
| semgrep scan (10 files) | <5s | ~2s |
| Pre-push total | <60s | ~45s |

### Exit Code Handling

Per ADR-035:
- Exit 0: No findings
- Exit 1: Findings found (blocking)
- Exit 2: Tool error (non-blocking skip)

### Integration with ADR-041

This ADR complements ADR-041's multi-tier strategy:

| Tier | Tool | Trigger | Speed | Coverage |
|------|------|---------|-------|----------|
| 1 (CI) | CodeQL | PR push | 2-5 min | Comprehensive |
| 2 (Local) | CodeQL CLI | Developer-initiated | 30-60s | Comprehensive |
| 3 (Auto) | CodeQL | PostToolUse hook | 5-15s | Quick queries |
| **4 (Pre-push)** | **semgrep** | **git push** | **1-5s** | **Fast OWASP** |

### Suppression Patterns

Document in CONTRIBUTING.md:

```python
# nosemgrep: path-traversal-check
# Justification: Input validated by sanitize_path() on line 42
os.path.join(base, user_input)
```

## Related Decisions

- [ADR-004: Pre-Commit Hook Architecture](./ADR-004-pre-commit-hook-architecture.md)
- [ADR-041: CodeQL Integration](./ADR-041-codeql-integration.md)
- [ADR-035: Exit Code Standardization](./ADR-035-exit-code-standardization.md)

## References

- [semgrep documentation](https://semgrep.dev/docs/)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
- `.agents/retrospective/2026-01-15-pr-908-comprehensive-retrospective.md`
- Issue #949

---

**Supersedes**: None (extends ADR-041)
**Amended by**: None
