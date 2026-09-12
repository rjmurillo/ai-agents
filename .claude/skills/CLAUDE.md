# .claude/skills/

111 skills; the single user-invocable surface in this repository (ADR-064). Consumed directly by Claude Code and, mirrored, by the Copilot CLI plugin.

## Matters

- `SKILL.md` is the contract per skill; `scripts/` holds executable code, `references/` long-form material, `templates/` output shapes, all optional.
- Skills are the only user-invocable surface (ADR-064); a commands directory under any plugin root is refused by a blocking validator.
- Mirrored to the Copilot CLI plugin by `generate_skills.py`; never hand-edit the mirror, edit the source skill and regenerate.
- Skills with a template under `templates/skills/` are template-owned (ADR-108): edit `templates/skills/<name>.SKILL.md.tmpl`, not `SKILL.md`. That template directory exists only in the `rjmurillo/ai-agents` repository, not in an installed plugin. Rerun the build pipeline (`build_all.py`, same repository) to regenerate each skill's `SKILL.md` and its Copilot mirror.
- `model:` is normally omitted (harness default). The only other valid state is a bare alias (`haiku`/`sonnet`/`opus`) plus `model-rationale:` (ADR-080); a versioned id fails the model-pin check. 7 skills use `model: haiku` today, none use a versioned id.
- Size: warns at 300 lines, blocks at 500; `size-exception: true` in frontmatter, with a rationale comment, declares a justified overage.
- Before a skill that configures, generates, or tests Claude Code or Copilot CLI artifacts: read the `agent-harness-reference` skill; cross-harness mutations go through the `ai-agents-portability-campaign` skill.

## Entry points

- New skill: the `skillforge` skill creates and reviews it end to end.
- `SKILL.md` frontmatter, line 1: `name` (`^[a-z0-9-]{1,64}$`), `version`, `description` (max 1024 chars, no XML tags, a "Do NOT use ... (use X)" discriminator), `license`. `version` and `model` are top-level fields, never nested under `metadata:`.
- Trigger phrases are a body `## Triggers` H2, not part of frontmatter `description`: 1 to 5 backtick-wrapped phrases (an unwrapped phrase counts as zero), shell metacharacters rejected. `skillforge`'s validator enforces this at commit time.
- Process section heading is `## Process` or `### Phase N` (110 of 111 skills use the former today); one of `## Verification`, `## Success Criteria`, `## Checklist` is also required.

## Where to look

| Path | Why |
|---|---|
| `<skill>/SKILL.md` | The contract: frontmatter plus process |
| `<skill>/scripts/` | Executable code the skill invokes |
| `<skill>/references/` | Long-form reference material, loaded on demand |
| `<skill>/templates/` | Output-shape templates the skill fills in |
| `tests/skills/<name>/` | The only place a skill's tests may live, outside this tree |

## Skip

- The generated Copilot CLI mirror of this tree: edit the source skill here and regenerate, never the mirror.
- `__pycache__/` under a skill's scripts directory: bytecode cache, not source.
- `<skill>/tests/`: new test files here are blocked; tests live only under `tests/skills/<name>/` (see Constraints).

## Constraints

- New skill scripts must be Python; new skills must ship pytest coverage under `tests/skills/<name>/`, not colocated (issue #4838): colocated tests ship to consumers.
- In-root executables named in `SKILL.md` must resolve through `"${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/<name>/scripts/<file>"`, never a bare `.claude/skills/...` path, which only resolves when the consumer's cwd happens to match.
- A path that exists only in the `rjmurillo/ai-agents` repository (governance, build, or other upstream-only automation trees) must not appear undeclared in a skill's prose: drop the reference, say "in the `rjmurillo/ai-agents` repository" instead of the path, or declare it with a `vendor-portability` HTML comment.
- A retired ADR named in a skill's `metadata.adr` fails a portability gate (issue #5665).
- A documented script plus exit code is an executable contract; a test under `tests/` must assert that exit code, not just a helper's return value.
- Subprocess text capture in a skill script must use `encoding="utf-8", errors="replace"`.
- Skill resolvers must anchor their in-repo lookup on `git rev-parse --show-toplevel`, ahead of any out-of-repo fallback, or an invocation from a subdirectory can silently resolve an arbitrarily old cached copy.

## Dangerous assumptions

- A script named `validate_skill_format.py` exists in the `rjmurillo/ai-agents` repository, but it validates the memory/skillbook atomic-format convention (scoped to Serena memory files), not `SKILL.md`. It is not part of this tree's gates; `skillforge` is what validates `**/SKILL.md` at commit time.
- A green frontmatter or drift check on the mirrored Copilot copy is not proof the mirror agrees with the source by content. Some checks enforce only co-change or a similarity floor, not textual agreement: read the checking script's own docstring before trusting a "matches" claim.
- The model-pin check reads as full ADR-080 enforcement; it is a draining ratchet. It fails only a new pin, a baselined pin whose value changed without evidence, or a baseline whose entry count grew, not every pin that predates the policy.

## Dependencies

- Feeds the Copilot CLI plugin's mirrored skills tree via the generator named in Matters.
- Pre-commit gates: skill-format validation on every `**/SKILL.md`, a size check, and a colocated-test check.
- Pre-push: the shift-left validation runner's skill gates (9 named `Skill*`: ADR bindings, script portability, markdown portability, markdown exec portability, resolver anchoring, contract tests, shell detection, SKIP clause routing, memory references; plus `Colocated Skill Tests` and `Shipped Skill Routes`).
- CI workflows: an agent/skill discriminator check, a passive-compliance check, and a description-budget check.

## Architecture

- Skill test location is inverted from most repository conventions: tests live in a parallel `tests/skills/<name>/` tree, never colocated with the skill (issue #4838).
- The pre-push `Skill*` gates are individually named checks over this same tree, not one monolithic validator; a failure names one gate, not "skills failed."
- Authoring standards live in three places, in the `rjmurillo/ai-agents` repository: schema authority is `claude-skills.md` (steering docs); creation criteria are `SKILL-CREATION-CRITERIA.md` (governance) and `SKILL-AUTHORING.md` (docs).

## Commands

Repository-only checks (not part of the shipped plugin); run from the `rjmurillo/ai-agents` repository root:

```bash
uv run python scripts/validation/skill_size.py --staged-only --ci
uv run python scripts/validation/check_colocated_skill_tests.py --staged-only
uv run python scripts/validation/pre_pr.py
```
