---
type: requirement
id: REQ-003
category: complex
status: draft
priority: P1
created: 2026-04-27
updated: 2026-04-27
---

# REQ-003: Multi-tool Artifact Build System

## Problem statement

The repo ships AI agent components to two production tool families with
divergent native conventions: **Claude Code** and **GitHub Copilot CLI**.
Today only **agents** are templatized through `templates/` +
`build/generate_agents.py`; **skills, hooks, commands, and rules** are
authored only against Claude conventions in `.claude/<artifact>/`. As a
result Copilot CLI users get agents but no other artifact types, even
where Copilot CLI natively supports them.

The wiki reference (`~/Documents/Mobile/wiki/comparisons/CLI Harness
Instruction Interoperability.md`) provides the cross-tool overview.
Verified Copilot CLI documentation (cited inline below) provides the
authoritative schema.

## Verified facts (researched 2026-04-27)

Sources: GitHub Copilot CLI plugin reference, hooks configuration,
custom instructions docs, command reference (all under
`https://docs.github.com/en/copilot/`).

| Item | Finding |
|---|---|
| **Plugin install path** | `~/.copilot/installed-plugins/<MARKETPLACE>/<PLUGIN-NAME>/` (marketplace) or `~/.copilot/installed-plugins/_direct/<SOURCE-ID>/` (direct) |
| **Plugin manifest discovery order** | `.plugin/plugin.json` → `plugin.json` → `.github/plugin/plugin.json` → `.claude-plugin/plugin.json`. **Copilot CLI reads `.claude-plugin/plugin.json` natively.** |
| **Marketplace manifest discovery order** | `marketplace.json` → `.plugin/marketplace.json` → `.github/plugin/marketplace.json` → `.claude-plugin/marketplace.json`. **Copilot CLI reads `.claude-plugin/marketplace.json` natively.** |
| **Plugin component fields in `plugin.json`** | `agents` (default `agents/`), `skills` (default `skills/`), `commands` (no default), `hooks` (path-or-inline-object, no default), `mcpServers`, `lspServers`. All optional. |
| **Hook config location** | `hooks.json` (Copilot-style at root) or `hooks/hooks.json` (Claude-style). Both supported by Copilot CLI. |
| **Hook config required wrapping** | `{"version": 1, "hooks": {<event>: [{...}]}}`. The `version: 1` key is REQUIRED for Copilot CLI. |
| **Hook events** | `sessionStart`, `sessionEnd`, `userPromptSubmitted`, `preToolUse`, `postToolUse`, `errorOccurred` |
| **Hook entry shape** | `{type: "command", bash: "...", powershell: "...", cwd: ".", timeoutSec: N, env: {}, comment: "..."}` |
| **Hook `cwd` field** | Defaults to plugin root. Scripts use relative paths anchored from `cwd`. There is **NO `${COPILOT_PLUGIN_ROOT}` env var** documented. |
| **Hook `matcher` field** | **NOT SUPPORTED in Copilot CLI hooks**. Filtering must happen inside the hook script via the `toolName` JSON input field. |
| **Hook input JSON for preToolUse** | `{timestamp, cwd, toolName, toolArgs}` |
| **Hook output for preToolUse (deny)** | `{permissionDecision: "deny", permissionDecisionReason: "..."}` (only `"deny"` currently processed) |
| **Agent file convention** | `<name>.agent.md`. Frontmatter `name`, `description`, `tools`. |
| **Skill file convention** | `<name>/SKILL.md`. Frontmatter: `name` (required), `description` (required), `allowed-tools`, `user-invocable` (default `true` → `/SKILL-NAME` invocation), `disable-model-invocation`. |
| **Custom slash commands in CLI** | **No custom slash commands**. Skills with `user-invocable: true` are the bridge — they fire as `/SKILL-NAME`. |
| **Path-specific custom instructions** | `.github/instructions/<NAME>.instructions.md` with `applyTo: "<glob>,<glob>"` frontmatter. **Currently only supported for Copilot cloud agent and Copilot code review** per docs — NOT for general Copilot CLI. |
| **Repo-wide instructions** | `.github/copilot-instructions.md` (no frontmatter) |
| **`AGENTS.md`** | Universal fallback, agent-by-directory-tree |
| **`COPILOT_HOME`** | Overrides `~/.copilot` user config dir. Not the plugin root. |
| **`COPILOT_CUSTOM_INSTRUCTIONS_DIRS`** | Comma-separated extra dirs scanned for custom instructions. |

