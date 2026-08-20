---
name: adr-review
version: 1.1.0
description: Multi-agent debate orchestration for Architecture Decision Records. Automatically triggers on ADR create/edit/delete. Coordinates architect, critic, independent-thinker, security, analyst, and high-level-advisor agents in structured debate rounds until consensus. Use when you say "review this ADR", when an ADR is created/edited/deleted, or when reviewing, accepting, or updating a decision file under .agents/architecture/, docs/architecture/, docs/decisions/, docs/adr/, or architecture/decisions/, including intent like "review this decision record" or "check this rationale for future maintainers". Do NOT use to author a new ADR (use adr-generator).
license: MIT
metadata:
  domains: [architecture, governance, multi-agent, consensus]
  type: orchestrator
  inputs: [adr-file-path, change-type]
  outputs: [debate-log, updated-adr, recommendations]
  file_triggers:
    patterns:
      - ".agents/architecture/ADR-*.md"
      - "docs/adr/ADR-*.md"
      - "docs/architecture/ADR-*.md"
      - "docs/decisions/ADR-*.md"
      - "architecture/decisions/ADR-*.md"
    events: [create, update, delete]
    auto_invoke: true
---

# ADR Review

Multi-agent debate pattern for rigorous ADR validation. Orchestrates 6 specialized agents through structured review rounds until consensus or 10 rounds maximum.

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `review this ADR` | Full 6-agent debate on specified ADR |
| `validate ADR-005` | Targeted review of specific ADR by number |
| `review this decision record` | ADR review for durable architecture/design decision records |
| `delete ADR-NNN` | Deletion review with dependency and supersession checks |
| `ADR file created, modified, or deleted` | Auto-triggered via detect_adr_changes.py |

---

## Quick Start

```text
# Manual triggers:
/adr-review .agents/architecture/ADR-005-api-versioning.md
"review this ADR"
"validate ADR-005"
"review this decision record under docs/decisions"
```

**Automatic Detection**: A Claude Code hook runs at session start and detects ADR changes, prompting you to invoke this skill. The pre-commit hook also detects staged ADR files and displays a reminder.

| Input | Output | Consensus Required |
|-------|--------|-------------------|
| ADR file path | Debate log + Updated ADR | 6/6 Accept or D&C |

## File Triggers

| Pattern | Location | Events |
|---------|----------|--------|
| `ADR-*.md` | `.agents/architecture/` | create, update, delete |
| `ADR-*.md` | `docs/adr/` | create, update, delete |
| `ADR-*.md` | `docs/architecture/` | create, update, delete |
| `ADR-*.md` | `docs/decisions/` | create, update, delete |
| `ADR-*.md` | `architecture/decisions/` | create, update, delete |

**Detection**: from the skill directory, run `python3 scripts/detect_adr_changes.py --base-path <repo-root>`. From repo root, run `.claude/skills/adr-review/scripts/detect_adr_changes.py` for the Claude skill tree or `src/copilot-cli/skills/adr-review/scripts/detect_adr_changes.py` for the Copilot CLI mirror.

## When to Use

**MANDATORY Triggers** (automatic):

- Architect creates or updates an ADR
- ANY agent modifies `.agents/architecture/ADR-*.md`, `docs/adr/ADR-*.md`, `docs/architecture/ADR-*.md`, `docs/decisions/ADR-*.md`, or `architecture/decisions/ADR-*.md`

**User-Initiated Triggers** (manual):

- User requests ADR review ("review this ADR", "validate this decision")
- User asks to review a durable design decision record or rationale for future maintainers
- User requests multi-perspective validation for strategic decisions

## Agent Roles

| Agent | Focus | Tie-Breaker Role |
|-------|-------|------------------|
| **architect** | Structure, governance, coherence, ADR compliance | Structural questions |
| **critic** | Gaps, risks, alignment, completeness | None |
| **independent-thinker** | Challenge assumptions, surface contrarian views | None |
| **security** | Threat models, security trade-offs | None |
| **analyst** | Root cause, evidence, feasibility | None |
| **high-level-advisor** | Priority, resolve conflicts, break ties | Decision paralysis |

