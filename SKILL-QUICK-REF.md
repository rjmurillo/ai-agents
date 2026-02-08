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

[Bot Comment Classification]
|DETECT: regex for CWE-(\d+), E(\d+) error codes, "missing documentation" patterns
|ROUTE: CWE-22|CWE-78 → security-scan, E501|E741 → style-enforcement, "XML doc"|"docstring" → doc-coverage
|VERIFY: skill exit code 0 before replying to bot
|PRINCIPLE: skills-encode-best-practices (don't rely on pre-training for security patterns)
```

---

## Pre-Execution Checkpoint

```text
[Skill-First Checkpoint]
|BEFORE any git/gh/script operation:
|  1. PAUSE: "Is there a skill for this?"
|  2. CHECK: Scan "User Phrasing → Skill" table below
|  3. USE skill if match found, raw command only if no skill exists
|WHY: Session 1183 proved agents bypass skills even with full awareness.
|     The problem is habit, not knowledge. This checkpoint builds the habit.
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
|  session-end: "/session-end", "complete session", "finalize session", "validate session end"
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
|"complete session" → session-end
|"finalize session" → session-end
|"validate session end" → session-end
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

## Skill vs Passive Context Decision Framework

```text
[Decision Framework]
|QUESTION: "Does this require tool execution or just knowledge?"

|USE PASSIVE CONTEXT (@import in CLAUDE.md) for:
|  - Framework knowledge (APIs, patterns, conventions)
|  - Always-needed information (constraints, protocols, gates)
|  - Domain concepts (terminology, relationships)
|  - Routing rules (comment classification, agent selection)
|  - Reference data (memory indexes, skill catalogs)

|USE SKILLS (.claude/skills/) for:
|  - Tool-based actions (file modification, API calls, git operations)
|  - User-triggered workflows (PR creation, issue management)
|  - Multi-step procedures (conflict resolution, session completion)
|  - Actions requiring validation (security scans, linting)
|  - Versioned, team-reviewed instructions across projects

|HYBRID PATTERN (both):
|  - Knowledge in passive context (routing, classification)
|  - Actions in skill (script execution, state changes)
|  - Example: pr-comment-responder has routing in SKILL-QUICK-REF.md, scripts in skill

|WHY THIS MATTERS:
|  - Skills create decision points ("should I invoke this?")
|  - Decision points introduce 4 failure modes (see below)
|  - Passive context eliminates all 4 by being always-available
```

### Skill Failure Modes (Why Passive Context Wins)

| Failure Mode | Description | Prevention |
|-------------|-------------|------------|
| Late retrieval | Agent makes decisions before consulting skill | Passive context |
| Partial retrieval | Skill scope doesn't cover all needed info | Broader skill or passive |
| Integration failure | Skill retrieved but not integrated with project context | Explore-first instructions |
| Instruction fragility | Minor prompt changes break skill invocation | Passive context |

### Examples

| Content Type | Placement | Why |
|-------------|-----------|-----|
| Session protocol phases | Passive (CRITICAL-CONTEXT.md) | Always needed, no action |
| PR comment routing rules | Passive (SKILL-QUICK-REF.md) | Classification knowledge |
| GitHub issue creation | Skill (github) | Tool execution required |
| Security scan patterns | Passive + Skill | Knowledge + action |
| Memory hierarchy | Passive | Reference data |
| Merge conflict resolution | Skill | Multi-step procedure |

---

## Why Passive Context

| Configuration | Pass Rate |
|---------------|-----------|
| Baseline (no docs) | 53% |
| Skill (default) | 53% |
| Skill + explicit instructions | 79% |
| **AGENTS.md passive context** | **100%** |

**Key insight**: No decision point required. Information is present every turn.

**Source**: [Vercel Research (Jan 2026)](https://vercel.com/blog/agents-md-outperforms-skills-in-our-agent-evals)

---

**For full skill documentation**: Read `.claude/skills/"<name>"/SKILL.md`
