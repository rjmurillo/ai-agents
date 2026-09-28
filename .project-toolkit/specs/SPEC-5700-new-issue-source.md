# SPEC: Provenance at the issue script (issue #5700)

Parent: epic #5698, spec `.project-toolkit/specs/SPEC-agent-backlog-provenance.md` (AC-1, AC-2).
This document lands in git history. Do not paste live secrets into any answer below.

## Step 0 First Principles

Inherited verbatim from the parent spec, owner-confirmed on 2026-09-15. Gate
result there: H3 on Q1 with a recorded owner override; Q3, Q5, and the hedge
scan pass. Q4 names this issue as half of the narrowest wedge.

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

## Step 0.5 Prior Art

Searched `.serena/memories` for provenance, new_issue, and source-label names:
one unrelated hit (`decision-eval-fixture-provenance-closed-loop.md`). Searched
the tree for `source:agent`: only the parent spec and
`.agents/governance/COST-GOVERNANCE.md:163`, which already defines the
human-only, agent-only, conflict, and unknown buckets this script feeds. No
halt: nothing built answers the question.

## Problem statement

`new_issue.py` records nothing about who selected the work, so an issue an
agent chose looks the same as one the owner asked for.

## User stories

1. As the owner, I filter issues by `source:human` or `source:agent` and see who selected each one.
2. As the owner, I read an agent-sourced issue and find who is blocked (Q3) and the signal that proves it (Q5).
3. As an agent, I get a one-line refusal before any GitHub call when my provenance or evidence is missing.

## Ontology

- **Source**: who selected the work. `human` requires an explicit human request selecting that work. An owner login, a human-started session, a user approval to publish, or a retrospective run is not proof of human selection. Provenance is not authorization.
- **SourceLabel**: `source:human` or `source:agent`. Exactly one per issue the script creates.
- **Step0Evidence**: the Q3 (blocked-by) and Q5 (signal) answers. Supplied by flags, or by an existing `## Step 0` block in the body. Never both.
- **IssueDoor**: any path that creates an issue. This spec changes one door, `new_issue.py`.

## Data model

Issue body: caller body, plus a `## Step 0` block with `### Q3` and `### Q5`
when evidence came from flags. Labels: the SourceLabel plus caller labels,
deduplicated. Invariant: a created issue always carries its SourceLabel,
because the label is part of the create call.

## Integrations

`gh label create` (best-effort ensure) and `gh issue create --label` (the
fail-closed point). gh resolves label names before it sends the create
mutation: in cli/cli `pkg/cmd/issue/create/create.go`, `AddMetadataToIssueParams`
returns on error before `api.IssueCreate`, and `pkg/cmd/pr/shared/params.go`
wraps a missing label as `could not add label: %w`. So an ensure failure other
than "already exists" (no triage permission, timeout) is logged to stderr and
the create call reports the missing label; no issue exists. Caller labels still
apply in a second call, as today.

## Failure modes

1. Unlabeled issue after a label failure. Prevented: the SourceLabel travels in `gh issue create`, which resolves labels before creating.
2. Missing label in a consumer repo. Prevented: the script creates the label when absent.
3. Duplicate or contradictory Step 0. Prevented: flags plus a body Step 0 block is a usage error.
4. Secret in evidence text. Prevented: flag evidence passes through the bundled redactor before it lands in the body.
5. Door bypass (MCP `issue_write`, raw `gh`, workflows). Not prevented here. Recorded under Out of scope and in the guarantee narrowing below.

## Security

Trust boundary: the script runs under the caller's token, so the label is an
assertion, not authentication. Input validation runs before any network call.
Evidence flags pass through a byte-identical copy of `scripts/redact_secrets.py`
(default profile) before publication.

## Observability

What proves this works: the share of new issues carrying a SourceLabel, read by
the #5702 report.

## Acceptance criteria

1. When `--source` is absent or not `human`/`agent`, the script shall exit 2 before any subprocess call.
2. When `--source agent` is given and the body has no `## Step 0` block, the script shall exit 2 naming `--blocked-by` or `--signal` if either is missing, empty, or whitespace-only.
3. When any Step0Evidence answer contains a canonical hedge phrase, the script shall exit 2 naming the phrase and the field.
4. When the body carries a `## Step 0` block and `--blocked-by` or `--signal` is also given, the script shall exit 2 and create nothing.
5. When the body carries a `## Step 0` block, the script shall require non-empty, hedge-free `### Q3` and `### Q5` sections and preserve the body unchanged.
6. When `--labels` carries the other SourceLabel, the script shall exit 2; when it carries the same one, the script shall pass it once.
7. When evidence comes from flags, the script shall append `## Step 0`, `### Q3`, `### Q5` with the redacted answers.
8. The script shall pass the SourceLabel in the `gh issue create` call, after ensuring the label exists, so a label failure creates no issue.
9. The script shall run every validation above before resolving the repository or calling `gh`.
10. Every retained shipped caller of `new_issue.py` shall pass `--source`: the retrospective agent (six surfaces), the research skill, task-decomposer's tool note, and `scripts/ci/ruleset_context_drift.py`, which derives Q3 and Q5 from its own drift result.
11. `source:human` and `source:agent` shall exist in rjmurillo/ai-agents.

## Guarantee narrowing (epic correction)

The script is not a repository-wide admission gate. Direct creation paths on
`main` that bypass it, left unchanged by this issue: `scripts/ci/drift_create_alert_issue.py`
(drift-detection workflow), `scripts/ci/main_pytest_failure_alert.py` (REST
issues endpoint), `.claude/skills/quality-grades/scripts/check_grade_changes.py`,
`.github/workflows/ai-metrics-analysis.yml` (inline `gh issue create`), and the
GitHub MCP `issue_write` tool. Each is excluded, not wrapped: they file on
deterministic CI signals, and the repo-side labeler (parent AC-3) is the
owner-pending control for every door.

## Out of scope

Other `issue/` scripts; the Step 0 gate text; `set_issue_labels.py`; removing
the retrospective filing path (#5703); the labeler workflow and the
`<!-- source:human -->` marker (parent AC-3, owner decision pending); the
generator sweep (parent AC-6).

## Deferred

| Decision | Owner |
|---|---|
| Whether "human" means web form only or also session requests (parent Open question 3) | owner |
| Wrapping or labeling the excluded direct creation paths | owner |

## Open questions

None blocking this issue.

## CVA summary

Common: every caller creates one issue through one script. Varies: who selected
the work and where the evidence lives (flags or body). Relationship: evidence
is required only for `agent`, validated wherever it appears.

## Buy-vs-build decision

N/A (extends an existing script; no new capability class).

## Complexity classification

Tier 2 (one script, its callers, tests). Cynefin: Clear. Methodology: TDD.
