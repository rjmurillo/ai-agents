# Changelog

## Unreleased

- `discover_skills.py` now indexes plugin-installed skills: `CLAUDE_PLUGIN_ROOT`, `COPILOT_PLUGIN_ROOT`, the folder holding SkillForge, `--extra-root`, and `SKILLFORGE_EXTRA_ROOTS` (#6646)
- `discover_skills.py` keeps one entry per skill name, from the lowest-priority-number source, and records hidden copies in `shadowed_paths` (#6646)
- `discover_skills.py` prefers `SKILL.md` over sibling markdown files when a `*/*.md` source gives them the same skill name (#6646)
- `discover_skills.py` warns when a plugin or extra root exists but holds no skill files, and names the parent directory fix when the root is itself a skill folder (#6646)
- `discover_skills.py` falls back to the folder name when a SKILL.md has a blank or non-string `name:`, and converts a non-string `description:` (such as a bare YAML date) to text, so these malformed values no longer abort the index run (#6646)

## v4.1.0 (Current)

- **Extended frontmatter support** - Full support for `model`, `context`, `agent`, `hooks`, `user-invocable`
- Created `scripts/_constants.py` for shared validation constants
- Updated `scripts/quick_validate.py` with extended property validation
- Updated `scripts/validate-skill.py` with hooks and agent validation
- Fixed `scripts/discover_skills.py` to extract version from `metadata.version`
- Added Hooks Integration section to SKILL.md and script-integration-framework.md
- Added Forked Context documentation to synthesis-protocol.md
- Updated skill template with modern best practices
- Expanded frontmatter requirements table with 10 properties

## v4.0.0

- **Phase 0 Skill Triage** - Intelligent routing before creation
- Universal input handling - any prompt works
- Skill ecosystem scanning with 250+ skills indexed
- Decision matrix: USE | IMPROVE | CREATE | COMPOSE
- Renamed from SkillCreator to SkillForge

## v3.2.0

- Added Script Integration Framework for agentic skills
- Added 4th Script Agent to synthesis panel (conditional)
- Added Phase 1D: Automation Analysis
- Added Automation Lens questions to regression questioning
- Created `references/script-integration-framework.md`
- Created `references/script-patterns-catalog.md`
- Created `assets/templates/script-template.py`
- Updated skill-spec-template.xml with `<scripts>` section
- Updated validate-skill.py with script validation
- Skills can now include self-verifying Python scripts

## v3.1.0

- Added progressive disclosure structure
- Fixed frontmatter for packaging compatibility
- Added validation & packaging section
- Deep dive sections now collapsible

## v3.0.0

- Complete redesign as ultimate meta-skill
- Added regression questioning loop
- Added multi-lens analysis framework (11 models)
- Added evolution/timelessness core lens
- Added multi-agent synthesis panel

## v2.0.0

- Pattern selection guide
- Quality standards checklist

## v1.0.0

- Basic skill structure
