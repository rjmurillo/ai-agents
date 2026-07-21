# Decision: Copilot CLI Plugin Hook Path Anchoring

Issue: #2205
Last updated: 2026-07-19

## Question

How should a generated Copilot CLI plugin hook locate its script without
depending on the user's working directory?

## Current official contract

The official Copilot CLI changelog states that plugin hooks receive:

- `PLUGIN_ROOT`
- `COPILOT_PLUGIN_ROOT`
- `CLAUDE_PLUGIN_ROOT`

Each points to the plugin installation directory. The official hook reference
defines command `cwd` as repository-relative or absolute. It does not promise
the plugin directory as cwd.

Sources:

- `.claude/skills/agent-harness-reference/references/official-hook-contracts.md`
- pinned `github/copilot-cli` changelog listed there

## Versioned empirical evidence

Copilot CLI 1.0.57 on Linux was probed with an installed plugin. With
`cwd: "."`, the hook ran from the user's working directory. All three
plugin-root variables pointed to the installation directory.

The probe proved:

- bare `./hooks/...` did not resolve from a foreign cwd;
- the plugin-root anchored command resolved;
- the generated command executed under the real CLI;
- the PowerShell fallback resolved with either Copilot or Claude root set.

## Decision

Generated bash commands use:

```bash
${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}
```

Generated PowerShell commands prefer `$env:COPILOT_PLUGIN_ROOT` and fall back
to `$env:CLAUDE_PLUGIN_ROOT`.

The implementation lives in
`build/scripts/generate_hooks_emit.py::_build_copilot_entry`.
`tests/build_scripts/test_generate_hooks_runtime_contract.py` executes the
launcher from a foreign cwd and includes a bare-path negative control.

## Scope

The 1.0.57 probe establishes cwd and plugin-root behavior for that version. It
does not establish matcher, event, permission, exit, or timeout semantics.
Use `agent-harness-reference` for those current rows.

## Lesson

The docs were silent during the incident and later caught up. Keep official
sources and versioned probes together. A test that compares generator output
with its own expected string cannot catch a wrong runtime variable.
