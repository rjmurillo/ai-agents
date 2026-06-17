# Issue 2622: LSP-first guards fail open when the language server is down

## Question

When the LSP runtime is configured but down (markdown LSP timed out at startup),
should the ADR-062 read/grep/pre-delegation guards keep hard-blocking native
Read/Edit/Grep, or fail open?

## Conventional answer

ADR-062 Section 8 says availability is a PURE configuration check with no live
probe, and the "configured != active" gap is "handled at the actual tool-call
boundary by fail-open." But before this fix the read and grep guards only failed
open on exceptions, a missing provider, or the SKIP_LSP_GATE kill switch. None of
those fire when the server times out while config still lists the language, so
the guards converted a degraded capability (no symbols) into a hard block on
basic file ops. The only escape was a manual session-wide SKIP_LSP_GATE=true.

## First-principles position

The fail-open promised by ADR-062 Section 5 was never wired for the runtime-down
case. Add an explicit runtime-health signal the guards consult, ALLOW + warn once
when it is set. Keep it a no-live-probe signal (env var LSP_DOWN) to preserve
Section 8 (sub-100ms, no probe timeout). Do NOT remove the block when the LSP can
actually serve: LSP-first enforcement stays intact when the server is up.

## Evidence

- scripts/hook_utilities/lsp_health.py (canonical; synced to .claude/lib via
  scripts/sync_plugin_lib.py): lsp_runtime_down() reads LSP_DOWN
  (true/1/yes/on); warn_once_lsp_down() emits one stderr line and writes a
  per-cwd marker (sha256(cwd) under XDG_STATE_HOME/ai-agents-lsp-gate, outside
  the git tree) so the warning is once per session; clear_lsp_down_marker() for
  SessionStart reset.
- Guards consult it AFTER the provider check (so it only fires when the guard
  would otherwise block): invoke_lsp_read_guard.evaluate, the grep guard main()
  after evaluate_command, the pre-delegation guard after provider_available.
- pytest tests/hooks (LSP suites): 261 passed; full tests/hooks: 1518 passed.
  Mutation of the read-guard fail-open made 3 tests fail, then restored.

## Decision

Shipped lsp_health as a deep module; three thin guards each gained a 3-line
fail-open consult. LSP_DOWN is the graceful-degradation signal (relaxes the gate
while the LSP cannot serve), distinct from SKIP_LSP_GATE (full kill switch).
Documented in .claude/rules/lsp-first.md. SECURITY/POLICY-SENSITIVE: this relaxes
an ADR-062 enforcement mechanism; routed for security/architect review before
merge. The signal producer (auto-set LSP_DOWN on observed server timeout) is a
follow-up; this PR adds the consumer + manual signal.
