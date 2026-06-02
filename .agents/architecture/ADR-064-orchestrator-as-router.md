# ADR-064: Orchestrator Is a Deterministic Router and Retry Policy, Not a Supervisor

## Status

Proposed

## Date

2026-05-29

## Context

The orchestrator agent is currently designed and documented as if it manages
sub-agents. Existing prompts ask the orchestrator to notice when sub-agents
are stuck, course-correct them, motivate them, and otherwise supervise their
work. Per `wiki/concepts/AI Strategy/LLMs as Ghosts not Animals.md`, this
framing describes a capability the system does not have. There is no
supervision loop between the orchestrator and sub-agents. There is only
context concatenation: the orchestrator emits a prompt, a sub-agent emits a
reply, and the orchestrator sees the reply as new input.

A ghost cannot supervise another ghost. The manager framing produces
orchestrator prompts that ask the LLM to do things it cannot do, and downstream
authors then write sub-agent prompts that depend on supervision that never
arrives. The gap is silent: nothing fails loudly when the orchestrator
"forgets" to course-correct, because the course-correction was never wired in.

### What Currently Exists

- Orchestrator agent definitions in `templates/agents/orchestrator*.md` and any
  agent labeled `role: orchestrator` use manager and supervisor vocabulary.
- Sub-agent frontmatter has no required `success_criterion` field. Authors
  declare success implicitly in prose.
- Retry behavior on sub-agent failure is ad hoc, expressed in prompt text
  rather than code, and not logged.
- Routing decisions (input to chosen agent) are not surfaced in run logs.

### Why Change Now

