# Feedback: fail-open must cover the launcher layer, not just the script body

**Origin:** PR #2205 customer-wedge incident. See `.agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md`.

## The blind spot

`build/scripts/generate_hooks.py` wraps each Claude hook body in a try/except fail-open shim (`_wrap_body_in_function` / `_has_fail_open_handler`): "hook error (fail-open): ... return 0". That protects against exceptions raised INSIDE the script. It does nothing when the LAUNCHER fails before the script runs. A wrong path makes `python3 -u "<path>"` exit code 2 ("can't open file") before reading a byte. The shim is unreachable.

Consequence: a single failing hook launcher can wedge the host environment (every tool call blocked), forcing uninstall to recover. Fail-open at the wrong layer is no protection.

## How to apply

- When you rely on fail-open for a hook, confirm WHICH layer fails. Launcher-level failures (file not found, interpreter not on PATH) bypass in-script handlers.
- Prefer launcher-level graceful degradation where the host tolerates it: shape the command so a missing/unresolved target logs to stderr and exits 0 instead of erroring. A path bug should be a logged warning, never a wedged environment.
- Treat a change to the launcher/command SHAPE as architecture (it is the exact surface that caused the incident); route through architect review before shipping.
- Always pair this with the verification rule: `mem:feedback-generated-artifact-runtime-verification`.
