# AGENTS

Memory|recall: `memory-search`|change: `memory-gate`|retain: `memory`|use a scoped project tool or repository files|this repo: `.serena/memories/`|verify recalled facts|no secrets
Serena code navigation|initialize once when available|active at start with `.mcp.json --project`|code: lsp-first (`using-serena-symbols`)|use local code search otherwise
Knowledge -> context|C7/DW/Web|mem|constraints gov|ADRs arch|skills/rules .claude|generators gov
Gates|S init/handoff/resume/memory/git|P `pre_pr.py`/no BLOCKING/security/style|E handoff/memory/lint/commit/check
**Always**: Python ADR-042|branch/skills/PR/lint|SHA Actions|workflows|No manifest version (ADR-092)|skill/agent->page or Docs-Reviewed
**Ask First**: architecture/ADR/breaking/security
**Autonomy Guardrail**: tiers ADR-112|irreversible->human|ambiguous minimal+flag
**Never**: Secrets|New bash scripts|YAML logic|Raw `gh`|Force-push|No-verify|Internal refs|Scratch
Setup|one command: `CONTRIBUTING.md` Setup Steps|non-root only
Disk|wt: `~/worktrees/<repo>/<branch>`|scratch: wt `.project-toolkit/scratch/`|done: remove wt+branch
Drive-by|default no|tidy in edited code: same PR, own commit, in body|needed for correctness: same PR|confirmed defect: own PR+proof if authorized|taste: never, no issue|no chains|stop when proven|`avoiding-manufactured-work`
Block|artifact->test|security->fix/owner|conflict->resolve|validation->pre-PR
Skills|route autoplan|no skill -> autoplan|multi -> orchestrator|conflict -> GitHub/merge-resolver|CI ladder|new cap buy-vs-build|agent-harness-reference|ai-agents-portability-campaign|ADR review: debate log required for any non-frontmatter ADR edit; full panel only when the change touches executable enforcement or a rule other gates read, else reduced panel (architect+critic)
