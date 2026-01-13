# Skill-Protocol-013: Verification-Based Enforcement

**Atomicity**: 88%
**Category**: Protocol design, compliance
**Source**: PR #669 PR co-mingling retrospective

## Pattern

Protocol requirements MUST generate observable artifacts that can be verified, not rely on agent memory.

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

## Problem

**Trust-Based Compliance** fails because:

- Agents have no persistent memory across tool calls
- Context limits cause instruction truncation
- No way to verify compliance after the fact

**Success rate**: ~0% for non-trivial protocols

**Evidence**: PR #669 - Trust-based "verify branch" requirement led to 4 PRs contaminated

## Design Criteria

For each protocol requirement, ask:

1. **Observable?** Does it generate an artifact (file, output, commit)?
2. **Verifiable?** Can compliance be checked after the fact?
3. **Blocking?** Does the next step depend on this artifact?

If "no" to any question, redesign with verification.

## Anti-Patterns to Avoid

| Bad (trust-based) | Good (verification-based) |
|-------------------|---------------------------|
| "Agent should..." | "Run [command] and verify output" |
| "Remember to..." | "Generate [artifact] before proceeding" |
| "Make sure..." | "Tool output MUST appear in transcript" |
| No artifact | File, output, commit, API response |
| Unverifiable | Programmatically checkable |

```markdown
# WRONG: Trust-based compliance
## Git Commit Protocol
- Remember to check your branch before committing
- Always verify you're on the right branch
- Don't commit to wrong branches

# Problem: No enforcement mechanism
```

## Session Protocol Pattern

```markdown
## Phase N: [Action Name] (BLOCKING)

Before [next step], perform [action]:

```bash
[command that generates observable output]
```

**Exit criteria**: [Artifact] exists and contains [expected content].
```

## Related Skills

- [protocol-014-trust-antipattern](protocol-014-trust-antipattern.md): Why trust-based fails
- [git-004-branch-verification-before-commit](git-004-branch-verification-before-commit.md): Application example
- [protocol-blocking-gates](protocol-blocking-gates.md): Gate design pattern
- [session-init-003-branch-declaration](session-init-003-branch-declaration.md): Session log tracking

## References

- PR #669: PR co-mingling retrospective
- Issue #684: SESSION-PROTOCOL branch verification (verification-based)
- Issue #686: Trust antipattern documentation

## Related

- [protocol-012-branch-handoffs](protocol-012-branch-handoffs.md)
- [protocol-014-trust-antipattern](protocol-014-trust-antipattern.md)
- [protocol-blocking-gates](protocol-blocking-gates.md)
- [protocol-continuation-session-gap](protocol-continuation-session-gap.md)
- [protocol-legacy-sessions](protocol-legacy-sessions.md)
