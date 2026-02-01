# Copilot CLI Frontmatter Regression Runbook

**Statement**: Pin Copilot CLI version and validate agent frontmatter when CLI updates break agent loading.

**Context**: When Copilot CLI updates cause "No such agent" errors, the root cause is likely frontmatter field validation regression. This runbook documents the investigation and resolution process from the 0.0.398+ regression (github/copilot-cli#1195).

**Evidence**: ADR-044, PR #1024, tested on 0.0.397 vs 0.0.400 (2026-02-01).

**Atomicity**: 95% | **Impact**: 9

## Symptoms

- CI agent review jobs fail with: `No such agent: [name], available: adr-generator, debug, janitor, prompt-builder`
- Available list shows only built-in agents; custom agents silently rejected
- No error in standard output; only visible with `--log-level all`

## Diagnostic Steps

### Step 1: Check CLI Version

```bash
copilot --no-auto-update --version
```

Compare with known good version (currently 0.0.397). The binary may auto-update independently of npm version.

### Step 2: Test Agent Loading with Debug Logs

```bash
copilot --no-auto-update --log-level all --agent [name] --prompt "Reply with only the word OK"
```

Check stderr for:
- `agent uses unsupported fields: [field]` - frontmatter regression
- `skipping agent due to validation failure` - agent rejected
- YAML parse errors - malformed frontmatter

### Step 3: Identify Failing Fields

Strip fields one at a time from a test agent to isolate which field causes rejection.

Known fields affected by 0.0.398+ regression:
- `argument-hint`
- `model`
- `handoffs`

### Step 4: Check Upstream Issue

Monitor: https://github.com/github/copilot-cli/issues/1195

## Resolution Pattern

### Pin to Last Known Good Version

```bash
npm install -g @github/copilot@0.0.397
```

Always use `--no-auto-update` on all invocations to prevent binary self-update.

### Version Verification

After install, verify the binary matches:

```bash
VERSION=$(copilot --no-auto-update --version 2>&1 | head -1)
echo "$VERSION"  # Should match pinned version
```

### Validate Agent Loading

Test each agent with debug logging. Zero warnings expected:

```bash
for agent in analyst architect critic devops explainer security qa roadmap; do
  copilot --no-auto-update --log-level all --agent "$agent" --prompt "Reply OK" 2>&1 | grep -i warning
done
```

## Key Findings

### Model Field Behavior

The frontmatter `model` field is accepted by 0.0.397 without warnings but does NOT control runtime model selection. Model must be passed via `--model` CLI flag.

| Invocation | Model Used |
|------------|-----------|
| No `--model` flag | `claude-sonnet-4.5` (CLI default) |
| `--model claude-opus-4.5` | `claude-opus-4.5` |

CI handles this via `copilot-model` action input (default: `claude-opus-4.5`).

### Auto-Update Bypass

npm-loader.js delegates to a platform-specific binary that auto-updates independently. `npm list -g` may show 0.0.382 while `copilot --version` reports 0.0.400. npm version pinning alone is insufficient; `--no-auto-update` is required.

### Platform-Specific Model Values

| Platform | Model Value | Config File |
|----------|------------|-------------|
| Copilot CLI | `claude-opus-4.5` | `templates/platforms/copilot-cli.yaml` |
| VS Code | `Claude Opus 4.5 (copilot)` | `templates/platforms/vscode.yaml` |
| Claude Code | `opus` | Hardcoded in `.claude/agents/` |

### Valid Frontmatter Fields by Platform

**Copilot CLI** (`.github/agents/`): name, description, tools, argument-hint, model, handoffs, infer, mcp-servers, metadata, target

**Claude Code** (`.claude/agents/`): name, description, tools, disallowedTools, model, permissionMode, skills, hooks

**GitHub.com Copilot** (web): name, description, tools, infer, mcp-servers, metadata, target (model/argument-hint/handoffs not supported on web)

## Related Files

- ADR: `.agents/architecture/ADR-044-copilot-cli-frontmatter-compatibility.md`
- CI action: `.github/actions/ai-review/action.yml`
- Platform configs: `templates/platforms/copilot-cli.yaml`, `templates/platforms/vscode.yaml`
- Build system: `build/Generate-Agents.Common.psm1`
- Agent templates: `templates/agents/*.shared.md`
- Generated output: `src/copilot-cli/`, `src/vs-code-agents/`, `.github/agents/`

## Investigation Narrative (2026-02-01)

This section documents the full investigation sequence including wrong turns. Future agents should read this to avoid repeating the same mistakes.

### Initial Misdiagnosis

1. CI failed after Copilot CLI auto-updated from 0.0.382 to 0.0.400.
2. Error: "No such agent: analyst, available: adr-generator, debug, janitor, prompt-builder"
3. Initial analysis: `argument-hint` was assumed to be an undocumented/unsupported field. `model` value `Claude Opus 4.5 (anthropic)` was clearly wrong (VS Code format, not CLI format).
4. **Wrong action**: Removed `argument-hint` and `model` from all agents. This worked on 0.0.400 but lost valid functionality.

### Course Correction

5. User identified that `model` is a valid Copilot CLI parameter; only the value was incorrect. Filed as github/copilot-cli#1195.
6. Issue #1195 confirmed: `model`, `argument-hint`, and `handoffs` are valid fields broken by a regression in 0.0.398+.
7. **Corrected action**: Pin to 0.0.397 (last working version), restore all fields, fix model value.

### Key Lesson

When an upstream tool rejects previously working configuration, verify whether it is a regression before adapting to the new behavior. Check the tool's issue tracker. The tool may be broken, not your configuration.

### Validation Sequence

1. Installed 0.0.397 locally, tested analyst agent with `argument-hint` and `model: claude-opus-4.5`. Passed with zero warnings.
2. Tested same agent on 0.0.400. Failed with `agent uses unsupported fields: argument-hint`. Confirmed regression.
3. Tested 9 agents (analyst, explainer, security, architect, critic, devops, qa, roadmap, skillbook). All exit 0, zero warnings.
4. Discovered model field is accepted but does not control runtime model selection. `--model` CLI flag is required.
5. Validated CI action YAML structurally (Python yaml.safe_load, version pin checks, --no-auto-update checks).
6. Ran `gh act` Docker simulation. Agent loaded, ran full review, produced PASS verdict.

## Local Workflow Testing with gh act

`gh act` (nektos/gh-act) can simulate GitHub Actions locally in Docker.

### Setup

```bash
gh extension list | grep act
docker pull catthehacker/ubuntu:act-latest
```

### Dry Run (Structure Validation)

```bash
gh act pull_request -n -W .github/workflows/ai-pr-quality-gate.yml
```

### Full Run (Single Job)

```bash
TOKEN=$(gh auth token)
gh act pull_request \
  -j "analyst-review" \
  -W .github/workflows/ai-pr-quality-gate.yml \
  -s "GITHUB_TOKEN=$TOKEN" \
  -s "BOT_PAT=$TOKEN" \
  -e event.json \
  -P ubuntu-latest=catthehacker/ubuntu:act-latest
```

### Known act Limitations

- PowerShell composite action steps fail with "Exec format error"
- actions/upload-artifact produces warnings in local mode
- Some GitHub context variables may be missing

## Anti-Pattern

Do NOT remove valid frontmatter fields to accommodate a regression. Pin the version instead. Fields like `model` and `argument-hint` are valid Copilot CLI features. The CLI is broken, not the fields.
