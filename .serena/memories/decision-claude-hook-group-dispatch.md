# Decision: Claude-side hook group dispatch (ADR-082, session 3044)

**Question**: How to cut per-event hook process spawn on Claude Code and Copilot (issue #3075, Windows Defender pain)?

**Conventional answer**: 2026-07-14 analysis rejected a Claude-side dispatcher (protocol hazards) and recommended prune/rescope only.

**First-principles position**: The rejection was about an ad hoc multiplexer, not consolidation itself. A purpose-built group runner meeting the analysis doc's own bar (single JSON output, per-event modes, no invented timeouts, generator ownership, negative-control tests) is safe. Implemented on branch perf/claude-hook-dispatch (stacked on perf/batch-claude-hooks / PR #3076).

**Key facts**:
- `.claude/lib/claude_hook_dispatch.py` + `.claude/hooks/invoke_dispatch_claude.py` + `dispatch_groups.json`: one spawn per (event, matcher) group; modes gate/gate_all/observe; stdout captured and merged into ONE protocol document (the concatenation hazard that killed the earlier attempt).
- Group contracts fail closed before execution: nonempty shims, reviewed event/mode pairs, unique relative `.py` paths, and hooks-directory containment. Unknown JSON is context and cannot terminate a gate before later shims run. Only event-valid blocking shapes are terminal; malformed, allow-shaped, unsupported, and invalid typed decision objects fail closed.
- Plugin double-fire fix: all plugin hooks.json entries route through the dispatcher; it exits 0 when the project publishes the same plugin (name match). Coverage invariant test: plugin shims minus repo shims == documented prune allowlist.
- Current Copilot docs and 1.0.72-1 probes show matcher support. PascalCase tool matchers filter Claude tool names. Argument-sensitive patterns still need script-side filtering.
- Copilot Stop and SubagentStop cannot use a plain observe dispatcher. Multiple structured decision objects concatenate into invalid JSON. Generated Copilot Stop hooks remain separate host registrations.
- `AI_AGENTS_PROJECT_REPO=1` in settings env kills the per-hook `git remote get-url origin` child spawn.
- Historical spawns: Bash 5->2, Write/Edit 5->2, prompt 4->1, Stop 3->1, push 11->2. Linux probe 202ms->81ms per Bash pre-gate. Current Copilot Stop uses direct registrations to preserve decisions.
- The false-completion gate matches completion words ANYWHERE in a Bash command (heredocs included) - split file-edit commands from `git commit` commands (issue #3089). LSP pre-delegation guard needs literal "LSP CONTEXT" or "defined at path:line" phrasing (issue #3091).
- Scope-explosion pre-commit gate counts files vs origin/main, so stacked branches false-positive at 50; documented escape SKIP_SCOPE_CHECK=1 requires user authorization under the auto-mode classifier.

**Related**: `agent-harness-reference`, `mem:copilot-disable-all-hooks-windows`, ADR-068, ADR-082, `.agents/analysis/2026-07-16-adr-082-architect-review.md`.