## Architectural decisions (locked, 2026-04-27)

| # | Decision | Rationale |
|---|---|---|
| D1 | Outputs are **fully native** per platform | Customers install and run; no extra runtime translation |
| D2 | **One plugin per provider** | Provider is axis of variation per CVA |
| D3 | **Cursor + Codex out of scope** | User scoped to Claude + Copilot CLI |
| D4 | **`.claude/<artifact>/` is canonical**; `.claude/settings.json` is canonical for hook registration | Single canonical authoring location |
| D5 | **Hook config is generated** with native `version: 1` wrapper, lowercase events, no matcher field, scripts invoked via `python3 ./hooks/<event>/<script>.py` from default `cwd` (plugin root) | Customers receive working hooks; matcher logic moves into Python script body |
| D6 | **Codex CLI out of scope** | User confirmed |
| D7 | **Claude commands → Copilot skills with `user-invocable: true`** (bridge `/cmd` ↔ `/SKILL-NAME`) | Copilot CLI has no custom slash commands native to plugins; user-invocable skill is the documented equivalent |
| D8 | **Custom instructions (`applyTo:`) generation is CONDITIONAL.** Generated under `.github/instructions/` IFF the source rule has a path scope, but since Copilot CLI per current docs does not consume them, ship a runtime warning until verified | Avoid shipping dead artifacts |
| D9 | **Only `.claude-plugin/marketplace.json` is shared.** Each provider has its OWN `plugin.json` inside its own source dir: Claude at `.claude/.claude-plugin/plugin.json`, Copilot CLI at `src/copilot-cli/.claude-plugin/plugin.json`. The marketplace entry's `source:` path determines which `plugin.json` each provider reads — no field collision (e.g., Claude `mcpServers` declarations cannot accidentally load on Copilot side). | Verified marketplace discovery order; per-source isolation prevents cross-provider load |
| D10 | **Hook `matcher` cannot be cross-generated.** Generator translates Claude's `matcher: "Bash(...)"` into a script-side `toolName`/`toolArgs` filter wrapping the original logic | Copilot CLI hooks lack matcher field |
| D11 | **`${CLAUDE_PLUGIN_ROOT}` references in Claude hooks become `./` (cwd-relative) on Copilot side** | Copilot CLI has no plugin-root env var; uses `cwd` field |

## In scope

- Per-artifact generators emitting fully native Copilot CLI outputs
  from `.claude/<artifact>/` sources.
- Restructure `src/copilot-cli/` to host all artifact types per
  Copilot CLI conventions.
- Update `.claude-plugin/marketplace.json` to declare two plugins (one
  per provider). The same manifest serves both Claude and Copilot CLI.
- Generalize `build/scripts/validate_marketplace_counts.py` to a
  config-driven counter loaded from `templates/platforms/copilot-cli.yaml`.
- Document provider×artifact mapping in `templates/README.md`.
- Generate Copilot CLI hook JSON from `.claude/settings.json` +
  `.claude/hooks/` so customers receive working hooks.
- Generator emits a `copilot-cli-toolkit` plugin under
  `src/copilot-cli/` whose internal layout matches the documented
  Copilot CLI plugin component-default conventions.

## Out of scope

- Cursor (`.cursor/rules/*.mdc`) generation
- Codex CLI generation
- VSCode-specific outputs as a SEPARATE plugin (VSCode reads the
  Copilot CLI artifacts; the `.github/agents/`, `.github/instructions/`
  consumer paths are write targets at install time, not separate
  plugins)
- Authoring new artifact content; build-pipeline-only
- Migrating existing `.claude/<artifact>/` content; `.claude/` stays
  canonical and unchanged

## CVA summary

### Axis = **provider** (per D2)

### Commonalities (across all artifacts and providers)

- **Identity**: each artifact has a name + body
- **Sourcing**: one canonical body emits one or more platform outputs
- **Plugin packaging**: each provider has a `plugin.json` manifest at
  the marketplace install root
