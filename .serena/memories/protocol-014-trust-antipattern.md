# Skill-Protocol-014: Trust-Based Compliance Antipattern

**Statement**: Trust-based compliance is an antipattern - always use verification-based enforcement

**Context**: When reviewing protocol designs or investigating compliance failures

**Evidence**: 3 documented failures - Session Protocol v1.0-v1.3 (skill violations), HANDOFF.md (update bloat), git operations (wrong-branch commits) - PR #669

**Atomicity**: 94% | **Impact**: 10/10

## Pattern

**Failure Pattern Recognition**:

Trust-based compliance shows these symptoms:
1. **Documentation Heavy**: "Remember to...", "Always...", "Don't forget..."
2. **No Programmatic Check**: No verification command before operation
3. **Post-Facto Discovery**: Violations found during review, not prevented
4. **Repetitive Failures**: Same mistake happens multiple times

**Fix: Convert to Verification-Based**:
1. Add programmatic verification step
2. Block operation if verification fails
3. Make compliance automatic, not voluntary

## Anti-Pattern

**Trust-Based Examples**:

```markdown
# Example 1: Session Protocol v1.0-v1.3
"Remember to check for existing skills before using gh commands"
Problem: No verification gate, 5+ violations in Session 15

# Example 2: HANDOFF.md
"Update HANDOFF.md with session context"
Problem: No size limit, grew to 35KB with 80% merge conflicts

# Example 3: Git operations (pre-PR #669)
"Verify you're on the right branch before committing"
Problem: No automated check, wrong-branch commits occurred
```

## Related Skills

- `protocol-013-verification-based-enforcement`: Implementation pattern
- `protocol-blocking-gates`: Gate design
- `git-004-branch-verification-before-commit`: Application example
