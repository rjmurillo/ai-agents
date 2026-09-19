[scripts/]
|Repo automation for developers, lefthook, and CI. (see: .agents/context/scripts/details/scripts.md)
[Matters]
|Python only (ADR-042); sole exception `scripts/bootstrap-vm.sh`, not a model ... (see: .agents/context/scripts/details/matters.md)
[Entry points]
|`uv run python scripts/validation/pre_pr.py` (`--quick`, `--markdown-lint-onl... (see: .agents/context/scripts/details/entry-points.md)
[Where to look]
|| Path | Why | (see: .agents/context/scripts/details/where-to-look.md)
[Skip]
|`scripts/ci/*_baseline.txt`: ratchet ceilings, paired with `*_ratchet.py`; us... (see: .agents/context/scripts/details/skip.md)
[Constraints]
|Subprocess text capture MUST pass `encoding="utf-8", errors="replace"` (`chec... (see: .agents/context/scripts/details/constraints.md)
[Dangerous assumptions]
|`scripts/README.md` opens "PowerShell scripts for the AI Agents system": stal... (see: .agents/context/scripts/details/dangerous-assumptions.md)
[Dependencies]
|Plugin lib source: `scripts/{github_core,hook_utilities,ai_review_common}`, `... (see: .agents/context/scripts/details/dependencies.md)
[Architecture]
|`_SEQUENCE`: a tuple of `_Gate(name, run, skip_when_quick, already_run_by, no... (see: .agents/context/scripts/details/architecture.md)
[Commands]
|(see detail file) (see: .agents/context/scripts/details/commands.md)