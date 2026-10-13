---
id: ADR-115
status: proposed
date: 2026-10-12
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
review-by: 2027-04-12
---

# ADR-115: Native Plugin Support for Cursor, Codex, Grok Build, Hermes, Devin, Pi, and Muse

## Status

Proposed. It refines ADR-072 Decision 2 and Decision 5 for seven more hosts. A reduced `adr-review` panel (architect and critic) reached consensus in round 3 on the first four hosts. The owner added Devin, Pi, and Muse on 2026-10-13. Rounds 4 and 5 reviewed that scope, and both reviewers accepted it in round 5. Acceptance is the owner's call. The debate log is `.project-toolkit/critique/ADR-115-debate-log.md`.

## Context

The toolkit ships two plugin trees today. `src/claude/` serves Claude Code and `src/copilot-cli/` serves Copilot CLI. `src/vs-code-agents/` holds agent files only. ADR-072 Decision 2 planned per-harness emitters for Cursor and Codex. Decision 5 shipped Cursor first and deferred Codex. Neither emitter exists.

On 2026-10-12 the owner asked for plugin support in six more hosts: Grok Build, Codex, Cursor, Hermes, Grok Bot, and Muse. The owner chose native emitters over a manifest-only reuse of `src/claude/`. The owner first chose to record Grok Bot and Muse as unsupported. On 2026-10-13 the owner added Pi and Devin, and pointed to `obra/superpowers` as a working example for Muse and Devin. That reopened Muse.

### Host facts

Research on 2026-10-12 read each host's own documentation and, where public, its source.

| Host | Manifest the host reads | Components a plugin can carry | Source |
|---|---|---|---|
| Cursor | `.cursor-plugin/plugin.json`, closed schema; marketplace `.cursor-plugin/marketplace.json` | rules (`.mdc`), agents, skills, commands, hooks, MCP | cursor.com/docs/reference/plugins, `cursor/plugins` schemas |
| Codex 0.162.1 | root `plugin.json` with an agent-plugins.org `$schema`, then `.codex-plugin/`, `.claude-plugin/`, `.cursor-plugin/` | skills, hooks, MCP, apps; custom agents and rules are not plugin components | developers.openai.com/codex/plugins/build, `openai/codex` source |
| Grok Build | `plugin.json`, `.grok-plugin/plugin.json`, `.claude-plugin/plugin.json`; marketplace probe starts at `.grok-plugin/marketplace.json` | skills, commands, agents, hooks, MCP, LSP; no rules component | docs.x.ai/build/features/skills-plugins-marketplaces, `xai-org/grok-build` `manifest.rs` |
| Hermes | portable `plugin.json` (Agent Plugins v1) with `skills/`, or native `plugin.yaml` with Python | skills, MCP (portable form); tools, hooks, commands (native form) | `NousResearch/hermes-agent` at `63d0b94120027d487c9a5235b9ec64b696af1b26` |
| Grok Bot 0.68.1 | not published | not published | docs.x.ai/grok-bot/get-started |
| Devin CLI (beta) | `.devin-plugin/plugin.json`, then `.claude-plugin/plugin.json`, then root `plugin.json`; install takes `owner/repo#path/to/plugin` | skills, `AGENTS.md`, `rules/*.md`, agents, `hooks.json`, `.mcp.json`; managing plugins needs `devin auth login` | docs.devin.ai/cli/extensibility/plugins/overview |
| Pi | a `pi` key in `package.json` with `extensions`, `skills`, `prompts`, `themes` arrays; `pi install git:<repo>`; a git subdirectory install is not documented | skills, TypeScript extensions, prompts, themes; no login noted | `earendil-works/pi` `packages/coding-agent/docs/` |
| Muse | not published by Meta; third-party reports put plugins behind `MUSE_EXPERIMENTAL_PLUGINS=1` with `install`, `approve`, and `validate` commands; superpowers ships `.muse-plugin/plugin.json` (`schemaVersion: 1`, `capabilities.skills` as `{id, path}` entries) | skills, hooks, commands, MCP, per superpowers | withone.ai; `obra/superpowers` at `bb92a77741419a4ab5f06e711a283343f1ada0c3` |

