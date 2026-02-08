# Passive Context Reference (Auto-loaded)

> **Purpose**: Skill awareness, memory hierarchy, and PR routing patterns.
> Based on Vercel research: passive context (100% pass rate) outperforms skill invocation (53-79%).
>
> **Principle**: Prefer retrieval-led reasoning over pre-training-led reasoning for session protocol,
> memory operations, and repository conventions.

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
|  github: "create a PR", "commit and push", "close issue", "add label", "check CI"
|  adr-review: "review this ADR", "validate ADR", "check architecture decision"
|  merge-resolver: "resolve merge conflicts", "fix conflicts", "can't merge"
|  planner: "plan this feature", "create implementation plan", "pick up next item", "execute plan"
|  decision-critic: "critique this decision", "devil's advocate on"
|  security-detection: "scan for security changes", "run security scan", "check infrastructure changes"
|  analyze: "analyze this codebase", "review code quality", "run security assessment", "find code smells"
|  session-log-fixer: "fix session validation", "session protocol failed", "fix failing session check"
|  reflect: "reflect on this session", "learn from this", "capture what we learned"
|  pr-comment-responder: "respond to PR comments", "address review feedback", "fix PR review issues"

|HYBRID (knowledge in passive context, actions in skill):
|  pr-comment-responder: routing above, actions in skill
|  session-log-fixer: patterns below, Fix-SessionLog.ps1 in skill
|  reflect: auto-trigger on corrections/praise, capture in skill
```

---

## Common User Phrasings → Skill Mapping

```text
[User Phrasing → Skill]
|"create a PR" → github
|"run PR review" → pr-quality:all
|"commit and push" → github
|"resolve conflicts" → merge-resolver
|"fix CI" → session-log-fixer (if session) or fix-ci agent
|"review the plan" → planner (executor mode)
|"pick up next item" → planner (executor mode)
|"run security scan" → security-detection
|"analyze code quality" → analyze
|"learn from this" → reflect
|"fix session validation" → session-log-fixer
|"sync docs" → doc-sync
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

```powershell
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
