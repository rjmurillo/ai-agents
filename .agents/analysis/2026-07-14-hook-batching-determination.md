---
status: determined
priority: high
blocking: false
---

# Hook Batching for Copilot CLI — Determination: Configuration, not Code

## Verdict

**The correct outcome is CONFIGURATION plus an explicit RUNTIME GAP, not new code.**

An earlier attempt in this session added a Claude-side in-process dispatcher that
consolidated the multi-shim matcher groups in `.claude/settings.json`. An independent
code review found blocking correctness defects. Every finding was reproduced and
confirmed here against GitHub's published hooks reference and the repo's own code. The
implementation was **reverted** (the feature branch was reset to `origin/main`; nothing
was pushed). This document replaces the earlier analysis, whose claims were invalid.

Why not code: in-process batching of the `.claude/settings.json` hooks **cannot preserve
Claude Code host semantics** (independent per-hook JSON stdout, parallelism, per-hook
timeouts, and which events may block). Why configuration: Copilot CLI already ships a
**valid** batched plugin dispatcher (ADR-068); the remaining problem is that Copilot ALSO
runs the unbatched repo-settings hooks additively, and there is no per-source disable
flag — so the mitigation is a configuration/structural change, documented below.

## Confirmed defects in the reverted approach

| # | Defect | Evidence |
|---|--------|----------|
| 1 | **Concatenated JSON stdout is invalid and dropped.** Running N hooks in one process concatenates their stdout. Several hooks emit JSON (`hookSpecificOutput.additionalContext`), so the host receives `{...}{...}` and ignores it — silently dropping injected context and any JSON-form decision. | GitHub hooks reference: *"Two or more non-progress JSON objects on stdout … concatenate into invalid JSON and be ignored — emit exactly one final decision object."* Code: `.claude/hooks/PreToolUse/invoke_topical_memory_injection.py` and `invoke_correction_applier.py` both `print(json.dumps({"hookSpecificOutput": {"additionalContext": …}}))`. |
| 2 | **Blocking events forced to observe.** `Stop` and `UserPromptSubmit` are blocking (exit 2 = block), but the generator classified everything except PreToolUse as `observe` (always return 0), discarding their block decisions. | `scripts/validation/hook_contracts.py`: `BLOCKING_HOOK_TYPES = {PreToolUse, PermissionRequest, Stop, SubagentStop, UserPromptSubmit}`. |
| 3 | **Fabricated timeout ceilings.** Hooks without an explicit `timeout` were assigned `_DEFAULT_TIMEOUT_SEC = 5` and the per-group budget was the *sum*; Claude's real default is ~60s per hook. Under Windows/Defender slowness the aggregate process can be host-killed below the real budget, converting advisory hooks into fail-closed denials. | `build/scripts/generate_claude_dispatchers.py:41,295`; mirrors `generate_dispatcher.py:236`. |
| 4 | **Regeneration footgun.** The generator has no dispatcher-entry guard; adding a hook to an already-consolidated group and regenerating can nest a dispatcher into its own manifest (self-referential shim → recursion → exit 2). | `consolidate_group` extracts a script from every hook command including `_dispatch__<key>.py`; no `is_dispatcher_entry` skip on the forward path. |
| 5 | **No build/drift ownership.** `generate()` has no caller in `build_all.py`; `build_all --check` does not validate it. `copy_bootstrap` copies `_bootstrap.py` only if missing, so a change to the canonical bootstrap silently drifts across copies. | Grep: only `generate_hooks_emit` (reverse `expand_all_dispatchers`) and the test import it; `copy_bootstrap` guards on `if not dest.is_file()`. |
| 6 | **Collision / trust risk.** `group_key` sanitizes matcher strings to filesystem-safe keys (distinct matchers can collide to one key, dropping a group), and the Copilot mirror's `expand_all_dispatchers` trusts `original_hooks` from possibly stale/malformed manifests. | `generate_claude_dispatchers.py` `group_key` + `expand_dispatcher_group`. |

Parallelism is also changed: Claude runs matching hooks concurrently with per-hook
timeouts; a single sequential `runpy` process serializes them under one budget.

## The runtime gap (why no clean config toggle exists)

Copilot CLI loads hooks from all sources **additively** and runs every entry: policy →
`.github/hooks` → user files → inline repo settings (**including `.claude/settings.json`**)
→ user settings → plugins. There is **no per-source disable flag** and no
`--no-repo-hooks`. So when both `.claude/settings.json` hooks and the installed
`project-toolkit` plugin are present, Copilot runs **both** — the unbatched repo shims
(sources) and the batched plugin dispatcher.