Grok Build's documentation states that a skill's `model` and `effort` keys are accepted but not applied.

### Prior art

`obra/superpowers` at the commit above ships one shared `skills/` tree at its repository root and one native manifest per host beside it: `.claude-plugin/`, `.codex-plugin/`, `.agents/plugins/`, `.cursor-plugin/`, `.devin-plugin/`, `.muse-plugin/`, `.hermes-plugin/` (native `plugin.yaml` with a `pre_llm_call` bootstrap), a `pi` key in `package.json`, and more. Each host has a manifest test. This record follows the same idea where a host can read the Claude tree, and generates a tree only where a host's format or caps require one.

### Measured on 2026-10-12

- **Codex marketplace precedence.** Codex 0.162.1 ran with a scratch `CODEX_HOME` against a scratch repository holding both `.agents/plugins/marketplace.json` and `.claude-plugin/marketplace.json`. `codex plugin marketplace add` registered only the `.agents` marketplace. The control, with only `.claude-plugin/marketplace.json`, registered that one. With both files sharing one marketplace name and one plugin name, `codex plugin add` installed the tree the `.agents` file named, and only that tree.
- **Hermes install scan.** Hermes runs `tools/plugin_guard.py` on every install. A `dangerous` verdict blocks the install, and `--force` does not override it. The guard at the pinned commit scanned `src/claude/skills/` as one plugin and returned `dangerous`, with 446 findings. Scanned one skill at a time, 85 skills are `safe`, 5 are `caution`, and 7 are `dangerous`. The dangerous ones are `adr-review`, `cva-analysis`, `memory-maintenance`, `memory-search`, `planner`, `security-scan`, and `stuck-detection`. Every critical finding is reference prose, such as an `echo ... | python3 -c` example.
- **Skill size.** `src/claude/skills/` holds 97 skills in 594 tracked files, 6.1 MB in total. The largest file is 159 KB. Hermes refuses a plugin over 400 files or 10 MB.
- **Cross-skill references.** 26 skills refer to another skill's `scripts/`, `references/`, or similar folder, with 43 edges in total. Grouped by those edges, the largest connected group holds 28 skills and 255 files, and it includes `github`.
- **Shared `lib/`.** 166 files under `src/claude/skills/` import `github_core`, `hook_utilities`, or `ai_review_common`. Each finds `lib/` through `COPILOT_PLUGIN_ROOT` or `CLAUDE_PLUGIN_ROOT`, and otherwise at `parents[3]/lib`, the plugin root. Without it the script raises `RuntimeError` (`src/claude/skills/chestertons-fence/scripts/investigate.py:18-29`). `src/claude/lib/` holds 40 files, 376 KB, and the pinned `plugin_guard` scans it as `safe`.
- **Script lookup.** 33 of 97 skills find their scripts through `CLAUDE_PLUGIN_ROOT`, `COPILOT_PLUGIN_ROOT`, `.claude/` in the repository, or the Claude and Copilot install folders (for example `src/claude/skills/pr-review/SKILL.md:106-121`). None names a Codex, Cursor, Grok Build, or Hermes location. Codex, Cursor, and Grok Build document a plugin-root variable for hook commands only. Whether a skill's shell sees one is unknown for every new host.
- **No plugin hooks.** `src/claude/hooks.json` reads `"hooks": {}` under ADR-097.
- **Existing Codex install.** Codex already installs `project-toolkit@ai-agents` from `.claude-plugin/marketplace.json`. `plugin-cli-smoke.yml` runs a `smoke-codex` job against that install (ADR-114 Decision 2).

## Decision Drivers

In priority order:

