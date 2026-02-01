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

Copilot CLI 0.0.400 introduced strict frontmatter field validation. Custom agent `.agent.md` files with unsupported frontmatter fields are rejected silently. Rejection is logged as WARNING in debug logs but not surfaced to users.

Specific failures:

1. **`argument-hint` field**: All 18 shared agents had this field. Debug logs show `agent uses unsupported fields: argument-hint`.
2. **`model` field**: 6 agents had this field (VS Code-targeted agents that were synced to `.github/agents/`). The `model` field controlled model selection for VS Code Copilot Chat but had no effect in Copilot CLI. Removing it has no impact on CI agent behavior.
3. **YAML parse errors**: 4 agents (code-reviewer, code-simplifier, comment-analyzer, pr-test-analyzer) had YAML parse errors from complex description values. These are Claude Code-only agents not used in CI, so they did not affect CI functionality.

The supported frontmatter fields in 0.0.400 are: `name`, `description`, `tools`. Only these three fields are allowed.

### Origin of Removed Fields

The `argument-hint` field was introduced when Copilot CLI added interactive agent invocation. It provided a cosmetic prompt suggestion in interactive mode (e.g., "Describe the topic to research"). No Copilot CLI documentation confirmed `argument-hint` as a supported field. It worked in 0.0.382 because earlier versions did not validate frontmatter fields. This project was using an undocumented feature that happened to work.

The `model` field was defined in the VS Code agent platform configuration (`templates/platforms/vscode.yaml`). The build system incorrectly included it in some `.github/agents/` files that were synced from VS Code output. It was never intended for Copilot CLI agents.

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

1. Remove `argument-hint` and `model` fields from all Copilot CLI agent frontmatter. Use only fields confirmed supported: `name`, `description`, `tools`.
2. Add pre-flight agent validation to the CI quality gate workflow. Before running agent reviews, validate that required agents are loadable via `copilot --list-agents`.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Pin Copilot CLI version in CI | Prevents future breakage | Auto-update mechanism bypasses npm version pinning | Ineffective due to binary auto-update; listed as defense-in-depth only |
| Add `--no-auto-update` flag | Prevents updates | Flag does not prevent initial binary download from being latest version | Does not solve version pinning |
| Keep `argument-hint` and wait | No code changes needed | Blocks CI indefinitely, no timeline from GitHub | Unacceptable business impact |
| Wrap `argument-hint` in extension | Could enable custom fields | No extension mechanism exists in Copilot CLI | Not technically feasible |
| Do nothing (status quo) | No effort | CI remains broken for all PRs | Unacceptable |

### Trade-offs

**Accepted**: Loss of `argument-hint` UI suggestion feature. This field provided cosmetic prompt suggestions in Copilot CLI interactive mode. It was an undocumented feature, not a supported API.

**Accepted**: Ongoing monitoring burden. Future Copilot CLI releases may change frontmatter field support again. Mitigated by pre-flight validation in CI.

**Avoided**: CI pipeline remains functional. Agent execution logic unaffected (argument hints were not used in agent behavior).

## Consequences

### Positive

- CI pipeline restored to working state
- All 18 custom agents load successfully in Copilot CLI 0.0.400
- Agents validate successfully with debug logging enabled
- Template architecture maintained consistency across all generated agents
- Pre-flight validation prevents future silent agent rejection in CI

### Negative

- `argument-hint` field content removed from all templates and generated files
- Interactive Copilot CLI UI no longer shows argument suggestions for custom agents
- Must monitor future Copilot CLI releases for frontmatter schema changes

### Neutral

- Build system field order updated to remove `argument-hint` from generation pipeline
- `.github/agents/` synced from `src/copilot-cli/` build output (18 shared agents; 6 additional Claude Code-only agents maintained separately)
- No functional change to agent execution logic (argument hints were cosmetic)

## Reversibility Assessment

**Rollback capability**: `argument-hint` values are preserved in git history. Restoring them requires reverting the template changes and regenerating. Low effort, no data loss.

