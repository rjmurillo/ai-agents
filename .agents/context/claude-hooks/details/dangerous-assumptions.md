## Dangerous assumptions

- `PreToolUse/_bootstrap.py` looks dead. The Copilot dispatcher generator copies this exact path into every generated event directory and reads its bytes as the clean-safe signature; deleting it fails two test modules.
- `PreCompact/CLAUDE.md` reads as a claude-mem stub. Hand-authored and stale: it describes an on-disk checkpoint write `invoke_compact_checkpoint.py` no longer makes (ADR-082, issue #3217). Sole output is a resume-context string on stdout.
- "Fail-open means uninstrumented": false for 2 of 6 invokers. `invoke_context_loader.py`/`invoke_checkout_freshness_check.py` append a best-effort audit line under `.project-toolkit/.hook-state/` even when degraded. The 4 importing `hook_utilities` call `skip_if_consumer_repo()` first, which reads the git origin remote, not `.agents/` presence.
