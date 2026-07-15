# Two-pipeline agent mirror recipe

When changing shared agents, update `templates/agents/{agent}.shared.md` and the manual Claude source `src/claude/{agent}.md`; generation syncs Copilot CLI and VS Code outputs, not Claude source. Validate with `build/scripts/build_all.py --check`, `build/scripts/validate_install_parity.py`, and scoped drift checks before push.

Why: PR #2707 session 2596 hit review feedback because agent mirror work must satisfy both generated outputs and the manual Claude source path.