- **Marketplace counter**: every plugin description carries count
  tokens validated against actual file counts
- **Marketplace + plugin manifest discovery**: both providers read
  `.claude-plugin/{marketplace,plugin}.json` natively per discovery
  order tables (D9)

### Variabilities (per provider)

| Axis | Claude (canonical) | Copilot CLI (generated) |
|---|---|---|
| **agents path** | `.claude/agents/<name>.md` | `src/copilot-cli/agents/<name>.agent.md` |
| **skills path** | `.claude/skills/<name>/SKILL.md` | `src/copilot-cli/skills/<name>/SKILL.md` (near-identity) |
| **commands path** | `.claude/commands/<name>.md` | `src/copilot-cli/skills/<name>/SKILL.md` with `user-invocable: true` (D7) |
| **rules path** | `.claude/rules/<name>.md` | `.github/instructions/<name>.instructions.md` (with D8 conditional warning) |
| **rules frontmatter scoping key** | `paths:` | `applyTo:` |
| **rules other frontmatter (`alwaysApply`, `priority`, `description`)** | preserved | dropped (`alwaysApply`/`priority` are Claude-only); `description` preserved |
| **hooks path** | `.claude/hooks/<Event>/<script>.py` + `.claude/settings.json` | `src/copilot-cli/hooks/hooks.json` + `src/copilot-cli/hooks/<event>/<script>.py` |
| **hooks JSON top-level wrapper** | `{hooks: {...}}` (Claude `hooks/hooks.json` format) | `{version: 1, hooks: {...}}` (Copilot requires `version: 1`) |
| **hook event name casing** | `PreToolUse`, `PostToolUse`, `Stop`, `SessionStart`, `UserPromptSubmit`, `SubagentStop`, `PermissionRequest`, `Notification`, `PreCompact` | `preToolUse`, `postToolUse`, `sessionEnd`, `sessionStart`, `userPromptSubmitted`, `errorOccurred` |
| **hook event coverage gaps** | n/a | Claude events not in Copilot: `SubagentStop`, `PermissionRequest`, `Notification`, `PreCompact`. These are dropped with warning emit. |
| **hook entry matcher** | `{matcher: "Bash(git commit*)" \| "^(Edit\|Write)$" \| ...}` | **NOT SUPPORTED**. Generator wraps script with a `toolName`/`toolArgs` filter shim that exits 0 (no-op) when the matcher would not have fired. |
| **hook script invocation** | `python3 -u "${CLAUDE_PLUGIN_ROOT}/hooks/<Event>/<script>.py"` | `python3 -u ./hooks/<event>/<script>.py` (relative to default `cwd`) |
| **bash + powershell parity** | n/a (Claude uses single command string) | both `bash` and `powershell` keys emit the same `python3 ./...` invocation (Python cross-platform) |
| **plugin install path** | `~/.claude/plugins/cache/<marketplace>/<plugin>/` | `~/.copilot/installed-plugins/<MARKETPLACE>/<PLUGIN-NAME>/` |

### Relationships

- **Skills**: near-identity transform. SKILL.md content is
  platform-neutral; only install location differs. Generation = copy
  with frontmatter normalization.
- **Rules**: frontmatter key remap (`paths:` → `applyTo:`), filename
  suffix change (`.md` → `.instructions.md`), Claude-only frontmatter
  keys (`alwaysApply`, `priority`) dropped.
- **Agents**: filename suffix only (`.md` → `.agent.md`).
- **Commands → user-invocable skills** (D7): filename + path move,
  frontmatter additions (`user-invocable: true`, `name`, `description`).
- **Hooks**: most divergent. Generator produces `hooks.json` with
  Copilot wrapper, lowercased events, matcher logic inlined into
  Python script wrapper, drops unsupported events with warning.

## Acceptance criteria

### Ubiquitous

**REQ-003-001 — Per-artifact generator interface**
The build system shall expose `build/scripts/generate_<artifact>.py` per artifact type (`agents`, `skills`, `commands`, `rules`, `hooks`). Each generator shall:
- read canonical sources from `.claude/<artifact>/` (and `.claude/settings.json` for hooks),
- read platform substitution rules from `templates/platforms/copilot-cli.yaml`,
- write fully native outputs to `src/copilot-cli/<artifact>/`,
- exit 0 on success, 1 on logic error, 2 on config error.

