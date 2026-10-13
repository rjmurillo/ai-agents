# Skill Output Structure and Packaging

## Frontmatter Requirements

Skills must use only these allowed frontmatter properties:

| Property | Required | Description |
|----------|----------|-------------|
| `name` | Yes | Hyphen-case, max 64 chars |
| `description` | Yes | Max 1024 chars, no angle brackets |
| `license` | No | MIT, Apache-2.0, etc. |
| `allowed-tools` | No | Restrict tool access (comma-separated or YAML list) |
| `model` | No | Omit to inherit the harness default. If pinned, only a bare alias pricing below the default (`haiku`) is allowed; a versioned id is rejected. |
| `model-rationale` | No | Required when `model` is set; one line justifying the pin. |
| `context` | No | Set to `fork` for isolated sub-agent context |
| `agent` | No | Agent type when `context: fork` (`Explore`, `Plan`, `general-purpose`) |
| `hooks` | No | Lifecycle hooks (`PreToolUse`, `PostToolUse`, `Stop`) |
| `user-invocable` | No | Show in slash menu (default: `true`) |
| `metadata` | No | Custom fields (version, author, domains, etc.) |

**Basic Example:**

```yaml
---
name: my-skill
description: What this skill does and when to use it
license: MIT
user-invocable: true
metadata:
  version: 1.0.0
  author: your-name
---
```

**Advanced Example (with forked context and hooks):**

```yaml
---
name: isolated-analyzer
description: Runs analysis in isolated context with validation hooks
license: MIT
context: fork
agent: Explore
user-invocable: true
allowed-tools:
  - Read
  - Glob
  - Grep
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "./scripts/validate.sh"
metadata:
  version: 1.0.0
---
```

**Field Details:**

| Field | Values | Notes |
|-------|--------|-------|
| `context` | `fork` | Creates isolated sub-agent with separate conversation history |
| `agent` | `Explore`, `Plan`, `general-purpose` | Only valid when `context: fork` |
| `user-invocable` | `true`, `false` | `false` hides from slash menu but Claude can still auto-invoke |
| `hooks` | Object | See [Hooks Integration](#hooks-integration) section |

---

## Skill Output Structure

```
~/.claude/skills/{skill-name}/
├── SKILL.md                    # Main entry point (required)
├── references/                 # Deep documentation (optional)
│   ├── patterns.md
│   └── examples.md
├── assets/                     # Templates (optional)
│   └── templates/
└── scripts/                    # Automation scripts (optional)
    ├── validate.py             # Validation/verification
    ├── generate.py             # Artifact generation
    └── state.py                # State management
```

### Scripts Directory

Scripts enable skills to be **agentic** - capable of autonomous operation with self-verification.

| Category | Purpose | When to Include |
|----------|---------|-----------------|
| **Validation** | Verify outputs meet standards | Skill produces artifacts |
| **Generation** | Create artifacts from templates | Repeatable artifact creation |
| **State Management** | Track progress across sessions | Long-running operations |
| **Transformation** | Convert/process data | Data processing tasks |
| **Calculation** | Compute metrics/scores | Scoring or analysis |

**Script Requirements:**

- Python 3.x with standard library only (graceful fallbacks for extras)
- `Result` dataclass pattern for structured returns, where a script produces structured output
- Exit codes follow the repo convention: 0=success, 1=logic error, 2=config error, 3=external error (see AGENTS.md)
- Self-verification where applicable
- Documented in SKILL.md with usage examples

See: [script-integration-framework.md](script-integration-framework.md)

### Hooks Integration

Skills can define lifecycle hooks for validation, logging, and safety:

```yaml
---
name: secure-skill
hooks:
  PreToolUse:
    - matcher: "Bash"
      hooks:
        - type: command
          command: "./scripts/validate-input.sh"
  PostToolUse:
    - matcher: "Write"
      hooks:
        - type: command
          command: "./scripts/log-output.sh"
          once: true
  Stop:
    - hooks:
        - type: command
          command: "./scripts/cleanup.sh"
---
```

**Hook Types:**

| Hook | When Triggered | Use Case |
|------|----------------|----------|
| `PreToolUse` | Before tool execution | Input validation, security checks |
| `PostToolUse` | After tool execution | Output logging, verification |
| `Stop` | When skill completes | Cleanup, state persistence |

**Hook Configuration:**

| Field | Description |
|-------|-------------|
| `matcher` | Tool name pattern to match (e.g., "Bash", "Write", "Bash(python:*)") |
| `type` | Hook type: `command` (shell) or `prompt` (Claude evaluation) |
| `command` | Shell command to execute (for `type: command`) |
| `once` | If `true`, run only once per session (default: `false`) |

Read `$TOOL_INPUT` / `$TOOL_OUTPUT` inside hook scripts from environment variables.
Do not interpolate untrusted tool payloads directly into shell command strings.

**When to Use Hooks:**

| Scenario | Hook Type | Example |
|----------|-----------|---------|
| Validate script inputs | PreToolUse | Check parameters before `python scripts/*.py` |
| Log generated artifacts | PostToolUse | Record files created by Write tool |
| Security gate | PreToolUse | Block dangerous bash commands |
| Cleanup temp files | Stop | Remove intermediate artifacts |

### Example: Script Validation Hook

For skills with scripts, add input validation:

```yaml
hooks:
  PreToolUse:
    - matcher: "Bash(python:scripts/*)"
      hooks:
        - type: command
          command: "python scripts/quick_validate.py . 2>/dev/null || true"
          once: true
```

---
