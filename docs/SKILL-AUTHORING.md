# Skill Authoring Guide

This guide covers how to create Claude Code skills with correct YAML frontmatter, model selection, and file structure.

Based on the analysis in `.project-toolkit/analysis/claude-code-skill-frontmatter-2026.md`.

## Frontmatter Schema

Every skill lives in a `SKILL.md` file inside a directory under `.claude/skills/`. The file starts with YAML frontmatter.

### Required Fields

| Field | Type | Constraints | Purpose |
|-------|------|-------------|---------|
| `name` | string | Lowercase, alphanumeric + hyphens, max 64 chars | Skill identifier. Must match directory name. |
| `description` | string | Max 1024 characters | Primary trigger mechanism. Claude uses this to decide when to activate the skill. |

### Optional Fields

| Field | Type | Constraints | Purpose |
|-------|------|-------------|---------|
| `model` | string | Bare rolling alias only (`haiku`), never a versioned id. Requires `model-rationale`. See [Model Selection](#model-selection). | Overrides the harness-inherited model. |
| `model-rationale` | string | Required whenever `model` is set | One line justifying the cheaper tier ([ADR-080](../.project-toolkit/architecture/ADR-080-model-pin-justification-policy.md) rule 3). |
| `allowed-tools` | string | Comma-separated tool names | Restricts which tools Claude can use during execution. |
| `version` | string | Semantic versioning (e.g., `1.0.0`) | Tracks skill evolution. Not validated by Claude Code. |
| `license` | string | SPDX identifier (e.g., `MIT`) | Legal licensing. Not validated by Claude Code. |
| `metadata` | object | Custom key-value pairs | Domain-specific configuration. |

### Minimum Valid Frontmatter

```yaml
---
name: my-skill
description: Does something useful when you need it
---
```

### Full Frontmatter

```yaml
---
name: advanced-skill
version: 2.0.0
license: MIT
description: Complex orchestration skill requiring maximum reasoning capability
allowed-tools: Bash(pwsh:*), Read, Write, Grep
metadata:
  domains: [architecture, planning]
  complexity: advanced
  capability:
    kind: orchestrator
    status: active
---
```

No `model:` line appears above on purpose: the skill inherits the harness
model, which is the correct default under
[ADR-080](../.project-toolkit/architecture/ADR-080-model-pin-justification-policy.md).

## Validation Rules

**YAML syntax:**

- Frontmatter MUST start with `---` on line 1. No blank lines before it.
- Frontmatter MUST end with `---` before Markdown content.
- Use spaces for indentation. Tabs are not allowed.

**Field validation:**

- `name`: Only lowercase letters, numbers, hyphens. Regex: `^[a-z0-9-]{1,64}$`
- `description`: Non-empty, max 1024 characters, no XML tags.
- `model`: Omitted, or a bare rolling alias that prices below the harness default (see Model Selection below). A versioned id is rejected.
- `model-rationale`: Required whenever `model` is present.
- `allowed-tools`: Tool names must match available Claude Code tools.

**File structure:**

- `SKILL.md` is the only required file in a skill directory.
- Keep `SKILL.md` under 500 lines for optimal performance.
- Use progressive disclosure for longer skills (see File Structure below).

## Model Selection

Omit `model:`. A skill inherits the model the harness is running, and that is
the correct default that needs no justification
([ADR-080](../.project-toolkit/architecture/ADR-080-model-pin-justification-policy.md)).
Most skills in `.claude/skills/` carry no `model:` line; the few that do all
use the `haiku` cost alias described below.

**A skill may never carry a versioned model id** (`claude-opus-4-6`,
`claude-haiku-4-5`, `claude-sonnet-4-6-20260101`). The eval harness sweeps
agents, not skills (`scripts/eval/eval-model-sweep.py` builds child arguments
for `--agent` only), so no evidence can justify a skill version pin, and
`scripts/validation/check_model_pins.py` rejects one:

```text
skill carries versioned id 'claude-opus-4-6'; skills and commands may not pin a version (ADR-080 rule 1)
```

### The Two Conformant States

**1. No `model:` line (default).** Use this unless you have a cost reason not to.

**2. A bare rolling alias that prices below the harness default, with a
`model-rationale:` line.** The default is `claude-sonnet-4-6`, so `haiku` is
the only alias that qualifies today. `opus` and `sonnet` do not price below the
default and fail the check with `cost rationale on 'sonnet' but it does not
price below the default 'claude-sonnet-4-6'`.

```yaml
model: haiku
model-rationale: cost. The 'haiku' rolling alias resolves via the platform model_tiers map to a tier priced below the sonnet-tier harness default; this unit is routing/mechanical work where the cheaper tier suffices (ADR-080 rule 3).
```

### Model Tiers

Aliases resolve through `model_tiers` in `templates/platforms/copilot-cli.yaml`.
Prices come from `MODEL_PRICING_RATES_USD_PER_1K_TOKENS` in
`scripts/eval/_eval_common.py`.

| Alias | Resolves to | Cost (Input/Output per MTok) | Allowed in a skill? |
|-------|-------------|------------------------------|---------------------|
| `opus` | `claude-opus-4.6` | $5 / $25 | No: does not price below the default |
| `sonnet` | `claude-sonnet-4.6` | $3 / $15 | No: it is the default, so not below it |
| `haiku` | `claude-haiku-4.5` | $1 / $5 | Yes, with `model-rationale` |

### When to Pin the Cost Alias

Pin `haiku` when the skill is routing or mechanical work: pattern matching,
format fixes, fast hooks. Reach for it as a cost decision, not a capability
decision. Anything that needs reasoning depth, orchestration, or judgment
should inherit instead, because inheriting tracks whatever model the harness
runs rather than freezing a guess.

### Agents Are Different

[ADR-080](../.project-toolkit/architecture/ADR-080-model-pin-justification-policy.md)
rule 2 lets an **agent** carry a versioned pin when a committed KEEP_PIN sweep
justifies it in `.agents/governance/model-pin-evidence.json`. That path does
not exist for skills or commands. Do not copy an agent's frontmatter into a
`SKILL.md`.

## Description Best Practices

The `description` field is the primary triggering mechanism. Include:

1. **What**: Clear statement of skill functionality.
2. **When**: Explicit trigger conditions.
3. **Keywords**: Terms users would naturally say.

```yaml
# Bad: too generic
description: Helps with testing

# Good: specific with triggers
description: Execute Pester tests with coverage analysis. Use when asked to "run tests", "check coverage", or "verify test suite".

# Bad: missing triggers
description: Analyzes code quality and suggests improvements

# Good: includes natural language triggers
description: Static analysis with Roslyn analyzers. Use for "check code quality", "run analyzers", "find code smells", or "enforce style guidelines".
```

## Allowed-Tools Configuration

Use `allowed-tools` to enforce least privilege.

```yaml
# Read-only analysis
allowed-tools: Read, Grep, Glob

# GitHub operations
allowed-tools: Bash(gh:*), Bash(pwsh:*), Read, Write
```

**Tool name patterns:**

- Exact tool: `Read`, `Write`, `Edit`
- Command prefix: `Bash(pwsh:*)`, `Bash(git:*)`
- Multiple: `Read, Write, Grep, Glob`

## File Structure

For skills under 500 lines, a single `SKILL.md` is sufficient.

For larger skills, use progressive disclosure:

```text
.claude/skills/my-skill/
  SKILL.md              # Essential info only (< 500 lines)
  references/
    workflow.md          # Detailed workflow diagrams
    examples.md          # Comprehensive examples
    api-reference.md     # Complete API documentation
  scripts/
    helper.py            # Automation scripts
```

`SKILL.md` should link to reference docs but not embed them.

## Portable Script Invocations (Required)

A `SKILL.md` runs in more than one place: the upstream `rjmurillo/ai-agents`
checkout (root `./.claude`), a Claude Code plugin install, and a GitHub Copilot
CLI vendored install. A command that hard-codes the upstream layout works only
upstream and fails silently everywhere else.

**Never invoke a bare `.claude/skills/...` script path:**

```bash
# WRONG: bare path exists only in the upstream checkout (issue #2837).
python3 .claude/skills/github/scripts/pr/test_pr_merge_ready.py --pull-request 1
```

**Resolve the script root through a plugin-root env var with a source
fallback**, then invoke via the variable. Re-declare the variable at the top of
each fenced `bash` block that uses it, so every snippet is runnable on its own:

```bash
# CORRECT: uses a harness plugin root when one is exported, otherwise source checkout.
SCRIPTS_DIR="${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/github/scripts/pr"
python3 "$SCRIPTS_DIR/test_pr_merge_ready.py" --pull-request 1
```

This form is sufficient when the host exports `COPILOT_PLUGIN_ROOT` or
`CLAUDE_PLUGIN_ROOT`, or when the command runs from the source checkout. If a
skill must run in a Copilot CLI install where neither variable is exported,
add a fallback that probes the installed plugin roots before the command runs.
The `/pr-autofix` skill uses that pattern for its PR helper scripts.

For skills that only target Claude Code, the shorter
`SCRIPTS_DIR="${CLAUDE_PLUGIN_ROOT:-.claude}/skills/..."` form is acceptable.

This is enforced by `scripts/validation/check_skill_md_exec_portability.py` (CI
job "Validate Vendor Portability"). The check grandfathers existing offenders in
`scripts/validation/skill_md_exec_portability_baseline.json` and fails a PR that
adds a new bare invocation or raises a file's count above its baseline. Migrate
grandfathered skills to the resolved form and run the check with
`--update-baseline` to tighten the baseline.

If a skill genuinely must invoke a bare upstream path (for example, a bootstrap
that runs before any plugin root exists), declare it with a machine-readable
marker so the exemption is reviewable:

```markdown
<!-- vendor-portability-exec: bootstrap runs before COPILOT_PLUGIN_ROOT is set -->
```

This marker is distinct from the prose guard's `vendor-portability` marker:
declaring a prose path dependency does not exempt executable invocations.

## Working Examples

Each example mirrors the frontmatter that ships in the named skill today
(descriptions abridged for length).

### Cost Alias: Mechanical Work

`.claude/skills/fix-markdown-fences/SKILL.md` is the one shape that may carry a
`model:` line: a bare alias cheaper than the default, plus its rationale.

```yaml
---
name: fix-markdown-fences
version: 1.1.0
model: haiku
model-rationale: cost. The 'haiku' rolling alias resolves via the platform model_tiers map to a tier priced below the sonnet-tier harness default; this unit is routing/mechanical work where the cheaper tier suffices (ADR-080 rule 3).
description: >-
  Repair malformed markdown code fence closings. Use when you say "fix markdown
  fences", "repair code block closings", or "markdown rendering broken".
license: MIT
---
```

### Inherited Default: Standard Workflow

`.claude/skills/doc-accuracy/SKILL.md` carries no `model:` line, so it runs on
whatever the harness runs.

```yaml
---
name: doc-accuracy
version: 1.0.0
description: >-
  Multi-phase documentation verification treating code as source of truth. Use
  when you say "check documentation accuracy", "verify code examples compile",
  or "audit docs vs code".
license: MIT
---
```

### Inherited Default: Multi-Agent Orchestration

Orchestration is not a reason to pin. `.claude/skills/analyze/SKILL.md`
coordinates multi-step investigation and still inherits.

```yaml
---
name: analyze
version: 1.1.0
description: Systematic multi-step codebase analysis producing prioritized findings with file-line evidence. Use when you say "analyze this codebase", "run security assessment", or "find code smells".
license: MIT
user-invocable: true
allowed-tools:
  - Read
  - Grep
  - Glob
  - Bash
  - Task
---
```

## Routing Role

Every skill template declares `metadata.routing`, stating who selects it and
how. `scripts/validation/check_skill_routing_roles.py` refuses a template
with no block, an invalid role, a role/invoker contradiction, or a malformed
`explicit-only` or `deprecated` declaration (REQ-038, DESIGN-036).

```yaml
metadata:
  routing:
    role: nested-helper
    invoker: pr-quality-all
    trigger: pr-quality-all runs the security axis
    user-facing: true
```

### The six roles

| Role | Legal invoker | Notes |
|---|---|---|
| `front-door` | `autoplan`, or `harness` for a skill the harness selects by description | The six lifecycle skills (`spec`, `plan`, `build`, `test`, `review`, `ship`) are front-door: autoplan routes to them. |
| `lifecycle` | one of `spec`, `plan`, `build`, `test`, `review`, `ship` | A skill one of the six lifecycle skills selects. |
| `conditional-adjunct` | any other skill or agent, not itself | Selected by another skill or agent under a condition. |
| `nested-helper` | any other skill or agent, not itself | Selected internally by another skill or agent. |
| `explicit-only` | `user` | Reachable only by the user naming it directly; requires `rationale`. |
| `deprecated` | any, or absent | Requires `replaced-by` (a non-deprecated skill name) or a positive `removal-issue`. |

`conditional-adjunct` and `nested-helper` may not be invoked by `user`,
`harness`, or the skill's own name.

### Required keys by role

| Key | Type | Required |
|---|---|---|
| `role` | one of the six roles above | always |
| `invoker` | skill, agent, `user`, or `harness` | unless `deprecated` |
| `trigger` | non-empty string | unless `deprecated` |
| `user-facing` | boolean | unless `deprecated` |
| `scenario` | relative path under `tests/evals/` | never; defaults to `tests/evals/skill-scenarios/<name>.json` |
| `intents` | non-empty list of non-empty strings | never; `front-door` only |
| `rationale` | non-empty string | `explicit-only` only |
| `replaced-by` | a non-deprecated skill name | `deprecated`, unless `removal-issue` is set |
| `removal-issue` | positive integer | `deprecated`, unless `replaced-by` is set |

No other key is allowed in the block.

`user-facing` is true when a person may ask for the skill directly, by name
or by its trigger phrases, and false for a helper only another skill or
agent runs. An `explicit-only` skill must set it to true. Its `rationale`
must say why automatic routing would be unsafe or noisy. Quote a value that
contains `:`, or YAML reads it as a nested key. Quote a value that contains
`" #"` (a space, then `#`, as in an issue reference like "issue #1234"), or
YAML reads the rest of the line as a comment and silently truncates the
scalar there.

### `intents` (DESIGN-037)

A `front-door` skill may declare `intents`: phrases the autoplan long-tail
resolver (`.claude/skills/autoplan/scripts/resolve_route.py`) matches
against a request that misses the high-traffic table. An intent matches
when every one of its words appears in the request (lowercased, stop words
dropped, a trailing `s` folded). Write two to six phrases naming the
skill's core question:

```yaml
    intents:
      - developer experience audit
      - developer friction
```

The gate refuses `intents` on any role but `front-door`, and refuses a
non-list, an empty list, or an empty string item. When two skills' intents
both cover a request, add a "When to use / Do NOT use" positive and
negative example pair to each; `programming-advisor` and
`buy-vs-build-framework` are the worked example.

### How to pick a role

1. Search every other skill template and agent body for your skill's exact
   name. If one names it, that is your invoker, and its role follows from
   the table above (a lifecycle skill selecting it makes it `lifecycle`; any
   other skill or agent makes it `conditional-adjunct` or `nested-helper`
   depending on whether the selection is conditional or an internal
   implementation detail). A redirect such as "Do NOT use for X (use
   your-skill)" counts as a conditional route: the trigger is X.
