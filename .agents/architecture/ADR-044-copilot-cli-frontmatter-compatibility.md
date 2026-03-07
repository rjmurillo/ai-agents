# ADR-044: Copilot CLI Frontmatter Compatibility

## Status

Accepted

## Date

2026-02-01

## Context

Our CI pipeline runs 6 parallel Copilot CLI agent reviews (security, qa, analyst, architect, devops, roadmap) in `ai-pr-quality-gate.yml`. After Copilot CLI auto-updated from version 0.0.382 to 0.0.400, all 6 jobs failed with identical errors:

```text
No such agent: analyst, available: adr-generator, debug, janitor, prompt-builder
```

The `available` list shows only built-in agents. Our 18 custom agents in `.github/agents/` were silently rejected without error messages in standard output.

### Root Cause

Copilot CLI 0.0.398+ introduced a regression in frontmatter field validation (tracked upstream as [github/copilot-cli#1195](https://github.com/github/copilot-cli/issues/1195)). Previously supported fields (`model`, `handoffs`, `argument-hint`) are now rejected as "unsupported." Custom agent `.agent.md` files with these fields are rejected silently. Rejection is logged as WARNING in debug logs but not surfaced to users.

Specific failures:

1. **`argument-hint` field**: All 18 shared agents had this field. Debug logs show `agent uses unsupported fields: argument-hint`. This was a working, supported field prior to 0.0.398.
2. **`model` field**: 6 agents had this field with an incorrect value (`Claude Opus 4.5 (anthropic)`) synced from VS Code platform config. The `model` field is a valid Copilot CLI parameter for specifying which model an agent should use, but it is also affected by the same regression. The incorrect value is a separate issue from the regression.
3. **YAML parse errors**: 4 agents (code-reviewer, code-simplifier, comment-analyzer, pr-test-analyzer) had YAML parse errors from complex description values. These are Claude Code-only agents not used in CI, so they did not affect CI functionality.

The only fields accepted in 0.0.398+ are: `name`, `description`, `tools`. This is a regression from previous behavior where `model`, `handoffs`, and `argument-hint` were all valid.

### Origin of Removed Fields

The `argument-hint` field was introduced when Copilot CLI added interactive agent invocation. It provided a prompt suggestion in interactive mode (e.g., "Describe the topic to research"). This was a supported feature that worked through 0.0.382 and was broken by the regression in 0.0.398+.

The `model` field is a valid Copilot CLI parameter for specifying which AI model an agent should use. It is also affected by the 0.0.398+ regression. In our agents, the `model` value was incorrect: `Claude Opus 4.5 (anthropic)` was the VS Code platform value from `templates/platforms/vscode.yaml`, not a valid Copilot CLI model identifier. The build system (`copilot-cli.yaml`) had `model: null`, so the field should not have appeared in Copilot CLI output. The 6 affected agents had the field from an earlier sync before the build system properly separated platform configs.

### Auto-Update Bypass

The npm package `@github/copilot@0.0.382` contains an `npm-loader.js` that delegates to a platform-specific binary. This binary auto-updates independently of the npm package version.

Result: `npm list -g` shows version 0.0.382 while `copilot --version` reports 0.0.400. This bypasses npm version pinning strategies.

### Reproduction

1. Install Copilot CLI 0.0.400: `npm install -g @github/copilot`
2. Move user agents aside: `mv ~/.copilot/agents ~/.copilot/agents.bak`
3. From repo root: `copilot --agent analyst --prompt "Reply OK"` - FAILS with "No such agent"
4. Run with debug: `copilot --log-level all --agent analyst --prompt "Reply OK"` - logs show `agent uses unsupported fields: argument-hint`
5. Remove `argument-hint` from agent file - agent loads successfully

### Debug Log Evidence

```text
[WARNING] agent uses unsupported fields: argument-hint
[WARNING] skipping agent due to validation failure
```

These warnings appear only with `--log-level all` flag. Default output shows no error explanation.

## Decision

1. **Pin Copilot CLI to 0.0.397** in CI (`npm install -g @github/copilot@0.0.397`) with `--no-auto-update` flag on all invocations. This is the last version before the frontmatter regression.
2. **Fix `model` field value** from VS Code format (`Claude Opus 4.5 (anthropic)`) to Copilot CLI format (`claude-opus-4.5`). Update `templates/platforms/copilot-cli.yaml` to generate correct values.
3. **Retain `argument-hint` and `model` fields** in all agent frontmatter. These are valid Copilot CLI fields broken by an upstream regression, not unsupported features.
4. **Add version verification** to CI. After install, verify `copilot --no-auto-update --version` matches the pinned version and warn if the binary auto-updated.
5. **Monitor [github/copilot-cli#1195](https://github.com/github/copilot-cli/issues/1195)** for resolution. When the regression is fixed, evaluate upgrading past 0.0.397.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Remove unsupported fields and upgrade | Works with any CLI version | Loses `model` and `argument-hint` functionality | Fields are valid; the CLI is broken, not the fields |
| Keep broken version and wait | No code changes needed | Blocks CI indefinitely, no timeline from GitHub | Unacceptable business impact |
| Pin version without `--no-auto-update` | Simple npm pin | Binary auto-update may bypass npm pin | `--no-auto-update` flag adds defense-in-depth |
| Migrate to Claude Code CLI | Eliminates Copilot CLI dependency | Different feature set, significant migration | Disproportionate effort for a regression that will be fixed |
| Do nothing (status quo) | No effort | CI remains broken for all PRs | Unacceptable |

### Trade-offs

**Accepted**: Pinning to 0.0.397 means CI does not receive Copilot CLI improvements until we explicitly upgrade. npm deprecation warning notes "a bug in this version caused invalid session id errors." This is acceptable because CI runs are non-interactive and session IDs do not affect agent review output.

**Accepted**: Ongoing monitoring of [github/copilot-cli#1195](https://github.com/github/copilot-cli/issues/1195) for when to upgrade.

**Avoided**: No loss of agent functionality. `argument-hint` and `model` fields remain operational.

### Model Field Behavior (Validated)

Testing on 0.0.397 revealed that the frontmatter `model` field is accepted without warnings but does **not** override the default model for agent invocations. All agents default to `claude-sonnet-4.5` unless `--model` is passed on the CLI.

| Invocation | Model Used |
|------------|-----------|
| `copilot --agent analyst --prompt "..."` | `claude-sonnet-4.5` (CLI default) |
| `copilot --agent analyst --model claude-opus-4.5 --prompt "..."` | `claude-opus-4.5` |

The CI action already passes `--model claude-opus-4.5` via the `copilot-model` input (default value). The frontmatter `model` field serves as declarative metadata for the agent's intended model, but the CLI flag is the mechanism that controls actual model selection. This means the `model` field in agent frontmatter functions as documentation of intent rather than runtime configuration on 0.0.397. Future Copilot CLI versions may change this behavior.

## Consequences

### Positive

- CI pipeline restored to working state on 0.0.397
- All 18 custom agents load with full frontmatter (`argument-hint`, `model`, `tools`)
- `model` field corrected from VS Code format to Copilot CLI format (`claude-opus-4.5`)
- Build system now generates platform-correct model values for both Copilot CLI and VS Code
- Version verification in CI detects binary auto-update bypass

### Negative

- Pinned to 0.0.397 until upstream regression is fixed; no new CLI features
- npm deprecation warning on 0.0.397 ("invalid session id errors") visible in CI logs
- Must monitor github/copilot-cli#1195 for regression fix

### Neutral

- `.github/agents/` synced from `src/copilot-cli/` build output (18 shared agents; 6 additional Claude Code-only agents maintained separately)
- `--no-auto-update` flag added to all CI copilot invocations

## Reversibility Assessment

**Rollback capability**: Version pin can be changed to any version. Fields are preserved in templates and regenerated via build system.

**Vendor lock-in**: Copilot CLI controls the frontmatter schema. We have no influence over future changes. Version pinning with `--no-auto-update` and version verification provide defense-in-depth.

**Exit strategy**: If Copilot CLI continues to introduce breaking changes, the CI quality gate can be migrated to use Claude Code CLI directly. The agent prompt content (body of `.agent.md` files) is platform-independent. Only the frontmatter differs between platforms, and the build system already handles this separation.

**Auto-update risk**: The binary auto-update mechanism means any CI run could receive a new version without warning. npm version pinning alone is insufficient. The `--no-auto-update` flag on all invocations plus version verification after install provides layered defense.

## Confirmation

Implementation compliance confirmed by testing on 2026-02-01:

1. **Version verification**: CI installs `@github/copilot@0.0.397` and `copilot --no-auto-update --version` outputs `0.0.397`. Warning emitted if binary auto-updated.
2. **Local validation**: 9 agents tested (analyst, explainer, security, architect, critic, devops, qa, roadmap, skillbook). All produce exit code 0 with zero validation warnings on 0.0.397 with `--log-level all`.
3. **Build system verification**: `pwsh build/Generate-Agents.ps1` generates `model: claude-opus-4.5` for Copilot CLI and `model: Claude Opus 4.5 (copilot)` for VS Code.
4. **Model behavior**: Frontmatter `model` field is accepted but does not control runtime model selection. CI uses `--model` CLI flag (default: `claude-opus-4.5`).
5. **Regression confirmation**: Same agents fail on 0.0.400 with `agent uses unsupported fields: argument-hint`, confirming the regression.

## Implementation Notes

### Files Modified

**CI Action**:

- `.github/actions/ai-review/action.yml` - Pin `npm install -g @github/copilot@0.0.397`, add `--no-auto-update` to all invocations, add version verification

**Platform Config**:

- `templates/platforms/copilot-cli.yaml` - Changed `model: null` to `model: "claude-opus-4.5"`

**Build System**:

- `build/Generate-Agents.Common.psm1` - Restored `argument-hint` in field order array

**Template Layer** (18 files):

- `templates/agents/*.shared.md` - `argument-hint` retained (was already present)

**Generated Output** (36 files):

- `src/copilot-cli/*.agent.md` - Regenerated with `argument-hint` and `model: claude-opus-4.5`
- `src/vs-code-agents/*.agent.md` - Regenerated with `model: Claude Opus 4.5 (copilot)`
- `.github/agents/*.agent.md` - 18 shared agents synced from `src/copilot-cli/` build output

Note: `.github/agents/` contains 24 total agent files. 18 are shared agents generated from templates. 6 are Claude Code-only agents (code-reviewer, code-simplifier, comment-analyzer, pr-test-analyzer, silent-failure-hunter, type-design-analyzer) maintained separately outside the build system.

### Monitoring Strategy

**Owner**: DevOps review during quarterly dependency audit.

**Detection**: Version verification in CI warns if binary auto-updated past 0.0.397. Agent loading failures caught by non-zero exit code from copilot invocation.

**Escalation**: Monitor [github/copilot-cli#1195](https://github.com/github/copilot-cli/issues/1195) for resolution. When fixed, evaluate upgrading and removing the version pin.

## Related Decisions

- ADR-036: Two-Source Agent Template Architecture (template inheritance model affected by this change)
- ADR-040: Skill Frontmatter Standardization (parallel effort for Claude Code skills)
- Issue #19: Copilot CLI user-level agents not loading (prior agent loading bug, different root cause)
- Issue #907: Epic: Claude Code Compatibility for VSCode and Copilot CLI
- [github/copilot-cli#1195](https://github.com/github/copilot-cli/issues/1195): Regression: Agent frontmatter fields model, handoffs, argument-hint now marked as unsupported

## Cross-Platform Frontmatter Reference

Our agents target three platforms. Each platform defines its own frontmatter schema. The build system (`Generate-Agents.ps1`) transforms shared templates into platform-specific output.

### GitHub Copilot Custom Agents (`.github/agents/*.agent.md`)

Source: <https://docs.github.com/en/copilot/reference/custom-agents-configuration>

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | No | Agent name (defaults to filename) |
| `description` | string | No | Agent description shown in selection UI |
| `tools` | array | No | Tools available to the agent |
| `infer` | boolean | No | Allow model to infer tool use |
| `mcp-servers` | object | No | MCP server configuration |
| `metadata` | object | No | Custom metadata key-value pairs |
| `target` | string | No | Target platform (`vscode`, `github-copilot`) |

Additional fields supported in Copilot CLI (pre-0.0.398):

| Field | Type | Description | Status |
|-------|------|-------------|--------|
| `model` | string | AI model identifier (e.g., `claude-opus-4.5`) | Regressed in 0.0.398+ |
| `argument-hint` | string | Prompt suggestion for interactive mode | Regressed in 0.0.398+ |
| `handoffs` | array | Agent-to-agent handoff configuration | Regressed in 0.0.398+ |

### Claude Code Subagents (`.claude/agents/*.md`)

Source: <https://code.claude.com/docs/en/sub-agents#supported-frontmatter-fields>

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Display name for the agent |
| `description` | string | Yes | Agent description and usage guidance |
| `tools` | array | No | Allowed tools (e.g., `Bash`, `Read`, `Edit`) |
| `disallowedTools` | array | No | Explicitly blocked tools |
| `model` | enum | No | `sonnet`, `opus`, `haiku`, or `inherit` |
| `permissionMode` | string | No | Permission level for tool use |
| `skills` | array | No | Skills available to the agent |
| `hooks` | object | No | Event hooks configuration |

### Platform Model Value Mapping

| Platform | Model Field Value | Source Config |
|----------|-------------------|--------------|
| Copilot CLI | `claude-opus-4.5` | `templates/platforms/copilot-cli.yaml` |
| VS Code | `Claude Opus 4.5 (copilot)` | `templates/platforms/vscode.yaml` |
| Claude Code | `opus` | Hardcoded in `.claude/agents/` (not generated) |

### Build System Field Handling

The build system uses platform config to determine which fields appear in output:

- `includeNameField: true` (Copilot CLI) or `false` (VS Code) controls `name` field presence
- `model` value is sourced from platform config; `null` suppresses the field entirely
- `argument-hint` is passed through from shared templates to both platforms
- `tools_vscode` and `tools_copilot` template keys map to `tools` in platform output

## References

- GitHub Copilot custom agents configuration: <https://docs.github.com/en/copilot/reference/custom-agents-configuration>
- Claude Code subagent frontmatter: <https://code.claude.com/docs/en/sub-agents#supported-frontmatter-fields>
- Copilot CLI npm package: <https://www.npmjs.com/package/@github/copilot>
- [github/copilot-cli#1195](https://github.com/github/copilot-cli/issues/1195): Regression: frontmatter fields marked unsupported
- [github/copilot-cli#1199](https://github.com/github/copilot-cli/discussions/1199): Discussion: reverting to older version
- Agent template architecture: `templates/agents/README.md`
- Build system documentation: `build/README.md`
- CI workflow: `.github/workflows/ai-pr-quality-gate.yml`

---

*Template Version: 1.0*
*Issue: Copilot CLI 0.0.400 breaking change*
*Impact: 18 templates, 36 generated files, CI pipeline*
