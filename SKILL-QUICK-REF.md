# Passive Context Reference (Auto-loaded)

> **Purpose**: Passive context for session protocol, memory hierarchy, and skill awareness.
> Based on Vercel research: passive context (100% pass rate) outperforms skill invocation (53-79%).
>
> **Principle**: Prefer retrieval-led reasoning over pre-training-led reasoning for session protocol,
> memory operations, and repository conventions.

---

## Session Protocol (Blocking Gates)

```text
[Session Protocol]
|BLOCKING-START: serena-init, handoff-read, log-create, branch-verify
|BLOCKING-END: log-complete, serena-update, lint-check, validate-pass
|QA-GATE: feature-impl requires qa-validation; skip-allowed: docs-only, investigation-only
|SCRIPTS: Validate-SessionJson.ps1, New-SessionLog.ps1
|EXIT-CODE: 0=PASS required; "errors" OR "failures" in test output = non-zero = BLOCK
```

**Session Start Checklist:**

1. `mcp__serena__activate_project` → `mcp__serena__initial_instructions`
2. Read HANDOFF.md (read-only)
3. Create log: `pwsh .claude/skills/session-init/scripts/New-SessionLog.ps1`
4. Read usage-mandatory memory
5. Verify branch: `git branch --show-current`

**Session End Checklist:**

1. Complete session log with outcomes
2. Update Serena memory
3. Run scoped markdownlint on changed files
4. Route to qa agent (features only)
5. Commit all changes
6. Validate: `pwsh scripts/Validate-SessionJson.ps1 -SessionPath "[log]"`

---

## Memory Hierarchy

```text
[Memory Hierarchy]
|PRIORITY: serena > forgetful > vscode-memory
|SERENA: .serena/memories/, L1=memory-index, L2=skills-*-index, L3={domain}-{topic}.md
|FORGETFUL: ~/.local/share/forgetful/forgetful.db, semantic-search
|PRINCIPLE: retrieve-before-reasoning
```

**Memory-First Rule**: Always check existing memories before reasoning from pre-training.

---

## PR Comment Routing

```text
[PR Comment Routing]
|CLASSIFY: sentiment(positive|negative|neutral), type(question|suggestion|concern|approval)
|QUICK-FIX: one-sentence-fix, single-file, obvious-change → implementer → qa
|STANDARD: investigation-needed, 2-5-files, some-complexity → analyst → planner → implementer → qa
|STRATEGIC: whether-not-how, scope-question, architecture-direction → independent-thinker → high-level-advisor → task-generator
```

---

## Skills Index

```text
[Skills Index]
|root: .claude/skills/
|IMPORTANT: Read SKILL.md before acting on any skill-based task.

|VERTICAL (explicit triggers - keep as skills):
|  github: "create PR", "triage issue", "respond to review", "add label"
|  adr-review: "review this ADR", "check architecture decision"
|  merge-resolver: "resolve merge conflict", "fix conflicts in X"
|  planner: "plan this feature", "create implementation plan"
|  decision-critic: "critique this decision", "devil's advocate on"
|  security-detection: "scan for security changes", "check security-critical"
|  analyze: "check code quality", "run analyzers", "find code smells"

|HYBRID (knowledge in passive context, actions in skill):
|  pr-comment-responder: routing above, actions in skill
|  session-log-fixer: patterns below, Fix-SessionLog.ps1 in skill
```

---

## Session Log Validation Patterns

Common validation failures and fixes:

| Pattern | Fix |
|---------|-----|
| Missing `outcomes` | Add array with session results |
| Empty `decisions` | Add key decisions made |
| Invalid `exitCode` | Must be 0 for PASS |
| Missing `branchVerified` | Add branch verification step |

---

## Vertical Skills Quick Reference

### GitHub Operations

```bash
# Get unaddressed PR comments
pwsh .claude/skills/github/scripts/pr/Get-UnaddressedComments.ps1 -PullRequest "<num>"

# Post PR comment reply  
pwsh .claude/skills/github/scripts/pr/Post-PRCommentReply.ps1 -PullRequest "<num>" -Body "..."

# Get PR check logs for CI failures
pwsh .claude/skills/github/scripts/pr/Get-PRCheckLogs.ps1 -PullRequest "<num>"
```

**NEVER**: Use raw `gh pr comment`, `gh issue edit` when these scripts exist.

### ADR Review

**Trigger**: Any file matching `.agents/architecture/ADR-*.md` created or edited.

**Process**: Routes through architect, security, critic agents.

### Merge Resolution

**Trigger**: "resolve merge conflict", "fix conflicts on {branch}"

**Read**: `.claude/skills/merge-resolver/SKILL.md`

---

## Why Passive Context

| Configuration | Pass Rate |
|---------------|-----------|
| Baseline (no docs) | 53% |
| Skill (default) | 53% |
| Skill + explicit instructions | 79% |
| **AGENTS.md passive context** | **100%** |

**Key insight**: No decision point required. Information is present every turn.

---

**For full skill documentation**: Read `.claude/skills/"<name>"/SKILL.md`
