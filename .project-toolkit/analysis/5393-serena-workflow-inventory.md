# Issue #5393 Serena workflow inventory

Migration inventory for issue #5393, produced on 2026-09-21 against `main` at
`8867edb35`. Classes follow the placement contract in
`.claude/rules/knowledge-persistence.md`: rule, skill, agent, memory, delete.
Issue #5392 already moved cross-cutting normative content to rules, so rows
below mark leftover normative text as `rule-residual` and hand it to the
downstream Serena thinning issue instead of re-deciding it here.

No row adds capability, ownership, or dependency metadata; issue #5396 owns
that mechanism.

## agent-workflow family (13 files, each resolved)

| Serena source | Classification | Existing destination | Action | Residual memory |
|---|---|---|---|---|
| `agent-workflow/agent-workflow-pipeline.md` | skill + agent | `autoplan` tier table; orchestrator Routing Algorithm step 4 | extend orchestrator (critic plan gate) | keep-thinned |
| `agent-workflow/agent-workflow-critic-gate.md` | skill + agent | `plan` step 7; critic Review Axes | extend orchestrator step 4; fix critic handoff route | keep-thinned |
| `agent-workflow/agent-workflow-post-implementation-critic-validation.md` | skill | `build` exit gates; `review` | none (already owned) | keep-thinned |
| `agent-workflow/agentworkflow-005-structured-handoff-formats-88.md` | agent | orchestrator Handoff Contract; role `## Handoff` sections | none (already owned) | keep-thinned |
| `agent-workflow/agentworkflow-004-proactive-template-sync-verification-95.md` | delete | `.claude/rules/generated-artifacts.md`, `build_all.py --check` | delete (pre-ADR-109 layout) | delete |
| `agent-workflow/agent-generation-edit-locations.md` | delete | `.claude/rules/generated-artifacts.md` (ADR-109 B1) | delete (states generated files are hand-maintained) | delete |
| `agent-workflow/agent-workflow-collaboration.md` | skill | `reflect` | none (already owned) | keep-thinned |
| `agent-workflow/agent-workflow-observations.md` | memory | `AGENTS.md` routing owns model selection | drop empty Constraints scaffolding | keep-thinned |
| `agent-workflow/agentskills-io-standard-integration.md` | memory (external reference) | `skillforge` owns skill authoring | none | unchanged |
| `agent-workflow/fleet-worktree-live-versus-abandoned.md` | skill + memory | `git-advanced-workflows` | extend skill with `references/worktree-triage.md` | keep-thinned (measurements) |
| `agent-workflow/agent-workflow-atomic-commits.md` | memory (#5392) | Universal Rules | none | unchanged |
| `agent-workflow/agent-workflow-mvp-shipping.md` | memory (#5392) | builder-ethos, Universal Rules | none | unchanged |
| `agent-workflow/agent-workflow-scope-discipline.md` | memory (#5392) | Universal Rules | none | unchanged |

## autonomous family (6 files, each classified)

All six carry the `placement: evidence` marker from #5392 and name their
owner in a Migration disposition section. No file in this family holds a
workflow-specific procedure that a skill lacks.

| Serena source | Classification | Existing destination | Action | Residual memory |
|---|---|---|---|---|
| `autonomous/autonomous-execution-guardrails.md` | memory (rule content moved by #5392) | Universal Rules "Autonomous execution boundaries"; `ship`, `review` | none | unchanged |
| `autonomous/autonomous-circuit-breaker.md` | memory | Universal Rules (three failed attempts); #5404 terminal semantics | none | unchanged |
| `autonomous/autonomous-circuit-breaker-pattern.md` | memory | Universal Rules; `plan` and `ship` handoff format | none | unchanged |
| `autonomous/autonomous-execution-failures-pr760.md` | memory | Universal Rules; `security-review`, `ship` | none | unchanged |
| `autonomous/autonomous-patch-signal.md` | memory | Universal Rules (user-supplied patch) | none | unchanged |
| `autonomous/autonomous-trust-metric.md` | memory | #5400 measurement, #5405 reporting | none | unchanged |

## skills-*-index families (34 indexes, 380 memories)

Family-level evaluation. Each row cites a file the auditor opened. `already-owned: thin downstream` means an existing skill, agent, or rule carries the procedure and the memory can shrink to evidence in the downstream Serena thinning issue. `extract` names a procedure with no current owner; each is a candidate for that issue or for the owner named, not a new skill created here.

| Family | Rows | Dominant class | Existing owner | Recommended action | Evidence |
|---|---|---|---|---|---|
| agent-workflow | 9 | skill/agent (resolved above, per file) | orchestrator, critic, `plan`, `build`, `review`, `reflect`, `git-advanced-workflows`, `autoplan` | done in this PR: 7 thinned, 2 deleted, 4 unchanged | per-file table above |
| autonomous-execution | 4 | evidence (#5392) | Universal Rules | evidence: keep | per-file table above; 6 files, 4 indexed |
| analysis | 6 | evidence | universal.md MUST-9 (partial) | already-owned: thin downstream | analysis-004-verify-codebase-state.md matches universal.md "MUST NOT assert an absence from a single probe" |
| architecture | 15 | rule-residual/evidence | .project-toolkit/architecture/ADR-0003, ADR-062 | already-owned: thin downstream | architecture-001-rolespecific-tool-allocation-92.md cites ADR-0003 directly |
| bash-integration | 3 | rule-residual | powershell.md, testing.md (partial) | extract: fold PS script-scope exit-vs-return contract into powershell.md | bash-integration-exit-codes.md not found verbatim in powershell.md or testing.md:25 |
| ci-infrastructure | 23 | evidence/rule-residual | ai-agents-debugging-playbook, ai-agents-diagnostics-toolkit | already-owned: thin downstream | debugging-playbook description covers "drift gate reds, hook exit 143" matching ci-infrastructure family |
| coderabbit | 6 | rule-residual (config) / evidence (triage) | pr-comment-responder (triage only, partial) | extract: CodeRabbit noise-tuning config (profile/path_instructions/markdownlint) uncovered | pr-comment-responder/SKILL.md:80-98 covers bot-priority triage, not config-strategy.md content |
| copilot | 13 | rule-residual/evidence | ADR-044, ADR-094, agent-harness-reference | already-owned: thin downstream | copilot-cli-frontmatter-regression-runbook.md cites ADR-044/ADR-094 explicitly |
| decision | 42 | evidence | .project-toolkit/architecture/ADR-* (per-entry) | already-owned: thin downstream | decision-adr-085-permission-surface-asymmetry.md maps to ADR-085-cross-harness-permission-surface-asymmetry.md |
| design | 8 | rule-residual | none found (searched: claude-agents.md, agent-harness-reference) | extract: agent/skill authoring norms (non-overlap, entry criteria, composability, interface, diagrams) | grep of claude-agents.md and agent-harness-reference/SKILL.md for "specializ|entry criteria|composab" returned no matches |
| documentation | 10 | rule-residual/skill | ai-agents-docs-of-record | already-owned: thin downstream | ai-agents-docs-of-record description covers "naming rules, house prose style" matching documentation-user-facing.md |
| gemini | 6 | skill (config reference) | none found (searched: .claude/skills/*/SKILL.md, .claude/rules/*.md, .claude/agents/*.md) | extract: Gemini Code Assist config reference (config.yaml schema, styleguide, path exclusions, enterprise config) | grep -rliE gemini across skills/rules/agents hit only ai-agents-validation-and-qa and benchmark-models (tangential) |
| gh-extensions | 11 | skill | .claude/skills/github/EXTENSIONS.md | already-owned: thin downstream | EXTENSIONS.md:1-20 lists identical gh-notify/gh-metrics/gh-milestone/gh-hook rows |
| git-hooks | 11 | skill | ai-agents-build-and-env (install), ai-agents-debugging-playbook (triage) | already-owned: thin downstream | ai-agents-build-and-env/SKILL.md:78-100 covers lefthook install/check-install mechanics |
| git | 21 | skill | git-advanced-workflows | already-owned: thin downstream | git-advanced-workflows/SKILL.md:105-115 covers worktree add/remove/prune, matching git-index worktree rows |
| github-cli | 16 | skill | .claude/skills/github/SKILL.md | already-owned: thin downstream | github/SKILL.md:4 description covers PRs, issues, milestones, labels, CI checks |
| graphql | 4 | skill | .claude/skills/github/scripts (gh_graphql usage) | already-owned: thin downstream | add_pr_review_thread_reply.py:48,132,224 use gh_graphql for thread reply/resolve |
| implementation | 9 | skill | build (test-first/TDD portion) | already-owned: thin downstream | build/SKILL.md:92 "Write the failing test first...TDD" matches implementation-002-testdriven-implementation-92.md |
| jq | 12 | skill | .claude/skills/github/references/patterns.md | already-owned: thin downstream | patterns.md:51-113 shows jq -r usage on thread/merge-readiness JSON, matching jq-github-cli-integration.md |
| labeler | 6 | evidence | none found (searched: labeler, .github/labeler.yml config only) | evidence: keep | labeler-001-negation-pattern-matcher-selection.md:1-9, PR #226/#229 incident |
| linting | 5 | evidence | .claude/skills/fix-markdown-fences/SKILL.md (fence subset only) | already-owned: thin downstream for fence rows / evidence: keep rest | linting-autofix.md:1-13, markdownlint-cli2 workflow, no full-linting skill found |
| orchestration | 10 | mixed skill-residual/evidence | .claude/agents/orchestrator.md, .claude/skills/autoplan/SKILL.md | already-owned: thin downstream / stale: delete validation-gate row | orchestration-validation-gate.md:3 requires a Session End checklist that session-logs.md:9 retired |
| pester-testing | 5 | rule-residual | .claude/rules/testing.md:19, .claude/rules/powershell.md:57 | already-owned: thin downstream | testing.md:19 "Pester 5.7.1+"; powershell.md:57 BeforeAll guidance duplicates pester-testing-discovery-phase.md |
| planning | 6 | mixed skill/evidence | .claude/skills/plan/SKILL.md, .claude/skills/execution-plans/SKILL.md | already-owned: thin downstream | planning-004 approval-checkpoint threshold overlaps plan skill's milestone gating |
| powershell | 9 | rule-residual | .claude/rules/powershell.md | already-owned: thin downstream | powershell.md:66-68 array-coercion rule duplicates powershell-array-handling.md |
| pr-review | 31 | skill-residual | .claude/skills/pr-review/SKILL.md, .claude/skills/pr-comment-responder/SKILL.md, .claude/skills/github/SKILL.md | already-owned: thin downstream | pr-review-core-workflow.md:5 conversation-resolution requirement matches pr-review SKILL.md description verbatim |
| protocol | 8 | rule-residual/evidence | Universal Rules and lefthook gates (verification over trust); .claude/skills/checkpoint/SKILL.md | already-owned: thin downstream | protocol-blocking-gates.md:3 states the verification-gate principle that lefthook.yml jobs now enforce deterministically |
| quality | 9 | skill-residual | .claude/skills/pr-quality-all/SKILL.md, .claude/skills/code-qualities-assessment/SKILL.md | already-owned: thin downstream | quality-shift-left-gate.md:3 "6 specialized agents pre-push" matches pr-quality-all's 6 axis agents |
| retrospective | 9 | evidence (skill-generated) | .claude/skills/retrospective/SKILL.md, .claude/agents/skillbook.md | already-owned: thin downstream | retrospective SKILL.md description "scores atomicity" matches retrospective-*.md Atomicity fields exactly |
| security | 14 | skill-residual | .claude/skills/security-review/SKILL.md, .claude/skills/security-scan/SKILL.md, .claude/skills/threat-modeling/SKILL.md, .claude/skills/security-detection/SKILL.md | already-owned: thin downstream | security-no-blind-suppression.md content overlaps security-review's CWE/CVE verdict scope |
| session-init | 7 | rule-residual, partly stale | AGENTS.md, .claude/rules/universal.md, .claude/rules/session-logs.md | stale: delete session-log rows (branch declaration, todo-in-evidence) / already-owned: thin rest | session/session-init-003-branch-declaration.md and session/session-writing-todo-in-evidence-trips-the-contradiction-scanner.md describe session-log mechanics; session-logs.md:9 "Session log creation is discontinued" |
| utilities | 7 | mixed evidence/skill-residual | .claude/skills/fix-markdown-fences/SKILL.md, .claude/skills/cva-analysis/SKILL.md, .claude/skills/security-scan/SKILL.md | already-owned: thin markdown-fences/cva/security rows / evidence: keep regex, pathinfo, scratch-script rows | utilities-markdown-fences.md title matches fix-markdown-fences SKILL.md name; utilities-cva-refactoring.md matches cva-analysis SKILL.md |
| validation | 17 | skill/script-residual | scripts/validation/*.py (60+ validators), .claude/skills/validation-authority/SKILL.md, .claude/skills/pipeline-validator/SKILL.md | already-owned: thin downstream | validation-domain-index-format.md describes the very format check_* validators in scripts/validation/ enforce |
| workflow-patterns | 8 | evidence/skill-residual | .claude/agents/devops.md, .claude/skills/security-scan/SKILL.md | already-owned: thin shell-safety row to security-scan / evidence: keep rest | workflow-patterns-shell-safety.md:3 "never interpolate user content" duplicates security-scan's CWE-78 scope |

### Extraction candidates handed downstream

Four families carry content with no current first-class owner. None is
created in this issue; each needs its own buy-versus-reuse check first.

| Candidate | Suggested owner | Why not here |
|---|---|---|
| `bash-integration` exit-versus-return contract for PowerShell scripts | `templates/rules/powershell.md` | cross-cutting normative; rule class belongs to the #5392 owner |
| `coderabbit` noise-tuning configuration reference | `pr-comment-responder` references, or a config reference under the `github` skill | vendor configuration, needs a reuse check against `.coderabbit.yaml` |
| `design` agent and skill authoring norms | `skillforge`, `templates/AGENTS.md`, or `.claude/rules/claude-agents.md` | authoring policy overlaps #5397 quality semantics |
| `gemini` Code Assist configuration reference | none found; candidate `references/` file under an existing review skill | vendor configuration with no consumer in `.claude/skills` today |

### Stale rows handed downstream

`orchestration/orchestration-validation-gate.md`,
`session/session-init-003-branch-declaration.md`, and
`session/session-writing-todo-in-evidence-trips-the-contradiction-scanner.md`
describe session-log mechanics that `.claude/rules/session-logs.md` retired
("Session log creation is discontinued", line 9). They are delete candidates
for the thinning issue.
