# AGENTS

Memory|recall: `memory-search`|change: `memory-gate`|retain: `memory`|scoped tools or repo files|repo: `.serena/memories/`|verify recalled facts|no secrets
Serena|init once if available|`.mcp.json --project` activates at start|LSP first (`using-serena-symbols`), else local search
Knowledge -> context|C7/DW/Web|mem|constraints gov|ADRs arch|skills/rules .claude|generators gov
Gates|S init/handoff/resume/memory/git|P `pre_pr.py`/no BLOCKING/security/style|E handoff/memory/lint/commit/check
**Always**: Python ADR-042|branch/skills/PR/lint|SHA Actions|workflows|No manifest version (ADR-092)|skill/agent->page or Docs-Reviewed
**Ask First**: architecture/ADR/breaking/security
**Autonomy Guardrail**: tiers ADR-112|irreversible->human|ambiguous minimal+flag
**Never**: Secrets|New bash scripts|YAML logic|Raw `gh`|Force-push|No-verify|Internal refs|Scratch
Setup|one command: `CONTRIBUTING.md` Setup Steps|non-root only
Disk|wt: `~/worktrees/<repo>/<branch>`|scratch: wt `.project-toolkit/scratch/`|done: remove wt+branch
Drive-by|default no|`avoiding-manufactured-work`
Block|artifact->test|security->fix/owner|conflict->resolve|validation->pre-PR
Skills|route autoplan|no skill -> autoplan|multi -> orchestrator|conflict -> GitHub/merge-resolver|CI ladder|new cap buy-vs-build|agent-harness-reference|ai-agents-portability-campaign|ADR review: log non-frontmatter edits; full panel for executable enforcement or rules gates read, else architect+critic