Verification (per-artifact, not universal):

| Artifact | Pass criterion |
|---|---|
| agents | Output count under `src/copilot-cli/agents/*.agent.md` equals source count under `.claude/agents/*.md` |
| skills | Output count under `src/copilot-cli/skills/*/SKILL.md` equals source count under `.claude/skills/*/SKILL.md` |
| commands | Output count under `src/copilot-cli/skills/<name>/SKILL.md` (with `user-invocable: true`) equals source count under `.claude/commands/*.md` |
| rules | Output count under `.github/instructions/*.instructions.md` equals source count under `.claude/rules/*.md` (unscoped rules emit with `applyTo: "**"`) |
| hooks | Output `src/copilot-cli/hooks/hooks.json` contains exactly one event-key per Copilot-supported Claude event (per mapping in `templates/platforms/copilot-cli.yaml`); per-event entry count equals number of Claude scripts mapped to that event minus matcher-only entries that filter out at runtime |

**REQ-003-002 — `templates/platforms/copilot-cli.yaml` schema (locked, versioned)**
This config file shall declare the following keys, each validated by `build/scripts/validate_templates_schema.py`. The `schemaVersion` key enables forward evolution: generators check compatibility at load time and exit 2 with a clear message if `schemaVersion` exceeds what the generator was built for. New fields can be added at minor schema versions without breaking older generators (additive); breaking changes require a major bump and per-generator update.

```yaml
schemaVersion: "1.0"                # SemVer; generators check against their max supported version
provider: "copilot-cli"             # for cross-reference
artifacts:
  agents:
    sourceDir: ".claude/agents"
    outputDir: "src/copilot-cli/agents"
    sourceSuffix: ".md"
    outputSuffix: ".agent.md"
    excludeFilenames: ["AGENTS.md", "CLAUDE.md"]
  skills:
    sourceDir: ".claude/skills"
    outputDir: "src/copilot-cli/skills"
    mode: "directory-copy"
  commands:
    sourceDir: ".claude/commands"
    outputDir: "src/copilot-cli/skills"
    transform: "command-to-skill"
    appendFrontmatter:
      user-invocable: true
  rules:
    sourceDir: ".claude/rules"
    outputDir: ".github/instructions"
    sourceSuffix: ".md"
    outputSuffix: ".instructions.md"
    frontmatterRemap:
      paths: applyTo
    frontmatterDrop:
      - alwaysApply
      - priority
  hooks:
    settingsSource: ".claude/settings.json"
    scriptSource: ".claude/hooks"
    outputConfig: "src/copilot-cli/hooks/hooks.json"
    outputScripts: "src/copilot-cli/hooks"
    eventRemap:
      PreToolUse: preToolUse
      PostToolUse: postToolUse
      Stop: sessionEnd
      SessionStart: sessionStart
      UserPromptSubmit: userPromptSubmitted
    eventDrop:
      - SubagentStop
      - PermissionRequest
      - Notification
      - PreCompact
    matcherPolicy: "inline-script-shim"
    versionField: 1
auditPolicy:
  pathBlocklist:                     # REQ-003-011 internal-path patterns rejected from audit output
    - "^/home/"
    - "^/Users/"
    - "^/root/"
    - "@[a-f0-9]{40}\\b"
    - "GITHUB_TOKEN"
    - "SECRET"
  output:
    file: "build/audit/GENERATION-AUDIT.md"
    stdoutFormat: "json"             # CI parses stdout, not committed file
```

`templates/` shall NOT contain content; only this YAML and `README.md`.

Verification: `python3 build/scripts/validate_templates_schema.py` exits 0 against the above shape; rejects unknown keys; rejects `..` or absolute paths in any path field.

**REQ-003-003 — Two-plugin marketplace model (single shared manifest)**
`.claude-plugin/marketplace.json` shall declare exactly two plugins:
- `claude-toolkit` with `source: "./.claude"`
- `copilot-cli-toolkit` with `source: "./src/copilot-cli"`

