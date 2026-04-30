Confirmed structural bug. The original `.claude/hooks/PreToolUse/invoke_session_log_guard.py` was registered under multiple matchers in `.claude/settings.json` and used a single body that branches on the actual command. The M5 generator splits a multi-matcher hook into per-matcher copies (one shimmed file per matcher) but did not split the body logic. Result: the pr-creation copy fires its shim correctly, then the body returns immediately because it only handles `git commit`.

Two ways to fix (both real work, neither in scope for current commits):
1. **Per-matcher body specialization**: emit the matched-command branch inline so each generated copy has only the relevant body. Requires source-side annotation of which matcher each branch handles.
2. **Stop splitting**: keep one body file with all branches, dispatch from a single shim that knows which matchers to fire on. Loses per-matcher filename auditability but matches the original semantics.

Tracking as M7 follow-up. Leaving unresolved.