1. A consumer must never get a broken install (`generated-artifacts.md`). This outranks reach.
2. One source tree per artifact class (ADR-109). No source file moves.
3. Native fidelity per host, as the owner chose on 2026-10-12.
4. No fabricated artifact fields (`universal.md` MUST NOT 12).
5. The smallest output that meets the first four.

## Decision

1. **A generated plugin tree for each host whose native format differs.** Cursor, Codex, Hermes, and Devin each get a tree under `src/<host>/`, rendered by `build_all.py` from a `templates/platforms/<host>.yaml` config, and gated by `build_all.py --check`. `OWNED_PREFIXES` already owns `src/`. Skills copy from `src/claude/skills/`, so every tree ships the same 97 skills as the Claude tree. This follows the Copilot rules stanza, which reads `src/claude/rules/`. Every tree also gets `lib/` at its plugin root, rendered by `lib_mirror.py` in the same run, the way `src/copilot-cli/lib/` is. Without it, skill scripts that import a shared package fail. `lib_mirror.py` hardcodes its two output roots in `PLUGIN_ROOTS`, so each host's pull request extends that tuple (one entry per Hermes pack) and adds the matching `lib` row to `surface-parity.yaml`. Grok Build and Pi get no tree (Decisions 4 and 5). Muse gets one generated manifest inside `src/claude/` (Decision 8).