2. If the skill exists to intercept requests automatically (its own
   description says it triggers on a pattern, as `autoplan` and
   `github-url-intercept` do), use `front-door` with `invoker: harness`.
   Plain description matching does not qualify, since every skill has it.
3. If nothing names it and the harness does not select it either, but the
   skill answers one clear question in the user's own words, use
   `front-door` with `invoker: autoplan` and add `intents`, instead of
   `explicit-only`. Fall back to `explicit-only` (`invoker: user`, a
   `rationale`) only when auto-routing is unsafe or too broad to phrase as
   a few intents.
4. A skill being retired uses `deprecated`, naming its replacement or a
   removal issue instead of a live `invoker`.

The lifecycle skills themselves (`spec`, `plan`, `build`, `test`, `review`,
`ship`) are front-door: autoplan is their invoker, not the other way around.

### Running the gate

```bash
uv run python scripts/validation/check_skill_routing_roles.py --report
uv run python scripts/validation/check_skill_routing_roles.py --report --format json
```

`--report` prints totals by role, the unresolved list (skills whose
declared invoker's own text never names them, an upper bound rather than a
refusal), the inbound-zero list (skills no skill or agent text names at
all), and scenario coverage. Scored routing accuracy is out of scope for
this gate; issue #5389 owns it.

