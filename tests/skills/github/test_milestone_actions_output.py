"""AC-DUP-1: Shared milestone output preserves existing file behavior."""

from pathlib import Path

import pytest
from github_core.api import RepoInfo
from test_helpers import import_skill_script

from scripts.github_core.actions_output import write_github_output, write_step_summary


def test_package_parser_helper_reuses_the_canonical_output_implementation() -> None:
    from scripts import github_core
    from scripts.github_core import output

    assert github_core.add_output_format_arg is output.add_output_format_arg


def test_shared_exit_documentation_retains_standard_failure_meanings() -> None:
    from scripts.github_core import output

    assert output.STANDARD_FAILURE_EXIT_CODES == (
        "    2 - Config error (plugin lib path missing)\n"
        "    3 - External error (gh/API failure)\n"
        "    4 - Auth error (not authenticated)\n"
    )


def test_actions_files_append_utf8(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output = tmp_path / "output"
    summary = tmp_path / "summary"
    output.write_text("existing=1\n", encoding="utf-8")
    summary.write_text("Existing\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    write_github_output({"title": "café", "found": "true"})
    write_step_summary("## Milestone\n")

    assert output.read_text(encoding="utf-8") == "existing=1\ntitle=café\nfound=true\n"
    assert summary.read_text(encoding="utf-8") == "Existing\n## Milestone\n"


@pytest.mark.parametrize("destination", ["unset", "empty", "directory"])
def test_optional_actions_files_do_not_raise(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, destination: str
) -> None:
    for name in ("GITHUB_OUTPUT", "GITHUB_STEP_SUMMARY"):
        monkeypatch.delenv(name, raising=False)
        if destination != "unset":
            monkeypatch.setenv(name, "" if destination == "empty" else str(tmp_path))

    write_github_output({"found": "true"})
    write_step_summary("Summary\n")

    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("consumer", ["get_latest_semantic_milestone", "set_item_milestone"])
def test_milestone_entrypoints_preserve_actions_output(
    consumer: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    mod = import_skill_script(consumer, "milestone")
    output = tmp_path / "output"
    summary = tmp_path / "summary"
    assert not output.exists() and not summary.exists()
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setattr(mod, "assert_gh_authenticated", lambda: None)
    monkeypatch.setattr(mod, "resolve_repo_params", lambda *args: RepoInfo(owner="o", repo="r"))
    if consumer == "get_latest_semantic_milestone":
        monkeypatch.setattr(
            mod, "gh_api_paginated", lambda *args: [{"title": "v1.2.3", "number": 7}]
        )
        args: list[str] = []
        expected = "milestone_title=v1.2.3\nmilestone_number=7\nfound=true\n"
    else:
        monkeypatch.setattr(mod, "_get_item_milestone", lambda *args: "v1.2.3")
        args = ["--item-type", "issue", "--item-number", "7"]
        expected = "milestone=v1.2.3\n"

    assert mod.main(args) == 0
    assert expected in output.read_text(encoding="utf-8")
    assert "## Milestone " in summary.read_text(encoding="utf-8")
    assert capsys.readouterr().err == ""
