[tests/]
|Pytest suite: root guard, `tests/conftest.py`, flat `test_*.py`, topic subdir... (see: .project-toolkit/context/tests/details/tests.md)
[Matters]
|Root `conftest.py` autouse `_guard_real_repo_head`, every test: fails (#2316)... (see: .project-toolkit/context/tests/details/matters.md)
[Entry points]
|`git_hook_policy.py pytest`: lefthook pre-push pytest command. (see: .project-toolkit/context/tests/details/entry-points.md)
[Where to look]
|| Path | Why | (see: .project-toolkit/context/tests/details/where-to-look.md)
[Skip]
|`tests/build_scripts/fixtures/*/expected/`: frozen ADR-109 B1/B2 lossless pin... (see: .project-toolkit/context/tests/details/skip.md)
[Constraints]
|New skill tests go under `tests/skills/<name>/`. `check_colocated_skill_tests... (see: .project-toolkit/context/tests/details/constraints.md)
[Dangerous assumptions]
|`check_nested_tests.py` does not scan every test file, and not by depth: help... (see: .project-toolkit/context/tests/details/dangerous-assumptions.md)
[Dependencies]
|Feeds `pytest.yml`'s `zero-collection-guard` (blocking, no `needs:`/`if:`) an... (see: .project-toolkit/context/tests/details/dependencies.md)
[Architecture]
|`tests/evals/` is ADR-057 prompt-regression corpora plus tests of its `script... (see: .project-toolkit/context/tests/details/architecture.md)
[Commands]
|(see detail file) (see: .project-toolkit/context/tests/details/commands.md)