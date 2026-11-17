# requirements-interview

Interviews you about an idea, one design decision at a time, until every branch has a confirmed answer. It can also audit an existing spec for ambiguity. You get a structured requirements document you can hand to a spec.

## When to use it

- You have a new idea or a vague request and want testable requirements before any code.
- You say `interview me on this`, `grill me on the requirements`, `walk the design tree`, or `stress-test this idea`.
- You have a multi-section spec and want to find gaps: say `audit this spec for ambiguity`.

## When not to use it

- The spec is clear and has no material ambiguity: the skill returns `NO MATERIAL GAPS` and asks nothing.
- You want the durable REQ, DESIGN, and TASK files: use [`spec-generator`](spec-generator.md) instead. This skill produces the input for it and does not write those files.

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:requirements-interview add rate limiting to the public API
```

In GitHub Copilot CLI, or in a Claude Code session inside a checkout of this repository, drop the prefix: `/requirements-interview`.

The skill restates your problem in one sentence and asks you to confirm it. Then it asks numbered questions, one decision each, with a recommended answer and its source. If the codebase can answer a question, the skill answers it and cites the file.

## What you get

| Artifact | Location | Purpose |
| --- | --- | --- |
| Interview transcript | `.project-toolkit/specs/interviews/INTERVIEW-<slug>.md` | Audit trail of decisions and rationale |
| Structured requirements | Returned to the caller | Input for downstream spec work |

The structured output has these sections: `Problem`, `User stories`, `Ontology`, `Data model`, `Integrations`, `Failure modes`, `Security`, `Observability`, `Acceptance criteria`, `Out of scope`, `Deferred`, and `Open questions`. Acceptance criteria use EARS syntax (`WHEN ... THE SYSTEM SHALL ... SO THAT ...`).

Each question ends with one status: `CONFIRMED`, `OVERRIDDEN`, `DEFERRED`, or `OUT_OF_SCOPE`.

## Advanced use

### Discovery mode

The skill builds a design tree and walks it depth first, resolving dependent decisions before siblings. The branch order is user stories, ontology, data model, integrations, failure modes, security, observability, and scope boundaries. It skips a branch only with a stated reason. For each branch it asks what would have to be true for the feature to fail in production.

If a caller passes an OntologyFragment from `/spec` Step 1, the skill reads it first and uses the O2 canonical names in its questions.

The interview ends when every branch has a confirmed decision, an explicit deferral, or an out-of-scope marker, and you confirm the final problem restatement and acceptance criteria.

### Ambiguity audit mode

For an existing multi-section spec, the skill writes a ledger of gaps. Each gap has a source anchor (a section plus an exact quote or line range). Categories are `edge_case`, `undefined_state`, `permissions`, `error_behavior`, `data_constraint`, `concurrency`, `contradiction`, and `terminology`. Gaps the document or codebase already answers get the disposition `answered_in_document` or `answered_in_codebase`.

`spec_audit.py` rejects any anchor that is not verbatim in the source. It prints one JSON object.

```bash
uv run python .claude/skills/requirements-interview/scripts/spec_audit.py check --help
uv run python .claude/skills/requirements-interview/scripts/spec_audit.py verify --help
```

`check` takes `--source`, `--ledger`, and optionally `--repo-root`, `--max-options`, and `--max-questions`. `verify` takes `--source`, `--ledger`, `--log`, `--rebuilt`, and optionally `--repo-root`.

| Status or exit code | Meaning |
| --- | --- |
| `no_material_gaps` | The skill returns `NO MATERIAL GAPS`. |
| `ask` | A batch of independent questions to present now. |
| `invalid`, `incomplete`, `revise_recommendation` | Exit 1. Fix the ledger. |
| `held` | Only held decisions remain. |
| `resolved` | Every live decision is answered. Rebuild the spec, then run `verify`. |
| Exit `0` | ok |
| Exit `1` | Invalid ledger, incomplete question, or failed verification. |
| Exit `2` | Unreadable file, or the `decision-question` engine is missing. |

The skill never picks business policy for the owner. Without repository evidence for a recommendation, the question reads `Owner decision, no evidence-backed recommendation`. `audit_check.py`, `audit_source.py`, and `audit_verify.py` are modules that `spec_audit.py` imports, not entry points.

### Chaining

[`spec-generator`](spec-generator.md) invokes this skill to walk the design tree before analysis. The caller (typically `/spec`) passes every PRD section to `spec-generator` unchanged, so it does not re-ask answered questions. Related skills: [`decision-critic`](decision-critic.md), [`pre-mortem`](pre-mortem.md), and [`cynefin-classifier`](cynefin-classifier.md).

Reference files: [`ambiguity-audit.md`](../../src/claude/skills/requirements-interview/references/ambiguity-audit.md) covers the ledger schema, question rules, batching, and rebuild verification.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`spec-generator`](spec-generator.md): turns the PRD into REQ, DESIGN, and TASK files.
- [`spec`](spec.md): the lifecycle command that calls this skill.
- [`decision-critic`](decision-critic.md): stress-tests a single decision.
- [`pre-mortem`](pre-mortem.md): finds failure causes before you build.
- Source: [`SKILL.md`](../../src/claude/skills/requirements-interview/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
