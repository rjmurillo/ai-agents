[tests/]
|Pytest suite: root guard, `tests/conftest.py`, flat `test_*.py`, topic subdir... (see: .project-toolkit/context/tests/details/tests.md)
[Matters]
|Root `conftest.py` autouse `_guard_real_repo_head`: fails (#2316) if a test g... (see: .project-toolkit/context/tests/details/matters.md)
[Entry points]
|`git_hook_policy.py pytest`: on-demand local `pytest --testmon` wrapper (not ... (see: .project-toolkit/context/tests/details/entry-points.md)
[Where to look]
|| Path | Why | (see: .project-toolkit/context/tests/details/where-to-look.md)
[Skip]
|`tests/build_scripts/fixtures/*/expected/`: frozen ADR-109 B1/B2 lossless pin... (see: .project-toolkit/context/tests/details/skip.md)
[Constraints]
|New skill tests go under `tests/skills/<name>/` (`check_colocated_skill_tests... (see: .project-toolkit/context/tests/details/constraints.md)
[Dangerous assumptions]
|`check_nested_tests.py` ignores helpers not named `test_*.py` (`tests/hook_te... (see: .project-toolkit/context/tests/details/dangerous-assumptions.md)
[Dependencies]
|Feeds `pytest.yml` `zero-collection-guard` (blocking, no `needs:`/`if:`) and ... (see: .project-toolkit/context/tests/details/dependencies.md)
[Architecture]
|`tests/evals/`: ADR-057 corpora & `scripts/eval/` tests. `evals/`: ADR-058 ag... (see: .project-toolkit/context/tests/details/architecture.md)
[Commands]
|(see detail file) (see: .project-toolkit/context/tests/details/commands.md)