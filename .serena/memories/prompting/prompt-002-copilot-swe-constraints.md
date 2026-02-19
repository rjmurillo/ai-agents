# Skill: Copilot SWE Prompting Constraints

**ID**: skill-prompt-002-copilot-swe-constraints
**Category**: Prompting
**Atomicity Score**: 92%
**Evidence**: PR #395 failure analysis (2025-12-25)

## Context

Copilot SWE (especially Sonnet 4.5) tends toward scope expansion unless explicitly constrained. This skill provides templates for effective prompting.

## Problem Prompt (Avoid)

```
Ran but didn't do anything. DeepThink. Debug.
```

Issues:
- Ambiguous scope
- No success criteria
- "DeepThink" triggers over-analysis
- No constraints

## Solution Templates

### Investigation Only

```
The [component] (run [ID]) [symptom]. 

Investigate WHY [specific question].

CONSTRAINTS:
- Read-only investigation first
- Report findings before any changes
- Do not modify code yet
```

### Minimal Fix

```
[Describe issue with evidence]

Fix by [specific approach].

CONSTRAINTS:
- Maximum [N] lines changed
- Do not modify tests
- Do not remove existing code
- Show plan before implementing
```

### Debug with Scope

```
Debug [run/issue reference].

CONSTRAINTS:
1. Read-only investigation first
2. Any fix must be under 50 lines
3. Do not modify tests
4. Do not remove existing code
5. Stop and report before expanding scope
```

## Model-Specific Notes

### Sonnet 4.5

- Requires explicit scope limits
- Will expand without constraints
- May ignore pushback ("YAGNI")
- Add: "Do not remove existing code"
- Add: "Maximum N lines"

### Opus 4.5

- Better scope discipline by default
- Responds to feedback quickly
- Still benefits from explicit constraints

## Checkpoint Phrases

Include to prevent scope creep:
- "Show plan before implementing"
- "Stop after minimal fix to verify"
- "Do not expand scope without asking"
- "Maximum N lines changed"

## Evidence

PR #395: "DeepThink. Debug." led to 847 lines, broken script.
With constraints, fix would have been ~50 lines.