Sources (GitHub Copilot CLI docs): hooks reference (*"all hook entries from all sources
are run"*; the stdout-concatenation rule; `preToolUse` is fail-closed so a non-zero exit
denies the tool) and the CLI config-dir reference (Copilot reads the cross-tool subset of
`.claude/settings.json`, including `disableAllHooks`, `enabledPlugins`, `hooks`).

Consequence specific to this repo: the `.claude/settings.json` Python shims emit Claude
Code's `decision`/`hookSpecificOutput` shape (not Copilot's `permissionDecision`) and
depend on `CLAUDE_*` env; under Copilot they frequently exit non-zero, and `preToolUse`
fail-closed turns that into *"Denied by preToolUse hook from 'repo settings' (hook
errored)"* on every matching tool call. So in-repo Copilot pays for these hooks **and**
gets denied by them — the batched plugin is the working path.

## Configuration path (the mitigation) — owner decision

There is no key that means "run plugin hooks, skip `.claude/settings.json` inline hooks."
The available levers, with tradeoffs:

- **A. Per-user unblock (immediate, reversible, no repo change).** Add a gitignored
  `.github/copilot/settings.local.json` with `{"disableAllHooks": true}`. Claude Code is
  unaffected. Cost: disables **all** Copilot hooks for that developer (including the
  plugin), so Copilot gets no in-repo hook enforcement — acceptable because the
  repo-settings hooks currently deny/slow Copilot anyway. This is the analog of a
  machine-config workaround.
- **B. Structural, distribution-wide (durable, higher blast radius).** Remove the `hooks`
  key from `.claude/settings.json` and rely on `enabledPlugins`
  (`{"project-toolkit@ai-agents": true}`) so both tools load the **batched plugin**
  dispatcher. Copilot then runs only the batched plugin (fast, valid, one merged decision
  per event). Cost: in-repo Claude Code loses its *native* settings.json hooks and depends
  on the plugin being installed; this changes maintainer/contributor dev flow and is an
  enforcement-policy change for the repo. **Recommend owner sign-off before applying.**
- **C. Machine config (no repo change).** On the affected Windows box, remove the
  WindowsApps Store-alias `py.exe`/`python3.exe` shadow (the ~205ms launcher) and/or add
  Defender exclusions for the interpreter and repo. Reduces per-spawn cost independent of
  hook count.

Not recommended: a "hook multiplexer" that parses each hook's JSON stdout and merges to a
single valid decision while honoring per-event blocking and per-hook timeouts. It is
possible in principle but serializes parallel execution, depends on undocumented merge
semantics, and cannot be claimed at parity without empirical proof across stdout merging,
blocking events, matcher behavior, and timeouts. The risk is not justified when a
configuration path exists.

## Claims from the reverted analysis that were INVALID (corrected for the record)

- "Preserves every hook outcome / parity" — **false**: findings 1 and 2 drop injected
  context and Stop/UserPromptSubmit block decisions.
- "69% faster (1266 ms → 398 ms)" — measured a **semantically broken** path; not a valid
  parity benchmark.
- "All positive/negative/edge tests pass" — the tests exercised the dispatcher's *own*
  gate/observe logic, **not** fidelity to Claude's host protocol (stdout JSON merge,
  blocking-event set, per-hook timeout, parallelism), so they validated the wrong contract.
- "Copilot mirror byte-identical → invariant holds" — true but irrelevant; the Claude-side
  change itself was unsafe.

## Still-valid audit facts (unchanged)

- The Copilot **plugin** dispatcher (ADR-068) is correct: it fans out internally but emits
  exactly one merged decision object, which is valid under Copilot's protocol.
- The `fix/batched-toolcalls-hook-shims` worktree/branch is **superseded** (main far
  ahead; working tree CRLF-only) — leave it untouched.
- The frontier-vs-weaker model asymmetry stands: damage-preventing gates matter for every
  tier; advisory-nudge hooks carry most per-event cost and least frontier value. This does
  not justify unsafe batching; it argues for the plugin path and for owner-chosen scoping.

## Recommendation

1. Immediate: apply **A** to unblock the maintainer's in-repo Copilot sessions.
2. Durable: decide on **B** (owner sign-off) so the distribution and both tools use the
   batched plugin, removing the duplicate unbatched repo-settings hooks.
3. Do not reintroduce Claude-side in-process hook batching.
