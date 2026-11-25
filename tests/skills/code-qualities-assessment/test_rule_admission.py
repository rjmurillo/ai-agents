"""Rule admissions for issue #7525.

A refactor that replaces local logic with one shared first-party import drops
coupling by a point, and a file that only loses unique lines drops
non-redundancy. Neither change adds a dependency or a duplicate, so the gate
admits the drop while the raw score and regression row stay in the report.
A new third-party import or a new duplicate still fails.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts.ai_review_common import adapt_local_axis_verdict

from .test_assess import _commit, _init_repo, _mod, _regression_argv, _run_git, _write, main

_AXIS = "code-qualities-assessment"
# No absolute minimums, so files added beside a change never fail the run.
_NO_MINIMUMS: dict[str, dict[str, int]] = {
    key: {} for key in ("cohesion", "coupling", "encapsulation", "testability", "nonRedundancy")
}
_ADMISSION = {"firstPartyCouplingAdmission": {"importRoots": ["lib"]}}

_LOCAL_LOGIC = "def caller(text):\n    head, _, body = text.partition('---')\n    return body\n"
_SHARED_MODULE = "def split(text):\n    head, _, body = text.partition('---')\n    return body\n"


def _repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    base: dict[str, str],
    head: dict[str, str],
) -> None:
    """Commit *base* files on main, then *head* files on a feature branch."""
    _init_repo(tmp_path)
    for name, body in base.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        _commit(tmp_path, name, body, f"base {name}")
    _run_git(tmp_path, "checkout", "-b", "feature")
    for name, body in head.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        _commit(tmp_path, name, body, f"head {name}")
    monkeypatch.chdir(tmp_path)


def _run(tmp_path: Path, config: dict[str, Any]) -> int:
    path = _write(tmp_path, ".qualityrc.json", json.dumps({"thresholds": _NO_MINIMUMS, **config}))
    result = main([*_regression_argv(), "--config", str(path)])
    assert isinstance(result, int)
    return result


def _comparison(out: str, name: str) -> dict[str, Any]:
    return next(c for c in json.loads(out)["comparisons"] if c["file_path"] == name)


def _shared_extraction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, head_import: str) -> None:
    """Base keeps local fence logic; head imports it and deletes the copy."""
    head = f"{head_import}\n\n\ndef caller(text):\n    return split(text)\n"
    _repo(
        tmp_path,
        monkeypatch,
        {"pkg/__init__.py": "", "tools/caller.py": _LOCAL_LOGIC},
        {
            "pkg/shared.py": _SHARED_MODULE,
            "lib/fence/__init__.py": _SHARED_MODULE,
            "tools/caller.py": head,
        },
    )


@pytest.mark.parametrize(
    "head_import",
    [
        "from pkg.shared import split",
        "from fence import split",
    ],
    ids=["package-at-workspace-root", "configured-import-root"],
)
def test_shared_import_extraction_is_admitted_and_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    head_import: str,
) -> None:
    _shared_extraction(tmp_path, monkeypatch, head_import)

    rc = _run(tmp_path, _ADMISSION)

    out, err = capsys.readouterr()
    comparison = _comparison(out, "tools/caller.py")
    coupling = next(d for d in comparison["deltas"] if d["quality"] == "coupling")
    assert rc == 0
    assert (coupling["base"], coupling["head"], coupling["delta"]) == (10.0, 9.0, -1.0)
    assert comparison["regressions"] == ["coupling"]
    assert comparison["rule_admissions"] == {
        "coupling": {
            "issue": 7525,
            "rule": "no_new_third_party_import",
            "baseThirdParty": [],
            "headThirdParty": [],
        }
    }
    assert "coupling regressed 10.0 -> 9.0" in err
    assert "ADMITTED: issue #7525, rule no_new_third_party_import" in err
    assert adapt_local_axis_verdict(_AXIS, out, rc) == "WARN"


def test_sibling_module_import_is_first_party(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    head = "from fence_helper import split\n\n\ndef caller(text):\n    return split(text)\n"
    _repo(
        tmp_path,
        monkeypatch,
        {"build/caller.py": _LOCAL_LOGIC},
        {"build/fence_helper.py": _SHARED_MODULE, "build/caller.py": head},
    )

    assert _run(tmp_path, _ADMISSION) == 0
    assert _comparison(capsys.readouterr().out, "build/caller.py")["rule_admissions"]


def test_import_root_is_needed_for_a_module_only_found_there(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _shared_extraction(tmp_path, monkeypatch, "from fence import split")

    rc = _run(tmp_path, {"firstPartyCouplingAdmission": {"importRoots": []}})

    out = capsys.readouterr().out
    assert rc == 10
    assert _comparison(out, "tools/caller.py")["rule_admissions"] is None
    assert adapt_local_axis_verdict(_AXIS, out, rc) == "FAIL"


def test_admission_is_inert_without_the_config_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _shared_extraction(tmp_path, monkeypatch, "from pkg.shared import split")

    rc = _run(tmp_path, {})

    out, err = capsys.readouterr()
    assert rc == 10
    assert _comparison(out, "tools/caller.py")["rule_admissions"] is None
    assert "ADMITTED" not in err


@pytest.mark.parametrize(
    "head_import",
    [
        "import requests\nfrom requests import get as split",
        "from pkg.shared import split\nimport requests",
    ],
    ids=["third-party-only", "shared-plus-third-party"],
)
def test_new_third_party_import_still_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    head_import: str,
) -> None:
    _shared_extraction(tmp_path, monkeypatch, head_import)

    rc = _run(tmp_path, _ADMISSION)

    out, err = capsys.readouterr()
    assert rc == 10
    assert _comparison(out, "tools/caller.py")["rule_admissions"] is None
    assert "ADMITTED: issue" not in err
    assert "NOT ADMITTED: tools/caller.py: coupling: new third-party requests" in err
    assert adapt_local_axis_verdict(_AXIS, out, rc) == "FAIL"


def test_swapping_one_third_party_package_for_another_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = "import requests\n\n\ndef get(url):\n    return requests.get(url)\n"
    head = "import httpx\nimport json\nimport yaml\n\n\ndef get(url):\n    return httpx.get(url)\n"
    _repo(tmp_path, monkeypatch, {"tools/net.py": base}, {"tools/net.py": head})

    assert _run(tmp_path, _ADMISSION) == 10


@pytest.mark.parametrize(
    "record",
    [
        {"importRoots": "lib"},
        {"importRoots": [""]},
        {"importRoots": ["../outside"]},
        {"importRoots": ["lib"], "extra": True},
        ["lib"],
    ],
    ids=["string", "blank", "escapes-workspace", "unknown-key", "not-an-object"],
)
def test_invalid_admission_config_is_a_script_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    record: object,
) -> None:
    _shared_extraction(tmp_path, monkeypatch, "from pkg.shared import split")

    rc = _run(tmp_path, {"firstPartyCouplingAdmission": record})

    assert rc == 1
    assert "ERROR:" in capsys.readouterr().err


def _body(unique: int, repeats: int) -> str:
    lines = [f"    v{i} = {i}\n" for i in range(unique)]
    lines += ["    value = compute()\n"] * repeats
    return "def build(compute):\n" + "".join(lines) + "    return value\n"


def test_shorter_file_with_no_new_duplicate_is_admitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _repo(tmp_path, monkeypatch, {"tools/body.py": _body(12, 3)}, {"tools/body.py": _body(2, 3)})

    rc = _run(tmp_path, {})

    out, err = capsys.readouterr()
    comparison = _comparison(out, "tools/body.py")
    assert rc == 0
    assert comparison["regressions"] == ["non_redundancy"]
    assert comparison["rule_admissions"] == {
        "non_redundancy": {
            "issue": 7525,
            "rule": "no_new_duplicate_lines",
            "baseDuplicateLines": 2,
            "headDuplicateLines": 2,
        }
    }
    assert "ADMITTED: issue #7525, rule no_new_duplicate_lines" in err
    assert adapt_local_axis_verdict(_AXIS, out, rc) == "WARN"


def test_added_duplicate_lines_still_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _repo(tmp_path, monkeypatch, {"tools/body.py": _body(12, 3)}, {"tools/body.py": _body(12, 8)})

    rc = _run(tmp_path, {})

    out, err = capsys.readouterr()
    assert rc == 10
    assert _comparison(out, "tools/body.py")["rule_admissions"] is None
    assert "NOT ADMITTED: tools/body.py: non_redundancy: a line gained a copy" in err
    assert adapt_local_axis_verdict(_AXIS, out, rc) == "FAIL"


def test_repository_config_opts_into_the_coupling_admission() -> None:
    root = Path(__file__).resolve().parents[3]
    config = json.loads((root / ".qualityrc.json").read_text(encoding="utf-8"))

    assert config["firstPartyCouplingAdmission"] == {"importRoots": ["src/claude/lib"]}
    assert (root / "src/claude/lib/hook_utilities").is_dir()


@pytest.mark.parametrize(
    "decoy",
    ["lib/requests/__init__.py", "lib/requests/NOTES.md", "tools/requests.py"],
    ids=["package-under-import-root", "bare-directory", "sibling-module"],
)
def test_checkout_decoy_cannot_hide_an_installed_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], decoy: str
) -> None:
    head = "import requests\n\n\ndef caller(text):\n    return requests.utils.quote(text)\n"
    _repo(
        tmp_path,
        monkeypatch,
        {"tools/caller.py": _LOCAL_LOGIC},
        {decoy: "", "tools/caller.py": head},
    )

    rc = _run(tmp_path, _ADMISSION)

    assert rc == 10
    assert _comparison(capsys.readouterr().out, "tools/caller.py")["rule_admissions"] is None


def test_directory_without_init_is_not_a_first_party_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    head = "from localdir import split\n\n\ndef caller(text):\n    return split(text)\n"
    _repo(
        tmp_path,
        monkeypatch,
        {"tools/caller.py": _LOCAL_LOGIC},
        {"localdir/split.py": _SHARED_MODULE, "tools/caller.py": head},
    )

    assert _run(tmp_path, _ADMISSION) == 10


def test_untracked_module_is_not_first_party(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    head = "from scratch_mod import split\n\n\ndef caller(text):\n    return split(text)\n"
    _repo(tmp_path, monkeypatch, {"tools/caller.py": _LOCAL_LOGIC}, {"tools/caller.py": head})
    _write(tmp_path, "tools/scratch_mod.py", _SHARED_MODULE)

    assert _run(tmp_path, _ADMISSION) == 10


def test_coupling_admission_covers_python_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    base = "export function caller(text: string) {\n  return text.split('---')[1];\n}\n"
    head = (
        "import { split } from './fence';\n\n"
        "export function caller(text: string) {\n  return split(text);\n}\n"
    )
    shared = "export function split(text: string) {\n  return text.split('---')[1];\n}\n"
    _repo(
        tmp_path,
        monkeypatch,
        {"web/caller.ts": base},
        {"web/fence.ts": shared, "web/caller.ts": head},
    )

    rc = _run(tmp_path, _ADMISSION)

    out, err = capsys.readouterr()
    comparison = _comparison(out, "web/caller.ts")
    assert "NOT ADMITTED: web/caller.ts: coupling: language is not Python" in err
    assert rc == 10
    assert comparison["regressions"] == ["coupling"]
    assert comparison["rule_admissions"] is None


def test_one_admitted_file_does_not_clear_another_files_regression(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    shared = "from pkg.shared import split\n\n\ndef caller(text):\n    return split(text)\n"
    third_party = "import requests\n\n\ndef caller(text):\n    return requests.get(text)\n"
    _repo(
        tmp_path,
        monkeypatch,
        {"pkg/__init__.py": "", "tools/caller.py": _LOCAL_LOGIC, "tools/net.py": _LOCAL_LOGIC},
        {"pkg/shared.py": _SHARED_MODULE, "tools/caller.py": shared, "tools/net.py": third_party},
    )

    rc = _run(tmp_path, _ADMISSION)

    out, err = capsys.readouterr()
    assert rc == 10
    assert _comparison(out, "tools/caller.py")["rule_admissions"]
    assert _comparison(out, "tools/net.py")["rule_admissions"] is None
    assert "tools/net.py: coupling regressed" in err
    assert adapt_local_axis_verdict(_AXIS, out, rc) == "FAIL"


def _swap_body(dup: str, unique: int) -> str:
    lines = [f"    v{i} = {i}\n" for i in range(unique)] + [f"    {dup}\n"] * 3
    return "def build(compute):\n" + "".join(lines) + "    return v0\n"


def test_swapping_one_duplicate_for_another_still_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    base = _swap_body("value = compute()", 12)
    head = _swap_body("other = compute(1)", 2)
    _repo(tmp_path, monkeypatch, {"tools/body.py": base}, {"tools/body.py": head})

    rc = _run(tmp_path, {})

    assert rc == 10
    assert _comparison(capsys.readouterr().out, "tools/body.py")["rule_admissions"] is None


def test_git_tree_timeout_raises_a_runtime_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # main() maps RuntimeError from the admission step to exit 1. The fake
    # records every call and raises, so no real git process runs.
    calls: list[list[str]] = []

    def hung_ls_tree(argv: list[str], **kwargs: Any) -> Any:
        calls.append(argv)
        raise subprocess.TimeoutExpired(argv, float(kwargs["timeout"]))

    monkeypatch.setattr(subprocess, "run", hung_ls_tree)
    _mod._tracked_python_paths.cache_clear()

    with pytest.raises(RuntimeError, match="git ls-tree timed out after 60 seconds"):
        _mod._tracked_python_paths(tmp_path)

    assert calls == [["git", "ls-tree", "-r", "-z", "--name-only", "HEAD"]]


def test_staged_but_uncommitted_module_is_not_first_party(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    head = "from staged_mod import split\n\n\ndef caller(text):\n    return split(text)\n"
    _repo(tmp_path, monkeypatch, {"tools/caller.py": _LOCAL_LOGIC}, {"tools/caller.py": head})
    _write(tmp_path, "tools/staged_mod.py", _SHARED_MODULE)
    _run_git(tmp_path, "add", "tools/staged_mod.py")

    rc = _run(tmp_path, _ADMISSION)

    assert rc == 10
    assert _comparison(capsys.readouterr().out, "tools/caller.py")["rule_admissions"] is None


def test_rule_pass_skips_a_comparison_change_records_admitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Fixed change records (ADR-122 item 10) and rule admissions never share
    # a comparison, so the adapter sees one kind of record per file.
    _repo(tmp_path, monkeypatch, {"tools/body.py": _body(12, 3)}, {"tools/body.py": _body(2, 3)})
    record = {"issue": 7493, "quality": "non_redundancy"}
    comparison = _mod.FileComparison(
        "tools/body.py", False, [], ["non_redundancy"], [], "tools/body.py", "M", None
    )
    comparison.change_admissions = [record]
    control = _mod.FileComparison(
        "tools/body.py", False, [], ["non_redundancy"], [], "tools/body.py", "M", None
    )

    _mod._apply_rule_admissions([comparison, control], {}, "main")

    assert comparison.rule_admissions is None
    assert control.rule_admissions is not None


_TEST_BASE = "def test_one():\n    assert 1\n"
_TEST_HEAD = (
    "import pytest\n\n\n@pytest.mark.parametrize('n', [1, 2])\ndef test_one(n):\n    assert n\n"
)


@pytest.mark.parametrize(
    "name", ["tests/test_widget.py", "tests/unit/test_widget.py", "tests/conftest.py"]
)
def test_pytest_added_to_a_test_module_is_admitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    _repo(tmp_path, monkeypatch, {name: _TEST_BASE}, {name: _TEST_HEAD})

    rc = _run(tmp_path, _ADMISSION)

    out, err = capsys.readouterr()
    comparison = _comparison(out, name)
    assert rc == 0
    assert comparison["regressions"] == ["coupling"]
    assert comparison["rule_admissions"]["coupling"]["headThirdParty"] == []
    assert "ADMITTED: issue #7525, rule no_new_third_party_import" in err
    assert adapt_local_axis_verdict(_AXIS, out, rc) == "WARN"


@pytest.mark.parametrize(
    "name", ["tools/test_widget.py", "tests/widget_helpers.py", "tests_extra/test_widget.py"]
)
def test_pytest_outside_a_test_module_still_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    _repo(tmp_path, monkeypatch, {name: _TEST_BASE}, {name: _TEST_HEAD})

    rc = _run(tmp_path, _ADMISSION)

    out, err = capsys.readouterr()
    assert rc == 10
    assert _comparison(out, name)["rule_admissions"] is None
    assert f"NOT ADMITTED: {name}: coupling: new third-party pytest" in err
    assert adapt_local_axis_verdict(_AXIS, out, rc) == "FAIL"


def test_other_package_added_to_a_test_module_still_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    name = "tests/test_widget.py"
    head = "import pytest\nimport requests\n\n\ndef test_one():\n    assert requests\n"
    _repo(tmp_path, monkeypatch, {name: _TEST_BASE}, {name: head})

    rc = _run(tmp_path, _ADMISSION)

    _out, err = capsys.readouterr()
    assert rc == 10
    assert f"NOT ADMITTED: {name}: coupling: new third-party requests" in err
