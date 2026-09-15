# SPEC: Agent-manufactured backlog growth (epic #5698)

**Date**: 2026-09-15
**Status**: Draft for owner review
**Epic**: #5698 and sub-issues #5699 to #5709
**Skill run**: spec (Step 0, Step 0.5, evaluation axes, PRD schema). Step 6 spec-generator emission is deferred: the sub-issues already exist as the TASK layer, and this run's purpose is to validate that they solve the problem.

## Step 0 First Principles

Answers are the owner's, confirmed verbatim on 2026-09-15.

### Q1 Demand Reality

We are a legit customer. Most of what we're building is because I want it. 3 external customers for business and building products.

### Q2 Status Quo

I open the issue list, read titles, cannot tell which ones I asked for versus which an agent filed under my login, and either leave them or close by hand. No filter, label, or script separates the two.

### Q3 Desperate Specificity

Me, as owner of rjmurillo/ai-agents, blocked on triaging 228 open issues with no provenance marker, while agents add about 10 a day.

### Q4 Narrowest Wedge

#5700, the required --source flag on the issue script (new_issue.py) with Step 0 answers demanded for agent-sourced issues, plus #5703, the retrospective agent no longer filing. About 6 to 8 hours of implementation.

### Q5 Observation

Measured 2026-09-10 and recorded in #5698: 405 issues created and 278 closed in 30 days; 226 of 228 open issues under my login; 0 carry a Step 0 block; 81 of 148 round-1 ADR debate findings were factual errors; the pre-push retro gate produced 96 retros in 40 days. My words: "it just keeps growing with shit the models keep finding."

### Q6 Future-fit

Yes. More agents and fleets raise the agent-selected share, so a provenance marker at the script and a cost split by who selected the work matter more, not less. The gate scales because it sits at the one script every agent calls.

### Gate result

