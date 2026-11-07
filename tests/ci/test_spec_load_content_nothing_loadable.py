"""The loader reports `loadable` so the workflow can skip the model steps (issue #6506).

An `AB#` only body arms the spec gates, but Azure Boards content cannot be read
here. The loader exits 0 with `loadable=false` and writes no spec file, so the
advisory job stays green and still posts its report.

- pos: Azure-only references give loadable=false, exit 0, no file, no gh call
- neg: a GitHub issue body or a spec file gives loadable=true and a spec file
- edge: Azure plus a non-issue number is still not loadable; non-issue numbers
        alone keep their pinned config error
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.ci import spec_load_content
from scripts.ci.spec_load_content import EXIT_CONFIG, EXIT_OK

_NOT_AN_ISSUE = "Could not resolve to an Issue with the number of 99"


def _run(
    tmp_path: Path, *, issue_refs: str = "", azure_refs: str = "", gh: MagicMock | None = None
) -> tuple[int, dict[str, str], MagicMock]:
    out_file = tmp_path / "load-out.txt"
    env = {
        "SPEC_REFS": "",
        "ISSUE_REFS": issue_refs,
        "AZURE_REFS": azure_refs,
        "GITHUB_REPOSITORY": "owner/repo",
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_OUTPUT": str(out_file),
        "GITHUB_RUN_ID": "0",
    }
    gh = gh or MagicMock(returncode=0, stdout="Title\n\nBody")
    with patch.dict(os.environ, env):
        with patch("scripts.ci.spec_load_content.subprocess.run", return_value=gh) as run:
            code = spec_load_content.main()
    outputs = (
        dict(line.split("=", 1) for line in out_file.read_text().splitlines() if "=" in line)
        if out_file.exists()
        else {}
    )
    return code, outputs, run


@pytest.mark.parametrize("azure_refs", ["AB#123", "AB#5 AB#900"])
def test_azure_only_is_not_loadable_and_exits_zero(tmp_path, capsys, azure_refs):
    code, outputs, run = _run(tmp_path, azure_refs=azure_refs)

    assert code == EXIT_OK
    assert outputs == {"loadable": "false"}
    run.assert_not_called()
    assert not (tmp_path / "spec-content-0.md").exists()
    assert "no requirements were loadable" in capsys.readouterr().err


def test_github_issue_body_is_loadable(tmp_path):
    code, outputs, _ = _run(tmp_path, issue_refs="42")

    assert code == EXIT_OK
    assert outputs["loadable"] == "true"
    assert Path(outputs["spec_file"]).read_text(encoding="utf-8").startswith("## Issue #42")


def test_azure_beside_an_issue_body_stays_loadable(tmp_path):
    code, outputs, _ = _run(tmp_path, issue_refs="42", azure_refs="AB#7")

    assert code == EXIT_OK
    assert outputs["loadable"] == "true"
    assert "## Azure Boards AB#7" in Path(outputs["spec_file"]).read_text(encoding="utf-8")


def test_azure_plus_a_non_issue_number_is_not_loadable(tmp_path):
    gh = MagicMock(returncode=1, stdout="", stderr=_NOT_AN_ISSUE)

    code, outputs, _ = _run(tmp_path, issue_refs="99", azure_refs="AB#7", gh=gh)

    assert code == EXIT_OK
    assert outputs == {"loadable": "false"}


def test_non_issue_number_alone_keeps_the_config_error(tmp_path):
    gh = MagicMock(returncode=1, stdout="", stderr=_NOT_AN_ISSUE)

    code, outputs, _ = _run(tmp_path, issue_refs="99", gh=gh)

    assert code == EXIT_CONFIG
    assert outputs == {}