## Frontmatter Checklist

Before committing a new skill, verify:

- [ ] Frontmatter starts with `---` on line 1 (no blank lines before)
- [ ] `name` field: lowercase, alphanumeric + hyphens, < 64 chars
- [ ] `description` field: includes trigger keywords, < 1024 chars
- [ ] `model` field: absent, or a bare cost alias (`haiku`) with `model-rationale`. Never a versioned id (ADR-080 rule 1)
- [ ] `allowed-tools` (if present): comma-separated valid tool names
- [ ] Frontmatter ends with `---` before Markdown content
- [ ] YAML uses spaces for indentation (not tabs)
- [ ] SKILL.md under 500 lines (use progressive disclosure if larger)
- [ ] Pre-commit validation passes (`.claude/skills/SkillForge/scripts/validate-skill.py <skill-dir>`, which Lefthook's `skillforge` job runs on staged `SKILL.md` files through `scripts/validation/git_hook_policy.py`)
- [ ] Model-pin check passes (`uv run python scripts/validation/check_model_pins.py`; `scripts/validation/pre_pr.py` runs it in warn mode)
- [ ] `metadata.routing` declared with a valid role and invoker (`uv run python scripts/validation/check_skill_routing_roles.py --report`)

## Troubleshooting

### Model Pin Rejected

**Symptom**: `check_model_pins.py` reports
`skill carries versioned id 'claude-sonnet-4-6'; skills and commands may not pin a version (ADR-080 rule 1)`.

**Fix**: Delete the `model:` line so the skill inherits, or drop to the bare
cost alias with a rationale.

```yaml
# Wrong: versioned id in a skill
model: claude-sonnet-4-6

# Right: inherit (delete the line), or:
model: haiku
model-rationale: cost. The 'haiku' rolling alias resolves via the platform model_tiers map to a tier priced below the sonnet-tier harness default; this unit is routing/mechanical work where the cheaper tier suffices (ADR-080 rule 3).
```

### 404 Not Found Error

**Symptom**: `404 not_found_error: model 'sonnet-4.6' not found`

**Cause**: A `model:` value that is neither a rolling alias nor a real model id.

**Fix**: Use a bare rolling alias, or remove the line and inherit. A skill
cannot fix this by reaching for a versioned id: the model-pin check rejects
that (see above).

```yaml
# Wrong
model: sonnet-4.6

# Right
model: haiku
model-rationale: cost. The 'haiku' rolling alias resolves via the platform model_tiers map to a tier priced below the sonnet-tier harness default; this unit is routing/mechanical work where the cheaper tier suffices (ADR-080 rule 3).
```

### Skill Not Triggering

**Cause**: Description lacks natural language trigger keywords.

**Fix**: Add explicit trigger phrases that match how users ask for the skill.

### Platform Mismatch

**Symptom**: Skill works in Claude Code but fails on Bedrock/Vertex.

**Cause**: Aliases are Anthropic API only. Use platform-specific identifiers or document requirements in metadata.

## References

- [Agent Skills, Claude Code Docs](https://code.claude.com/docs/en/skills)
- [Models overview, Claude Docs](https://platform.claude.com/docs/en/about-claude/models/overview)
- [Skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- Source analysis: `.project-toolkit/analysis/claude-code-skill-frontmatter-2026.md`
