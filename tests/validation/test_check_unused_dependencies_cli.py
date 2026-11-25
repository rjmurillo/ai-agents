"""CLI tests for check_unused_dependencies.py against a real deptry run.

Split from ``test_check_unused_dependencies.py`` so neither file crosses the
500-line taste limit. Shared loader and helpers live in
``_unused_dependencies_support.py``.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.validation._unused_dependencies_support import (
    REPO,
    cud,
    git_init,
    make_project,
    write_policy,
)

# --- CLI against a real deptry run -----------------------------------------


def test_cli_clean_project_exits_zero(tmp_path, capsys):
    policy = make_project(tmp_path, '"pyyaml"', "import yaml\nimport sibling\n")
    code = cud.main(["--root", str(tmp_path), "--policy", str(policy)])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "1 declared packages across 1 manifests, 0 findings" in out


def test_cli_unused_dependency_exits_one(tmp_path, capsys):
    policy = make_project(tmp_path, '"pyyaml", "jsonschema"', "import yaml\n")
    code = cud.main(["--root", str(tmp_path), "--policy", str(policy)])
    out = capsys.readouterr().out
    assert code == 1
    assert "DEP002 jsonschema" in out


def test_cli_undeclared_third_party_import_exits_one(tmp_path, capsys):
    policy = make_project(
        tmp_path, '"pyyaml"', "import yaml\nimport definitely_not_installed_pkg\n"
    )
    code = cud.main(["--root", str(tmp_path), "--policy", str(policy)])
    out = capsys.readouterr().out
    assert code == 1
    assert "DEP001 definitely_not_installed_pkg" in out


def test_cli_local_yaml_module_does_not_hide_declared_pyyaml(tmp_path, capsys):
    policy = make_project(tmp_path, '"pyyaml"', "import yaml\nimport sibling\n")
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "yaml.py").write_text("Y = 1\n", encoding="utf-8")
    code = cud.main(["--root", str(tmp_path), "--policy", str(policy)])
    out = capsys.readouterr().out
    assert code == 0, out
    assert "0 findings" in out


def test_cli_unrelated_yaml_module_does_not_hide_undeclared_yaml(tmp_path, capsys):
    policy = make_project(tmp_path, '"jsonschema"', "import jsonschema\nimport yaml\n")
    argv = ["--root", str(tmp_path), "--policy", str(policy)]

    assert cud.main(argv) == 1
    before = capsys.readouterr().out
    assert "DEP003 yaml" in before

    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "yaml.py").write_text("Y = 1\n", encoding="utf-8")
    assert cud.main(argv) == 1
    after = capsys.readouterr().out
    assert "DEP003 yaml" in after


def test_cli_local_module_unrelated_to_installed_distributions_stays_first_party(tmp_path, capsys):
    policy = make_project(tmp_path, '"pyyaml"', "import yaml\nimport helper_mod\n")
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "helper_mod.py").write_text("Y = 1\n", encoding="utf-8")
    assert cud.main(["--root", str(tmp_path), "--policy", str(policy)]) == 0
    assert "0 findings" in capsys.readouterr().out


def test_cli_missing_policy_exits_two(tmp_path, capsys):
    code = cud.main(["--root", str(tmp_path), "--policy", str(tmp_path / "absent.toml")])
    assert code == 2
    assert "CONFIG ERROR" in capsys.readouterr().err


def test_cli_missing_manifest_exits_two(tmp_path, capsys):
    policy = write_policy(tmp_path, '[[manifest]]\npath = "nowhere"\n')
    git_init(tmp_path)
    code = cud.main(["--root", str(tmp_path), "--policy", str(policy)])
    assert code == 2
    assert "manifest not found" in capsys.readouterr().err


def test_run_deptry_without_report_is_external_error(tmp_path, monkeypatch, capsys):
    policy = write_policy(tmp_path, '[[manifest]]\npath = "."\n')
    (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\nversion="0"\n', encoding="utf-8")
    git_init(tmp_path)

    def boom(*_a, **_k):
        raise RuntimeError("deptry produced no report")

    monkeypatch.setattr(cud, "run_deptry", boom)
    code = cud.main(["--root", str(tmp_path), "--policy", str(policy)])
    assert code == 3
    assert "EXTERNAL ERROR" in capsys.readouterr().err


def test_repository_policy_is_clean(capsys):
    code = cud.main(["--root", str(REPO)])
    assert code == 0, capsys.readouterr().out


@pytest.mark.parametrize(
    ("returncode", "report", "expected"),
    [(2, [], 3), (1, [], 3), (0, {}, 3), (0, [{}], 3), (0, [], 0)],
)
def test_cli_rejects_failed_or_malformed_deptry_reports(
    tmp_path, monkeypatch, returncode, report, expected
):
    policy = make_project(tmp_path, '"pyyaml"', "import yaml\n")

    def fake_run(argv, **kwargs):
        if argv[0] == "git":
            return subprocess.CompletedProcess(argv, 0, b"pyproject.toml\0app.py\0", b"")
        assert argv[1] == "-c"
        extra_args = json.loads(kwargs["input"])
        assert extra_args[extra_args.index("--known-first-party") + 1] == "app"
        output = Path(argv[argv.index("--json-output") + 1])
        output.write_text(json.dumps(report), encoding="utf-8")
        return subprocess.CompletedProcess(argv, returncode, "", "scanner error")

    monkeypatch.setattr(cud.subprocess, "run", fake_run)
    assert cud.main(["--root", str(tmp_path), "--policy", str(policy)]) == expected
