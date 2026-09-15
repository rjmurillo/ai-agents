# .claude/skills/

111 skills; 110 mirror into the Copilot CLI plugin via `generate_skills.py` (`merge-resolver` excluded, repo-specific).

## Matters

- `templates/skills/*.SKILL.md.tmpl` skills are template-owned (ADR-108): edit the template, regenerate, in the `rjmurillo/ai-agents` repository.
- `model:` normally omitted; the only other valid state is `model: haiku` plus `model-rationale:` (ADR-080). `sonnet`, `opus`, and versioned ids fail the model-pin check.
- Size: two blocking ceilings, lines (warn 300, block 500) and bytes (warn 12,288, block 24,576); a table-heavy skill passes lines, fails bytes. `size-exception: true` plus an HTML rationale comment (first 40 lines, 200+ chars) declares a justified overage.

## Entry points

- New skill: the `skillforge` skill creates and reviews it end to end.
- `SKILL.md` frontmatter: `name` (`^[a-z][a-z0-9-]*[a-z0-9]$|^[a-z]$`, no `--`, max 64, equals the directory name); `description` (5+ words, no `<` or `>`, 1024-char soft cap). Keys are allowlisted; an unlisted key hard-fails. `version` is unenforced by the commit gate, required by `claude-agents.md` MUST-2.
- `## Triggers` H2: 1 to 5 backtick-wrapped phrases (unwrapped counts as zero), no shell metacharacters; enforced at commit.
- `## Process` or `### Phase N`, plus one of `## Verification`, `## Success Criteria`, `## Checklist`.

## Where to look

| Path | Why |
|---|---|
| `<skill>/SKILL.md` | Frontmatter plus process, the contract |
| `<skill>/scripts/` | Executable code |
| `<skill>/references/` | Long-form material, loaded on demand |
| `<skill>/templates/` | Output-shape templates |

## Skip

- The generated Copilot CLI mirror of this tree: edit the source skill here and regenerate.

## Constraints

- Cross-harness hook/event/Copilot-artifact change: read `agent-harness-reference` first, route through `ai-agents-portability-campaign`.
- A retired ADR named in a skill's `metadata.adr` fails a portability gate.
- Subprocess text capture in a skill script: `encoding="utf-8", errors="replace"`. The count ratchet scans every tracked `*.py`, skill scripts included, and sits at its baseline; one new violation reds pre-push and CI.

## Dangerous assumptions

- `validate_skill_format.py` validates Serena-memory atomic format, not `SKILL.md`. `skillforge` validates `**/SKILL.md` at commit time.
- `version` looks top-level-only; `security-scan`, `skillforge`, `style-enforcement`, `validation-authority` nest it under `metadata:`, unrejected.
- The model-pin ratchet has drained: `model_pin_baseline.json` is `frozen_count: 0`, full ADR-080 enforcement in CI. The pre-push gate is warn-only; `pr-validation.yml` runs `--mode enforce`.
- Colocated tests are a forward-only ratchet (issue #4838), not zero: older tests remain under `<skill>/tests/`; new `test_*.py`/`*_test.py` there is blocked.

## Dependencies

- Pre-commit: `skillforge` (`**/SKILL.md`, excludes `evals/`) and `skill-size` checks; colocated-test fires on staged `<skill>/tests/**test*.py`, not `SKILL.md`.
- Pre-push: 10 `Skill*` gates (ADR bindings, template drift, script/markdown/markdown-exec portability, resolver anchoring, contract tests, shell detection, SKIP routing, memory references), plus `Colocated Skill Tests` and `Shipped Skill Routes`.
- CI: passive-compliance and frontmatter self-containment block; the description-budget step is `continue-on-error`, advisory. The agent/skill discriminator diffs the agent trees only, so a skill change never triggers it.

## Architecture

- New tests target `tests/skills/<name>/` (in the `rjmurillo/ai-agents` repository), inverting the repo norm.
- Pre-push `Skill*` gates are named individually; a failure names one gate.
- Schema authority: `claude-skills.md` (steering docs, in the `rjmurillo/ai-agents` repository); `claude-agents.md` MUST-2 binds it. Creation criteria: `SKILL-CREATION-CRITERIA.md`, `SKILL-AUTHORING.md`.

## Commands

Repository-only, run from the `rjmurillo/ai-agents` root:

```bash
uv run python scripts/validation/skill_size.py --staged-only --ci
uv run python scripts/validation/check_colocated_skill_tests.py --staged-only
uv run python scripts/validation/pre_pr.py
```
