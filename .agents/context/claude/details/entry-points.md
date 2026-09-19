## Entry points

- New rule: `templates/rules/<name>.md` with `paths:` frontmatter; a literal `{{` is written `\{{`. Needs an activation scenario or its id in the pre-PR `Rule Activation Coverage` baseline. Language-universal scope is budget-gated, not blocked: pre-PR `Instruction Budget (always-on)`.
- Always-on rules use `paths: ["**"]` and `priority: critical`: `rules/universal.md`, `builder-ethos.md`, and `voice.md`. Keep membership aligned with `skills/context-optimizer/references/model-context-doctrine.md`. The pre-PR `Always-on Corpus Claims` gate checks that membership.
- `settings.json` renders from `templates/hooks/settings.tmpl`, no plugin-tree hop: `hooks` wires four session-boundary events for this checkout (`SessionStart`, `UserPromptSubmit`, `SessionEnd`, `PreCompact`); `permissions`, `env`, `enabledPlugins` are separate top-level keys; `enabledPlugins` pins `project-toolkit@ai-agents` to `false` (JSON `false` only) so this checkout does not load its own plugin twice.
