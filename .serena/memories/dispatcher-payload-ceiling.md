# Dispatcher payload ceiling

## Contract

The generated Copilot hook dispatcher reads at most 64 MiB plus one byte from
stdin. Payloads at or below 64 MiB dispatch normally. Payloads above 64 MiB
return before any shim receives the truncated buffer.

Gate events deny oversize input with exit 2. Observe events return exit 0
because observers do not gate host actions. Both paths log the event and static
shim names without logging payload bytes.

## Security reasoning

The bounded read mitigates CWE-400 resource exhaustion. A prompt-injected tool
call cannot bypass a PreToolUse guard by padding its payload because gate events
fail closed before the tool runs. Oversize observe events can skip best-effort
telemetry, but they emit a loud anomaly diagnostic and cannot bypass a gate.

## Evidence

- `build/scripts/generate_dispatcher.py` owns the canonical entrypoint.
- `tests/build_scripts/test_generate_dispatcher.py` covers exact-ceiling allow,
