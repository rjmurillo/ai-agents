---
name: chestertons-fence
version: 1.1.0
model: claude-sonnet-4-6
description: Investigate historical context of existing code, patterns, or constraints before proposing changes. Automates git archaeology, PR/ADR search, and dependency analysis to prevent removing structures without understanding their purpose.
license: MIT
user-invocable: true
---

# Chesterton's Fence Investigation

Enforce epistemic humility before changing existing systems. Understand original purpose before proposing changes.

## Quick Start

```text
# Investigate why code exists before changing it
/chestertons-fence "path/to/file.py" "remove unused validation"

# Investigate an ADR before deprecating it
/chestertons-fence ".agents/architecture/ADR-005.md" "allow bash scripts"
```

## Triggers

| Phrase | Context |
|--------|---------|
| `why does this exist` | Investigating existing code or patterns |
| `chestertons fence` | Explicit investigation request |
| `before removing` | Planning deletion or replacement |
| `investigate history` | Researching original rationale |
| `prior art investigation` | ADR-required investigation |

## Quick Reference

| Input | Output | Destination |
|-------|--------|-------------|
| File path or ADR number | Investigation report | `.agents/analysis/NNN-chestertons-fence-TOPIC.md` |
| Component description | Historical context summary | stdout (JSON) |

## When to Use

Use this skill BEFORE proposing changes to existing:

- Code patterns or architectural decisions
- ADRs, constraints, or protocol rules
- Workflow configurations or CI pipelines
- Skills, hooks, or agent prompts

## Process

```text
1. Identify Structure       What exists? Where is it defined?
       |
       v
2. Git Archaeology          git log, git blame to find origin commit
       |
       v
3. PR/ADR Search            Find the PR or ADR with original rationale
       |
       v
4. Dependency Analysis      What references or depends on this?
       |
       v
5. Generate Report          Fill the investigation template
       |
       v
6. Decision                 REMOVE | MODIFY | PRESERVE | REPLACE
```

### Step Details

**Step 1: Identify Structure.** Locate the exact file, function, pattern, or constraint under investigation. Record its current form.

**Step 2: Git Archaeology.** Run `git log --follow` and `git blame` on the target. Identify the commit that introduced it, the author, and the date.

**Step 3: PR/ADR Search.** Search for the originating PR using `gh pr list --search`. Check `.agents/architecture/` for related ADRs. Look for comments explaining intent.

**Step 4: Dependency Analysis.** Use `grep` or `Grep` tool to find all references. Map upstream and downstream dependencies. Identify what breaks if the structure is removed.

**Step 5: Generate Report.** Use the template at `.agents/templates/chestertons-fence-investigation.md`. Fill all sections with evidence from steps 1 through 4.

**Step 6: Decision.** Based on evidence, recommend one action:

| Decision | When to Use |
|----------|-------------|
| PRESERVE | Original rationale still applies |
| MODIFY | Purpose valid but implementation needs updating |
| REPLACE | Better approach exists, original concern addressed |
| REMOVE | Original rationale no longer applies, with evidence |

## Usage

```bash
# Investigate a file or pattern
python3 scripts/investigate.py --target path/to/file.py --change "remove unused validation"

# Investigate an ADR
python3 scripts/investigate.py --target .agents/architecture/ADR-005.md --change "allow bash scripts"

# Output as JSON (for automation)
python3 scripts/investigate.py --target path/to/file.py --change "description" --format json
```

## Integration with Agent Workflows

| Agent | How to Integrate |
|-------|------------------|
| **Analyst** | Run this skill first when investigating changes. The report is a prerequisite for any change proposal. |
| **Architect** | ADRs that deprecate or replace existing patterns MUST include a "Prior Art Investigation" section. Use this skill to generate it. |
| **Implementer** | Before implementing deletions or major refactoring, verify an investigation report exists. If missing, route to analyst. |
| **Critic** | When validating plans that remove or replace existing systems, check for investigation evidence. Auto-reject proposals without historical context. |

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Removing code you do not understand | May break hidden invariants | Investigate first, then decide |
| Assuming dead code is unused | Hyrum's Law: someone depends on it | Run dependency analysis |
| Skipping PR/ADR search | Loses original design rationale | Always check git history and PRs |
| Proposing replacement without evidence | Cannot compare tradeoffs | Document original constraints first |

## Template

Investigation reports use the template at `.agents/templates/chestertons-fence-investigation.md`.

## References

| File | Content |
|------|---------|
| `references/chestertons-fence-mental-model.md` | Core mental model, principle, investigation checklist, related models |
| `references/boy-scout-rule.md` | Scoped improvement boundaries, connection to investigation workflow |
| `references/legacy-code-techniques.md` | Bottom-up refactoring approach, inheritance vs composition, reading list |
