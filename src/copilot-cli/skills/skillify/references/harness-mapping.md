# Harness Mapping

Detail for the `skillify` skill. The upstream version of this procedure used
three tool names that no supported harness exposes: `skills_list`,
`skill_view`, and `skill_manage`. Use the replacements below. `verify` fails
any generated skill that still contains those names.

| Upstream step | Replacement | Claude Code | Copilot CLI |
|---------------|-------------|-------------|-------------|
| List skills, search descriptions | `skillify.py overlap --root ...` over each skills root | same | same |
| View a skill | Read `<root>/<name>/SKILL.md` with the file-read tool | `Read` | the file-read tool |
| Create a skill | Write `<root>/<name>/SKILL.md` with the file-write tool | `Write` | the file-write tool |
| Patch a skill | Edit with a unique old string | `Edit` | the file-edit tool |
| Confirm it loaded | `skillify.py verify`, then the harness skill list | `Skill` tool list | the skills listing |

## Project skill roots

| Harness | Project root | Evidence |
|---------|--------------|----------|
| Claude Code | `.claude/skills/<name>/SKILL.md` | `agent-harness-reference` skill; repository `CLAUDE.md` install table |
| Copilot CLI | `.github/skills/<name>/SKILL.md` | `agent-harness-reference` `references/probe-evidence.md` section 10 loaded a skill from that path |

Claude Code also loads a user-scope tree at `~/.claude/skills/`. The Copilot
CLI user-scope path was not verified for this skill; take it from an explicit
user instruction. Do not create `.github/skills/` in a repository only to
mirror a Claude Code skill.

Copilot CLI file-tool names are not pinned here. Describe the action, and let
the harness choose its tool.

## Why `triage_skill_request.py` is not reused

The `skillforge` script `triage_skill_request.py` scores a user query against
a prebuilt skill index at `~/.cache/skillrecommender/skill_index.json` and
exits 2 when that index is missing. It returns a 0 to 100 score from query
domains and keywords. Skillify needs the opposite: a scan of named skills
roots at call time, with no cache, and a coverage ratio of workflow terms
against each skill's name, description, triggers, and procedure. The 0.70
patch rule needs that ratio, so `skillify.py overlap` computes its own.