Per D9, this single manifest is read natively by BOTH Claude Code (current behavior) and Copilot CLI (verified discovery order).

Each plugin's description shall carry per-artifact counts that match actual file counts under its source directory.

Verification: `python3 build/scripts/validate_marketplace_counts.py` exits 0; `jq '.plugins | length' .claude-plugin/marketplace.json` = 2.

**REQ-003-004 — Counter generalization (config-driven)**
`build/scripts/validate_marketplace_counts.py` shall replace the hard-coded `PLUGIN_COUNTERS` dict with a config-driven table loaded from `templates/platforms/copilot-cli.yaml` (per provider). Adding a new artifact type shall require only:
- adding files under `.claude/<artifact>/`,
- adding the artifact entry in `copilot-cli.yaml`,
- updating the plugin description count tokens.

Zero Python edits required for new artifact types.

Verification: add a fake artifact entry to the YAML; counter validates without touching `.py` files.

### Event-driven

**REQ-003-005 — Source change triggers regeneration**
When any file under `.claude/<artifact>/` or `.claude/settings.json` changes, the build system shall regenerate `src/copilot-cli/<artifact>/`. CI shall fail when `git diff` shows uncommitted regeneration deltas.

Verification: pre-commit hook OR CI step runs `python3 build/build_all.py --check` and fails on staleness.

**REQ-003-006 — Frontmatter remap for rules → instructions**

For each `.claude/rules/<name>.md`:
- If frontmatter has `paths:` or `applyTo:`, emit `.github/instructions/<name>.instructions.md` with frontmatter normalized: scoping key becomes `applyTo:`, `alwaysApply` and `priority` dropped, all other keys preserved verbatim, body unchanged.
- If frontmatter has neither `paths:` nor `applyTo:`, emit with synthesized `applyTo: "**"` (universal scope is the default for unscoped rules).

Rationale (Round 3 amendment): rules are universal across providers; there is no use case for Claude-only or Copilot-only rules. Severity field, governance-keyword scan, and conditional skip logic from earlier rounds are removed as unnecessary complication. A rule exists in `.claude/rules/` → it ships to `.github/instructions/`.

Verification: round-trip a fixture rule with `paths:` → output frontmatter has `applyTo:`; round-trip a fixture without scope → output has `applyTo: "**"`; existing rules generate without errors.

### State-driven

**REQ-003-007 — Hook generation is native and complete (D5, D10, D11)**
For each Claude hook script registered in `.claude/settings.json.hooks.<Event>[].hooks[]`, the hook generator shall:

1. **Map event name** per `eventRemap` in `copilot-cli.yaml`. Drop events listed in `eventDrop` with one-line WARN per dropped script.
2. **Copy the Python script** from `.claude/hooks/<Event>/<script>.py` (or `.claude/hooks/<script>.py` for flat-layout scripts) to `src/copilot-cli/hooks/<event>/<script>.py`.
3. **Emit a Copilot hook entry** under `src/copilot-cli/hooks/hooks.json`:
   ```json
   {
     "type": "command",
     "bash": "python3 -u \"./hooks/<event>/<script>.py\"",
     "powershell": "python3 -u \"./hooks/<event>/<script>.py\"",
     "cwd": ".",
     "timeoutSec": <copied or default 30>
   }
   ```
