# .claude/skills/

111 skills; 110 mirror into the Copilot CLI plugin by `generate_skills.py` (`merge-resolver` excluded by name as repo-specific, issue #2026).

## Matters

- `templates/skills/*.SKILL.md.tmpl` skills are template-owned (ADR-108); edit the template, regenerate, in the `rjmurillo/ai-agents` repository.
- `model:` normally omitted; the only other valid state is `model: haiku` plus `model-rationale:` (ADR-080), the one alias priced below the `claude-sonnet-4-6` default. `sonnet`, `opus`, and any versioned id fail the model-pin check.
- Size: two independent blocking ceilings, lines (warn 300, block 500) and bytes (warn 12,288, block 24,576); a table-heavy skill can pass lines and fail bytes. `size-exception: true` plus an HTML rationale comment (first 40 lines, 200+ chars) declares a justified overage.

## Entry points

- New skill: the `skillforge` skill creates and reviews it end to end.
- `SKILL.md` frontmatter line 1: `name` (`^[a-z][a-z0-9-]*[a-z0-9]$|^[a-z]$`, no `--`, max 64, must equal the directory name); `description` (5+ words, no `<` or `>`, 1024 chars soft cap). Frontmatter keys are allowlisted; an unlisted key hard-fails. `license` optional; `version` is unenforced by the commit gate but required by `claude-agents.md` MUST-2 and the schema authority in Architecture.
- Trigger phrases: `## Triggers` H2, 1 to 5 backtick-wrapped (unwrapped counts as zero), no shell metacharacters; enforced at commit time.
- Process heading: `## Process` or `### Phase N`; one of `## Verification`, `## Success Criteria`, `## Checklist` also required.

## Where to look

| Path | Why |
|---|---|
| `<skill>/SKILL.md` | Frontmatter plus process, the contract |
| `<skill>/scripts/` | Executable code |
| `<skill>/references/` | Long-form material, loaded on demand |
| `<skill>/templates/` | Output-shape templates |
| `tests/skills/<name>/` (in the `rjmurillo/ai-agents` repository) | New tests target here (see Architecture) |

## Skip

- The generated Copilot CLI mirror of this tree: edit the source skill here and regenerate, never the mirror.
- `<skill>/tests/`: new `test_*.py`/`*_test.py` blocked (see Architecture).

## Constraints

- Cross-harness hook/event/Copilot-artifact change: read `agent-harness-reference` first, route through `ai-agents-portability-campaign`.
- A retired ADR named in a skill's `metadata.adr` fails a portability gate (issue #5665).
- Subprocess text capture in a skill script: `encoding="utf-8", errors="replace"`. Blocking, not convention: the count ratchet scans every tracked `*.py`, skill scripts included, and sits exactly at its baseline, so one new violation reds pre-push and CI.

## Dangerous assumptions

- `validate_skill_format.py` (in the `rjmurillo/ai-agents` repository) validates Serena-memory atomic format, not `SKILL.md`. `skillforge` validates `**/SKILL.md` at commit time.
- `version` looks top-level-only; `security-scan`, `skillforge`, `style-enforcement`, `validation-authority` nest it only under `metadata:`, unrejected.
- The model-pin ratchet has drained: `model_pin_baseline.json` is `frozen_count: 0`, so for skills it is full ADR-080 enforcement in CI, not a lenient ratchet. The pre-push gate is warn-only; `pr-validation.yml` runs `--mode enforce`.

## Dependencies

- Pre-commit: `skillforge` (`**/SKILL.md`, excludes `evals/`) and `skill-size` (`**/SKILL.md`) checks; colocated-test fires on staged `<skill>/tests/**test*.py`, not `SKILL.md`.
- Pre-push: 10 `Skill*` gates (ADR bindings, template drift, script/markdown/markdown-exec portability, resolver anchoring, contract tests, shell detection, SKIP routing, memory references), plus `Colocated Skill Tests` and `Shipped Skill Routes`.
- CI: passive-compliance and frontmatter self-containment (desc/name, zero-tolerance) block; the description-budget step is `continue-on-error`, advisory only. The agent/skill discriminator diffs the agent trees only (`.claude/agents` and the agent templates), so a skill change never triggers it.

## Architecture

- Tests invert the repo norm: new tests target `tests/skills/<name>/` (in the `rjmurillo/ai-agents` repository), forward-only ratchet (issue #4838); older tests remain colocated under `<skill>/tests/`.
- Pre-push `Skill*` gates are named individually; a failure names one gate, not "skills failed."
- Schema authority: `claude-skills.md` (steering docs, in the `rjmurillo/ai-agents` repository); `claude-agents.md` MUST-2 binds it. Creation criteria: `SKILL-CREATION-CRITERIA.md` (governance), `SKILL-AUTHORING.md` (docs).

## Commands

Repository-only, run from the `rjmurillo/ai-agents` root (not part of the shipped plugin):

```bash
uv run python scripts/validation/skill_size.py --staged-only --ci
uv run python scripts/validation/check_colocated_skill_tests.py --staged-only
uv run python scripts/validation/pre_pr.py
```
