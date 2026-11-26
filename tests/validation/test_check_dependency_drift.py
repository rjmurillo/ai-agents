"""Tests for check_dependency_drift.py (cross-manifest constraint consistency).

Positive: consistent manifests pass. Negative: each drift kind fails with the
documented exit code. Edge: stale allow entries, missing manifests, extras and
groups, npm overrides, unsatisfiable ranges, and the real repository policy.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from packaging.specifiers import SpecifierSet

_REPO = Path(__file__).resolve().parents[2]
_MODULE_PATH = _REPO / "scripts" / "validation" / "check_dependency_drift.py"
_spec = importlib.util.spec_from_file_location("check_dependency_drift", _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
cdd = importlib.util.module_from_spec(_spec)
sys.modules["check_dependency_drift"] = cdd
_spec.loader.exec_module(cdd)


def _pyproject(
    path: Path,
    deps: list[str],
    *,
    python: str = ">=3.14",
    extras: dict[str, list[str]] | None = None,
    overrides: list[str] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["[project]", 'name = "x"', f'requires-python = "{python}"']
    lines.append("dependencies = [" + ", ".join(f'"{d}"' for d in deps) + "]")
    for name, items in (extras or {}).items():
        lines.append(
            f"[project.optional-dependencies]\n{name} = ["
            + ", ".join(f'"{d}"' for d in items)
            + "]"
        )
    if overrides:
        lines.append(
            "[tool.uv]\noverride-dependencies = [" + ", ".join(f'"{d}"' for d in overrides) + "]"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _policy(
    path: Path,
    py: list[str],
    npm: list[str] | None = None,
    allow: list[tuple[str, str, str]] | None = None,
) -> Path:
    text = "[drift]\n"
    text += "python_manifests = [" + ", ".join(f'"{m}"' for m in py) + "]\n"
    text += "npm_manifests = [" + ", ".join(f'"{m}"' for m in (npm or [])) + "]\n"
    for package, manifest, reason in allow or []:
        text += "[[drift.allow]]\n"
        text += f'package = "{package}"\nmanifest = "{manifest}"\nreason = "{reason}"\n'
    policy = path / "policy.toml"
    policy.write_text(text, encoding="utf-8")
    return policy


def _run(tmp: Path, policy: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = cdd.main(["--root", str(tmp), "--policy", str(policy)])
    out = capsys.readouterr()
    return code, out.out + out.err


def test_consistent_manifests_pass_and_report_counts(tmp_path, capsys):
    _pyproject(tmp_path / "a/pyproject.toml", ["pyyaml>=6.0.3", "ruff>=0.15"])
    _pyproject(tmp_path / "b/pyproject.toml", ["PyYAML>=6.0.3"])
    policy = _policy(tmp_path, ["a/pyproject.toml", "b/pyproject.toml"])
    code, out = _run(tmp_path, policy, capsys)
    assert code == 0
    assert "2 python manifests" in out and "0 findings" in out


@pytest.mark.parametrize(
    ("constraint", "witness"),
    [
        (">1.0.0,<1.0.1", "1.0.0.1"),
        (">1.0.0,<1.0.0.0.1", "1.0.0.0.0.1"),
        (">1!1.0.0,<1!1.0.1", "1!1.0.0.1"),
        (">1.0rc1,<1.0rc3", "1.0rc2"),
        (">1.0.post1,<1.0.post3", "1.0.post2"),
    ],
)
def test_valid_narrow_ranges_do_not_raise_false_conflicts(tmp_path, capsys, constraint, witness):
    assert witness in SpecifierSet(constraint)
    _pyproject(tmp_path / "a/pyproject.toml", [f"sample{constraint}"])
    _pyproject(tmp_path / "b/pyproject.toml", [f"sample{constraint}"])
    code, out = _run(tmp_path, _policy(tmp_path, ["a/pyproject.toml", "b/pyproject.toml"]), capsys)
    assert code == 0, out


def test_conflicting_pins_fail_as_conflict(tmp_path, capsys):
    _pyproject(tmp_path / "a/pyproject.toml", ["pyyaml==6.0.3"])
    _pyproject(tmp_path / "b/pyproject.toml", ["pyyaml<6"])
    code, out = _run(tmp_path, _policy(tmp_path, ["a/pyproject.toml", "b/pyproject.toml"]), capsys)
    assert code == 1
    assert "CONFLICT pyyaml" in out


def test_conflict_cannot_be_allowed(tmp_path, capsys):
    _pyproject(tmp_path / "a/pyproject.toml", ["pyyaml==6.0.3"])
    _pyproject(tmp_path / "b/pyproject.toml", ["pyyaml<6"])
    policy = _policy(
        tmp_path,
        ["a/pyproject.toml", "b/pyproject.toml"],
        allow=[("pyyaml", "b/pyproject.toml", "nope")],
    )
    code, out = _run(tmp_path, policy, capsys)
    assert code == 1
    assert "CONFLICT pyyaml" in out


def test_floor_drift_fails_without_allow_entry(tmp_path, capsys):
    _pyproject(tmp_path / "a/pyproject.toml", ["ruff>=0.15.16"])
    _pyproject(tmp_path / "b/pyproject.toml", ["ruff>=0.1.0"])
    code, out = _run(tmp_path, _policy(tmp_path, ["a/pyproject.toml", "b/pyproject.toml"]), capsys)
    assert code == 1
    assert "FLOOR-DRIFT ruff: b/pyproject.toml floor 0.1.0 trails 0.15.16" in out


def test_floor_drift_allowed_for_named_manifest_only(tmp_path, capsys):
    _pyproject(tmp_path / "a/pyproject.toml", ["ruff>=0.15.16"])
    _pyproject(tmp_path / "b/pyproject.toml", ["ruff>=0.1.0"])
    _pyproject(tmp_path / "c/pyproject.toml", ["ruff>=0.2.0"])
    names = ["a/pyproject.toml", "b/pyproject.toml", "c/pyproject.toml"]
    policy = _policy(tmp_path, names, allow=[("ruff", "b/pyproject.toml", "wide floor")])
    code, out = _run(tmp_path, policy, capsys)
    assert code == 1
    assert "c/pyproject.toml floor 0.2.0" in out
    assert "b/pyproject.toml floor" not in out


def test_stale_allow_entry_fails(tmp_path, capsys):
    _pyproject(tmp_path / "a/pyproject.toml", ["ruff>=0.15.16"])
    _pyproject(tmp_path / "b/pyproject.toml", ["ruff>=0.15.16"])
    policy = _policy(
        tmp_path,
        ["a/pyproject.toml", "b/pyproject.toml"],
        allow=[("ruff", "b/pyproject.toml", "old reason")],
    )
    code, out = _run(tmp_path, policy, capsys)
    assert code == 1
    assert "STALE-ALLOW ruff" in out


def test_allow_for_unlisted_manifest_is_stale(tmp_path, capsys):
    _pyproject(tmp_path / "a/pyproject.toml", ["ruff>=0.15.16"])
    policy = _policy(tmp_path, ["a/pyproject.toml"], allow=[("ruff", "gone/pyproject.toml", "x")])
    code, out = _run(tmp_path, policy, capsys)
    assert code == 1
    assert "not in python_manifests" in out


def test_requires_python_drift_is_detected(tmp_path, capsys):
    _pyproject(tmp_path / "a/pyproject.toml", [], python=">=3.14")
    _pyproject(tmp_path / "b/pyproject.toml", [], python=">=3.11")
    code, out = _run(tmp_path, _policy(tmp_path, ["a/pyproject.toml", "b/pyproject.toml"]), capsys)
    assert code == 1
    assert "FLOOR-DRIFT python" in out


def test_same_package_in_extra_with_different_specifier_is_intra_manifest_drift(tmp_path, capsys):
    _pyproject(tmp_path / "a/pyproject.toml", ["ruff>=0.15"], extras={"dev": ["ruff>=0.14"]})
    code, out = _run(tmp_path, _policy(tmp_path, ["a/pyproject.toml"]), capsys)
    assert code == 1
    assert "INTRA-MANIFEST ruff" in out


def test_override_pins_must_match_across_manifests(tmp_path, capsys):
    _pyproject(tmp_path / "a/pyproject.toml", [], overrides=["certifi==2026.10.19"])
    _pyproject(tmp_path / "b/pyproject.toml", [], overrides=["certifi==2026.7.22"])
    code, out = _run(tmp_path, _policy(tmp_path, ["a/pyproject.toml", "b/pyproject.toml"]), capsys)
    assert code == 1
    assert "certifi" in out


def test_override_may_differ_from_declared_range_in_same_manifest(tmp_path, capsys):
    _pyproject(tmp_path / "a/pyproject.toml", ["click>=8"], overrides=["click==8.3.3"])
    code, _ = _run(tmp_path, _policy(tmp_path, ["a/pyproject.toml"]), capsys)
    assert code == 0


def test_name_normalization_matches_across_manifests(tmp_path, capsys):
    _pyproject(tmp_path / "a/pyproject.toml", ["pytest_cov>=7"])
    _pyproject(tmp_path / "b/pyproject.toml", ["Pytest.Cov>=4"])
    code, out = _run(tmp_path, _policy(tmp_path, ["a/pyproject.toml", "b/pyproject.toml"]), capsys)
    assert code == 1
    assert "FLOOR-DRIFT pytest-cov" in out


def test_npm_mismatch_fails_and_match_passes(tmp_path, capsys):
    for name, spec in (("one", "1.0.0"), ("two", "1.0.0")):
        (tmp_path / name).mkdir()
        (tmp_path / name / "package.json").write_text(
            json.dumps({"dependencies": {"left-pad": spec}}), encoding="utf-8"
        )
    _pyproject(tmp_path / "a/pyproject.toml", [])
    policy = _policy(tmp_path, ["a/pyproject.toml"], ["one/package.json", "two/package.json"])
    code, _ = _run(tmp_path, policy, capsys)
    assert code == 0

    (tmp_path / "two" / "package.json").write_text(
        json.dumps({"devDependencies": {"left-pad": "^1.0.0"}}), encoding="utf-8"
    )
    code, out = _run(tmp_path, policy, capsys)
    assert code == 1
    assert "NPM-DRIFT left-pad" in out


def test_missing_manifest_is_config_error(tmp_path, capsys):
    policy = _policy(tmp_path, ["absent/pyproject.toml"])
    code, out = _run(tmp_path, policy, capsys)
    assert code == 2
    assert "manifest not found" in out


def test_missing_policy_and_empty_policy_are_config_errors(tmp_path, capsys):
    code, _ = _run(tmp_path, tmp_path / "nope.toml", capsys)
    assert code == 2
    empty = tmp_path / "empty.toml"
    empty.write_text("[drift]\n", encoding="utf-8")
    code, out = _run(tmp_path, empty, capsys)
    assert code == 2
    assert "no manifests" in out


def test_invalid_requirement_is_config_error(tmp_path, capsys):
    _pyproject(tmp_path / "a/pyproject.toml", ["not a valid ((requirement"])
    code, _ = _run(tmp_path, _policy(tmp_path, ["a/pyproject.toml"]), capsys)
    assert code == 2


def test_invalid_requires_python_is_config_error_not_traceback(tmp_path, capsys):
    _pyproject(tmp_path / "a/pyproject.toml", [], python="not a specifier")
    code, out = _run(tmp_path, _policy(tmp_path, ["a/pyproject.toml"]), capsys)
    assert code == 2
    assert "CONFIG ERROR" in out
    assert "requires-python" in out


def test_non_string_requires_python_is_config_error(tmp_path, capsys):
    path = tmp_path / "a/pyproject.toml"
    path.parent.mkdir()
    path.write_text("[project]\nrequires-python = 3\n", encoding="utf-8")
    code, out = _run(tmp_path, _policy(tmp_path, ["a/pyproject.toml"]), capsys)
    assert code == 2
    assert "requires-python" in out


@pytest.mark.parametrize(
    "body",
    [
        "project = 3\n",
        '[project]\ndependencies = "pyyaml"\n',
        '[project]\n[project.optional-dependencies]\ndev = "pytest"\n',
        '[project.optional-dependencies]\ndev = ["pytest"]\n[project]\noptional-dependencies = 1\n',
        "dependency-groups = 4\n",
        "[dependency-groups]\ndev = 4\n",
        "tool = 1\n",
        "[tool]\nuv = 1\n",
        "[tool.uv]\noverride-dependencies = 1\n",
        "[project\n",
    ],
)
def test_malformed_python_manifest_shapes_are_config_errors(tmp_path, capsys, body):
    path = tmp_path / "a/pyproject.toml"
    path.parent.mkdir()
    path.write_text(body, encoding="utf-8")
    code, out = _run(tmp_path, _policy(tmp_path, ["a/pyproject.toml"]), capsys)
    assert code == 2, out
    assert "CONFIG ERROR" in out


@pytest.mark.parametrize(
    "body",
    [
        "[]",
        '{"dependencies": ["a"]}',
        '{"devDependencies": 3}',
        '{"overrides": ["a"]}',
        "{not json",
    ],
)
def test_malformed_npm_manifest_shapes_are_config_errors(tmp_path, capsys, body):
    (tmp_path / "package.json").write_text(body, encoding="utf-8")
    code, out = _run(tmp_path, _policy(tmp_path, [], ["package.json"]), capsys)
    assert code == 2, out
    assert "CONFIG ERROR" in out


def test_null_npm_tables_are_treated_as_empty(tmp_path, capsys):
    (tmp_path / "package.json").write_text('{"dependencies": null}', encoding="utf-8")
    code, _ = _run(tmp_path, _policy(tmp_path, [], ["package.json"]), capsys)
    assert code == 0


@pytest.mark.parametrize(
    "policy_body",
    [
        "drift = 3\n",
        "[drift]\npython_manifests = 'a'\n",
        "[drift]\npython_manifests = [1]\n",
        "[drift]\nnpm_manifests = {a = 1}\n",
        "[drift]\npython_manifests = ['a']\nallow = 'x'\n",
        "[drift]\npython_manifests = ['a']\nallow = ['x']\n",
    ],
)
def test_malformed_policy_shapes_are_config_errors(tmp_path, capsys, policy_body):
    policy = tmp_path / "policy.toml"
    policy.write_text(policy_body, encoding="utf-8")
    code, out = _run(tmp_path, policy, capsys)
    assert code == 2, out
    assert "CONFIG ERROR" in out


def test_allow_entry_requires_reason(tmp_path, capsys):
    _pyproject(tmp_path / "a/pyproject.toml", [])
    policy = tmp_path / "policy.toml"
    policy.write_text(
        '[drift]\npython_manifests = ["a/pyproject.toml"]\n'
        '[[drift.allow]]\npackage = "x"\nmanifest = "a/pyproject.toml"\nreason = " "\n',
        encoding="utf-8",
    )
    code, out = _run(tmp_path, policy, capsys)
    assert code == 2
    assert "reason" in out


@pytest.mark.parametrize(
    ("specs", "expected"),
    [
        (["==6.0.3", ">=6.0"], True),
        (["==6.0.3", "<6"], False),
        ([">=3.14", ">=3.11"], True),
        ([">=2", "<2"], False),
        (["~=1.4", ">=1.4.5"], True),
        ([], True),
    ],
)
def test_satisfiable(specs, expected):
    assert cdd.satisfiable(specs) is expected


def test_repository_policy_is_clean():
    code = cdd.main(["--root", str(_REPO)])
    assert code == 0
