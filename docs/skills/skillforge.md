# skillforge

Takes any input (a goal, a question, an error message, a URL) and decides what to do about skills: recommend an existing one, improve one, compose several, or create a new one. It checks for duplicates before it builds anything.

## When to use it

- You want to create a skill, or ask whether you already have one.
- You want to improve a skill's structure.
- Trigger phrases: `create a skill`, `do I have a skill for`, `which skill should I use`, `improve the X skill`, `SkillForge: {goal}`.

## When not to use it

- Context optimization, placement analysis, markdown compression, extraction and indexing, or rule audits: use [`context-optimizer`](context-optimizer.md) instead.
- Eval-gated optimization of an existing skill: use [`skillopt`](skillopt.md) instead.
- Saving a workflow you just finished as a skill: use [`skillify`](skillify.md) instead.

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:skillforge SkillForge: create a skill for automated code review
```

In a Claude Code session inside a checkout of this repository, drop the prefix: `/skillforge`. In GitHub Copilot CLI, name the skill with a slash in your prompt, such as `Use the /skillforge skill to ...`.

The skill triages first. It scores your input against installed skills and routes to `USE_EXISTING`, `IMPROVE_EXISTING`, `CREATE_NEW`, `COMPOSE`, or `CLARIFY`. It creates a new skill only when no existing skill covers the need.

## What you get

- Routing: a strong match (80% or more, or 60% or more for a skill question) gets a recommendation. A match of 50 to 79% gets an improvement. Below 50% gets a creation. Multi-domain requests get a composition.
- For a new skill: a `SKILL.md`, plus `references/`, `assets/`, and `scripts/` where they help, and a specification file.
- A validation pass before you distribute the skill.

Commands:

| Command | Action |
| --- | --- |
| `SkillForge: {goal}` | Full run |
| `SkillForge --plan-only {goal}` | Specification only |
| `SkillForge --quick {goal}` | Bounded tier for a low-risk edit with a deterministic verifier |
| `SkillForge --triage {input}` | Triage only |
| `SkillForge --improve {skill}` | Improve an existing skill |

## Advanced use

**Depth contract.** The skill states the accepted outcome first (what must be true, the check, who accepts it), then picks the lightest tier that covers the unresolved risk:

| Tier | Case | Path |
| --- | --- | --- |
| Bounded | Structural edit, known scope, a deterministic verifier | Triage, edit, validators |
| Standard | A few open questions | Bounded path plus the analysis lenses that address a named risk |
| Full | New ambiguous capability | Phases 0 to 4, all 11 lenses, panel review |

A change to a safety control, a permission boundary, a shipped default, or anything irreversible keeps a human decision and an independent review, whatever the tier.

**Phases.** Triage, analysis, specification, generation, then a synthesis panel of 3 to 4 independent evaluators who must all approve (required at the Full tier and for consequential changes). The skill scores timelessness and requires 7 or more at Standard and Full tiers.

**Placement check.** A new skill or an edit that adds or moves standing knowledge triggers this check. The skill runs [`context-optimizer`](context-optimizer.md) on the whole `SKILL.md` draft before moving detail to `references/`. The analyzer reads only `SKILL.md`. The skill weighs planned or existing script actions before following a Passive Context or Hybrid result. Mechanics-only edits (scripts, tests, wording) skip it.

**External skill catalogs.** To adapt a third-party skill source, it requires a commit-pinned source, reuses local skills over duplicating, and rejects skills coupled to one product. It compares techniques, not skill names: a method an existing local skill lacks is added to that skill, not shipped as a new one.

**Validation.** From the root of a checkout of this repository, with `SKILL` set to a skill directory:

```bash
uv run python .claude/skills/skillforge/scripts/quick_validate.py "$SKILL" --root "$HOME/.claude"
uv run python .claude/skills/skillforge/scripts/validate-skill.py "$SKILL" --root "$HOME/.claude"
uv run python .claude/skills/skillforge/scripts/conformance.py "$SKILL" --root "$HOME/.claude"
uv run python .claude/skills/skillforge/scripts/lint_skill_frontmatter.py "$SKILL" --root "$HOME/.claude"
uv run python .claude/skills/skillforge/scripts/check_docs_safety.py "$SKILL"
uv run python .claude/skills/skillforge/scripts/skill_modularity_audit.py "$SKILL" --ci
uv run python .claude/skills/skillforge/scripts/package_skill.py "$SKILL" ./dist
```

Other scripts: `init_skill.py` (scaffold, `--path`, `--dry-run`, `--docs-section`; when `--path` is a folder named `skills` in a repository with `docs/skills/README.md`, it also writes `docs/skills/<name>.md` and adds or prints the README row), `triage_skill_request.py` (`--json`, `--verbose`; exits `2` if the skill index is missing), and `discover_skills.py` (builds the index; `--extra-root`, `--output`, `--json`). Validators enforce a path guard: the skill directory must sit under the current directory or under `--root`. Read [`references/scripts-and-validation.md`](../../src/claude/skills/skillforge/references/scripts-and-validation.md) before you act on an exit code.

`lint_skill_frontmatter.py` runs nine deterministic rules: frontmatter the stdlib parser can read, the 24576-byte cap with 256 bytes of headroom for generated mirrors, artifact and capability shapes, routable trigger phrases, the Handoff line, and a description redirect. It exits `0` with no MUST failure, `1` on a MUST failure (or any SHOULD warning with `--strict`), and `2` on a usage error. `--list` prints the rules. [`references/frontmatter-and-limits.md`](../../src/claude/skills/skillforge/references/frontmatter-and-limits.md) explains each rule and its fix.

Checklist limits: name is hyphen-case and 64 characters or fewer, description is 1024 characters or fewer, `SKILL.md` stays under 500 lines, and the skill defines 3 to 5 trigger phrases. Start with least-privilege tools (`Read`, `Glob`, `Grep`, `Write`, `Edit`) and add others only when the skill needs them. Write only what the model cannot already know.

Without PyYAML, `quick_validate.py` and `validate-skill.py` share `_yaml_scalars.py`.
That internal helper handles scalar typing and unquoting for their fallback parsers.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`skillify`](skillify.md): extracts a skill from a finished workflow.
- [`skillopt`](skillopt.md): measured improvement with a held-out gate.
- [`context-optimizer`](context-optimizer.md): placement and compression.
- [`skill-bootstrap`](skill-bootstrap.md): builds a whole project skill library.
- Source: [`SKILL.md`](../../src/claude/skills/skillforge/SKILL.md)
- Content rules: [`skill-content-rules.md`](../../src/claude/skills/skillforge/references/skill-content-rules.md)
- Depth contract: [`depth-contract.md`](../../src/claude/skills/skillforge/references/depth-contract.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
