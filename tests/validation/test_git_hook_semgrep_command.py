from scripts.validation import git_hook_policy as policy


def test_semgrep_command_bounds_worker_and_rule_budgets() -> None:
    command = policy._semgrep_command("auto", ["source.py"])
    separator = command.index("--")

    assert command.index("--jobs=1") < separator
    assert command.index("--timeout=30") < separator
