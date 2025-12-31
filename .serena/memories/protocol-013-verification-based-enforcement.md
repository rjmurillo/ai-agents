# Skill-Protocol-013: Verification-Based Enforcement

**Statement**: Use verification-based enforcement for git ops instead of trust-based compliance

**Context**: When designing new protocol gates or improving existing compliance mechanisms

**Evidence**: PR #669 analysis identified trust-based compliance as 3rd documented failure type (Session Protocol v1.0-v1.3, HANDOFF.md, git operations)

**Atomicity**: 88% | **Impact**: 9/10

## Pattern

**Verification-Based Enforcement**:
1. Execute verification command FIRST
2. Check output programmatically
3. Block operation if verification fails
4. Proceed only after confirmation

```bash
# Example: Branch verification before commit
CURRENT_BRANCH=$(git branch --show-current)
if [[ "$CURRENT_BRANCH" != "feat/issue-123" ]]; then
  echo "ERROR: Wrong branch. Expected feat/issue-123, got $CURRENT_BRANCH"
  exit 1
fi
git commit -m "..."
```

**Trust-Based Compliance** (AVOID):
1. Document requirement
2. Hope agent follows it
3. No programmatic check
4. Failures discovered post-facto

## Anti-Pattern

```markdown
# WRONG: Trust-based compliance
## Git Commit Protocol
- Remember to check your branch before committing
- Always verify you're on the right branch
- Don't commit to wrong branches

# Problem: No enforcement mechanism
```

## Related Skills

- `protocol-014-trust-antipattern`: Why trust-based fails
- `git-004-branch-verification-before-commit`: Application example
- `protocol-blocking-gates`: Gate design pattern
