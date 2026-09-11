# .claude/skills/

111 skills. `SKILL.md` is the contract; code under `scripts/`, long reference under `references/`,
output shapes under `templates/`. Skills are the only user-invocable surface (ADR-064;
`.claude/commands/` is refused by `check_commands_retired.py`). Mirrored to
`src/copilot-cli/skills/` by `build/scripts/generate_skills.py`; never edit the mirror.
Rules firing here: `claude-agents.md`, `plugin-self-containment.md`, `generated-artifacts.md`, `ci-scripts.md`.

Before a skill that configures, generates, or tests Claude Code or Copilot CLI artifacts: read
`agent-harness-reference`; cross-harness mutations go through `ai-agents-portability-campaign`.

## SKILL.md contract

- Frontmatter on line 1: `name` (`^[a-z0-9-]{1,64}$`), `version`, `description` (max 1024 chars; 3-5 backtick-wrapped trigger phrases; a "Do NOT use ... (use X)" discriminator), `license`. `version` and `model` are top-level, never under `metadata:`.
- `model:` omitted (harness default). Only `model: haiku` plus `model-rationale:` is allowed (ADR-080); versioned ids fail `check_model_pins.py`.
- Size: warn at 300 lines, block at 500 (`scripts/validation/skill_size.py`); `size-exception: true` declares a justified overage.
- Process section heading is `## Process` or `### Phase N`.
- Documented script + exit code = executable contract; a test under `tests/` must assert it (`check_skill_contract_tests.py`).
- In-root executables: `"${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/<name>/scripts/<file>"`, never bare `.claude/skills/...` (`check_skill_md_exec_portability.py`, `check_plugin_frontmatter_self_containment.py`).
- Upstream-only paths (`.agents/`, `build/`, `scripts/`) need a `vendor-portability` declaration (`check_skill_md_portability.py`, `check_vendor_portability.py`); say "in the `rjmurillo/ai-agents` repository".
- Retired ADR in `metadata.adr` fails `check_skill_adr_bindings.py`.
- Scripts: Python (ADR-042), exit codes ADR-035, subprocess `encoding="utf-8", errors="replace"`, resolver anchored on `git rev-parse --show-toplevel` (`check_skill_resolver_anchoring.py`).

## Tests

`tests/skills/<name>/` only. New files under `.claude/skills/<name>/tests/` are blocked
(`check_colocated_skill_tests.py`, #4838): colocated tests ship to consumers.

## Gates

Pre-commit `skillforge`, `skill-size`, `colocated-skill-tests`; pre-push `pre_pr.py` Skill* gates
(`validate_skill_format.py --staged-only --ci`, ADR bindings, skip clauses, memory references,
resolver anchoring, shells); CI `agent-skill-discriminator-check.yml`, `skill-passive-compliance.yml`,
`scripts/skill_description_budget.py`.

## Authoring

`skillforge` skill creates and reviews. Schema authority: `.agents/steering/claude-skills.md`.
Criteria: `.agents/governance/SKILL-CREATION-CRITERIA.md`, `docs/SKILL-AUTHORING.md`.
New capability: buy-vs-build quick pass before `/spec` (root `AGENTS.md`).
