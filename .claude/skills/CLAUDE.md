# .claude/skills/

111 skills; every `SKILL.md` is generated, nearly every other file hand-maintained.

## Matters

- `SKILL.md` renders from `templates/skills/<name>.SKILL.md.tmpl` plus `partials/*.mustache`, all 111: edit the template and regenerate, in the `rjmurillo/ai-agents` repository. Render map: `templates/AGENTS.md`.
- `<skill>/scripts/`, `references/`, `templates/`, `tests/` stay hand-edited, except `review/scripts/validate_review_marker.py` (synced from `scripts/validation/`). `review/references/*.md` is hand-edited but sources the PR-quality prompts; regenerate after editing (`build_all` skips it).
- `model:` usually absent; the other valid state is `model: haiku` plus `model-rationale:` (ADR-080). `sonnet` and `opus` need a rationale pricing below the harness default; versioned ids always fail. The local gate warns; `pr-validation.yml` runs `--mode enforce`.
- Size: two blocking ceilings, lines (warn 300, block 500) and bytes (warn 12,288, block 24,576). `size-exception: true` plus an HTML rationale comment (first 40 lines, 200+ chars) declares a justified overage.

## Entry points

- New skill: `skillforge` creates and reviews it.
- Frontmatter: `name` (`^[a-z][a-z0-9-]*[a-z0-9]$|^[a-z]$`, no `--`, max 64, equals the directory name); `description` (5+ words, no `<` or `>`, 1024-char soft cap). Keys are allowlisted; an unlisted key hard-fails. `version` is unenforced at commit, required by `claude-agents.md` MUST-2.
- `## Triggers` H2: 1 to 5 backtick-wrapped phrases (unwrapped counts as zero), no shell metacharacters.
- `## Process` or `### Phase N`, plus one of `## Verification`, `## Success Criteria`, `## Checklist`.

## Where to look

| Path | Why |
|---|---|
| `<skill>/SKILL.md` | Generated; the contract |

## Skip

- The Copilot CLI mirror and `src/claude/skills/`: both regenerate.

## Constraints

- Cross-harness hook/event/Copilot-artifact change: read `agent-harness-reference` first, route through `ai-agents-portability-campaign`.
- A retired ADR in a skill's `metadata.adr` fails the `Skill ADR Bindings` ratchet.
- Skill-script subprocess text capture: `encoding="utf-8", errors="replace"`; count ratchet at baseline.
- 110 of 111 ship to the Copilot CLI plugin; `merge-resolver` is excluded as repo-specific, and no shipped routing table may point at it.

## Dangerous assumptions

- `validate_skill_format.py` validates Serena-memory atomic format, not `SKILL.md`. `skillforge` validates `**/SKILL.md` at commit.
- `version` looks top-level-only; five skills nest it under `metadata:`, four with no top-level key, unrejected.
- Colocated tests are a forward-only ratchet, not zero: 55 remain under `<skill>/tests/`; a new `test_*.py`/`*_test.py` there is blocked.

## Dependencies

- Pre-commit: `skillforge` and `skill-size`; colocated-test fires on staged `<skill>/tests/**test*.py`, not `SKILL.md`.
- Pre-push: 10 `Skill*` gates (ADR bindings, template drift, script/markdown/markdown-exec portability, resolver anchoring, contract tests, shell detection, SKIP routing, memory references), plus `Colocated Skill Tests` and `Shipped Skill Routes`.
- CI: passive-compliance and plugin frontmatter self-containment block; description-budget advisory.

## Architecture

- New tests target `tests/skills/<name>/`, in the `rjmurillo/ai-agents` repository.
- Schema authority: `claude-skills.md` under the steering docs in the `rjmurillo/ai-agents` repository; `claude-agents.md` MUST-2 binds it. Creation criteria: `SKILL-CREATION-CRITERIA.md`, `SKILL-AUTHORING.md`.

## Commands

Repository-only, from the `rjmurillo/ai-agents` root:

```bash
uv run python scripts/validation/skill_size.py --staged-only --ci
uv run python scripts/validation/check_colocated_skill_tests.py --staged-only
uv run python scripts/validation/pre_pr.py
```
