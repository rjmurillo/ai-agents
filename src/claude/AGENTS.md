# src/claude/

31 generated Claude Code agent prompts; `claude-agents` plugin source in the `rjmurillo/ai-agents` repository, binplaced as `.claude/agents/<name>.md`.

<!-- vendor-portability: contributor guide for the rjmurillo/ai-agents repository; names templates/, build/, .github/agents/, and sibling src/ trees that do not ship with this plugin -->

## Matters

- `agents/` holds 31 generated files, rendered from `templates/agents/<stem>.claude.md.tmpl` via `agent_templates.py` (ADR-109). `claude-instructions.template.md`, `security/references/`, `.claude-plugin/plugin.json` are hand-maintained.
- `name`, `description`, `argument-hint` in all 31. `metadata.role` in 25. `tools:` only in `analyst.md`, `security.md`. `model:` only in `code-reviewer.md` (`haiku` + `model-rationale:`).
- No enforced sections except `qa` (`detect_agent_drift.py` `REQUIRED_AGENT_SECTIONS`: `Reviewer Asymmetry (Read First)`, `Completeness Verification (Mandatory)`; dropping either forces DRIFT DETECTED): `## Core Identity` 17/31, `## Constraints` 10, `## Memory Protocol` 13, `## Handoff Options` 13, `## Output Format` 7.
- Edit the template, never `agents/<name>.md`. A hand-edit fails the Agent Template Drift gate (`agent_templates.py --validate`) next run.

## Entry points

- `templates/agents/<stem>.claude.md.tmpl`: edit for Claude-only behavior (MCP tool ids, Serena calls, `Task` syntax).
- In the `rjmurillo/ai-agents` repository: `uv run python build/scripts/build_all.py` regenerates every agent tree (pipeline owned by `templates/AGENTS.md`). Local consequence: a `.claude.md.tmpl` edit moves `agents/` and `.claude/agents/` only. Shared Claude-plus-Copilot text belongs in `templates/agents/partials/` (both `.tmpl` variants include the same partial), so one partial edit moves all four `.tmpl`-fed trees; `src/vs-code-agents/` reads no partial and needs the `<stem>.shared.md` edit too.

## Where to look

| Path | Why |
|---|---|
| `agents/<name>.md` | Full prompt, frontmatter plus body; generated, do not hand-edit |
| `claude-instructions.template.md`, `security/references/` | Hand-maintained: shared preamble, and the `security` agent's checklist/threat-model text |
| `agents/merge-resolver.md`, `agents/pr-comment-responder.md`, `agents/quality-auditor.md` | Hard-code a plugin-root skills path; see Constraints |

## Skip

- `.claude/agents/<name>.md` (byte-for-byte binplace of `agents/<name>.md`) and `.github/agents/<name>.agent.md` (rendered from `<stem>.copilot.md.tmpl`, no `model:` field: GitHub rejects it, issue #4938), both in the `rjmurillo/ai-agents` repository. Neither hand-edited.

## Constraints

- Cross-harness change (hook, event, generated-Copilot): read `agent-harness-reference` first, route through `ai-agents-portability-campaign`.
- `model:` MUST NOT be added without an ADR-080 `KEEP_PIN` entry in the sidecar manifest, or a bare rolling alias (`sonnet`, `opus`, `haiku`) with `model-rationale:` that prices strictly below the harness default through the platform `model_tiers` map (`check_model_pins.py`). Only `code-reviewer.md` qualifies today.
- The three agents above build script paths from `${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/...` (`merge-resolver.md:79` still uses the bare `${CLAUDE_PLUGIN_ROOT:-.claude}`; `plugin-self-containment.md` MUST 2 wants the nested form). Either resolves only when `project-toolkit` (`.claude/`) installs alongside `claude-agents`: `src/claude/` ships no `skills/`.

## Dangerous assumptions

- Assuming a green `detect_agent_drift.py` run proves `src/vs-code-agents/` parity is wrong: it renders from a separate `<stem>.shared.md`, and the tool's default `--claude-path` still points at `src/claude`, not `src/claude/agents`, so it compares 0 of 31 real agents. The `Agent Drift Detection` pre-PR gate runs it with no arguments, so that row is green for the same reason. Pass `--claude-path src/claude/agents`.
- Assuming `templates/README.md`'s Required Sections list (six `##` headings) is enforced here is wrong: none appears in more than 17 of 31 files.
- Assuming a hand edit here is invisible to the build gates is wrong: `OWNED_PREFIXES` in `build_all.py` is the bare `src/`, so `build_all.py --check` and the `Generated Artifact Staleness` pre-PR gate report every unstaged or untracked path under `src/`, this file and `security/references/` included, as `STALENESS DETECTED: uncommitted regen drift` and exit non-zero. The check reads `git diff --name-only` plus untracked, so `git add` alone silences it and proves nothing. The remedy they print (regenerate) does nothing; commit.

## Dependencies

- Consumed by the `claude-agents` marketplace entry (`source`: this directory); nothing above it ships to an installer.

## Architecture

- A render stage, not a source: `templates/agents/<stem>.claude.md.tmpl` plus shared partials are canonical.
- `claude-instructions.template.md` is hand-maintained, no template counterpart, outside the generation pipeline.

## Commands

```bash
# Run from the rjmurillo/ai-agents repository root, not from an installed plugin.
uv run python build/scripts/build_all.py  # regenerate agents/ + downstream mirrors
uv run python build/scripts/agent_templates.py --validate  # check agents/ matches its templates
```
