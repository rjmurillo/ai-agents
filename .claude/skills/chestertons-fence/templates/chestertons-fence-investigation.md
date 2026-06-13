# Chesterton's Fence Investigation: [Component/System Name]

## What Exists

- **Structure**: [Describe the fence: what code, pattern, or constraint exists]
- **Location**: [File paths, ADR numbers, or protocol sections]
- **Scope**: [What it affects: entire codebase, specific module, etc.]

## Historical Context (REQUIRED)

- **When created**: [PR/commit/ADR reference, date]
- **Who created it**: [Author, GitHub handle]
- **Original purpose**: [Why was it built? What problem did it solve?]
- **Historical evidence**: [Links to PRs, ADRs, commit messages]

## Current Function Analysis (REQUIRED)

- **Intended function**: [What it was designed to do]
- **Emergent functions**: [What else does it do now? Unintended benefits?]
- **Dependencies**: [What code or systems rely on this?]
- **Failure modes prevented**: [What breaks if we remove it?]

## Proposed Change Context

- **What you want to do**: [Remove, modify, replace]
- **Why you want to change it**: [What problem does current state create?]
- **Risks if wrong**: [What is the blast radius if we misunderstand?]

## Investigation Findings

- **Original problem still exists?**: [Yes/No, evidence]
- **Better solution available now?**: [Yes/No, what is it?]
- **Hidden costs of change**: [Second-order effects, migration costs]
- **Reversibility**: [Can we undo this if wrong? At what cost?]

## Decision (Only after completing above sections)

- [ ] **REMOVE**: Original problem obsolete, no hidden dependencies found
- [ ] **MODIFY**: Core function valid but implementation suboptimal
- [ ] **PRESERVE**: Still serves important purpose, change would break things
- [ ] **REPLACE**: Better solution exists with migration plan

## Rationale

[Explain decision based on investigation findings]

## Action Items

- [ ] [Specific next steps based on decision]