This issue (#1857) is the first ADR-class follow-up to make the ghost-not-
animal framing operative in the codebase. Related companions #1854 and #1855
extend the same framing into evals and gates. Without this ADR landing first,
those downstream changes have no anchor to cite.

## Decision

The orchestrator is a deterministic router with a retry policy. It is not a
supervisor. This ADR codifies four binding rules.

1. **Strip manager language from orchestrator definitions.** Orchestrator
   agent files (`templates/agents/orchestrator*.md`, any agent declaring
   `role: orchestrator` in frontmatter) MUST NOT use manager, supervisor,
   coach, mentor, notice-when-stuck, course-correct, motivate, or
   semantically equivalent language. A lint check enforces this on CI.

2. **Every sub-agent declares an explicit `success_criterion` in frontmatter.**
   Two forms are allowed:

   - **Machine-checkable.** A schema, regex, named test, exit code, or
     equivalent signal the router can evaluate without LLM judgment. Preferred
     where it fits the agent's job.
   - **Human-judgment with rationale.** The literal value `human-judgment`
     paired with a `rationale:` field explaining why no machine signal applies
     (for example, "agent drafts an ADR; quality is judged by review, not
     regex"). The escape hatch is explicit so it cannot be abused silently.

   Schema:

   ```yaml
   success_criterion:
     kind: exit-code | schema | regex | test | human-judgment
     value: <expression>            # required for machine-checkable kinds
     rationale: <one sentence>      # required when kind == human-judgment
   ```

3. **Routing decisions are logged.** Each route emits a structured record:
   `input_id`, `chosen_agent`, `reason` (`rule-id` or
   `classifier-confidence`). Logs are written to the standard run log so
   retrospectives and audits can replay routing without re-running the LLM.

4. **Retry policy lives in code, not prompt.** Default `N=3` retries per
   sub-agent invocation. Each retry embeds the prior failure signal (the
   `success_criterion` evaluation output) into the next call's context.
   Exhaustion surfaces as a visible CI or run failure. The orchestrator MUST
   NOT silently fall back to best-effort.

## Prior Art Investigation

- `wiki/concepts/AI Strategy/LLMs as Ghosts not Animals.md`: the frame this
  ADR operationalizes. Ghosts have no continuous identity across calls.
  Anything that looks like supervision must be deterministic state managed
  outside the LLM.
- ADR-013, ADR-033, ADR-010: prior decisions on agent boundaries and prompt
  discipline. None bind the orchestrator to a router-only role; this ADR
  closes that gap.
- ADR-051 (synthesis-panel frontmatter standard): precedent for requiring
  structured frontmatter fields enforced by schema. The `success_criterion`
  field follows the same pattern.
- ADR-057 (prompt behavioral evaluation): adjacent. Evaluations test whether
  prompts behave as claimed; this ADR removes claims the prompt cannot
  satisfy in the first place.
- Issues #739 (workflow orchestration epic), #619 (Do Router mandatory
  routing gates), #1726 (deterministic gates): all point at the same shift
  from LLM-judged orchestration to deterministic gates. This ADR is the
  written decision those issues require.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Keep manager framing, add retries | Minimal prompt churn | Preserves the false claim that the LLM supervises | Contradicts the ghosts-not-animals frame; the bug is in the framing, not the wording |
| Require machine-checkable criterion always | Strongest CI signal | Forces authors to invent fake signals for inherently human-judged work (ADR drafting, design review) | Issue edit log explicitly added the `human-judgment` escape hatch for this reason |
| Put retry policy in the orchestrator prompt | Author flexibility | Non-deterministic; retries become advisory; exhaustion can be silently ignored | Violates rule 4; the whole point of router-not-supervisor is moving control out of the prompt |
| Log only on failure | Smaller log volume | Loses the routing-rationale signal on successful routes, which is the higher-value audit trail | Routing decisions are cheap to log and expensive to reconstruct |

### Trade-offs

- The `human-judgment` escape hatch will be abused if reviewers do not enforce
  the `rationale` field substantively. Mitigation: the lint check rejects
  empty or boilerplate rationales (length floor, banned phrases).
- Hard retry cap (`N=3`) may surface failures that previously hid behind
  best-effort behavior. This is the intended consequence. Visible failure is
  the precondition for fixing the underlying agent quality.
- Stripping manager vocabulary will read as a regression to authors who liked
  the framing. The ADR text is the canonical answer to "why did you remove
  that?"

## Consequences

### Positive

- Orchestrator prompts stop asking the LLM to do things it cannot do.
- Sub-agent quality has a single declared signal per agent, queryable from
  frontmatter.
- Routing decisions become auditable without re-running the LLM.
- Retry exhaustion is visible. Silent best-effort goes away.
- Downstream issues (#1854, #1855) have a written decision to cite.

### Negative

- Migration cost: every existing orchestrator file and every sub-agent file
  must be updated. Estimated at one focused PR per concern (ADR, lint,
  schema, prompt refactor, retry policy code).
- New CI checks add wall-clock time to PR runs. Expected under 30 seconds
  combined.
- The `human-judgment` rationale field is judgment-loaded. Review burden on
  authors and reviewers increases slightly.

### Neutral

- The orchestrator continues to be an LLM call. The ADR does not propose
  replacing it with a rules engine. The change is what the LLM is asked to
  do, not whether an LLM is used.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| `templates/agents/orchestrator*.md` | Direct | Strip manager language; reframe as router | Low |
| All sub-agent files declaring `role:` | Direct | Add `success_criterion` frontmatter | Low |
| Agent registry / schema validator | Direct | Require `success_criterion`; accept both forms | Low |
| Orchestrator runtime (code path) | Direct | Implement retry policy with N=3 cap and failure-signal embedding | Medium |
| Run log schema | Direct | Add routing-decision record shape | Low |
| `scripts/validation/` | Direct | New lint check for banned manager tokens in orchestrator files | Low |
| Retrospective tooling | Indirect | Can now query routing decisions and retry exhaustion from logs | None (additive) |

## Implementation Notes

The ADR is the unit of decision. Enforcement and refactor land as separate
PRs, in this order, to keep each change reviewable:

1. **This ADR** (PR-1): decision text only.
2. **Schema check** (PR-2): extend the sub-agent frontmatter validator to
   require `success_criterion`. Land with a grace-period flag if necessary;
   flip to BLOCKING once all sub-agents are updated.
3. **Lint check** (PR-3): banned-token scanner for orchestrator files.
   Initial token list: `manage`, `supervise`, `coach`, `mentor`,
   `course-correct`, `notice when`, `course correct`, `motivate`,
   `oversee`. Update list as patterns emerge.
4. **Sub-agent migration** (PR-4..N): add `success_criterion` to each
   sub-agent. Group by area.
5. **Orchestrator refactor** (PR-N+1): rewrite orchestrator prompts to the
   router framing.
6. **Retry policy code** (PR-N+2): implement the N=3 retry loop with
   structured failure-signal embedding and visible exhaustion.

The acceptance checklist on issue #1857 tracks the full sequence. This ADR
closes only step 1.

## Related Decisions

- ADR-051: synthesis panel frontmatter standard (precedent for required
  frontmatter fields)
- ADR-057: prompt behavioral evaluation (adjacent; evaluates what this ADR
  removes the option to claim falsely)
- ADR-059: PR review completion gate dispatcher (adjacent deterministic gate)

## References

- Issue #1857: this ADR's source of record
- Wiki: `wiki/concepts/AI Strategy/LLMs as Ghosts not Animals.md`
- Issue #739: workflow orchestration epic
- Issue #619: Do Router mandatory routing gates
- Issue #1726: deterministic gates
- Issues #1854, #1855: eval/gate companions that depend on this decision
