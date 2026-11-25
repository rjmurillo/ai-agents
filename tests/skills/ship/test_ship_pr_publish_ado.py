"""Behavior tests for ship_pr.py publish on Azure DevOps.

Pushes go to a real bare repository through ``pushInsteadOf``. ``gh``, ``az``,
and the helper scripts are fakes.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.skills.ship.ship_helpers import (
    ADO,
    TITLE,
    ado_created,
    assert_snapshot,
    publish,
    values,
)


class TestPublishAdo:
    @pytest.fixture
    def ado(self, make_repo, fakes, body_file):
        repo = make_repo(ADO)
        fakes.no_pr_ado()
        fakes.marker(0)
        fakes.rule(
            "validate_pr_description",
            [],
            {"stdout": json.dumps({"ErrorCount": 0, "WarningCount": 1, "Validations": {}})},
        )
        return repo, body_file(repo)

    def test_create_uses_the_fixed_argument_list(self, ado, fakes, scripts, capsys):
        _repo, body = ado
        fakes.rule("az", ["repos", "pr", "create"], ado_created())
        code, lines = publish(
            scripts,
            capsys,
            body,
        )
        assert code == 0, lines
        assert values(lines, "PR") == [
            "host=ado number=88 url=https://dev.azure.com/c/p/_git/r/pullrequest/88"
        ]
        create = [call for call in fakes.calls("az") if call[1:4] == ["repos", "pr", "create"]][0]
        assert create[1:] == [
            "repos",
            "pr",
            "create",
            "--output",
            "json",
            "--title",
            TITLE,
            "--description",
            create[9],
            "--target-branch",
            "main",
            "--draft",
            "false",
        ]
        assert sum(arg.startswith("@") for arg in create) == 1
        assert_snapshot(Path(create[9][1:]), body)

    def test_draft_flag_reaches_az(self, ado, fakes, scripts, capsys):
        _repo, body = ado
        fakes.marker(1)
        fakes.rule("az", ["repos", "pr", "create"], ado_created())
        code, _lines = publish(
            scripts,
            capsys,
            body,
            "--draft",
        )
        assert code == 0
        create = [call for call in fakes.calls("az") if call[1:4] == ["repos", "pr", "create"]][0]
        assert create[-2:] == ["--draft", "true"]

    def test_at_fallback_description_stops_exit_3_and_names_the_pr(
        self, ado, fakes, scripts, capsys
    ):
        _repo, body = ado
        fakes.rule("az", ["repos", "pr", "create"], ado_created(description=f"@{body}"))
        code, lines = publish(
            scripts,
            capsys,
            body,
        )
        assert code == 3
        assert values(lines, "PR")[0].startswith("host=ado number=88")
        assert lines[-1].startswith("STOP: description-upload-failed PR 88 is open")

    @pytest.mark.parametrize(
        ("response", "reason", "code"),
        [
            ({"rc": 1, "stderr": "TF401019\n"}, "pr-create-failed", 3),
            ({"rc": 1, "stderr": "Please run 'az login'\n"}, "auth-failed", 4),
            ({"stdout": "{}"}, "pr-create-failed", 3),
        ],
    )
    def test_create_failures(self, ado, fakes, scripts, capsys, response, reason, code):
        _repo, body = ado
        fakes.rule("az", ["repos", "pr", "create"], response)
        exit_code, lines = publish(
            scripts,
            capsys,
            body,
        )
        assert exit_code == code
        assert lines[-1].startswith(f"STOP: {reason}")

    def test_missing_web_url_reports_unknown(self, ado, fakes, scripts, capsys):
        _repo, body = ado
        fakes.rule(
            "az",
            ["repos", "pr", "create"],
            {"stdout": json.dumps({"pullRequestId": 4, "description": "ok"})},
        )
        code, lines = publish(
            scripts,
            capsys,
            body,
        )
        assert code == 0
        assert values(lines, "PR") == ["host=ado number=4 url=unknown"]