4. **Wrap with `version: 1`** at top level: `{"version": 1, "hooks": {<event>: [<entry>, ...]}}`.
5. **Translate `matcher` field** (D10): when source has `matcher: "<pattern>"`, the generator shall NOT emit the matcher to Copilot config. Instead it shall PREPEND a Python shim block at the top of the copied script. The shim shall:
   - **Buffer stdin once**: `_raw = sys.stdin.buffer.read()` immediately at script start, before any other code runs. The original script body is moved into a function `_original_main(stdin_bytes)`; the shim then replaces `sys.stdin` with `io.TextIOWrapper(io.BytesIO(_raw))` before calling `_original_main(_raw)`. This guarantees the original script reads the same bytes the shim inspected — no double-consumption.
   - **Pattern-match disambiguation** (explicit, not heuristic):
     - If pattern starts with `^` AND ends with `$` → treat as **regex**, use `re.fullmatch`.
     - If pattern matches `^[A-Za-z_][A-Za-z0-9_]*\(.*\)$` → treat as **tool-glob form** (e.g., `Bash(git commit*)`). Extract `toolName = pattern[:lparen]` and `argsGlob = pattern[lparen+1:-1]`. Match `toolName` exactly; match `toolArgs` against `argsGlob` via `fnmatch.fnmatchcase` AFTER whitespace normalization.
     - Otherwise → treat as **bare tool name match** against `toolName` (no args check).
   - **Whitespace normalization for glob matching**: collapse all runs of whitespace (`\s+`) in the comparison `toolArgs` (extracted from JSON) to a single space before `fnmatchcase`. The pattern itself is NOT normalized; authors write patterns assuming single spaces.
   - **Exit policy**: if pattern does NOT match, the shim shall `sys.exit(0)` silently (no-op = allow). If pattern DOES match, the shim shall call `_original_main(_raw)` and exit with whatever the original returns. **Crash policy**: any exception inside the shim itself (regex parse error, JSON decode failure on shim input) shall print to stderr and `sys.exit(2)` (config error) so Copilot CLI surfaces the failure rather than silently allowing the tool call.
   - **Idempotency**: the shim block shall be marked with a sentinel comment `# AUTO-GENERATED MATCHER SHIM (REQ-003-007)` at line 1 and `# END MATCHER SHIM` at the end. Subsequent generator runs detect the sentinels and replace, never stack.

Verification: install `copilot-cli-toolkit` into a clean Copilot CLI repo; `cat .claude/settings.json | jq '.hooks | keys'` and the generated `hooks.json` show consistent event coverage; trigger each event and observe behavior matches Claude side, accounting for documented event-coverage gaps.

### Unwanted behavior

**REQ-003-008 — Stale platform outputs are detected; manual edits opt out via sentinel**
If a `.claude/<artifact>/<name>` source is deleted, the corresponding `src/copilot-cli/<artifact>/<name>.<suffix>` (or `.github/instructions/<name>.instructions.md` for rules) shall be flagged for removal by the generator's `--check` mode (exit 1). Build's `--clean` mode shall remove orphans.

**Manual-edit opt-out**: any generated file containing the line `# NO-REGEN` (Python/markdown comment) or `<!-- NO-REGEN -->` (HTML comment for `.md` files), OR sitting next to a sidecar `<filename>.noregen` file, shall be treated by the generator as customer-owned. The generator shall:

- skip overwriting it during regeneration,
- skip removing it during `--clean`,
- emit a NOTICE listing the protected file in the audit log (REQ-003-011) so customers see drift between the protected file and what the source would generate today.

This protects emergency hotfixes a customer applied to `src/copilot-cli/` between releases without forcing them to commit changes upstream.

Verification: delete a source file → `python3 build/build_all.py --check` returns non-zero with orphan(s) listed; touch `src/copilot-cli/hooks/preToolUse/foo.py.noregen` → re-run generator → file unchanged; audit log lists `foo.py` as protected.

**REQ-003-009 — Path traversal in template paths is rejected**
Generators shall reject any `templates/platforms/copilot-cli.yaml` whose path values (`sourceDir`, `outputDir`, etc.) contain `..` or absolute paths, returning exit 2 (config error). Same applies to substitution-value paths.

Verification: malformed YAML causes deterministic config error; no file write occurs outside repo root.

**REQ-003-010 — `.claude/` is read-only to the build**
The build shall never write to `.claude/<artifact>/` or `.claude/settings.json`. All generation targets `src/copilot-cli/` or `.github/instructions/`. Customers editing `.claude/` directly shall not have their changes overwritten.

Verification: `git diff` after running `python3 build/build_all.py` shows changes only under `src/copilot-cli/` and `.github/instructions/`.

**REQ-003-011 — Generation audit log: bounded content + same-process CI parse**
The generator's NOTICE/WARN audit shall be written to `build/audit/GENERATION-AUDIT.md` (NOT inside `src/copilot-cli/` — keeps internal build metadata out of customer plugin install) and shall ALSO be emitted to stdout during `build_all.py` so CI can parse from the same process invocation.

