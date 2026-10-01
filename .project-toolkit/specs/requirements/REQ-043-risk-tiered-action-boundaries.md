---
type: requirement
id: REQ-043
title: Enforce risk-tiered action boundaries for agent tools
status: implemented
priority: P1
category: security
source: issue-5767
related:
  - DESIGN-041
  - TASK-052
  - ADR-112
  - ADR-097
  - ADR-085
  - ADR-101
created: 2026-09-28
updated: 2026-09-28
author: spec
tags:
  - security
  - autonomy
  - least-privilege
  - v0.7.0
---

# REQ-043: Enforce risk-tiered action boundaries for agent tools

## Step 0 First Principles

### Q1 Demand Reality

Issue #5767, filed by rjmurillo as a child of epic #5456. The epic owner, the
security agent contract (`templates/agents/security.shared.md`), and the
`AGENTS.md` Never list all state limits that nothing enforces today.

### Q2 Status Quo

An agent reads the `AGENTS.md` line "Never: Force-push|No-verify" and the
Autonomy Guardrail line, then decides for itself. Claude Code's settings deny
only eight git config-injection flags. A force push, a `--no-verify` commit,
an `rm -rf`, a `gh repo delete`, or an admin merge runs with no check at agent
time.

### Q3 Desperate Specificity

The repository owner, who runs agents in `bypassPermissions` mode. In that
mode nothing prompts, so a prose-only "ask first" rule is the only barrier
between a mistaken agent and an irreversible action.

### Q4 Narrowest Wedge

About six hours: deny rules in `templates/hooks/settings.tmpl` with matcher
tests, pinned-target and readback checks in `merge_pr.py`, read-only grants
for the two agents whose own contract says read-only, and one ADR that owns
the tier contract and its gap table.

### Q5 Observation

- `.claude/settings.json` `permissions.deny` holds 8 rules, all git config
  injection (measured at `8050657d6`).
- 29 of 31 Claude agents carry no `tools:` key and inherit every tool
  (`grep -L "^tools:" .claude/agents/*.md`).
- `templates/agents/code-reviewer.shared.md:99` admits the read-only promise
  holds on three harnesses, not Claude.
- `merge_pr.py` reports `merged` on a zero exit without reading the PR back,
  and does not pin the head SHA it checked.

### Q6 Future-fit

Yes. Deny rules cost nothing per call and scale with no spawn. The tier
contract names one owner, so a new tool maps to a tier instead of adding a
new policy file.

## Prior Art / Constraints

- ADR-097 retired every tool-use hook. `.claude/rules/tool-use-hook-bar.md`
  MUST 2 requires a host-native declarative surface first. `permissions.deny`
  is that surface.
- `tests/test_security_agent_git_write_guard.py` already models the Claude
  deny matcher and pins that plain `git commit` and `git push` stay allowed.
- `.github/scripts/safe_push_pr_branch.py` already does pinned-lease push,
  porcelain check, `ls-remote` readback, and an audit record.
- `scripts/validation/git_hook_policy.py` blocks force push at pre-push.
- ADR-085 Decision 1: Copilot has no committed permission surface.

## Problem statement

Consequential agent actions are held back by prose alone. The repository
needs deny-first enforcement for the highest tier, deterministic checks for
shared-repository mutations, and an honest record of what stays advisory.

## User stories

1. As the owner, I want a force push, hook bypass, or destructive `gh` call
   from an agent denied at the harness, so a mistaken agent cannot run it.
2. As an agent running `merge_pr.py`, I want the merge pinned to the head SHA
   I reviewed and read back afterward, so a moved branch or a silent failure
   is never reported as merged.
3. As a reviewer, I want one document that says which controls the harness
   enforces and which are advice, so I do not assume protection that is absent.

## Ontology

- **ActionTier**: one of `read-only`, `reversible-local`, `shared-repository`,
  `consequential`.
- **Control**: a mechanism that enforces or advises on an ActionTier. Has a
  plane (harness, script, git hook, CI, server) and a kind (enforced, advisory).
- **Grant**: the tool set an agent holds on one harness.
- **AuditRecord**: actor, target, action, approval, result, residual risk.
- Decision rule: a consequential action with no human approval is denied.
  Approval means the human runs it (the `!` prefix or their own shell).