2. **New generator modes, each a schema change with tests.** `validate_templates_schema.py` and the generators gain these keys, each with positive, negative, and edge tests:
   - `artifacts.rules.outputFormat`: `instructions` (today's behavior, the default) or `cursor-mdc`. The Copilot output must stay byte-identical, and a test pins that.
   - `artifacts.agents.frontmatterDrop` and `artifacts.agents.sourceDir`, for an agent copy that reads `src/claude/agents/`.
   - `artifacts.skills.mode: hermes-packs` with `packMaxFiles`, plus a `packs` table (Decision 6).

3. **Cursor gets `src/cursor/`.**
   - Skills: a directory copy that keeps only the keys Cursor's skill schema defines: `name`, `description`, `paths`, `disable-model-invocation`, `icon`, `color`, and `metadata`. Every other key is dropped, including `model`, `model-rationale`, `allowed-tools`, `argument-hint`, `version`, `license`, `user-invocable`, and `size-exception`. The stanza is an allow list, so a new source key cannot leak into the tree.
   - Rules: `outputFormat: cursor-mdc` writes `rules/<name>.mdc`. A rule whose `paths` is `["**"]` gets `alwaysApply: true`. Any other `paths` list becomes a comma-separated `globs` string with `alwaysApply: false`. `priority` is dropped. Internal-only globs are filtered as they are for `src/copilot-cli/instructions/`. A rule whose globs are all internal is skipped, the same as the Copilot plugin tree does today.
   - Agents: `src/claude/agents/*.md` becomes `agents/*.md`. `name` and `description` stay. `model` is dropped, so the agent inherits the host default. Keys Cursor does not define are dropped.
   - Manifest: `src/cursor/.cursor-plugin/plugin.json` is hand-maintained, like the other two trees' manifests. It carries only keys in Cursor's closed schema.

4. **Grok Build reuses `src/claude/`. Devin gets `src/devin/`.**
   - Grok Build reads `.claude-plugin/plugin.json` without change, so a separate tree would copy bytes it already reads. The `model` pins in the Claude tree are inert, because Grok accepts the key and does not apply it. The only native file is `.grok-plugin/marketplace.json`, which lists `project-toolkit` at `./src/claude`. Rules do not load, because Grok plugins have no rules component.
   - Devin also reads `.claude-plugin/plugin.json`, but it loads a root `AGENTS.md` as an always-on rule, and `src/claude/AGENTS.md` is a repository-only contributor guide. Pointing Devin at `src/claude/` would put that guide in every Devin user's session. So Devin gets a generated tree under Decision 1: skills, agents, rules, and `lib/`, with no `AGENTS.md` or `CLAUDE.md`, and a hand-maintained `.devin-plugin/plugin.json`. Internal-only rule globs are filtered as they are for Cursor. The install command is `devin plugins install rjmurillo/ai-agents#src/devin`. How Devin reads a rule's `paths` key and a skill's `model` alias is not documented, so the Devin pull request measures both and sets the stanza's drop lists from the result.

5. **Pi reads a root `package.json`.** Pi installs a package from a git repository root, and a subdirectory install is not documented. The repository has no root `package.json` today. The Pi pull request adds one that is `private`, carries the `pi-package` keyword, and holds only `pi.skills: ["./src/claude/skills"]`. Skills stay inside `src/claude/`, so `parents[3]/lib` still finds `src/claude/lib/`. No Pi extension ships, because the toolkit has no hook or bootstrap to inject. The pull request confirms that the new file changes no other tool's behavior, such as Renovate or the `packages/ai-agents-cli` workspace.

6. **Hermes gets `src/hermes/`, packed under the install cap.**
   - Format: the portable Agent Plugins v1 form, a `plugin.json` plus `skills/`. It runs no plugin code in the host process. The Hermes plugin guide (`website/docs/developer-guide/plugins/index.md` at the pinned commit) gives two more reasons. Skills a native plugin registers with `ctx.register_skill` are "not listed in the system prompt's `<available_skills>` index", so they load only when named. Portable skills load through `skills_list` and `skill_view`. A portable package also gets `PLUGIN_ROOT`, set to the package root, which the script resolvers use under Decision 9. The toolkit ships no hook or command, so the native `plugin.yaml` form adds nothing.
   - Frontmatter: the portable validator requires `metadata` to be a flat string map, and every shipped skill nests it. The stanza drops `metadata` along with the model keys.
   - Packs: `templates/platforms/hermes.yaml` holds a hand-maintained `packs` table that maps each shipped skill to one pack, `src/hermes/project-toolkit-<name>/`. A skill can be listed under `excluded` instead, with a reason. The table gives a pack a stable identity, so a new skill never moves an old one. Every pack carries its own copy of `lib/` (40 files), so the skill budget per pack is 340 files. The largest reference group, 255 files, fits.
   - The build fails when any of these hold:
     - a shipped skill is in no pack and not excluded, or is in two;
     - a pack, counting `lib/`, exceeds `packMaxFiles` (380) or 10 MB;
     - a skill refers to a skill in another pack, or to an excluded skill;
     - the pinned `plugin_guard` returns `dangerous` for a pack.
   - Exclusions: the 7 dangerous skills are excluded at first. Exclusion is transitive: a skill that refers to an excluded skill, directly or through other skills, is excluded too, and the build computes the closure. A later change can restore a skill by rewording the flagged prose at its template. A pack with a `caution` verdict ships, and the install guide names it, because Hermes asks the user to confirm it.
   - Index: the build writes `src/hermes/README.md`, listing each pack and its skills, and `--check` gates it.

7. **Codex gets `src/codex/` under the existing plugin id.**
   - Why a tree: ADR-111 drops `model` keys for a host with no per-skill model field, and Codex reads interface metadata only from a root `plugin.json`. The Claude tree carries neither change.
   - Skills: a directory copy with the Copilot drop list, plus `lib/` at the plugin root. Today's Codex installs load `src/claude/`, which has `lib/`. Moving them to a tree without it would break the `github`, `pr-review`, and `merge-resolver` scripts that work now.
   - Manifest: a hand-maintained `src/codex/plugin.json` with the agent-plugins.org `$schema` and `extensions["com.openai"].interface`.
   - Marketplace: `.agents/plugins/marketplace.json` is named `ai-agents` and lists `project-toolkit` at `./src/codex`. The measurement above shows Codex then reads only this file. Every existing `project-toolkit@ai-agents` Codex install moves to `src/codex` with no rename and no duplicate skills. The `smoke-codex` job's install command does not change, and its assertions move to the Codex tree in the same pull request.
   - Agents and rules: not shipped. Codex loads custom agents only from `.codex/agents/` and `~/.codex/agents/`, and no plugin path carries rules or `AGENTS.md`. This keeps ADR-072's rule that a Codex emitter never writes a hand-authored `AGENTS.md`.

8. **Muse is experimental. Grok Bot is unsupported.**
   - Muse: the build generates `src/claude/.muse-plugin/plugin.json`, listing every shipped skill as a `capabilities.skills` entry. It is generated because the list must match the tree. A new `artifacts.muse` stanza drives it, with a `surface-parity.yaml` row and a `--check` drift gate. Its shape comes from the superpowers manifest, a third-party example that nobody here has run. The emitted fields are `schemaVersion`, `name`, `displayName`, `description`, `compat`, and `capabilities.skills`, and nothing else. `version` is omitted, per ADR-092. So the Muse pull request installs the Muse CLI and runs `muse plugins validate` and `install` on the tree with `MUSE_EXPERIMENTAL_PLUGINS=1`. That run, recorded in the pull request, is the schema check Decision 11 requires, because Meta publishes no schema. The same run settles two questions: whether `validate` accepts a manifest with no `version`, and whether Muse needs the ADR-111 `model` drop. If `validate` requires `version`, Muse ships no entry until an ADR-092 exception is recorded. If either answer needs a change the Claude tree cannot carry, Muse gets a generated tree under Decision 1. If the CLI rejects the shape, Muse ships no entry. The install guide labels Muse experimental and states that Meta publishes no plugin documentation.
   - Grok Bot: xAI publishes no plugin manifest, skill directory, or install contract, and no working example is known. A guessed manifest would be a fabricated artifact field. The install guide names it as unsupported.
   - At each `review-by` date the owner checks Meta's and xAI's documentation for a published format.

9. **Skills find their scripts on every host.** Each host's pull request measures where the host installs a plugin and whether a skill's shell sees a plugin-root variable. It then adds that location to the script resolvers at their skill templates, ahead of the fallback to `.claude/` in the repository. A measured location is recorded in this record's host facts by amendment. An unmeasured one is never guessed. When the host exposes no variable to a skill's shell, the resolver uses the measured install path. When neither is measurable, the host ships no marketplace entry under Decision 10.

10. **No marketplace entry before a real-runtime smoke passes.** This applies `generated-artifacts.md` MUST 4 and MUST NOT 2 without a new exception. A host's marketplace file lands only in the pull request whose smoke does all three of these in that host: installs the tree, loads a skill, and runs one script-backed step that imports `lib/` through the skill's own resolver, such as the `github` skill's `get_pr_checks.py --help`.
   - Codex: a CI leg in `plugin-cli-smoke.yml`.
   - Hermes: a CI leg that installs `hermes-agent` at the pinned commit and installs every pack.
   - Pi: a CI leg, because loading a package needs no login.
   - Cursor, Grok Build, Devin, and Muse: a CI leg when the host CLI loads plugins without login. Otherwise the smoke runs locally with the owner's login, the same pattern MUST 4 names, and the pull request records the command, the host version, and the output. Muse runs with `MUSE_EXPERIMENTAL_PLUGINS=1`.

   A host whose smoke cannot run ships no marketplace entry, and its row in the install guide says so. Devin installs by path and has no marketplace file, so for Devin the install-guide row is what waits for the smoke. A skipped smoke is never reported as a pass.

11. **Committed-artifact gates.** Each manifest is validated against the host's published schema, as MUST 3 requires. The root marketplace files are hand-maintained and outside the `surface-parity.yaml` roots, so a new validator checks them. Each one must parse, each `source` must resolve to a tree that holds that host's manifest, and the names must match. `check_plugin_manifest_parity.py` and `tests/test_marketplace_two_plugin.py` hardcode two marketplaces today, and each host's pull request extends them.

12. **Ship order: one pull request per host.** The hosts that reuse `src/claude/` go first, because each is one file and one smoke: Grok Build, then Pi. Then the generated trees: Devin, Cursor, Codex, Hermes. Muse goes last, because it depends on an experimental host flag. The install guide lands with the last one.

## Deferred Items

- A Codex agent emitter that writes `.codex/agents/*.toml` into a consumer repository. No plugin path carries it, so it needs its own install story.
- Cursor and Codex hooks. No tree has a hook to project (ADR-097). Revisit when the first plugin hook returns.
- Rewording the flagged prose in the 7 Hermes-dangerous skills so they can ship to Hermes. Each needs an edit at its template.

## Alternatives Considered

- **Manifests only over `src/claude/`.** Cursor, Codex, and Grok read Claude-shaped skills. The owner rejected it on 2026-10-12 because Cursor rules and Hermes packaging need native output.
- **One Hermes plugin with only `SKILL.md` files.** It fits the cap with 97 files, but the 212 script files and 236 reference files would be missing, and skills that call their scripts would break.
- **Packing Hermes skills by name order.** The boundary would split `pr-review` and `pr-autofix` from the `github` scripts they call, and any new skill would shift every later pack.
- **A second Codex marketplace name.** Codex reads only the `.agents` file when both exist, so the old `ai-agents` name would disappear, and every existing install and the blocking smoke would break.
- **Converting the hand-authored `AGENTS.md` files for Codex.** ADR-072 Decision 5 already rejected it.

## Consequences

### Positive

- Seven more hosts get an install path from one source tree. Grok Build and Pi need no new tree, and Muse needs only one generated manifest.
- Each tree is gated by the drift check the other trees use, so it cannot fall behind its source.
- Existing Codex installs keep their plugin id.

### Negative

- Four more generated trees add about 2,400 skill files, plus 40 `lib/` files per tree and per Hermes pack, plus the Cursor rule and agent copies.
- Hermes users install several packs, and at least 7 skills do not ship to Hermes.
- A host whose smoke cannot run stays without a marketplace entry until it can.

### Neutral

- Claude Code and Copilot CLI behavior does not change. Their `SKILL.md` text changes where Decision 9 adds host locations to a resolver, and the existing locations keep their order ahead of the fallback.

## Reversibility Assessment

Each change is additive. Removing a host deletes its tree, its platform config, and its marketplace file. Grok Build has only the marketplace file, Pi has only the root `package.json`, and Muse has only its generated manifest. Removing `.agents/plugins/marketplace.json` returns Codex installs to `src/claude/`, as the control measurement shows. Per `templates.md` MUST NOT 2, removing a platform target needs an ADR, and this record is that ADR for these seven.

## Related Decisions

- ADR-072: per-harness emission and the Cursor and Codex plan this record refines.
- ADR-097: zero plugin hooks, which removes hook projection from scope.
- ADR-109: template-first distribution and the binplace model the trees follow.
- ADR-111: model pins dropped per harness.
- ADR-114: the plugin CLI smoke workflow the new legs join.

## References

- <https://cursor.com/docs/reference/plugins>
- <https://developers.openai.com/codex/plugins/build>
- <https://docs.x.ai/build/features/skills-plugins-marketplaces>
- <https://github.com/NousResearch/hermes-agent/tree/63d0b94120027d487c9a5235b9ec64b696af1b26>
- <https://docs.x.ai/grok-bot/get-started>
- <https://docs.devin.ai/cli/extensibility/plugins/overview>
- <https://github.com/earendil-works/pi/tree/main/packages/coding-agent/docs>
- <https://github.com/obra/superpowers/tree/bb92a77741419a4ab5f06e711a283343f1ada0c3>
- <https://runtimewire.com/article/meta-opens-muse-connectors-developers>
- <https://www.withone.ai/blog/muse-code-skills-not-mcp/md>
