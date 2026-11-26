"""Tests for check_unused_dependencies.py (deptry wrapper with granular policy).

Unit tests cover policy parsing, first-party discovery, and finding evaluation
without deptry. CLI tests run the locked deptry from the development environment.
"""

from __future__ import annotations

import subprocess

import pytest

from tests.validation._unused_dependencies_support import (
    cud,
    git_init,
    make_project,
    write_policy,
)


def _raw(code: str, module: str, file: str = "pyproject.toml", line: int = 0) -> dict:
    return {
        "error": {"code": code, "message": f"{code} message"},
        "module": module,
        "location": {"file": file, "line": line, "column": 0},
    }


def test_cli_malformed_policy_shape_exits_two_without_traceback(tmp_path, capsys):
    policy = write_policy(tmp_path, '[[manifest]]\npath = "."\ntool_only = "ruff"\n')
    assert cud.main(["--root", str(tmp_path), "--policy", str(policy)]) == 2
    assert "CONFIG ERROR" in capsys.readouterr().err


@pytest.mark.parametrize(
    "pyproject",
    [
        "project = 3\n",
        '[project]\nname = "x"\ndependencies = "pyyaml"\n',
        '[project]\nname = "x"\n[project.optional-dependencies]\ndev = "pytest"\n',
        '[project]\nname = "x"\n[dependency-groups]\ndev = 5\n',
        "[project\n",
    ],
)
def test_cli_malformed_manifest_shape_exits_two(tmp_path, capsys, pyproject):
    policy = write_policy(tmp_path, '[[manifest]]\npath = "."\n')
    (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    git_init(tmp_path)
    assert cud.main(["--root", str(tmp_path), "--policy", str(policy)]) == 2
    assert "CONFIG ERROR" in capsys.readouterr().err


# --- manifest and first-party discovery ------------------------------------


def test_declared_packages_covers_runtime_extras_and_groups(tmp_path):
    path = tmp_path / "pyproject.toml"
    path.write_text(
        '[project]\nname = "x"\ndependencies = ["PyYAML==6.0", "a_b>=1"]\n'
        '[project.optional-dependencies]\ndev = ["pytest>=9", "bandit[sarif]>=1"]\n'
        '[dependency-groups]\ndev = ["ruff", {include-group = "other"}]\n',
        encoding="utf-8",
    )
    assert cud.declared_packages(path) == {"pyyaml", "a-b", "pytest", "bandit", "ruff"}


def test_first_party_names_use_stems_and_dirs_and_skip_declared_modules():
    files = [
        "scripts/github_core/__init__.py",
        "skills/x/scripts/helper_mod.py",
        "skills/x/scripts/yaml.py",
        "docs/readme.md",
        "other/outside.py",
        "9bad-name/file.py",
    ]
    names = cud.first_party_names(files, ".", declared_modules={"yaml"})
    assert "github_core" in names and "helper_mod" in names and "scripts" in names
    assert "yaml" not in names
    assert "readme" not in names
    assert "9bad-name" not in names


def test_first_party_names_scope_to_manifest_directory():
    files = ["pkg/src/mod_a.py", "elsewhere/mod_b.py"]
    names = cud.first_party_names(files, "pkg", declared_modules=set())
    assert "mod_a" in names and "mod_b" not in names


def test_installed_third_party_modules_exclude_own_distribution(monkeypatch):
    monkeypatch.setattr(
        cud.importlib.metadata,
        "packages_distributions",
        lambda: {
            "yaml": ["PyYAML"],
            "frontmatter": ["python-frontmatter"],
            "scripts": ["fixture-dist"],
            "shared": ["fixture-dist", "other"],
        },
    )
    assert cud.installed_third_party_modules("Fixture_Dist") == {"yaml", "frontmatter", "shared"}
    assert cud.installed_third_party_modules(None) == {
        "yaml",
        "frontmatter",
        "scripts",
        "shared",
    }


def test_project_name_is_normalized_or_none(tmp_path):
    path = tmp_path / "pyproject.toml"
    path.write_text('[project]\nname = "Python_Frontmatter"\n', encoding="utf-8")
    assert cud.project_name(path) == "python-frontmatter"
    path.write_text("[tool.x]\n", encoding="utf-8")
    assert cud.project_name(path) is None


def test_deptry_args_carry_policy():
    manifest = cud.Manifest(
        path=".",
        extend_exclude=("packages/x",),
        module_map={"plugin-scanner": ("plugin_scanner",), "pyyaml": ("yaml", "yaml2")},
    )
    args = cud.deptry_args(manifest, ["alpha", "beta"])
    assert args.count("--known-first-party") == 2
    assert ".*packages/x" in args
    assert "plugin-scanner=plugin_scanner,pyyaml=yaml|yaml2" in args


# --- evaluate --------------------------------------------------------------


def _manifest(**kwargs) -> object:
    return cud.Manifest(path=".", **kwargs)


def _tool(package="ruff", pattern="ruff", file="lefthook.yml") -> object:
    return cud.ToolOnly(package, "reason", file, pattern)


def test_unused_dependency_is_reported(tmp_path):
    findings = cud.evaluate(_manifest(), [_raw("DEP002", "left-pad")], tmp_path, [])
    assert [f.code for f in findings] == ["DEP002"]


def test_tool_only_with_live_evidence_is_exempt(tmp_path):
    (tmp_path / "lefthook.yml").write_text("run: ruff check\n", encoding="utf-8")
    manifest = _manifest(tool_only=(_tool(),))
    assert cud.evaluate(manifest, [_raw("DEP002", "ruff")], tmp_path, ["lefthook.yml"]) == []


def test_tool_only_evidence_never_passes_when_no_files_are_tracked(tmp_path):
    (tmp_path / "lefthook.yml").write_text("run: ruff check\n", encoding="utf-8")
    manifest = _manifest(tool_only=(_tool(),))
    findings = cud.evaluate(manifest, [_raw("DEP002", "ruff")], tmp_path, [])
    assert [f.code for f in findings] == ["STALE-EXEMPTION"]


def test_tool_only_with_vanished_evidence_is_stale(tmp_path):
    (tmp_path / "lefthook.yml").write_text("run: nothing\n", encoding="utf-8")
    manifest = _manifest(tool_only=(_tool(),))
    findings = cud.evaluate(manifest, [_raw("DEP002", "ruff")], tmp_path, ["lefthook.yml"])
    assert [f.code for f in findings] == ["STALE-EXEMPTION"]


def test_tool_only_with_missing_evidence_file_is_stale(tmp_path):
    manifest = _manifest(tool_only=(_tool(),))
    findings = cud.evaluate(manifest, [_raw("DEP002", "ruff")], tmp_path, ["lefthook.yml"])
    assert [f.code for f in findings] == ["STALE-EXEMPTION"]


def test_tool_only_evidence_file_must_be_tracked(tmp_path):
    (tmp_path / "lefthook.yml").write_text("ruff\n", encoding="utf-8")
    manifest = _manifest(tool_only=(_tool(),))
    findings = cud.evaluate(manifest, [_raw("DEP002", "ruff")], tmp_path, ["other.txt"])
    assert [f.code for f in findings] == ["STALE-EXEMPTION"]


def test_tool_only_for_package_that_is_now_used_is_stale(tmp_path):
    (tmp_path / "lefthook.yml").write_text("ruff\n", encoding="utf-8")
    manifest = _manifest(tool_only=(_tool(),))
    findings = cud.evaluate(manifest, [], tmp_path, [])
    assert [f.code for f in findings] == ["STALE-EXEMPTION"]


def test_tool_only_name_matching_is_normalized(tmp_path):
    (tmp_path / "f.yml").write_text("pip-audit\n", encoding="utf-8")
    manifest = _manifest(tool_only=(_tool("pip_audit", "pip-audit", "f.yml"),))
    assert cud.evaluate(manifest, [_raw("DEP002", "pip-audit")], tmp_path, ["f.yml"]) == []


def test_other_codes_have_no_exemption_path(tmp_path):
    raw = [_raw("DEP001", "ghost", "a.py", 3), _raw("DEP004", "pytest", "b.py", 1)]
    findings = cud.evaluate(_manifest(), raw, tmp_path, [])
    assert [f.code for f in findings] == ["DEP001", "DEP004"]


def test_transitive_ok_only_under_prefix_and_with_declared_parent(tmp_path):
    entry = cud.TransitiveOk("grimp", "import-linter", "tests/", "r")
    manifest = _manifest(transitive_ok=(entry,))
    in_tests = _raw("DEP003", "grimp", str(tmp_path / "tests" / "t.py"), 1)
    in_scripts = _raw("DEP003", "grimp", str(tmp_path / "scripts" / "s.py"), 1)

    assert cud.evaluate(manifest, [in_tests], tmp_path, [], {"import-linter"}) == []
    outside = cud.evaluate(manifest, [in_scripts], tmp_path, [], {"import-linter"})
    assert [f.code for f in outside] == ["DEP003"]
    orphan = cud.evaluate(manifest, [in_tests], tmp_path, [], set())
    assert {f.code for f in orphan} == {"DEP003", "STALE-EXEMPTION"}


def test_transitive_ok_without_matching_finding_is_stale(tmp_path):
    entry = cud.TransitiveOk("grimp", "import-linter", "tests/", "r")
    findings = cud.evaluate(_manifest(transitive_ok=(entry,)), [], tmp_path, [], {"import-linter"})
    assert [f.code for f in findings] == ["STALE-EXEMPTION"]


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("declared", [set(), {"import-linter"}])
def test_transitive_mixed_locations_preserve_findings_and_parent_requirement(
    tmp_path, reverse, declared
):
    manifest = _manifest(transitive_ok=(cud.TransitiveOk("grimp", "import-linter", "tests/", "r"),))
    raw = [
        _raw("DEP003", "grimp", "tests/t.py", 1),
        _raw("DEP003", "grimp", "scripts/s.py", 2),
    ]
    if reverse:
        raw.reverse()

    findings = cud.evaluate(manifest, raw, tmp_path, [], declared)

    if declared:
        assert [(f.code, f.where) for f in findings] == [("DEP003", "scripts/s.py:2")]
    else:
        assert [(f.code, f.where) for f in findings] == [
            ("DEP003", f"{item['location']['file']}:{item['location']['line']}") for item in raw
        ] + [("STALE-EXEMPTION", str(cud.DEFAULT_POLICY))]
        assert findings[-1].message == (
            "transitive_ok relies on 'import-linter', which the manifest no longer declares"
        )


def test_stale_policy_entries_keep_transitive_fixture_tool_order_and_diagnostics(tmp_path):
    manifest = _manifest(
        transitive_ok=(cud.TransitiveOk("grimp", "import-linter", "tests/", "r"),),
        fixture_modules=(cud.FixtureModule("fixture_only", "tests/t.py", "reason"),),
        tool_only=(_tool("pip_audit"),),
    )

    findings = cud.evaluate(manifest, [], tmp_path, [], {"import-linter"})

    assert [f.render() for f in findings] == [
        f".: STALE-EXEMPTION grimp ({cud.DEFAULT_POLICY}): "
        "transitive_ok entry no longer matches any DEP003 finding; delete it",
        f".: STALE-EXEMPTION fixture_only ({cud.DEFAULT_POLICY}): "
        "fixture_module matches no DEP001 finding in tests/t.py; delete the entry",
        f".: STALE-EXEMPTION pip_audit ({cud.DEFAULT_POLICY}): "
        "listed under tool_only but deptry no longer reports it unused "
        "(removed from the manifest, or now imported); delete the exemption",
    ]


def _fixture(module="imported_only", used_in="tests/t.py"):
    return cud.FixtureModule(module, used_in, "reason")


def test_fixture_module_exempts_dep001_only_in_its_file(tmp_path):
    manifest = _manifest(fixture_modules=(_fixture(),))
    inside = _raw("DEP001", "imported_only", "tests/t.py", 4)
    assert cud.evaluate(manifest, [inside], tmp_path, []) == []


def test_fixture_module_does_not_hide_the_import_outside_its_file(tmp_path):
    manifest = _manifest(fixture_modules=(_fixture(),))
    raw = [
        _raw("DEP001", "imported_only", "tests/t.py", 4),
        _raw("DEP001", "imported_only", "scripts/other.py", 9),
        _raw("DEP001", "imported_only", "tests/t.py.bak", 1),
    ]
    findings = cud.evaluate(manifest, raw, tmp_path, [])
    assert [(f.code, f.where) for f in findings] == [
        ("DEP001", "scripts/other.py:9"),
        ("DEP001", "tests/t.py.bak:1"),
    ]


def test_fixture_module_directory_prefix_scopes_to_the_directory(tmp_path):
    manifest = _manifest(fixture_modules=(_fixture(used_in="tests/fx/"),))
    raw = [
        _raw("DEP001", "imported_only", "tests/fx/a.py"),
        _raw("DEP001", "imported_only", "tests/fxother/a.py"),
    ]
    findings = cud.evaluate(manifest, raw, tmp_path, [])
    assert [f.where for f in findings] == ["tests/fxother/a.py:0"]


def test_fixture_module_without_a_matching_finding_is_stale(tmp_path):
    manifest = _manifest(fixture_modules=(_fixture(),))
    elsewhere = _raw("DEP001", "imported_only", "scripts/other.py")
    findings = cud.evaluate(manifest, [elsewhere], tmp_path, [])
    assert [f.code for f in findings] == ["DEP001", "STALE-EXEMPTION"]
    assert [f.code for f in cud.evaluate(manifest, [], tmp_path, [])] == ["STALE-EXEMPTION"]


def test_fixture_module_ignores_other_finding_codes(tmp_path):
    manifest = _manifest(fixture_modules=(_fixture(),))
    raw = [_raw("DEP003", "imported_only", "tests/t.py")]
    findings = cud.evaluate(manifest, raw, tmp_path, [])
    assert [f.code for f in findings] == ["DEP003", "STALE-EXEMPTION"]


def test_relative_paths_resolve_against_the_deptry_directory(tmp_path):
    sub = tmp_path / "pkg"
    assert cud._relative("tests/t.py", tmp_path, sub) == "pkg/tests/t.py"
    assert cud._relative("tests/t.py", tmp_path) == "tests/t.py"


# --- tracked_files fails closed --------------------------------------------


def test_tracked_files_lists_untracked_unignored_files(tmp_path):
    git_init(tmp_path)
    (tmp_path / "a.py").write_text("", encoding="utf-8")
    assert cud.tracked_files(tmp_path) == ["a.py"]


def test_tracked_files_outside_git_raises(tmp_path):
    with pytest.raises(RuntimeError, match="git ls-files failed"):
        cud.tracked_files(tmp_path)


def test_tracked_files_without_git_binary_raises(tmp_path, monkeypatch):
    def missing(*_a, **_k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(cud.subprocess, "run", missing)
    with pytest.raises(RuntimeError, match="cannot list tracked files"):
        cud.tracked_files(tmp_path)


def test_tracked_files_timeout_raises(tmp_path, monkeypatch):
    def slow(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="git", timeout=600)

    monkeypatch.setattr(cud.subprocess, "run", slow)
    with pytest.raises(RuntimeError, match="timed out"):
        cud.tracked_files(tmp_path)


def test_cli_deptry_timeout_exits_three(tmp_path, monkeypatch, capsys):
    policy = make_project(tmp_path, '"pyyaml"', "import yaml\n")

    def fake_run(argv, **kwargs):
        if argv[0] == "git":
            return subprocess.CompletedProcess(argv, 0, b"pyproject.toml\0app.py\0", b"")
        raise subprocess.TimeoutExpired(cmd="deptry", timeout=600)

    monkeypatch.setattr(cud.subprocess, "run", fake_run)
    assert cud.main(["--root", str(tmp_path), "--policy", str(policy)]) == 3
    assert "EXTERNAL ERROR" in capsys.readouterr().err


def test_cli_outside_git_exits_three(tmp_path, capsys):
    policy = write_policy(tmp_path, '[[manifest]]\npath = "."\n')
    (tmp_path / "pyproject.toml").write_text('[project]\nname="x"\nversion="0"\n', encoding="utf-8")
    assert cud.main(["--root", str(tmp_path), "--policy", str(policy)]) == 3
    assert "EXTERNAL ERROR" in capsys.readouterr().err


def test_cli_without_git_binary_exits_three(tmp_path, monkeypatch, capsys):
    policy = make_project(tmp_path, '"pyyaml"', "import yaml\n")

    def missing(*_a, **_k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(cud.subprocess, "run", missing)
    assert cud.main(["--root", str(tmp_path), "--policy", str(policy)]) == 3
    assert "EXTERNAL ERROR" in capsys.readouterr().err