**Vendor lock-in**: Copilot CLI controls the frontmatter schema. We have no influence over future changes. The pre-flight validation step mitigates this by detecting breakage early rather than silently failing.

**Exit strategy**: If Copilot CLI continues to introduce breaking changes, the CI quality gate can be migrated to use Claude Code CLI directly. The agent prompt content (body of `.agent.md` files) is platform-independent. Only the frontmatter differs between platforms, and the build system already handles this separation.

**Auto-update risk**: The binary auto-update mechanism means any CI run could receive a new Copilot CLI version without warning. npm version pinning is ineffective. The `--no-auto-update` flag is recommended as defense-in-depth but is not guaranteed to work. The pre-flight validation is the primary defense.

## Confirmation

Implementation compliance will be confirmed by:

1. **CI pre-flight check**: `copilot --list-agents | grep -q analyst` runs before quality gate. Exit code 1 blocks the pipeline with a clear error message.
2. **Local verification**: `copilot --log-level all --agent analyst --prompt "test"` produces no validation warnings.
3. **Build system verification**: `pwsh build/Generate-Agents.ps1` succeeds and produces no `argument-hint` in Copilot CLI output.

## Implementation Notes

### Files Modified

**Template Layer** (18 files):

- `templates/agents/*.shared.md` - Removed `argument-hint` from frontmatter

**Build System**:

- `build/Generate-Agents.Common.psm1` - Removed `argument-hint` from field order array

**Generated Output** (36 files):

- `src/copilot-cli/*.agent.md` - Regenerated via `pwsh build/Generate-Agents.ps1`
- `src/vs-code-agents/*.agent.md` - Regenerated (VS Code agents retain `model` field per platform config)
- `.github/agents/*.agent.md` - 18 shared agents synced from `src/copilot-cli/` build output

Note: `.github/agents/` contains 24 total agent files. 18 are shared agents generated from templates. 6 are Claude Code-only agents (code-reviewer, code-simplifier, comment-analyzer, pr-test-analyzer, silent-failure-hunter, type-design-analyzer) maintained separately outside the build system.

### CI Hardening (Required)

1. **Pre-flight validation** (REQUIRED): Add `copilot --list-agents | grep -q analyst` before quality gate runs. Failure blocks pipeline with clear error.
2. **Version logging** (REQUIRED): Log `copilot --version` output at start of CI job for diagnostics.

### CI Hardening (Defense-in-Depth)

3. Add `--no-auto-update` to CI copilot installation (may not be effective, but low cost)
4. Pin Copilot CLI npm version despite auto-update behavior (establishes intent, even if binary updates independently)

### Monitoring Strategy

**Owner**: DevOps review during quarterly dependency audit.

**Detection**: Pre-flight validation in CI catches agent loading failures before they silently skip reviews. This is the primary detection mechanism.

**Escalation**: If pre-flight validation fails in CI, the pipeline blocks and produces a clear error message. This replaces the previous failure mode (silent agent rejection with no diagnostic output).

## Related Decisions

- ADR-036: Two-Source Agent Template Architecture (template inheritance model affected by this change)
- ADR-040: Skill Frontmatter Standardization (parallel effort for Claude Code skills)
- Issue #19: Copilot CLI user-level agents not loading (prior agent loading bug, different root cause)
- Issue #907: Epic: Claude Code Compatibility for VSCode and Copilot CLI

## References

- GitHub Copilot CLI: <https://githubnext.com/projects/copilot-cli>
- Copilot CLI npm package: <https://www.npmjs.com/package/@github/copilot>
- Agent template architecture: `templates/agents/README.md`
- Build system documentation: `build/README.md`
- CI workflow: `.github/workflows/ai-pr-quality-gate.yml`

---

*Template Version: 1.0*
*Issue: Copilot CLI 0.0.400 breaking change*
*Impact: 18 templates, 36 generated files, CI pipeline*