## Process

| Phase | Purpose | Details |
|-------|---------|---------|
| **Phase 0** | Related work research | Search issues/PRs for context |
| **Phase 1** | Independent review | Each agent reviews ADR using [Zimmermann 7-question checklist](references/zimmermann-review-guidance.md) |
| **Phase 2** | Consolidation | Identify consensus and conflicts; flag [review anti-patterns](references/zimmermann-review-guidance.md) |
| **Phase 3** | Resolution | Propose updates for P0/P1 issues |
| **Phase 4** | Convergence check | Agents vote: Accept/D&C/Block |

**Consensus**: All 6 agents Accept OR Disagree-and-Commit. Max 10 rounds.

See [references/debate-protocol.md](references/debate-protocol.md) for full phase details.

## Deletion Workflow

| Phase | Purpose |
|-------|---------|
| **D1** | Detection - identify deleted ADR |
| **D2** | Impact assessment - find dependencies |
| **D3** | Archival decision - archive accepted ADRs |
| **D4** | Cleanup - update references |

See [references/deletion-workflow.md](references/deletion-workflow.md) for full workflow.

## Issue Resolution

| Priority | Requirement | Gate |
|----------|-------------|------|
| **P0** | Must resolve | BLOCKING |
| **P1** | Resolve OR defer with issue | BLOCKING |
| **P2** | Document | Non-blocking |

See [references/issue-resolution.md](references/issue-resolution.md) for deferral protocol.

## Phase 4: Strategic Review (Principal-Level Validation)

After structural and technical review, apply strategic lenses:

### Strategic Validation Checklist

#### Chesterton's Fence (Change Justification)

- [ ] If removing/changing existing patterns: Original purpose documented
- [ ] Investigation evidence provided (git archaeology, interviews, documentation)
- [ ] Confirmation original problem no longer exists
- [ ] Assessment: [PASS | FAIL | N/A]

#### Path Dependence (Irreversibility Recognition)

- [ ] Historical constraints identified and documented
- [ ] Reversibility assessment complete (rollback capability, vendor lock-in)
- [ ] Migration/exit strategy defined if adding dependencies
- [ ] Irreversible decisions explicitly flagged and justified
- [ ] Assessment: [PASS | FAIL | N/A]

#### Core vs Context (Investment Prioritization)

- [ ] Capability classified as Core (differentiating) or Context (commodity)
- [ ] If building Context: Justification for not buying/outsourcing
- [ ] If Core: Competitive differentiation explained
- [ ] Assessment: [PASS | FAIL | N/A]

#### Second-System Effect (Over-Engineering Detection)

- [ ] If replacing existing system: Scope boundaries explicit
- [ ] Feature list justified (not "everything we didn't do last time")
- [ ] Simplicity preservation strategy documented
- [ ] Assessment: [PASS | FAIL | N/A]

### Strategic Review Verdict

**Overall Strategic Assessment**: [APPROVED | CONCERNS | REJECTED]

**Blocking Issues**:

- [Strategic issue 1 with required mitigation]
- [Strategic issue 2 with required mitigation]

**Recommendations**:

- [Strategic improvement 1]
- [Strategic improvement 2]

## Scripts

| Script | Purpose |
|--------|---------|
| `.claude/skills/adr-review/scripts/detect_adr_changes.py` | Detect ADR file changes for the Claude skill tree |
| `src/copilot-cli/skills/adr-review/scripts/detect_adr_changes.py` | Detect ADR file changes for the Copilot CLI mirror |

```bash
# Basic detection from repo root
uv run python .claude/skills/adr-review/scripts/detect_adr_changes.py

# Skill-relative detection from the Claude skill directory
cd .claude/skills/adr-review
python3 scripts/detect_adr_changes.py --base-path ../../..
cd ../../..

# Compare to specific commit
uv run python .claude/skills/adr-review/scripts/detect_adr_changes.py --since-commit abc123

# Include untracked ADR files
uv run python .claude/skills/adr-review/scripts/detect_adr_changes.py --include-untracked

# Copilot CLI mirror from repo root
uv run python src/copilot-cli/skills/adr-review/scripts/detect_adr_changes.py --include-untracked

# Skill-relative detection from the Copilot CLI mirror
cd src/copilot-cli/skills/adr-review
python3 scripts/detect_adr_changes.py --base-path ../../../..
cd ../../../..
```