**Bounded content scope** — the audit MUST contain ONLY:
- Event names dropped per D5 / `eventDrop` (e.g., `SubagentStop`).
- Rules emitted per REQ-003-006 (every rule ships; no skip logic).
- Matcher patterns translated to inline shims per REQ-003-007.
- Per-artifact output counts (input → output transform summary).

The audit MUST NOT contain:
- Absolute filesystem paths from the build host (e.g., `/home/<user>/...`).
- CI runner identifiers or commit SHAs unless `--include-build-meta` is explicitly passed.
- Internal repo paths outside `.claude/`, `templates/`, `src/copilot-cli/`, `.github/instructions/`, or `build/`.
- Script source content (file names only, no excerpts).

A blocklist regex shall reject any audit line that matches `^/home/|^/Users/|^/root/|@[a-f0-9]{40}\b|GITHUB_TOKEN|SECRET`. The generator shall fail (exit 2) if it would have emitted a line matching the blocklist.

**CI sequencing** — the parse-and-fail step shall consume the audit from `build_all.py` stdout (or `--audit-format json` output stream), NOT from the committed `build/audit/GENERATION-AUDIT.md` file. This prevents stale-read failures when generation and parse run in separate jobs.

Verification: `python3 build/build_all.py --audit-format json | jq '.audit'` returns valid JSON post-build listing all skipped artifacts; injection of a path-blocklist trigger string into source causes generator exit 2; build/audit/GENERATION-AUDIT.md contains no internal-path patterns.

### Optional / Complex

**REQ-003-012 — Backward compatibility window**
The existing `claude-agents` and `copilot-cli-agents` plugin entries in marketplace.json may co-exist with new `claude-toolkit` / `copilot-cli-toolkit` entries for one release cycle. The new entries shall be additive; legacy entries shall not be removed in the same PR.

Verification: `git log --diff-filter=D -- .claude-plugin/marketplace.json` shows no deletions in the introducing PR.

## Resolved questions (from prior round)

All Q1-Q6 from the prior round resolved by user; OQ-1 through OQ-4 from the analyst round resolved by docs research:

| OQ | Resolution |
|---|---|
| OQ-1 (plugin install path) | `~/.copilot/installed-plugins/<MARKETPLACE>/<PLUGIN-NAME>/` (verified) |
| OQ-2 (`${COPILOT_PLUGIN_ROOT}` env var) | **Does not exist**. Use `cwd` field in hook entries (defaults to plugin root). Scripts use relative paths. (D11) |
| OQ-3 (event mapping completeness) | Mapping verified. Claude events not in Copilot (`SubagentStop`, `PermissionRequest`, `Notification`, `PreCompact`) are dropped with WARN. |
| OQ-4 (`.github/agents/` for VSCode) | VSCode reads the same `.github/agents/` files Copilot uses; D3 keeps it out of separate plugin scope; existing VSCode-bound outputs stay untouched. |

## Residual open questions

