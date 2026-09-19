## Matters

- Python only (ADR-042); sole exception `scripts/bootstrap-vm.sh`, not a model for new scripts.
- `pre_pr.py` runs the gates in `pre_pr_sequence.py` (`grep -c "_Gate(" scripts/validation/pre_pr_sequence.py` for the count).
- `git_hook_policy.py` is one file behind dozens of unrelated lefthook subcommands; 34 of 76 jobs call other modules directly. Reading one handler explains no other.