## Data model

- `AuditRecord` (merge): `actor` (GitHub login from readback), `target`
  (`repo`, `pull_request`, `head_sha`), `action`, `approval`, `result`,
  `rollback`, `residual_risk`. Emitted inside the skill envelope `Data`.

## Integrations

- Claude Code `permissions.deny` (deny evaluated before ask and allow, and
  honored in `bypassPermissions` mode).
- GitHub CLI `gh pr merge --match-head-commit`, `gh pr view --json`.

## Failure modes

| Failure | Handling |
|---|---|
| Head moved after review | `--match-head-commit` refuses; exit 6 with a stale-target message |
| Wrong PR number | Pre-check of `--expected-head-sha` fails; exit 1 (when the caller passes it; `pr-autofix` does) |
| Merge command fails but PR merged | Readback wins; report `merged`, `recovered: true` |
| Merge command succeeds but PR not merged | Report queued only with a queue or auto-merge entry; else exit 3 |
| Retry after success | Already-merged path returns `action: none`; no second merge |
| Merge command times out | Treat as unknown; readback decides |
| Readback query fails | Exit 3; never claim success |

## Security

- Trust boundary: the agent is untrusted for consequential actions; the
  harness deny list and GitHub branch protection are the enforcement.
- Threats: prompt injection asking for force push, secret reads through
  `gh auth token`, admin merge past review, remote deletion.
- Residual risk: deny rules match command text only. Recorded as gaps in
  ADR-112, not claimed closed.

## Observability

The merge audit record in the skill envelope is the proof. Metric: every
`merge_pr.py` success envelope carries `readback.state`.

## Acceptance criteria

1. The system shall list every autonomy, grant, hook, security, and generated
   control in ADR-112 with its plane and kind, and name ADR-112 the owner.
2. The system shall map all 31 Claude agents and the shared toolsets to an
   ActionTier with a keep or remove disposition and reason.
3. When an agent runs a consequential command in the ADR-112 deny set, the
   harness shall deny it, and a test shall prove each rule matches its
   exploit and spares its legitimate neighbor.
4. When `merge_pr.py` receives `--expected-head-sha` and the PR head differs,
   the script shall exit non-zero without calling `gh pr merge`.
5. When `merge_pr.py` merges, the script shall pass `--match-head-commit` and
   read the PR back before it reports a result.
6. If the merge command fails and readback shows `MERGED`, then the script
   shall report the merge as recovered, not as a failure.
7. If the merge command succeeds and readback shows neither `MERGED` nor a
   queue or auto-merge entry, then the script shall exit 3.
8. When a PR is already merged, the script shall make no merge call.
9. The `code-reviewer` and `comment-analyzer` Claude grants shall hold no
   Bash, Edit, Write, or NotebookEdit tool.
10. ADR-112 shall state which controls are harness-enforced and which are
    advisory, and list each open enforcement gap.
11. The change shall not grow `AGENTS.md`; the guardrail line shall point to
    ADR-112 at equal or smaller size.

## Out of scope

- A new PreToolUse hook (ADR-097 bar not cleared).
- A Copilot permission surface (none exists, ADR-085).
- An IAM or deployment platform.
- Scoping the 27 remaining broad Claude grants without measured task data.

## Deferred

- Per-agent Bash scoping on Claude: needs a subagent permission surface that
  Claude Code does not offer. Owner: rjmurillo.

## Open questions

None blocking.

## CVA summary

Common: every tier needs a precondition, an approval rule, evidence, and a
readback. Varies: the plane that enforces it (harness deny, script check,
git hook, server rule). Relationship: the highest tier gets the cheapest
deny-first plane; the shared tier gets script checks because only a script
sees both the intent and the result.

## Buy-vs-build decision

Context, not core. Alternatives: Claude Code `permissions.deny` (buy, used),
a PreToolUse hook (rejected, ADR-097), GitHub rulesets (buy, already in
place server-side). Recommendation: buy the host surfaces, build only the
merge readback, which no host surface provides.

## Complexity classification

Tier 3. Domain: Complicated. Methodology: analyze, then build in slices.

## ADR cross-reference

ADR-112 (`.project-toolkit/architecture/ADR-112-risk-tiered-action-boundaries.md`).