1. **`commands` field in Copilot CLI plugin.json** — docs list it as a component path but do not document the file format inside. Confirm before relying on D7's command→skill bridge. **Owner:** Richard. **Mitigation:** D7 maps to skills, not commands, so this is a future-proofing question rather than a blocker.
2. **`applyTo:` in CLI vs cloud** — docs explicitly say path-specific instructions are "currently only supported for Copilot cloud agent and Copilot code review." If Copilot CLI does NOT load `.github/instructions/*.instructions.md`, REQ-003-006 ships dead artifacts. D8 mitigates with WARN; need empirical test post-merge. **Owner:** Richard.
3. **`hooks/hooks.json` `description` key** — Claude side has it (added in PR #1795). Copilot schema does not document it. Test: does Copilot CLI tolerate the extra key, or reject the manifest? **Owner:** Richard.
4. **Bash + PowerShell parity** — REQ-003-007 emits the same `python3 ./...` invocation in both. Confirm Python is on Copilot CLI runner PATH on Windows + macOS + Linux. **Owner:** Richard.

## Traceability

- **Wiki interop matrix**: `~/Documents/Mobile/wiki/comparisons/CLI Harness Instruction Interoperability.md`
- **Copilot CLI plugin reference**: https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference
- **Copilot CLI hooks configuration**: https://docs.github.com/en/copilot/reference/hooks-configuration
- **Copilot CLI use-hooks tutorial**: https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-hooks
- **Copilot CLI plugins-creating**: https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/plugins-creating
- **Copilot CLI command reference**: https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference
- **Custom instructions format**: https://docs.github.com/copilot/customizing-copilot/adding-custom-instructions-for-github-copilot
- **Existing implementation**: `build/generate_agents.py`, `build/generate_agents_common.py`, `templates/platforms/*.yaml`
- **Existing validator**: `build/scripts/validate_marketplace_counts.py`
- **Marketplace**: `.claude-plugin/marketplace.json`
- **Canonical content roots**: `.claude/{agents,skills,hooks,commands,rules}/`, `.claude/settings.json`
- **Related ADRs**: ADR-006 (no logic in YAML), ADR-042 (Python migration strategy), ADR-007 (memory-first)
- **Aftermath of**: PR #1773 (regression) + PR #1795 (P0 fix) — informs schema rigor

## Risks (pre-mortem candidates)

- **Hook semantic drift** — Copilot CLI lacks 4 Claude events. Some Claude-side gating relies on these. REQ-003-007 drops with WARN, but customers may experience silent permission grant differences on Copilot side. **Mitigation:** REQ-003-011 audit log surfaces; CI gate on audit threshold.
- **`applyTo:` not yet consumed by Copilot CLI** — D8 + RQ #2 acknowledge. Generated `.github/instructions/` files may not actually scope on Copilot CLI installs today. **Mitigation:** WARN emit; revisit when Copilot CLI extends path-specific instructions to non-cloud-agent flows.
- **Matcher shim correctness** — REQ-003-007 step 5 inlines a Python regex/glob filter into copied scripts. Implementation bugs could open security holes (e.g., a `Bash(git push*)` matcher that fails to match `Bash(git  push --force)` due to whitespace). **Mitigation:** parameterize shim, exhaustive unit test per matcher pattern in source `.claude/settings.json`, snapshot regression tests.
- **Plugin install path mismatch** — verified for marketplace install; direct install differs (`_direct/`). Check downstream tooling assumes marketplace path.
- **YAML logic ban (ADR-006)** — `copilot-cli.yaml` declares mappings (suffix, frontmatter remap, event remap, drop list). Justification: configuration data, not control flow. Pre-empt ADR review.
- **Skill generation from commands** (D7) — `user-invocable: true` makes the skill fire as `/SKILL-NAME`. If a Claude command is `/spec` and the generated Copilot skill is `spec`, the Copilot CLI invocation matches. Validate the agent ID derivation (Copilot derives agent/skill ID from filename) does not collide.
- **Hooks `description` field tolerance** (RQ #3) — extra keys may be silently tolerated or rejected. PR #1795 cursor[bot] reviewer flagged similar issue on Claude side. **Mitigation:** strip `description` for Copilot output; preserve only documented Copilot keys.
- **Python on Windows runner PATH** (RQ #4) — `python3` invocation in `powershell` block requires Python on Windows PATH. Some Copilot CLI Windows hosts may have only `python.exe`. **Mitigation:** detect platform in script; or use `py -3 -u` form which is Windows Python launcher.

## Implementation phasing (informational; not part of acceptance criteria)

Suggested order:

1. **Phase 1**: Define `templates/platforms/copilot-cli.yaml` + write `validate_templates_schema.py` (REQ-003-002).
2. **Phase 2**: Generalize `validate_marketplace_counts.py` config-driven (REQ-003-004).
3. **Phase 3**: Implement `generate_agents.py` v2 + `generate_skills.py` (lowest-transform artifacts).
4. **Phase 4**: Implement `generate_commands.py` (command→skill bridge per D7).
5. **Phase 5**: Implement `generate_rules.py` with conditional emit (REQ-003-006, D8).
6. **Phase 6**: Implement `generate_hooks.py` with matcher shim (REQ-003-007, D10).
7. **Phase 7**: Update `marketplace.json` to two-plugin model; remove legacy entries after one release (REQ-003-012).
