---
name: auto
version: 0.1.0
description: Route any request to the right skill, command, or agent chain with
  defaults, so nobody hand-picks from the full catalog. Use when you say `/auto`,
  `just handle this`, `do the right thing`, or when a request names no skill.
  Do NOT use when the user names a specific skill or lifecycle command;
  invoke that directly.
license: MIT
model: claude-sonnet-4-6
metadata:
  type: router
  inspiration: gstack /autoplan (garrytan/gstack autoplan/SKILL.md.tmpl)
---

# Auto

One lazy entry point for the whole catalog. Classify the request, route it,
apply defaults, and only stop for decisions that are genuinely the user's.
Models and people do not hand-route across dozens of skills; this skill does.

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `/auto` followed by the request text | Classify and route the request |
| `just handle this` | Classify and route the current request |
| `do the right thing` | Classify and route the current request |
| `figure out what to run` | Classify, then report the route before running |

## Process

### Phase 1: Classify

Answer two questions before any tool call.

**Intent family.** Match the request against the routing table below. When two
families match, prefer the more specific row (a failing CI check on a PR is
`Session-protocol CI failure`, not `PR ops`).

**Size.** Pick the smallest honest tier:

| Tier | Signal | Pipeline depth |
|------|--------|----------------|
| Trivial | One known file, no new capability, no contract change | Fix, test, commit |
| Standard | Bounded change, existing capability surface | /build then /test then /review then /ship |
| Feature | New capability, new module, or ambiguous requirements | /spec then /plan then the Standard chain |

When unsure between tiers, start one tier down and escalate on contact with
evidence (failing tests, widening diff), not on speculation.

### Phase 2: Route

| Intent | Route |
|--------|-------|
| Build a feature, "add X" | Lifecycle chain per size tier above |
| New capability (Context, module, scanner, validator, pipeline component) | Skill: buy-vs-build-framework (Quick tier) BEFORE /spec, then the Feature chain |
| Bug, error, "why is this broken" | Skill: analyze, then /build for the fix |
| PR, issue, label, milestone ops | Skill: github |
| Respond to PR review threads | Skill: pr-comment-responder |
| Merge conflicts | Skill: merge-resolver |
| Session-protocol CI failure | Skill: session-log-fixer |
| Push, ship, "open a PR" | /ship (or /push-pr for push-only) |
| "what do we know about X" | Skill: memory-search |
| Research an unfamiliar topic | Skill: context-gather, then research-and-incorporate |
| Code quality, health check | Skill: quality-grades (repo-wide) or review (pre-merge) |
| "Did I touch security-critical files?" | Skill: security-detection |
| Review a diff or snippet for vulnerabilities | Skill: security-review; injection scan via security-scan |
| Save progress, checkpoint | Skill: session-end |
| Correction received, lesson learned | Skill: reflect |
| Document a decision | Skill: adr-generator |
| New skill wanted | Skill: SkillForge |
| Multi-step, cross-cutting, or no row matches | Task(subagent_type="orchestrator") |

The user naming a skill or command bypasses this table entirely. User
Sovereignty wins over any row.

### Phase 3: Execute with defaults

Apply these without asking. Log each application for the final gate.

1. **Completeness.** Fix every case the bug applies to, not only the reported
   one. Tests cover positive, negative, and edge in the same change.
2. **Run the checks.** Tests, lint, and type checks always run before a commit
   claims completion. Never ask "should I run the tests?".
3. **DRY at the knowledge level.** Reuse the existing helper, skill, or script
   before writing a sibling.
4. **Bias to action.** Internal and reversible: act. Flag what you assumed in
   the final gate instead of pausing mid-run.
5. **Mirrors and gates.** Honor repo obligations without prompting: sync
   generated mirrors, bump plugin manifests, write the session log, keep
   commits atomic.

Classify every decision the run surfaces; never promote silently.

| Class | Definition | Handling |
|-------|------------|----------|
| Mechanical | One defensible answer (run tests, fix lint, sync a mirror) | Decide silently |
| Taste | Viable trade-offs, low reversal cost (naming, small refactor shape) | Decide, surface at the final gate |
| Sovereignty | Architecture, new ADRs, breaking changes, security posture, anything external or irreversible | Stop and ask. Never auto-decide |

The Sovereignty row is the AGENTS.md Ask First list plus the Autonomy
Guardrail. When a Sovereignty decision blocks the whole run, present 2 to 3
options with trade-offs per the Confusion Protocol and wait.

### Phase 4: Final gate

Every /auto run ends with one summary block, not a narration stream:

1. **Route taken** and why (one line).
2. **Auto-decided items**, Mechanical count plus each Taste decision with its
   one-line rationale.
3. **Open Sovereignty questions**, if any, with options.
4. **Evidence**: tests run and their counts, gates passed, artifacts produced.

## Verification

A routed run is complete when every box checks:

- [ ] The request was classified (intent family and size tier named).
- [ ] The route was one table row, a lifecycle chain, or the orchestrator
      fallback, and it was stated in the final gate.
- [ ] Every Mechanical default that fired is counted in the final gate.
- [ ] Every Taste decision appears in the final gate with a rationale.
- [ ] No Sovereignty decision was auto-decided.
- [ ] Evidence (test counts, gate results) is present in the final gate.

## Anti-Patterns

- **Routing everything to the orchestrator.** The fallback row is for the long
  tail, not a substitute for classification. Two orchestrator fallbacks in a
  row on classifiable requests means the table needs a row, not more fallback.
- **Asking mechanical questions.** "Should I run the tests?" is never a
  question. If one defensible answer exists, act.
- **Silent sovereignty.** Auto-deciding architecture, ADRs, breaking changes,
  or security posture because the run had momentum. Stop and ask.
- **Narration instead of a gate.** Streaming every micro-decision as chat
  defeats the point; batch them into the Phase 4 summary.

## Extension Points

- **New routing row.** When a new skill lands and requests start missing the
  table, add one row (intent, route) here and mirror the change in the
  CLAUDE.md Skill routing section until that section delegates here.
- **Tier signals.** Size-tier signals may grow project-specific entries (for
  example, "touches templates/agents/" implies Standard or above because of
  mirror obligations).
- **Escape hatches.** Route fails mid-run: fall back to
  Task(subagent_type="orchestrator") with the failure context rather than
  retrying the same route blind. Two consecutive routing misses on one
  request: stop, ask which route the user wanted, and log the miss with the
  reflect skill.

## Copilot CLI invocation reference

This skill body uses Claude Code call syntax. Under GitHub Copilot CLI, translate as follows (verified against Copilot CLI 1.0.66-1).

### Sub-agent calls

| Claude Code syntax | Copilot CLI equivalent |
| --- | --- |
| `Task(subagent_type="orchestrator")` | `task` tool, `agent_type: "project-toolkit:orchestrator"` |

If a referenced skill or agent is unavailable in the Copilot CLI environment, perform that step inline and note the reduced coverage.
