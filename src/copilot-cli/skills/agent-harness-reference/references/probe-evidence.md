<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->

# Probe Evidence: Verbatim Measurements Behind the Contract Tables

This file quotes the primary measurements the SKILL.md tables summarize, so a
reader can audit the contract without re-opening every source. Quotes are
verbatim per the canonical-source-mirror rule
(`.claude/rules/canonical-source-mirror.md`).

## 1. Plugin root and cwd (issue #2205, session 1873)

Measured against GitHub Copilot CLI 1.0.57 and Claude Code 2.1.159 by
installing a probe plugin whose hook dumped its environment and executed the
generated command from a non-plugin cwd.

Verbatim from ADR-071
(`.agents/architecture/ADR-071-plugin-hook-runtime-contract-verification.md`,
section "Verified Runtime Contract"):

```text
EVENT: preToolUse  PWD=/tmp
COPILOT_PLUGIN_ROOT=[/home/.../installed-plugins/_direct/<plugin>]
CLAUDE_PLUGIN_ROOT=[/home/.../installed-plugins/_direct/<plugin>]
PR-form anchored=[${...}/hooks/probe_target.txt] exists=YES
bare ./hooks/probe_target.txt exists=NO
```

Verbatim from the decision memory
(`.serena/memories/decision-copilot-cli-hook-plugin-root-contract.md`):

```text
Copilot launches a plugin hook with cwd = the user's working dir (measured
PWD=/tmp) and exports BOTH COPILOT_PLUGIN_ROOT and CLAUDE_PLUGIN_ROOT (plus a
bare PLUGIN_ROOT), all pointing at the install dir
```

The same memory records that the public hooks reference documents NONE of
these variables, and one external source claimed `CLAUDE_PLUGIN_ROOT` is "not
available in Copilot-format plugins". The docs were wrong by omission; only
the probe settled it.

## 2. Payload casing (issue #2290, session fix/2290)

Measured against GitHub Copilot CLI 1.0.58 by installing a probe plugin that
captured stdin for both event-key casings.

Verbatim from `.serena/memories/copilot-hooks-observations.md`:

```text
camelCase events send toolName/toolArgs, PascalCase events send
tool_name/tool_input. Always use PascalCase in eventRemap to get snake_case
payloads matching what hook scripts expect.
```

```text
toolArgs in camelCase payloads is a raw JSON string, not a parsed dict. Must
json.loads() before passing to _shim_normalize_args. PascalCase tool_input is
already a parsed dict.
```

Why the gap existed: ADR-071's probe verified env vars and cwd but never
captured stdin. The test that "covered" payload parsing constructed its own
payload, proving internal consistency only (the self-referential test
anti-pattern, banned by `.claude/rules/canonical-source-mirror.md`).

## 3. Timeout and kill budget (issue #2295)

Verbatim from ADR-068
(`.agents/architecture/ADR-068-consolidated-hook-dispatcher.md`, Context):

```text
Measured cold-start cost on Windows (py -3 -u <shim>) is ~246 ms per
invocation. Sequential aggregate is ~8.7 s. Copilot's observed kill
threshold is 2-3 s, which timeoutSec: 5 in hooks.json does not raise:
the budget is host-controlled, not generator-controlled.
```

Exit 143 is SIGTERM from that kill, not a payload crash. Exit-code triage:
143 = timeout, 2 = hook logic rejected or crashed, 1 = logic error
(`.serena/memories/copilot-hooks-observations.md`).

## 4. How to re-run a probe

Follow `ai-agents-empirical-probe-toolkit` recipe 1. Minimum bar for a new
contract dimension:

1. Pin and record the CLI version (`copilot --version`, `claude --version`).
2. Run the probe from a cwd that is NOT the plugin root.
3. Capture env AND stdin (the #2290 lesson: env-only probes miss half the
   contract).
4. Include a negative control (a deliberately wrong form that must fail).
5. Record the result in a Serena decision memory and update the SKILL.md
   table row with the new version and date.
