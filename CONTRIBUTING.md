# Contributing to AI Agent System

<!-- # taste-lint: ignore file-size -->
<!-- Long-form contributor guide; prose docs are not split into modules. -->

Thank you for your interest in contributing to this project. This guide explains how to contribute effectively, with special attention to the agent template system.

## Table of Contents

- [Getting Started](#getting-started)
- [Git Configuration](#git-configuration)
- [Agent Template System](#agent-template-system)
- [How to Modify an Agent](#how-to-modify-an-agent)
- [How to Add a New Agent](#how-to-add-a-new-agent)
- [Validating Prompt, Skill, and Agent Changes (ADR-057)](#validating-prompt-skill-and-agent-changes-adr-057)
- [Platform Configuration](#platform-configuration)
- [Pre-Commit Hooks](#pre-commit-hooks)
- [Pre-Push Hooks](#pre-push-hooks)
- [Session Protocol](#session-protocol)
- [Running Tests](#running-tests)
- [Copilot CLI Version Management](#copilot-cli-version-management)
- [ADR-to-Protocol Sync Process](#adr-to-protocol-sync-process)
- [Pull Request Guidelines](#pull-request-guidelines)
  - [Commit Count Thresholds](#commit-count-thresholds)
- [Third-Party License Attribution](#third-party-license-attribution)
- [Security Scanning](#security-scanning)

## Getting Started

### Prerequisites

**Required Versions:**

- **Python 3.14.x** (primary scripting language per ADR-042)
- **UV** (Python package manager, see [installation](https://docs.astral.sh/uv/getting-started/installation/))

### Setup Steps

1. Fork the repository
2. Clone your fork locally
3. **Install Python 3.14.x** (see Prerequisites above)
4. **Set up Python environment**: `uv sync --frozen --extra dev` (creates `.venv` from `uv.lock` without re-resolving it). This matches the locked environment the pre-push gate and CI use. On managed containers, `scripts/bootstrap-vm.sh` runs this automatically.
5. Configure Git for cross-platform development (see [Git Configuration](#git-configuration) below)
6. Install Git hooks: `uv run --frozen lefthook install --reset-hooks-path`, then verify with `uv run --frozen lefthook check-install`
7. Make your changes following the guidelines below
8. Submit a pull request

**After setup, quality gates are automated.** Pre-commit hooks run ruff (Python) and markdownlint on staged files. Pre-push hooks run full test suites, drift detection, and security scans before each push. CI runs the complete validation suite. No manual test commands needed for routine development.

### Dogfood the shipped Copilot base

Copilot CLI runs plugin hooks from an installed plugin directory, not from your
checkout. By default that directory holds a published copy of `project-toolkit`,
so a local checkout does not exercise the hooks it ships to customers. A broken
hook can then reach customers before anyone here notices (see issue #3247).

To run the exact hooks, skills, and agents you ship, copy your working tree over
the installed plugin (the same way the marketplace install puts it there):

```bash
# Copy src/copilot-cli over ~/.copilot/installed-plugins/ai-agents/project-toolkit
python3 scripts/dev/dogfood_copilot_plugin.py --install

# Confirm the current state (flags a stale copy)
python3 scripts/dev/dogfood_copilot_plugin.py --status

# Restore the published copy
python3 scripts/dev/dogfood_copilot_plugin.py --uninstall
```

Re-run `--install` after editing `src/copilot-cli` to refresh the copy; the new
hooks load on your next Copilot session. The prior installed copy is backed up
once and restored by `--uninstall`. Set `COPILOT_HOME` to target a Copilot home
other than `~/.copilot` (the install path follows it). This provides the dogfood
install from ADR-083 decision item 3, copy-only on every platform; the ADR's
platform-split wording is being reconciled in #3252. Refs #3222.

## Git Configuration

This repository enforces LF line endings for all files via `.gitattributes` to prevent cross-platform issues. To ensure smooth collaboration, configure your Git client based on your operating system:

### Windows

```bash
git config --global core.autocrlf true
```

**What this does:**

- **On checkout:** Git converts LF → CRLF for your text editors (Windows native)
- **On commit:** Git converts CRLF → LF for the repository
- **Result:** Repository always has LF, your editor always shows CRLF

### Linux/macOS

```bash
git config --global core.autocrlf input
```

**What this does:**

- **On checkout:** Git leaves LF as-is (Unix native)
- **On commit:** Git converts any CRLF → LF for the repository
- **Result:** Repository always has LF, your editor always shows LF

### Why This Matters

**Problem without proper configuration:**

- YAML frontmatter in agent files fails to parse with CRLF line endings
- GitHub Copilot CLI shows "Unexpected scalar at node end" errors
- Git diffs show entire files changed due to line ending differences
- Collaboration becomes difficult when contributors use different platforms

**Solution:**

- `.gitattributes` enforces LF in the repository (`* text=auto eol=lf`)
- `core.autocrlf` gives you native line endings in your working directory
- Together, they ensure consistency without sacrificing developer experience

**References:**

- [GitHub Copilot CLI Issue #694](https://github.com/github/copilot-cli/issues/694)
- [GitHub Copilot CLI Issue #673](https://github.com/github/copilot-cli/issues/673)
- [Issue #896](https://github.com/rjmurillo/ai-agents/issues/896)

## Agent Template System

This project uses a **template-based generation system** to maintain agent definitions across multiple platforms (VS Code, Copilot CLI). This ensures consistency while allowing platform-specific customizations.

### Architecture Overview

```text
templates/
  agents/                    # Shared agent definitions (SOURCE OF TRUTH)
    analyst.shared.md
    implementer.shared.md
    orchestrator.shared.md
    ...
  platforms/                 # Platform-specific configurations
    vscode.yaml
    copilot-cli.yaml

src/
  vs-code-agents/           # GENERATED - Do not edit directly
    analyst.agent.md
    implementer.agent.md
    ...
  copilot-cli/              # GENERATED - Do not edit directly
    analyst.agent.md
    implementer.agent.md
    ...
```

### Key Concepts

| Component | Location | Purpose |
|-----------|----------|---------|
| Shared Templates | `templates/agents/*.shared.md` | Single source of truth for agent behavior |
| Platform Configs | `templates/platforms/*.yaml` | Platform-specific settings (model, tools, syntax) |
| Generated Files | `src/vs-code-agents/`, `src/copilot-cli/` | Output files used by each platform |

## How to Modify an Agent

To change an existing agent's behavior, follow these steps:

### Step 1: Edit the Shared Template

Edit the source file in `templates/agents/`:

```bash
# Example: Modify the analyst agent
code templates/agents/analyst.shared.md
```

### Step 2: Regenerate Platform Files

Run the generation script:

```bash
uv run python build/generate_agents.py
```

### Step 3: Verify the Changes

Check that generated files look correct:

```bash
# Preview what would be generated without writing
uv run python build/generate_agents.py --what-if

# Verify generated files match templates
uv run python build/generate_agents.py --validate
```

### Step 4: Commit Both Files

Always commit the template AND generated files together:

```bash
git add templates/agents/analyst.shared.md
git add src/vs-code-agents/analyst.agent.md
git add src/copilot-cli/agents/analyst.agent.md
git commit -m "feat(analyst): add new research capability"
```

## How to Add a New Agent

### Step 1: Create the Shared Template

Create a new file in `templates/agents/` with the `.shared.md` extension:

```bash
# Example: Create a new "reviewer" agent
code templates/agents/reviewer.shared.md
```

### Step 2: Define the Template Structure

Use this template structure (see existing agents in `templates/agents/` for examples):

**Required Frontmatter:**

```yaml
---
description: Brief description of the agent's purpose
argument-hint: Describe the input expected from the user
tools_vscode:
  - vscode
  - read
  - search
  - cloudmcp-manager/*
tools_copilot:
  - shell
  - read
  - edit
  - search
  - agent
  - cloudmcp-manager/*
---
```

> **Note:** Use block-style YAML arrays (hyphen-bulleted) for cross-platform compatibility. Inline array syntax `['tool1', 'tool2']` fails on GitHub Copilot CLI with CRLF line endings.

**Required Sections:**

- `# Agent Name` - The agent's display name
- `## Core Identity` - Role description
- `## Core Mission` - Primary objective
- `## Key Responsibilities` - Numbered list of responsibilities
- `## Constraints` - What the agent should NOT do
- `## Memory Protocol` - How to use cloudmcp-manager
- `## Output Format` - Expected outputs
- `## Handoff Protocol` - When/how to hand off to other agents

See `templates/agents/analyst.shared.md` for a complete example.

### Step 3: Configure Platform-Specific Tools

In the frontmatter, define tools for each platform:

- `tools_vscode`: Tools available in VS Code / GitHub Copilot
- `tools_copilot`: Tools available in Copilot CLI

Example:

```yaml
---
description: Code review specialist
tools_vscode:
  - vscode
  - read
  - search
  - cloudmcp-manager/*
  - github/*
tools_copilot:
  - shell
  - read
  - edit
  - search
  - agent
  - cloudmcp-manager/*
  - github/*
---
```

### Step 4: Generate and Verify

```bash
# Generate all agents
uv run python build/generate_agents.py

# Verify outputs
uv run python build/generate_agents.py --validate
```

### Step 5: Update Documentation

Add the new agent to:

- `README.md` (Agents table)
- `CLAUDE.md` (Agent Catalog table)
- `USING-AGENTS.md` (if it exists)

## Writing a New Hook

ADR-047 (`.agents/architecture/ADR-047-plugin-mode-hook-behavior.md`) is the canonical specification for hook bootstrap. Read it before adding a new hook.

The shipped pattern:

1. **Copy the inline bootstrap from an existing hook verbatim.** Do not introduce a new resolver, do not extract to a helper, do not rewrite the manifest walk-up. The grep-style test in `tests/test_plugin_path_resolution.py` requires the literal string `os.environ.get("CLAUDE_PLUGIN_ROOT")` and a literal `os.path.isdir(_lib_dir)` validation in every file with a `from hook_utilities` or `from github_core` import. Helper-extraction breaks the test, even when it is functionally equivalent.

2. **`setup_hook_lib_path()` exists in `.claude/lib/bootstrap.py` for cases that do not need ADR-047 grep-test compliance** (for example, scripts that live outside `.claude/hooks/`). Hooks themselves must use the inline form.

3. **Pick the right exit code on bootstrap failure.** Use `sys.exit(2)` for blocking hooks (the missing lib means the hook cannot run, so the gate must fail closed). Use `sys.exit(0)` for non-blocking hooks where a missing lib should not stop the user. Add the inline annotation `# Non-blocking hook: exit 0 on bootstrap failure (intentional, not a typo)` next to a `sys.exit(0)` so the next reader does not "fix" it.

4. **Canonical implementation examples.** Pick a sibling at the same blocking/non-blocking tier:
   - Blocking (exit 2): `.claude/hooks/PreToolUse/invoke_require_subagent_model.py`
   - Non-blocking (exit 0): `.claude/hooks/PostToolUse/invoke_observation_sync.py`, `.claude/hooks/SessionStart/invoke_context_loader.py`

   Internal policy and advisory hooks were removed under ADR-084 in issues #3184
   and #3295. Retrieve behavioral guidance through static rules and skills.
   Push-time policy belongs in Lefthook and CI.

5. **Run the platform regen after adding the hook.** `uv run python build/scripts/build_all.py --platform copilot-cli` (and any other downstream platform) so the regenerated copy under `src/<provider>/hooks/` stays in sync.

6. **Before pushing, run the relevant tests.** `uv run pytest tests/test_plugin_path_resolution.py tests/test_bootstrap.py tests/hooks/ -q` is the minimum.

## Validating Prompt, Skill, and Agent Changes (ADR-057)

Changes to prompts, skills, and agent definitions can alter LLM behavior. ADR-057 requires behavioral evaluation before merging changes to these files.

### What Requires Behavioral Evaluation

| Category | File Patterns |
|----------|---------------|
| Commands | `.claude/commands/*.md` |
| Quality gate prompts | `.github/prompts/*.md` |
| Security prompts | `.agents/security/prompts/*.md` |
| Agent definitions (Claude Code) | `.claude/agents/*.md` |
| Agent definitions (published) | `src/claude/*.md`, `src/copilot-cli/*.md`, `src/vs-code-agents/*.md` |
| Skill definitions | `.claude/skills/*/SKILL.md` |

### When to Run Evals

- **Structural changes only** (sections added, renamed, moved): Run structural tests (ADR-023). No behavioral eval needed.
- **Behavioral changes** (instructions, thresholds, decision logic): Run behavioral evals (ADR-057). Required before merge.
- **Both structural and behavioral**: Run both.
- **Ambiguous**: When in doubt, run behavioral evals.

### How to Run

```bash
# Auto-detect changes and route to correct evaluator:
uv run --frozen python scripts/eval/eval-suite.py --dry-run   # Preview what would run
uv run --frozen python scripts/eval/eval-suite.py              # Full run (requires ANTHROPIC_API_KEY)

# Evaluate a specific prompt change (before/after comparison):
uv run python scripts/eval/eval-prompt-change.py \
  --prompt .claude/commands/research.md \
  --scenarios tests/evals/research-scenarios.json \
  --base-ref main

# Security-critical prompts (5 runs, 100% pass required):
uv run python scripts/eval/eval-prompt-change.py \
  --prompt .agents/security/prompts/security-review.md \
  --scenarios tests/evals/security-review-scenarios.json \
  --base-ref main --security-critical
```

### Writing Scenario Files

Scenarios define expected LLM behavior. See `scripts/eval/examples/example-scenarios.json` for a template.

```json
{
  "scenarios": [
    {
      "id": "S1",
      "desc": "What this scenario tests",
      "input": "Simulated context the LLM receives",
      "expected_verdict": "STOP",
      "expected_reason_contains": "budget"
    }
  ]
}
```

**Minimum requirements (ADR-057):**

- At least one scenario per decision branch the change introduces or modifies
- At least one regression scenario for existing behavior the change could affect
- Store scenarios in `tests/evals/` (general) or `.agents/security/benchmarks/` (security)

### Acceptance Gate

A prompt change passes when all three criteria hold:

1. `after_score >= before_score` (no regression)
2. Targeted scenarios move from fail to pass
3. No scenario flips pass to fail without justification in the PR

### Enforcement

- **CI gate**: The `/spec` eval in `.github/workflows/slash-command-quality.yml` blocks merge on regression (see ADR-057 Amendment 2026-07-22 for advisory vs blocking scope).
- **PR review**: For prompt files without a blocking CI leg, the gate is advisory and PR review carries judgment.

### References

- [ADR-057](.agents/architecture/ADR-057-prompt-behavioral-evaluation.md): Full methodology
- [ADR-023](.agents/architecture/ADR-023-quality-gate-prompt-testing.md): Structural validation (complement)
- [scripts/eval/README.md](scripts/eval/README.md): Script reference and quick start

## Platform Configuration

Platform configurations in `templates/platforms/` control how agents are transformed for each platform.

### VS Code Configuration (`vscode.yaml`)

```yaml
platform: vscode
outputDir: src/vs-code-agents
fileExtension: .agent.md

frontmatter:
  model: "Claude Opus 4.6 (copilot)"
  includeNameField: false

handoffSyntax: "#runSubagent"
```

### Copilot CLI Configuration (`copilot-cli.yaml`)

```yaml
platform: copilot-cli
outputDir: src/copilot-cli
fileExtension: .agent.md

frontmatter:
  # Copilot CLI model: use CLI model identifiers (not VS Code display names)
  model: "claude-opus-4.6"
  includeNameField: true

handoffSyntax: "/agent"
```

### Key Differences Between Platforms

| Feature | VS Code | Copilot CLI |
|---------|---------|-------------|
| Model field | `Claude Opus 4.6 (copilot)` | `claude-opus-4.6` |
| Name field | Not included | Required |
| Handoff syntax | `#runSubagent` | `/agent` |
| Tools prefix | `tools_vscode` | `tools_copilot` |
| `argument-hint` | Included | Included |

> **Note:** These model values reflect the current platform configuration, not durable policy. ADR-080 governs model-pin evidence. Runtime model selection follows the current Copilot CLI contract and action inputs.

## Important: Do Not Edit Generated Files

**Never edit files directly in:**

- `src/vs-code-agents/`
- `src/copilot-cli/`

These files are auto-generated and include a header comment:

```markdown
<!-- AUTO-GENERATED FILE - DO NOT EDIT DIRECTLY
     Generated from: templates/agents/[name].shared.md
     To modify this file, edit the source and run: uv run python build/generate_agents.py
-->
```

**CI will reject PRs** that modify generated files without corresponding template changes.

## Useful Commands

```bash
# Generate all agent files from templates
uv run python build/generate_agents.py

# Verify generated files match templates (used in CI)
uv run python build/generate_agents.py --validate

# Preview what would be generated without writing files
uv run python build/generate_agents.py --what-if

# Generate with verbose logging
uv run python build/generate_agents.py
```

## CI Drift Detection

The `agent-drift-detection.yml` workflow runs on every PR that touches agent-related files. It:

1. Regenerates all platform-specific files from source templates
2. Compares generated output against committed files
3. Fails CI with an actionable diff if semantic drift is detected

### What counts as drift?

Drift is detected when any generated file (`src/vs-code-agents/*.agent.md`, `src/copilot-cli/agents/*.agent.md`) differs from what `generate_agents.py` would produce from the current templates. This includes both:

- **Content drift**, body text changed directly in a generated file
- **Frontmatter drift**, YAML frontmatter edited outside the generation pipeline

Whitespace-only differences (line endings, trailing spaces) are ignored during comparison.

### When CI fails: how to fix

```bash
# 1. Edit the source template (NOT the generated file)
code templates/agents/<agent-name>.shared.md

# 2. Regenerate
uv run python build/generate_agents.py

# 3. Commit the regenerated files
git add src/vs-code-agents/ src/copilot-cli/
git commit -m "fix(agents): regenerate from updated template"
```

### Intentional divergence (bypass procedure)

In rare cases (e.g., emergency hotfix), you may need to skip drift detection:

1. Add `[skip-drift-check]` to a commit message in your PR
2. Document the reason clearly in the PR description
3. Update `templates/README.md` to record the intentional difference
4. Obtain explicit code-owner approval for the bypass

> **Note:** Bypasses are auditable. They appear in the workflow summary and require reviewer acknowledgement.

## Pre-Commit Hooks

Enable automated validation on commits:

```bash
uv run --frozen lefthook install --reset-hooks-path
uv run --frozen lefthook check-install
```

Lefthook installs shims under Git's hook directory. Linked worktrees share
those shims through the common Git directory. Lefthook reads `lefthook.yml` at
runtime, so configuration edits do not require another install.

`pre_pr.py` runs `lefthook check-install` as a local gate. It verifies that the
pinned binary, `lefthook.yml`, and installed shims are available. CI skips this
local-clone check because workflows invoke validation directly.

Lefthook filters staged files and runs the named pre-commit validators declared
in `lefthook.yml`. That file is the authoritative list of local Git hook jobs.

## Pre-Push Hooks

The pre-push hook validates files in the push range. Lefthook filters the
changed files and runs the named validators declared in `lefthook.yml`. Consult
that file for the current jobs instead of relying on a duplicated checklist.

## Lifecycle Hooks (Claude Code)

Claude Code runs a small internal lifecycle surface from `.claude/settings.json`.
Customer-value markdown hooks remain on the plugin surface. Deterministic commit
and push enforcement runs through Lefthook, `pre_pr.py`, and CI under ADR-084.

| Hook | File | Purpose | Bypass env var |
|------|------|---------|----------------|
| SessionStart | `invoke_context_loader.py` | Auto-loads latest retrospective into context | none (fail-open) |
| PostToolUse | `invoke_observation_sync.py` | Syncs Serena observations to Forgetful | none (fail-open) |
| PreCompact | `invoke_compact_checkpoint.py` | Snapshots WIP state before context compaction | none (always runs) |

**Diagnosability:** Hook errors print to stderr (visible in the harness output)
tagged `[hook-error] {hook_name} {context}: {ExceptionClass}: {message}`. The
remaining hooks surface recoverable failures instead of swallowing them.

Refer to `.agents/architecture/ADR-008-protocol-automation-lifecycle-hooks.md` for the design rationale.

### Adding a New Lifecycle Hook

A new hook must satisfy the ADR-084 customer-value bar and match the existing
hook contract.

**1. Pick the event.** Claude Code lifecycle events: `SessionStart`, `PreToolUse`, `PostToolUse`, `PreCompact`, `Stop`. One file per hook, one event per file.

**2. Create the file.** Path: `.claude/hooks/<EventName>/invoke_<purpose>.py`. Example: `.claude/hooks/PreToolUse/invoke_my_gate.py`.

**3. Use the boilerplate.** Every hook follows this skeleton:

```python
#!/usr/bin/env python3
"""<EventName> hook: <one-line purpose>.

Hook Type: <EventName> (blocking | non-blocking)
Exit Codes: 0 = allow, 2 = block (only if blocking)
Bypass: SKIP_<NAME>=true (or "none" if always-runs)

Related:
- Issue #<n>
- ADR-008 (lifecycle hooks)
"""

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

_plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
_lib_dir = str(Path(_plugin_root).resolve() / "lib") if _plugin_root \
           else str(Path(__file__).resolve().parents[2] / "lib")
if os.path.isdir(_lib_dir) and _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

try:
    from hook_utilities import get_project_directory as _get_project_directory

    def get_project_directory() -> Path | None:
        result = _get_project_directory()
        return Path(result) if result else None
except ImportError:
    def get_project_directory() -> Path | None:
        env_dir = os.environ.get("CLAUDE_PROJECT_DIR")
        if env_dir:
            return Path(env_dir)
        current = Path.cwd()
        while current != current.parent:
            if (current / ".git").exists():
                return current
            current = current.parent
        return None


def main() -> int:
    if sys.stdin.isatty():
        return 0
    try:
        stdin_data = sys.stdin.read()
        if not stdin_data.strip():
            return 0
        hook_input = json.loads(stdin_data)
    except Exception as e:
        print(f"[hook-error] invoke_<purpose> stdin: {type(e).__name__}: {e}", file=sys.stderr)
        return 0  # fail-open

    # Correlation IDs for audit
    session_id = str(hook_input.get("session_id", ""))
    tool_use_id = str(hook_input.get("tool_use_id", ""))

    # ... your logic here ...

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**4. Audit every terminal.** If your hook makes a decision (allow/block/bypass), log it. Include `decision`, `reason`, `session_id`, `tool_use_id`, `schema: 1`. Wrap append-mode opens with `hook_utilities.lock_file`/`unlock_file` to survive parallel sessions (cross-platform, Windows + POSIX). Silent fail-open is a bug.

**5. UTC dates only.** Use `datetime.now(tz=UTC).strftime("%Y-%m-%d")` for any date-derived path or timestamp. Naive `datetime.now()` will mismatch hooks running at UTC and split audit/session files across days.

**6. Stderr on broad except.** Every `except Exception:` block must `print(f"[hook-error] <hook> <ctx>: {type(e).__name__}: {e}", file=sys.stderr)` before returning 0.

**7. Register in `.claude/settings.json`.** Add an entry under the matching event with `timeout: 5` (seconds). A hung hook without a timeout blocks the session, defeating fail-open.

```json
{
  "type": "command",
  "command": "python3 -u .claude/hooks/<EventName>/invoke_<purpose>.py",
  "timeout": 5,
  "statusMessage": "<one-line description>"
}
```

**8. Document the bypass env var.** Add a row to the Lifecycle Hooks table in this file. If your hook always runs (no bypass), say "none" explicitly.

**9. Write tests.** Path: `tests/test_<purpose>.py`. Cover at minimum: TTY-stdin returns 0 silently, empty stdin returns 0 silently, happy path returns expected exit code, fail-open path returns 0 on internal error. Use `datetime.now(tz=UTC)` in test fixtures so they don't TZ-flake.

**10. Update ADR-008's Implementation Status table** with a row for the new hook, and bump the count of hooks in CONTRIBUTING.md and the PR description.

## Session Protocol

This project preserves continuity through per-issue handoffs and Serena memory.
Committed session logs are optional.

### Session Logs

Create a log at `.agents/sessions/YYYY-MM-DD-session-NN.json` only when you
want an explicit committed record. Any staged or explicitly supplied log must
pass `scripts/validate_session_json.py`.

### QA Validation

The pre-commit hook validates that QA has been performed for sessions involving code changes. There are two exemptions:

| Exemption Type | When to Use | Evidence Value |
|----------------|-------------|----------------|
| **Docs-only** | All changes are documentation files (Markdown) with no code, config, or test changes | `SKIPPED: docs-only` |
| **Investigation-only** | Session is research/analysis with only investigation artifacts staged | `SKIPPED: investigation-only` |

**Investigation artifacts** (allowlist for investigation-only exemption):

- `.agents/sessions/` - Optional session logs and per-issue handoffs
- `.agents/analysis/` - Research findings
- `.agents/retrospective/` - Learning extractions
- `.serena/memories/` - AI memory updates
- `.agents/security/` - Security assessments

See [ADR-034](.agents/architecture/ADR-034-investigation-session-qa-exemption.md) for the full specification.

## Running Tests

### Automated Quality Gates (Shift Left)

The repository enforces quality automatically at multiple stages:

| Stage | What Runs | Trigger |
|-------|-----------|---------|
| **Pre-commit hook** | Python linting (ruff), Markdown linting | Every commit |
| **Pre-push hook** | Full pytest, drift detection, lint, security scans | Every push |
| **CI pytest.yml** | pytest, pip-audit, bandit | Every PR/push |

**No manual test runs required for routine development.** Quality gates run automatically.

### Manual Testing (Optional)

For local debugging or development iteration:

```bash
# Python tests
uv run pytest                               # All tests
uv run pytest tests/test_example.py         # Specific file
uv run pytest --cov --cov-report=html       # With coverage

# Security scanning (also runs in CI)
uv run pip-audit                            # Dependency vulnerabilities
uv run bandit -r .claude/ scripts/          # Static analysis
```

### Agent Generation Tests

```bash
# Run generation tests
uv run pytest tests/build_scripts/test_generate_agents.py
```

## Copilot CLI Version Management

The CI pipeline uses GitHub Copilot CLI to run agent reviews. The CLI version is pinned to prevent regressions from auto-updates.

### Current Pin

The required review path reads `COPILOT_VERSION` from `.github/actions/ai-review/action.yml`. The fallback in `scripts/ci/install_copilot_cli.py` must match it. The nightly smoke workflow carries an independent, Renovate-managed version.

`scripts/validation/check_copilot_version_pin.py` rejects known-bad required-review pins. It is a denylist guard, not the version source or proof of runtime compatibility. See [ADR-094](.agents/architecture/ADR-094-govern-copilot-cli-compatibility.md).

### Why Version Pinning

Copilot CLI's npm package contains a loader that delegates to a platform-specific binary. This binary auto-updates independently of the npm package version. npm version pinning alone is insufficient; the `--no-auto-update` flag prevents the binary from self-updating during CI runs.

### Validating Agent Frontmatter

After modifying agent templates or platform configs, validate agents load correctly:

```bash
# Check installed version
copilot --no-auto-update --version

# Test a single agent with debug logging (check for warnings)
copilot --no-auto-update --log-level all --agent analyst --prompt "Reply with only the word OK"

# Test all shared agents
for agent in analyst architect backlog-generator critic devops explainer high-level-advisor implementer independent-thinker memory milestone-planner orchestrator pr-comment-responder qa retrospective roadmap security skillbook task-decomposer; do
  copilot --no-auto-update --log-level all --agent "$agent" --prompt "Reply OK" 2>&1 | grep -i warning && echo "FAIL: $agent" || echo "PASS: $agent"
done
```

### Local Workflow Testing with gh act

Use `gh act` (nektos/gh-act) to simulate CI workflows locally:

```bash
# Install gh act extension (one time)
gh extension install nektos/gh-act

# Pull Docker image (one time, ~600MB)
docker pull catthehacker/ubuntu:act-latest

# Dry run (validate workflow structure)
gh act pull_request -n -W .github/workflows/ai-spec-validation.yml

# Full run (single job)
TOKEN=$(gh auth token)
gh act pull_request \
  -j "validate-spec" \
  -W .github/workflows/ai-spec-validation.yml \
  -s "GITHUB_TOKEN=$TOKEN" \
  -s "BOT_PAT=$TOKEN" \
  -P ubuntu-latest=catthehacker/ubuntu:act-latest
```

**Known limitation:** PowerShell composite action steps fail with "Exec format error" in `act`. This is a known `act` limitation, not a workflow bug. The Copilot CLI install and agent invocation steps run correctly.

### Upgrading the Required Review Pin

When changing the required review path's Copilot CLI version:

1. Install the new version locally: `npm install -g @github/copilot@X.Y.Z`
2. Run the agent validation loop above
3. Update `.github/actions/ai-review/action.yml` and `scripts/ci/install_copilot_cli.py` together
4. Run `gh act` dry-run to validate workflow structure
5. Run `uv run pytest tests/test_check_copilot_version_pin.py`
6. Run `uv run python scripts/validation/check_copilot_version_pin.py`

Routine version bumps do not require an ADR edit. See `.serena/memories/copilot/copilot-cli-frontmatter-regression-runbook.md` for the diagnostic runbook.

## ADR-to-Protocol Sync Process

When you create or update an Architecture Decision Record (ADR) that introduces enforceable requirements (MUST, SHOULD, MAY per RFC 2119), you must sync those requirements into SESSION-PROTOCOL.md so agents enforce them.

### Manual Checklist

1. Identify MUST/SHOULD requirements in the ADR's Decision section
2. Add a "Protocol Integration" section to the ADR listing which SESSION-PROTOCOL.md sections need updates
3. Update SESSION-PROTOCOL.md with the new requirements
4. Update the ADR Cross-Reference table in SESSION-PROTOCOL.md

### Automated Audit

Run the sync audit script to detect ADRs with MUST requirements not referenced in SESSION-PROTOCOL.md:

```bash
uv run python scripts/sync_adr_protocol.py
```

The script parses all ADR files, extracts RFC 2119 requirements, and reports coverage gaps. See [ADR-050](.agents/architecture/ADR-050-adr-protocol-sync.md) for the full process.

## Pull Request Guidelines

1. **Spec references**: Feature PRs (`feat:`) require spec references (issue, REQ-*, or `.agents/planning/` files)
2. **Template changes**: Always include both template and generated files
3. **Validation**: Run `uv run python build/generate_agents.py --validate` before submitting
4. **Tests**: Ensure all tests pass
5. **Documentation**: Update relevant docs if adding new agents
6. **Commit messages**: Use conventional commit format (e.g., `feat(agent):`, `fix(template):`)

### Commit Count Thresholds

PRs with many commits often indicate scope creep or should be split into smaller PRs. The repository enforces commit thresholds automatically:

| Commit Count | Action | Label Applied |
|--------------|--------|---------------|
| 10 commits | Warning notice in PR | `needs-split` |
| 15 commits | Alert warning in PR | `needs-split` |
| Above active limit | PR blocked from merge | `needs-split` |

#### What This Means

- **10 commits**: The workflow adds a notice. Consider whether the PR should be split.
- **15 commits**: The workflow adds an alert. Splitting is strongly recommended.
- **Above active limit**: The workflow blocks the PR. You MUST split the PR, or ask a human maintainer to decide on the `commit-limit-bypass` label. That label is human-only (see "Bypassing the Limit" below); do not apply it yourself.

The active limit is 20 by default. Validation may raise it to 40 after detecting
a qualifying base merge. Exactly 20 or 40 commits remains an alert, not a block.

#### Handling `needs-split` Labels

**For contributors**:

1. Review the commit history to identify logical groupings
2. Split into smaller, focused PRs where possible
3. If splitting is not practical, add a comment explaining why and request the `commit-limit-bypass` label

**For AI agents (pr-review, pr-comment-responder)**:

When encountering a PR with the `needs-split` label:

1. **Run a retrospective analysis**: Determine why the PR required so many commits
2. **Analyze commit history**: Group commits by logical change to identify potential split points
3. **Provide recommendations**: Suggest how the work could be divided into smaller PRs
4. **Document findings**: Save analysis to `.agents/retrospective/PR-[number]-needs-split-analysis.md` for future reference

#### Bypassing the Limit

To bypass the active commit limit:

1. A human maintainer MUST add the `commit-limit-bypass` label
2. The bypass is visible in the PR labels and auditable
3. Use this sparingly for genuinely large, atomic changes that cannot be split

### PR Description Validation

The `Validate PR` workflow runs `scripts/validation/pr_description.py` to compare files mentioned in the PR description against files in the diff. Inline-code filenames (`` `path/file.py` ``) in `## Summary` and similar sections are treated as change claims; if those files are not in the diff the validator emits a `CRITICAL` issue and the workflow fails.

#### Contextual Reference Sections

To reference an existing file as context (a pattern source, a related spec, prior art) without it being treated as a change claim, place the mention under one of these h2 sections:

- `## Test Plan`
- `## Design Decisions`
- `## Related`
- `## References`
- `## See Also`
- `## Notes`
- `## Background`
- `## Inspired By`
- `## Pattern From`
- `## Prior Art`

The validator strips these sections before extracting file mentions, so any inline-code filenames inside them are ignored.

#### Bypassing Description Validation

For PRs where the contextual section allowlist does not fit (e.g. inline pattern reference inside `## Summary`), ask a human maintainer to apply the `description-validation-bypass` label. Do not apply it yourself.

1. A human maintainer MUST add the `description-validation-bypass` label (case-insensitive match)
2. The validator still runs and prints all issues for visibility, but exits 0
3. The bypass is visible in the PR labels and auditable
4. When run in CI, the bypass also appends a structured record to `GITHUB_STEP_SUMMARY` (marker: `<!-- DESCRIPTION-VALIDATION-BYPASS -->`) so audit tooling can count usage without parsing logs
5. Use this sparingly; prefer rewriting the description to use a contextual section

### Spec Reference Best Practices

For traceability and AI-assisted validation:

- **Features (`feat:`)**: Always link to an issue or create a planning document in `.agents/planning/` before submitting
- **Bug fixes (`fix:`)**: Link to issue if it exists; for complex bugs, explain root cause
- **Refactors (`refactor:`)**: Explain rationale and scope in PR description
- **Documentation (`docs:`)**: Spec references not required
- **Infrastructure (`ci:`, `build:`, `chore:`)**: Link to related infra/CI/tooling issue or spec; call out operational risk and rollback plan if applicable

Supported reference formats:

- Issue links: `Closes #123`, `Fixes #456`, `Implements #789`
- Requirement IDs: `REQ-001`, `DESIGN-002`, `TASK-003`
- Spec files: `.agents/specs/requirements/...`, `.agents/planning/...`

The AI Spec Validation workflow will check for these references on all PRs.

## Forgetful MCP Server

This project uses the [Forgetful MCP](https://github.com/ScottRBK/forgetful) server for AI agent memory. Forgetful provides semantic search, automatic knowledge graph construction, and cross-session memory persistence.

### Setup

Forgetful uses stdio transport with automatic installation via `uvx`. No manual service setup required.

**Configure MCP client** (`.mcp.json`):

```json
{
  "mcpServers": {
    "forgetful": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "forgetful-ai"
      ]
    }
  }
}
```

### Forgetful Installation Prerequisites

Install `uv` if not already present:

**Linux/macOS:**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows:**

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Security Note**: Optional: verify installer integrity or use a package manager (e.g., brew/winget) when available.

### Verifying Connection

After configuration, verify the MCP connection in your client:

- **Claude Code**: Run `mcp__forgetful__discover_forgetful_tools()` to see available tools
- Check logs if issues occur (uvx manages the process lifecycle automatically)

### Importing Shared Memories

Import the project's shared Forgetful memories to get cross-session context:

```bash
python3 scripts/forgetful/import_forgetful_memories.py
```

This imports all JSON exports from `.forgetful/exports/` into your local Forgetful database. The import is idempotent and safe to run multiple times.

**Note**: See `scripts/forgetful/README.md` for limitations on ID-based sync between divergent databases.

## Claude Router Plugin

This project supports the [Claude Router](https://github.com/0xrdan/claude-router) plugin for intelligent model routing and cost optimization.

### What is Claude Router?

Claude Router automatically directs queries to the most cost-effective Claude model (Haiku, Sonnet, or Opus) based on task complexity, reducing costs by up to 98% without sacrificing quality.

### How It Works

**Routing Logic:**

- **Fast (Haiku):** Simple queries, factual questions, syntax help
- **Standard (Sonnet):** Bug fixes, feature implementation, code review, refactoring
- **Deep (Opus):** Architecture decisions, security audits, multi-file refactors, system design

**Classification Mechanism:**

1. **Rule-Based (Primary):** Instant pattern matching (~0ms latency, no API costs)
2. **LLM Fallback (Secondary):** Uses Haiku for edge cases (~100ms latency, ~$0.001 per classification)

### Installation

**Option 1 - Plugin Marketplace (Recommended):**

```bash
# In any Claude Code session:
/plugin marketplace add 0xrdan/claude-router
/plugin install claude-router@claude-router-marketplace
```

Then restart Claude Code to load the plugin.

**Option 2 - One-Command Install:**

```bash
curl -sSL https://raw.githubusercontent.com/0xrdan/claude-router/main/install.sh | bash
```

**Option 3 - Manual Install:**

```bash
git clone https://github.com/0xrdan/claude-router.git
cd claude-router && ./install.sh
```

**Important:** Choose only one installation method to avoid conflicts.

### Configuration

**API Key (Required for LLM Fallback):**

Set your Anthropic API key as an environment variable:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Or add to `.env` file.

**Routing Enforcement:**

The router enforcement rules are already configured in this project's `CLAUDE.md`. When Claude receives a routing directive, it will automatically spawn the appropriate executor subagent.

### Usage

**Automatic Routing (Default):**

Submit queries normally. The UserPromptSubmit hook automatically classifies and routes them.

**Manual Override:**

Force a specific model when needed:

```bash
/route fast <query>     # Use Haiku
/route standard <query> # Use Sonnet
/route deep <query>     # Use Opus
```

**View Statistics:**

```bash
/router-stats
```

Displays routing history and cost savings metrics.

### Notes

- The marketplace must be added per project (updates are automatic thereafter)
- Classification uses instant rule-matching when possible
- LLM fallback only triggers for uncertain cases
- Token overhead optimized to ~3.4k tokens per interaction
- Slash commands (`/route`, `/router-stats`) and router questions are handled directly, not routed

## Third-Party License Attribution

This project ships plugins via `.claude-plugin/marketplace.json`. Any
third-party component redistributed in a shipped plugin path requires
license attribution in `THIRD-PARTY-NOTICES.TXT`.

### What Requires Attribution

| Component Type | Example | Requires Attribution |
|----------------|---------|---------------------|
| Forked/vendored source code | SkillForge | Yes |
| Runtime dependencies in shipped `requirements.txt` | anthropic SDK | Yes |
| Dev-only tools | pytest, ruff | No |
| CI infrastructure | GitHub Actions | No |
| Transitive pip packages | pydantic, httpx | No |
| Test frameworks | pytest, pytest-cov | No |

### Adding a New Third-Party Component

1. Verify the license is compatible with MIT (see `docs/third-party-license-attribution.md`)
2. Add the component to `FORKED_COMPONENTS` or `RUNTIME_DEPENDENCIES` in
   `scripts/generate_third_party_notices.py`
3. Run `uv run python3 scripts/generate_third_party_notices.py` to regenerate
4. Commit both the script and `THIRD-PARTY-NOTICES.TXT` together
5. Run `--check` mode to verify: `uv run python3 scripts/generate_third_party_notices.py --check`

### Full Policy

See `docs/third-party-license-attribution.md` for the complete policy,
license compatibility matrix, and compliance checklist.

## Security Scanning

Lefthook's pre-push `security-scan` job runs
[Semgrep](https://semgrep.dev/docs/) on changed code files. It catches local
security findings before PR creation. See
[ADR-054](.agents/architecture/ADR-054-local-security-scanning.md) for the
decision rationale.

### Restoring the Pinned Scanner

```bash
# Restore every development and hook dependency
uv sync --frozen --extra dev

# Verify the pinned Semgrep executable
uv run --frozen --extra dev semgrep --version
```

Do not install or select a separate Semgrep version for repository hooks. The
frozen uv environment is the supported runtime. A missing scanner blocks the
push as an environment failure.

### Security Scan Process

The Lefthook job delegates to
`scripts/validation/git_hook_policy.py semgrep-push`, which:

1. Reads every ref update from Git's pre-push standard input
2. Resolves the exact commits and changed files being pushed
3. Materializes pushed trees without trusting the working tree
4. Filters to supported extensions: `.py`, `.ps1`, `.psm1`, `.js`, `.ts`, `.yaml`, `.yml`
5. Runs the pinned scanner with native suppressions and ignore files disabled
6. Enforces a 15-minute Lefthook timeout and a 14-minute (840-second) Python
   subprocess timeout, leaving 60 seconds for captured diagnostics and Python
   exit-code propagation

**Severity thresholds:**

| Semgrep severity | Local action |
|------------------|--------------|
| `ERROR` | Selected by `--severity ERROR`; a finding blocks push with a nonzero exit |
| Other severities | Not selected by the local command; CI and security review retain their own policies |

### Security Scan Findings

Inline scanner suppressions are prohibited. Fix the finding or rewrite the code
so the scanner can prove the operation is safe. A false positive that cannot be
removed without a suppression requires security review and a policy change
before merge.

### Resolving Security Scan Findings

Fix reported findings before pushing. Do not bypass the scanner.

## Questions?

If you have questions about contributing, please open an issue or discussion.
