# architect agent

The `architect` agent is the technical authority for system design. It writes ADRs (architecture decision records), reviews designs, and checks that new work fits existing patterns and boundaries. It hands back a decision document or a design review with a clear status.

## When to use it

- You need an ADR for a decision that has high impact, needs investment, has many dependencies, or sits outside the team's comfort zone.
- You need a design review before planning, during plan analysis, or after implementation.
- You want a technical choice challenged against existing ADRs and design principles.
- You need a trade-off analysis or a blueprint that protects long-term system health.
- A planner needs the architecture impact of a feature.

## When not to use it

- You want code written: use [`implementer`](implementer.md) instead. The architect writes no code.
- You want a plan created: use [`milestone-planner`](milestone-planner.md) instead.
- You want an ADR debated by several agents: use the [`adr-review`](../skills/adr-review.md) skill instead. The architect's ADR output routes there.
- You want to author a new ADR with the generator workflow: use the [`adr-generator`](../skills/adr-generator.md) skill instead.

## Quick start

In Claude Code, start your prompt with the agent name:

```text
architect: write an ADR for moving hook dispatch from per-event scripts to a single dispatcher, and cite any existing ADR that governs hooks
```

In GitHub Copilot CLI:

```bash
copilot --agent architect --prompt "write an ADR for moving hook dispatch from per-event scripts to a single dispatcher, and cite any existing ADR that governs hooks"
```

In VS Code or Visual Studio Copilot Chat:

```text
@architect write an ADR for moving hook dispatch from per-event scripts to a single dispatcher, and cite any existing ADR that governs hooks
```

## What you get

The agent edits only files under `.project-toolkit/architecture/`:

| File | Content |
| --- | --- |
| `ADR-NNNN-[decision].md` | An ADR in the MADR 4.0 template |
| `DESIGN-REVIEW-[topic].md` | A design review with YAML frontmatter |

Design review frontmatter carries `status`, `priority`, `blocking`, `reviewer`, `date`, `pr`, and `issue`.

| Status | Meaning | `blocking` |
| --- | --- | --- |
| `APPROVED` | Design meets all criteria | false |
| `NEEDS_CHANGES` | Minor issues, proceed with fixes | false |
| `NEEDS_ADR` | An ADR is required first | true |
| `BLOCKED` | Major issues, cannot proceed | true |
| `REJECTED` | The design is flawed at its base | true |

CI enforces this: `scripts/validation/pre_pr.py` checks the required frontmatter fields, and the `synthesis-panel-gate.yml` workflow blocks PRs whose verdict is `NEEDS_CHANGES`, `FAIL`, or `REJECTED`.

## Advanced use

Before it recommends anything, the agent answers three questions and writes the answers into the ADR or review: which ADRs already govern the area (it searches `.project-toolkit/architecture/`), which quality attributes the design serves and which it gives up, and the top failure mode in two years. It searches the ADR catalog before it drafts a new one, and it cites ADR numbers.

An ADR is ready when it passes the START check (Stakeholders, Time, Alternatives, Requirements, Template) and done when it passes ecADR (Evidence, Criteria, Agreement, Documentation, Realization and review). When a new ADR supersedes an old one, the agent sets the old ADR to `superseded by ADR-NNNN` in the same change.

Length caps: the Context section is at most 3 sentences, at most 5 considered options, at most 4 bullets per option, a design review summary of 3 sentences, at most 7 issues per priority tier, and at most 5 recommendations.

ADR exception requests get a blocking evaluation. The agent rejects a request, with no partial approval, if the original rationale is paraphrased instead of quoted, "impact if removed" is generic, fewer than two compliance attempts are documented, the scope is unbounded, conditions are not enforceable, the exception does not say what it must not set a precedent for, there is no reversibility, or it is a standalone document instead of an amendment to the original ADR.

Every ADR it creates or updates ends with a mandatory routing note: the orchestrator must run the `adr-review` skill before any other agent. The agent must not recommend any other route until that review completes.

Before it finishes, the agent runs a self-critique pass: list weaknesses, fix each or record it as an accepted risk, and list unresolved risks in a table.

Optional references live in the `adr-review` skill's `references/` folder: `architect-impact-analysis.md`, `architect-code-organization-review.md`, `architect-vendor-lock-in.md`, and `architect-strategic-principles.md`.

In impact analysis mode, when `milestone-planner` asks, it saves `.project-toolkit/planning/impact-analysis-architecture-[feature].md`. For migrations it picks a pattern: Strangler Fig, Expand/Contract, or Sacrificial Architecture.

The agent cannot delegate. It recommends these handoffs:

| Target | When | Purpose |
| --- | --- | --- |
| `milestone-planner` | Architecture approved | Proceed with planning |
| `analyst` | More research needed | Investigate options |
| `high-level-advisor` | Major decision conflict | Strategic guidance |
| `implementer` | Design finalized | Begin implementation |
| `roadmap` | Alignment validation needed | Verify strategic fit |
| `critic` | Decision challenge requested | Independent review |

A multi-step prompt:

```text
architect: review the proposed queue design in .project-toolkit/planning/PRD-merge-queue.md against existing ADRs, name the quality attribute it gives up, write the design review with a status, and say which agent runs next.
```

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| VS Code and Visual Studio | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`adr-review`](../skills/adr-review.md): the multi-agent review every ADR goes through.
- [`adr-generator`](../skills/adr-generator.md): authors ADRs from a template.
- [`critic`](critic.md): gives an independent review of a decision.
- [`milestone-planner`](milestone-planner.md): plans after the design is approved.
- [`implementer`](implementer.md): builds the finished design.
- Source template: [`architect.shared.md`](../../templates/agents/architect.shared.md)
- How to call agents on each host: [Call agents and skills](../call-agents-and-skills.md)