Hedge scan: no hits. Q3 specificity: pass (named individual, uniquely identified repository). Q5 speculative test: pass (metrics, artifact #5698, direct quote). Q1 aspirational test: fail on condition 1 (one named requester, three unnamed) and condition 3 (a generic category).

```step0-halt
trigger: H3
question: Q1 Demand Reality
answer: "We are a legit customer. Most of what we're building is because I want it. 3 external customers for business and building products."
test_failed: aspirational test conditions 1 and 3 (fewer than three named requesters; "3 external customers" is an unnamed group)
deferral: Name the three external customers (team or product name) and re-run; or proceed under owner override as recorded below.
```

Tally: `2026-09-15T03:25:29Z | fail | H3 | Q1 Demand Reality` appended to `.agents/metrics/STEP-0-METRICS.md`.

**Owner override, recorded once.** The owner confirmed the answers and said continue. Under builder-ethos User Sovereignty the gate result stands as recorded and the spec proceeds. Trade-off: the three customers' names never enter the record, so no acceptance criterion below can be tied to a named external consumer. Everything below is scoped to the owner as the blocked party.

## Step 0.5 Prior Art

ProvisionalTier: hours_tier 3 (Q4 says 6 to 8 hours; 8 falls in the 8 to 40 band), entity_tier 3 (six named entities across Q3 and Q4: rjmurillo/ai-agents, new_issue.py, the --source flag, spec Step 0, #5700, #5703, the retrospective agent). Tier 3, medium depth: point search plus a dependency pass.

### Direct prior art from memory

- Twelve queries over `.serena/memories` and `.agents/memory/episodes` (three variants per topic: issue script, retrospective agent, spec Step 0, backlog growth). Every non-zero hit was an episode about a different follow-up (PR 4296 memory follow-up, a subprocess encoding change). No memory records a decision about issue provenance, agent-filed issues, or a backlog cap.
- ADR-020 (feature-request review step), status proposed, implemented false, dated 2025-12-19: designs an intake review step on issue open where the analyst agent evaluates a feature request before it is worked. Same shape as the repo-side gate this spec recommends; never implemented.
- Chesterton pass on `.claude/skills/github/scripts/issue/new_issue.py`: callers are the research skill, the retrospective agent template and its three copies, `scripts/github_core/api.py`, `scripts/ci/ruleset_context_drift.py`, and the github skill references. No ADR governs who may create an issue. Git history in this checkout is shallow (one visible commit), so the archaeology is partial.

### Connected context from prior-art search

Issue generators discovered that #5698 does not name. Adjudicated in-scope (acknowledged as part of this spec's scope) because each is a door the provenance rule must cover:

| Generator | Where | What it does today |
|---|---|---|
| adr-review deferral protocol | `.claude/skills/adr-review/references/issue-resolution.md:15` | "Deferred P1 items MUST be backlogged as GitHub issues." A MUST that manufactures issues to clear a gate. |
| qa agent CONDITIONAL verdict | `.claude/agents/qa.md:585` | A CONDITIONAL verdict must cite a follow-up issue number, so passing QA requires filing an issue. |
| security agent CONDITIONAL verdict | `.claude/agents/security.md:221`, `:398`, `:546` | Same shape: the gate clears only when a follow-up issue exists. |
| research skill | `.claude/skills/research/SKILL.md:4`, `:91` | Files a follow-up issue by design at the end of every run. |
| task-decomposer agent | `.claude/agents/task-decomposer.md:46` | Uses raw `gh issue create`, bypassing new_issue.py and any flag it grows. |
| GitHub workflows with `issues: write` | 14 files under `.github/workflows/` (drift-detection, ai-metrics-analysis, artifact-insight-scanner, quality-grades among them) | Create issues under the github-actions login; already distinguishable by login. |

Adjudicated out-of-scope: `claude.yml` (runs on issues.opened but only answers mentions; it is not a generator).

Blast-radius count after adjudication: 0. No Step 0.5 halt.

### Coverage notes

- Serena MCP was disconnected this session; `search_memory.py` read the memory files directly (SerenaQueried true, EpisodesQueried true in its status block), so coverage is the file corpus, not the MCP index.
- "backlog growth" and "retro gate pre-push" returned zero results after three variants each: absence of evidence, not evidence of absence.
- `chestertons-fence` was run by hand (git log, caller grep, ADR grep) rather than through its `investigate.py`, because the shallow clone gives that script one commit to work with.

## Problem statement

Agents file issues under the owner's login at about 10 a day with no provenance, so the tracker cannot separate owner demand from agent-manufactured demand, and nothing bounds how many tasks the agents choose to run.

## User stories

1. As the owner, when I open the issue list, I can filter to issues I asked for, so triage takes minutes instead of a day.
2. As the owner, when an agent finds something while doing a task, the finding reaches me in the PR body or the retro file, not as a new issue I have to close.
3. As an agent with no prior context, when I pick up a sub-issue, the issue tells me everything I need, and I never file follow-ups from what I notice.
4. As the owner, each week I can see what share of new issues and retros the agents selected, and a threshold tells me when to intervene.
5. As an ADR reviewer seat, the draft I receive has already been fact-checked, so the round is about the decision.

## Ontology

Canonical names (O2):

- **WorkItem**: a GitHub issue in rjmurillo/ai-agents.
- **Provenance**: who selected the WorkItem: `human` or `agent`. Carried as a label `source:human` or `source:agent`.
- **Generator**: any agent, skill, or workflow able to create a WorkItem. Seven named above plus retrospective and backlog-generator.
- **IssueDoor**: an entry path a Generator can use: `new_issue.py`, the `mcp__github__issue_write` tool, raw `gh issue create`, the REST or GraphQL API from a workflow, and the web form.
- **AdmissionTest**: the Step 0 Q3 and Q5 answers an agent-sourced WorkItem must carry.
- **Consumer**: the owner and the three external customers. Only the owner is named.
- **Finding**: something an agent notices while doing a task. Lands in a PR body or a retro file, never as a WorkItem.
- **CostLedger**: the weekly measurement of WorkItems and retros by Provenance, in COST-GOVERNANCE.md.
- **RetroTrigger**: an event that warrants a retrospective (notable success or failure), as opposed to a push or a date.
- **ClaimsLedger**: the per-claim verification table an ADR draft carries before adr-review.
- **GuidanceBundle**: rule text compiled into a skill at the step it governs (#5706).

Relationships: a Generator uses an IssueDoor to create a WorkItem; a WorkItem has exactly one Provenance; an agent-sourced WorkItem must satisfy the AdmissionTest; a Finding is never a WorkItem; the CostLedger aggregates WorkItems by Provenance per week.

Aggregate boundary: Provenance is decided at the IssueDoor, once, and never rewritten by an agent.

Decision rule: a WorkItem created under the owner login with no `source:human` marker is agent-sourced. The default is agent, because the two share a login and only a human can assert human.

Open ontology question: whether "human" means the owner typed the request in a session, or the owner filed through the web form. The former is unverifiable from the record; the latter is.

## Data model

| Entity | Identity | Invariants | Lifecycle |
|---|---|---|---|
| WorkItem | issue number | exactly one `source:*` label after creation; agent-sourced carries a `## Step 0` block with Q3 and Q5 | open, closed (completed or not planned) |
| Provenance | label name | one of two values; set at creation; changed only by the owner | immutable for agents |
| Finding | PR number plus heading "Noticed, not done", or retro file path | never becomes a WorkItem without an owner action | lives with its PR or retro |
| CostLedger row | ISO week | counts by Provenance sum to total created | appended weekly, never edited |
| ClaimsLedger | ADR id | one row per factual claim; every row has a command and a result | written before adr-review, attached to the debate log |

## Integrations

| System | Use | Failure mode | Idempotency |
|---|---|---|---|
| GitHub REST via `new_issue.py` | primary IssueDoor for skills | script exits 2 when `--source` or Step 0 answers are missing | creation is not idempotent; a retry after a label failure duplicates (research SKILL.md line 149 already warns) |
| `mcp__github__issue_write` | IssueDoor for Claude Code sessions and workflow agents | no flag exists; the tool cannot be made to demand Step 0 | same |
| raw `gh issue create` | IssueDoor used by task-decomposer | bypasses every script-side check | same |
| GitHub Actions on `issues.opened` | proposed repo-side enforcement | workflow lag of seconds to minutes; a burst can land before labeling | labeling is idempotent |
| GitHub search API | weekly CostLedger script | index lag; paging | read-only |

## Failure modes

1. **Door bypass.** An agent files through the MCP tool or raw gh and never sees `--source`. This session did exactly that three times (issues #5705 and two epic updates went through `mcp__github__issue_write`), and the two workflow runs that filed #5699 to #5709 used the same tool. A script-only gate covers a minority of real traffic. Early warning: an issue under the owner login with no `source:*` label. Prevention: repo-side labeler (AC-3).
2. **Gate-clearing issues.** adr-review, qa, and security agents require an issue number to pass a verdict, so removing retrospective and backlog-generator leaves three generators that file to clear gates. Early warning: issues labeled `adr-followup` or cited in a CONDITIONAL verdict with no human in the thread. Prevention: AC-6.
3. **Forged provenance.** An agent passes `--source human` because it shares the login. Early warning: `source:human` issues with agent-shaped bodies (six required headings, burst timing). Prevention: human means web-form or owner comment; the labeler treats an API-created issue as agent unless the body carries the form marker (AC-3), and the weekly report flags bursts (AC-7).
4. **Burst before label.** A task-decomposer run creates 5 issues in 6 seconds; the labeler runs after. Impact: seconds of unlabeled state; no data loss.
5. **Reset closes a wanted item.** The #5704 close pass closes something the owner wanted. Prevention: keep list from the owner before any close; closed as not planned is reversible.
6. **Retro gate removal loses learnings.** Retiring the push gate (#5709) means sessions that would have written a retro write nothing. Prevention: reflect at session stop is the replacement and must land in the same PR.
7. **ADR gate escape.** A factual error survives the adr-generator gates. Prevention: the debate log records gate escapes (AC-10) so the gate is measured, not assumed.
8. **Metrics without stop.** The CostLedger reports a runaway condition and nobody acts. Prevention: AC-8, a circuit breaker with an owner reset, proposed and awaiting the owner's word.

## Security

Trust boundary: the IssueDoor. Everything inside a session runs under the owner's credentials, so the label is an assertion, not an authentication. Threats: an agent asserting `source:human` (mitigated by defaulting API-created issues to agent, AC-3); Step 0 answers carrying secrets into issue bodies (the spec skill's `redact_secrets.py` runs before any durable write; the issue script must run the same redactor on `--blocked-by` and `--signal`, AC-2); the weekly script reading with a token that can write (use a read-only token or the existing github_core helper's least-privilege path). No PII beyond the owner's login, which is already public on every issue.

## Observability

What metric proves this works: the weekly CostLedger row. SLIs: share of new issues with `source:agent` (target below 50 percent within four weeks of AC-3 landing), share of new issues about repo machinery by title (target below 30 percent), retros per week (target: equal to RetroTrigger events, so a week with no notable event has zero), ADR debate rounds to consensus (target: median 2 or fewer after AC-10 lands, from median 3), gate escapes per ADR (target 0). Alert threshold: the runaway condition in #5705. Logs: the labeler workflow's run log names each issue it labeled and why.

## Acceptance criteria

EARS syntax. Each is pass or fail from evidence. The sub-issue that carries it is named; gaps are marked NEW.

1. The issue script shall refuse to create an issue unless `--source human` or `--source agent` is given, and shall apply the matching `source:*` label. (#5700)
2. When `--source agent` is given, the issue script shall require `--blocked-by` and `--signal`, reject the canonical hedge phrases, run the secret redactor over both answers, and append a `## Step 0` block with Q3 and Q5 to the body. (#5700, redaction is NEW within #5700)
3. NEW. When an issue is opened in rjmurillo/ai-agents by any door, a repository workflow shall label it `source:agent` unless the body carries the web-form marker or the author login is not the owner's, and shall label it `source:human` when the marker is present. (Amends #5700; the script becomes the friendly door and the workflow the enforcement point. Prior art: ADR-020's intake step.)
4. The retrospective agent shall write findings only to the retrospective file and shall never call an IssueDoor. (#5703)
5. The backlog-generator agent shall not exist in any template, generated tree, catalog, or routing table. (#5701)
6. NEW. The adr-review deferral protocol, the qa agent, the security agent, the research skill, and the task-decomposer agent shall not require or perform issue creation to clear a verdict or finish a run; a deferred or conditional item shall be recorded in the debate log, the PR body under "Noticed, not done", or the retro file. task-decomposer shall use the issue script with `--source agent` when the owner has asked it to decompose an epic, and never raw gh.
7. The weekly report shall state, for the trailing 7 days, the count and share of new issues by `source:*` label, the count of bursts (3 or more issues by one login within 10 minutes), and the machinery share by title, and shall exit 0 with a markdown table and JSON. (#5702)
8. NEW, awaiting the owner's word. While the trailing-7-day `source:agent` share exceeds 50 percent, the labeler shall close any newly opened agent-sourced issue as not planned with a comment naming the epic and the threshold, until the owner posts a reset comment on the epic. This is the only criterion that stops rather than measures.
9. COST-GOVERNANCE.md shall carry a Model Token Cost Policy with the two-line cost model, the five weekly metrics, the 2026-09-10 baseline, the runaway condition, and a weekly review line. (#5705)
10. adr-generator shall run five mandatory exit gates (claims ledger, citation freshness, doc-accuracy, self-consistency, one refuting analyst seat) before Phase G5, and adr-review's debate log shall record any factual finding a seat raises after the gates as a gate escape. (#5708)
11. When a session stops, the reflect skill shall run by a mechanism the harness can actually fire; a full retrospective shall be written only on a RetroTrigger; lefthook shall carry no retrospective push gate. (#5709)
12. builder-ethos.md shall state the two-line cost model and that an agent may boil a lake the user named and may only flag, never file, a lake it found; voice.md's ownership example shall agree. (#5699)
13. Each of the 8 skills carrying `@CLAUDE.md` shall compile from a SKILL.md.tmpl, the generated file shall be byte-identical to the committed one, and the Copilot mirror shall contain no `{{` and no `@CLAUDE.md`. (#5706)
14. The owner shall receive one triage sheet for the 228 open issues as a single epic comment, and no issue shall be closed before the owner's keep list is posted. (#5704)

## Coverage evaluation (axis 1 through 5)

**Problem clarity.** The epic names the right root cause (no provenance, no human at the door) and the right doctrine error (per-task pricing of per-period spend). It under-states the door: it treats `new_issue.py` as the one script every agent calls (Q6 says so), and the measured traffic says otherwise. The reframing that changes the outcome is to make "agents never file; a human files" the invariant and to enforce it where every door converges, the repository, with the script as the courteous path. That is AC-3 and AC-6, and it is the shape ADR-020 proposed in December 2025 and never built.

**Testability.** Every criterion above names a command, a grep, or an observable state. AC-8 is testable but is a policy decision the owner has not made.

**Completeness.** Gaps between the epic and the problem, each now a criterion: door bypass (AC-3), gate-clearing generators (AC-6), redaction of Step 0 answers (AC-2), a stop rather than a report (AC-8). One gap has no criterion: token spend itself. No telemetry in the repo records tokens per session or per PR (`.agents/metrics/` holds a Step 0 tally, an audit TSV, and dashboard templates; nothing token-shaped). The CostLedger measures issues and retros as proxies. Recorded under Open questions.

**Traceability.** Sub-issue to criterion: #5699 AC-12; #5700 AC-1, AC-2, AC-3; #5701 AC-5; #5702 AC-7; #5703 AC-4; #5704 AC-14; #5705 AC-9; #5706 AC-13; #5708 AC-10; #5709 AC-11. Criteria with no sub-issue: AC-6, AC-8.

**Feasibility.** All criteria reuse existing code: the issue script, `check_citation_freshness.py`, doc-accuracy, generate_agents and generate_skills, lefthook. AC-3 is a small workflow under ADR-006 (logic in a Python script, YAML thin). AC-8 adds one branch to that script.

## Out of scope

- Naming or onboarding the three external customers into the tracker.
- Cutting any always-on rule file (follows #5706).
- Changing adr-review's seat count or round cap.
- Converting all 112 skills to templates in one pass.
- Rewriting FAILURE-MODES.md's gate doctrine.

## Deferred

| Decision | Owner |
|---|---|
| AC-8 circuit breaker: adopt, or keep measurement only | owner |
| Whether "human" means web form only (verifiable) or also owner-typed session requests (unverifiable) | owner |
| ADR for the provenance rule under governance.md MUST 2, and whether ADR-020 is revived or superseded by it | owner and architect |
| Always-on rules cut after #5706 | owner |

## Open questions

1. Token spend has no source of truth in the repo. Which harness surface exposes per-session or per-PR tokens, and can it be written to `.agents/metrics/` without a new dependency? Owner.
2. The retrospective push gate blocks pushes from this session (two files changed, so not trivial; no retro dated today). This spec cannot be pushed without either writing a retro nobody asked for or bypassing a hook. Reported, not bypassed. Owner decides whether #5709 lands first.
3. Does the owner file through the web form, or only through sessions? Decides AC-3's human marker.

## CVA summary

Common: every Generator wants to record a Finding; every Finding has a location and a proposed action. Varies: the door used, the login, whether a human asked. Relationship: Provenance is a property of the door plus the human, not of the content, so the abstraction is a labeled door, not a smarter body check. The wrong abstraction to avoid: classifying issues by how they read.

## Buy-vs-build decision

Classification: context, not core. Alternatives: GitHub issue forms (required fields, but web-only, so the API doors are untouched); GitHub issue types (organization-only, this is a user repository); GitHub Projects fields (manual); a third-party triage bot (adds a vendor to the trust boundary for a two-label decision). Recommendation: build the small labeler workflow and reuse the issue script; use the issue form as the human marker. Rationale: the enforcement point must see every door, and only a repository workflow does.

## Complexity classification

Engineering tier: 4 (cross-cutting: rules, scripts, agents, hooks, build pipeline, workflows; sets direction for how the repository takes in work). Cynefin: Complex for the behavior (agents' loops emerge from many small instructions; probe, sense, respond, which is why AC-7 measures before AC-8 stops) and Clear for the mechanism (a label at a door). Methodology: land the measurement and the door first, read one week of CostLedger rows, then decide AC-8.

## ADR cross-reference

Tier 4 requires one. The provenance rule is a new governance rule under `.claude/rules/governance.md` MUST 2. Candidate: revive ADR-020 (proposed, unimplemented, same shape) as the intake decision, amended to cover provenance and the labeler, rather than a new number. adr-review verdict: not yet run. Bidirectional link: this spec to ADR-020; ADR-020 to #5698.