## Verification Checklist

Before marking complete, run the bundled detector to check for pending ADR changes:

```bash
uv run python .claude/skills/adr-review/scripts/detect_adr_changes.py --include-untracked
echo "exit=$?"   # must be 0; non-zero means git error or I/O failure
```

- [ ] The detector script exited 0 (no git or I/O errors)
- [ ] If skill was auto-triggered by a file change, `HasChanges` should be `true`; if skill was manually invoked on an existing committed ADR, `HasChanges: false` is expected and acceptable

After skill invocation:

- [ ] Debate log exists at `.agents/critique/ADR-NNN-debate-log.md`
- [ ] ADR status updated using the frontmatter enum below; use prose for review nuance
- [ ] Frontmatter `status` field present and a valid enum value: one of
      `proposed | accepted | rejected | deprecated | superseded` (ADR-073).
      A missing or out-of-enum `status` is a P1 blocker; the frontmatter enum is
      authoritative for tooling, the prose `## Status` carries the human nuance.
- [ ] If this review transitions `status` to `accepted`: the same change carries
      adr-review debate-log evidence at `.agents/critique/ADR-NNN-debate-log.md`
      (ADR-073 Phase-3 acceptance gate). A hand-edit to `accepted` with no
      debate-log artifact is a forgeable approval signal and MUST be rejected.
<!-- vendor-portability: declared. adr-review checks accepted-transition evidence under .agents/critique/; a consumer repo without it reports missing evidence, not a silent pass. Issue #2050. -->
- [ ] All P0 issues addressed or documented
- [ ] Dissent captured for Disagree-and-Commit positions
- [ ] Recommendations provided to orchestrator

## Anti-Patterns

### Process Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Single-agent ADR review | Misses domain expertise | Use full 6-agent debate |
| Skipping Phase 0 | Duplicates existing work | Always research first |
| Ignoring D&C dissent | Loses important context | Document all reservations |
| Manual ADR monitoring | Error-prone | Use detect_adr_changes.py |
| Deleting accepted ADRs without archive | Loses knowledge | Always archive accepted ADRs |

### Review Anti-Patterns (Zimmermann)

Each agent should self-check against these. Phase 2 consolidation flags violations.

| Anti-Pattern | Problem | Detection |
|-------------|---------|-----------|
| **Pass Through** | Few/no comments, document barely read | Agent produces no substantive findings |
| **Copy Edit** | Focuses on wording, ignores content | All findings editorial, none architectural |
| **Siding/Dead End** | Comments switch topic, deviate from ADR | Agent drifts from decision at hand |
| **Self Promotion** | Recommends reviewer's preferred solution | Agent pushes technology without objective rationale |
| **Power Game** | Authority claims instead of technical arguments | Agent uses position over evidence |
| **Offended Reaction** | Defends criticized position subjectively | Agent reacts emotionally to rationale |
| **Groundhog Day** | Same message repeated across rounds | Agent re-raises resolved issues |

See [zimmermann-review-guidance.md](references/zimmermann-review-guidance.md) for full practices and pledges.

## References

| Document | Content |
|----------|---------|
| [debate-protocol.md](references/debate-protocol.md) | Full Phases 0-4 workflow |
| [deletion-workflow.md](references/deletion-workflow.md) | Phases D1-D4 workflow |
| [issue-resolution.md](references/issue-resolution.md) | P0/P1/P2 handling and deferral |
| [artifacts.md](references/artifacts.md) | Output formats and templates |
| [agent-prompts.md](references/agent-prompts.md) | Detailed agent prompt templates |
| [zimmermann-review-guidance.md](references/zimmermann-review-guidance.md) | Review practices, 7 anti-patterns, checklist, reviewer pledge (Zimmermann 2023) |
