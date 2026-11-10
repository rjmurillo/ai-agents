"""Round-three regressions for conditional constraints and malformed members."""

from __future__ import annotations

import json

import pytest
from packaging.markers import Marker
from packaging.specifiers import SpecifierSet

from scripts.validation import python_dependency_constraints as constraints
from tests.validation.test_check_dependency_drift import _policy, _pyproject, _run, cdd


@pytest.mark.parametrize("reverse", [False, True])
def test_identical_platform_alternatives_pass(tmp_path, capsys, reverse):
    deps = [
        "samplelib==1; sys_platform == 'win32'",
        "samplelib==2; sys_platform != 'win32'",
    ]
    _pyproject(tmp_path / "a.toml", deps)
    _pyproject(tmp_path / "b.toml", list(reversed(deps)) if reverse else deps)
    for platform, expected in [("win32", "==1"), ("linux", "==2")]:
        selected = [
            d.split(";")[0]
            for d in deps
            if Marker(d.split(";")[1]).evaluate({"sys_platform": platform})
        ]
        assert selected == [f"samplelib{expected}"]
    code, out = _run(tmp_path, _policy(tmp_path, ["a.toml", "b.toml"]), capsys)
    assert code == 0, out


@pytest.mark.parametrize(
    ("left", "right", "overlap", "environment"),
    [
        ("sys_platform == 'win32'", "sys_platform == 'linux'", False, {"sys_platform": "linux"}),
        ("sys_platform == 'win32'", "sys_platform != 'linux'", True, {"sys_platform": "win32"}),
        (
            "sys_platform == 'win32' or sys_platform == 'linux'",
            "sys_platform == 'linux'",
            True,
            {"sys_platform": "linux"},
        ),
        ("python_version < '3.12'", "python_version >= '3.12'", False, {"python_version": "3.12"}),
        ("python_version > '3.12'", "python_version < '3.14'", True, {"python_version": "3.13"}),
        ("'win' in sys_platform", "sys_platform == 'win32'", True, {"sys_platform": "win32"}),
        (
            "sys_platform in 'win32,linux'",
            "sys_platform == 'darwin'",
            False,
            {"sys_platform": "darwin"},
        ),
        (
            "sys_platform == 'win32' and platform_machine == 'ARM64'",
            "platform_machine != 'ARM64'",
            False,
            {"sys_platform": "win32", "platform_machine": "x86"},
        ),
    ],
)
@pytest.mark.parametrize("location", ["across", "group"])
def test_only_overlapping_environments_are_compared(
    tmp_path, capsys, left, right, overlap, environment, location
):
    assert (Marker(left).evaluate(environment) and Marker(right).evaluate(environment)) == overlap
    _pyproject(tmp_path / "a.toml", [f"samplelib==1; {left}"])
    manifests = ["a.toml"]
    if location == "across":
        _pyproject(tmp_path / "b.toml", [f"samplelib==2; {right}"])
        manifests.append("b.toml")
    else:
        with (tmp_path / "a.toml").open("a", encoding="utf-8") as stream:
            stream.write(
                "\n[dependency-groups]\ndev = [" + json.dumps(f"samplelib==2; {right}") + "]\n"
            )
    code, out = _run(tmp_path, _policy(tmp_path, manifests), capsys)
    assert code == int(overlap), out
    if overlap:
        assert ("CONFLICT" if location == "across" else "INTRA-MANIFEST") in out


@pytest.mark.parametrize(
    ("constraint", "witness"),
    [
        (">1.0rc1,<1.0rc2", "1.0rc2.dev1"),
        (">1.0a1,<1.0a2", "1.0a2.dev0"),
        (">1.0b8,<1.0b9", "1.0b9.dev0"),
        (">1.0.dev1,<1.0.dev3", "1.0.dev2"),
        (">1.0.post1.dev1,<1.0.post1.dev3", "1.0.post1.dev2"),
        (">2!1.0rc1,<2!1.0rc2", "2!1.0rc2.dev1"),
        (">1.0.0,<1.0.0.0.1", "1.0.0.0.0.1"),
        ("==1.0+local", "1.0+local"),
        ("===custom", "custom"),
    ],
)
def test_boundary_intervals_have_packaging_witnesses(tmp_path, capsys, constraint, witness):
    assert SpecifierSet(constraint).contains(witness)
    for name in ["a.toml", "b.toml"]:
        _pyproject(tmp_path / name, [f"samplelib{constraint}"])
    code, out = _run(tmp_path, _policy(tmp_path, ["a.toml", "b.toml"]), capsys)
    assert code == 0, out


@pytest.mark.parametrize("constraint", [">=2,<2", ">1rc2,<1rc1", "==1,!=1", ">1.dev1,<1.dev2"])
def test_contradictory_intervals_still_fail(tmp_path, capsys, constraint):
    for name in ["a.toml", "b.toml"]:
        _pyproject(tmp_path / name, [f"samplelib{constraint}"])
    code, out = _run(tmp_path, _policy(tmp_path, ["a.toml", "b.toml"]), capsys)
    assert code == 1, out
    assert "CONFLICT samplelib" in out


@pytest.mark.parametrize("member", ["123", "true", "{}", "{include-group = 'dev'}", "''", "' '"])
@pytest.mark.parametrize("section", ["project", "optional", "group", "override", "constraint"])
def test_invalid_dependency_members_are_configuration_errors(tmp_path, capsys, member, section):
    bodies = {
        "project": f"[project]\ndependencies = [{member}]\n",
        "optional": f"[project.optional-dependencies]\ndev = [{member}]\n",
        "group": f"[dependency-groups]\ndev = [{member}]\n",
        "override": f"[tool.uv]\noverride-dependencies = [{member}]\n",
        "constraint": f"[tool.uv]\nconstraint-dependencies = [{member}]\n",
    }
    (tmp_path / "a.toml").write_text(bodies[section], encoding="utf-8")
    code, out = _run(tmp_path, _policy(tmp_path, ["a.toml"]), capsys)
    assert code == 2, out
    assert "CONFIG ERROR" in out


def test_valid_include_group_tables_preserve_group_constraints(tmp_path, capsys):
    (tmp_path / "a.toml").write_text(
        "[dependency-groups]\nbase = ['samplelib>=1']\ndev = [{include-group = 'base'}]\n",
        encoding="utf-8",
    )
    _pyproject(tmp_path / "b.toml", ["samplelib>=1"])
    code, out = _run(tmp_path, _policy(tmp_path, ["a.toml", "b.toml"]), capsys)
    assert code == 0, out


@pytest.mark.parametrize(
    "member", ["{include-group = 1}", "{include-group = ''}", "{include-group = 'base', other = 1}"]
)
def test_invalid_include_group_tables_fail(tmp_path, capsys, member):
    (tmp_path / "a.toml").write_text(
        f"[dependency-groups]\nbase = []\ndev = [{member}]\n", encoding="utf-8"
    )
    code, out = _run(tmp_path, _policy(tmp_path, ["a.toml"]), capsys)
    assert code == 2, out


@pytest.mark.parametrize(
    ("markers", "expected"),
    [
        ([], {()}),
        (["", ""], {(0, 1)}),
        (["sys_platform == 'win32'", "sys_platform != 'win32'"], {(0,), (1,)}),
        (["python_version in '3.12'", "python_version >= '3.12'"], {(), (0,), (1,), (0, 1)}),
        (["python_version not in ''"], {(0,)}),
        (["python_version in ''"], {()}),
        (["'win' in sys_platform", "'linux' not in sys_platform"], {(), (0,), (1,), (0, 1)}),
        (["extra == 'test_suite'", "extra == 'test-suite'"], {(), (0, 1)}),
        (
            [
                "(sys_platform == 'win32' or sys_platform == 'linux') and os_name == 'posix'",
                "os_name != 'posix'",
            ],
            {(), (0,), (1,)},
        ),
    ],
)
def test_marker_partitions_include_all_boolean_alternatives(markers, expected):
    assert constraints.active_groups(markers) == expected


@pytest.mark.parametrize("marker", ["invalid marker", "", "  "])
def test_invalid_marker_syntax_is_not_treated_as_unconditional(marker):
    if marker == "":
        assert constraints.active_groups([marker]) == {(0,)}
    else:
        with pytest.raises(ValueError):
            constraints.active_groups([marker])


@pytest.mark.parametrize(
    "specs",
    [
        [">=1", "==1.1rc1"],
        ["===custom", ">=1"],
        ["===one", "===two"],
        ["==1.*", "!=1.*"],
    ],
)
def test_incompatible_intersections_do_not_fail_open(specs):
    assert not constraints.satisfiable(specs)


def test_three_way_conflict_is_not_reduced_to_pairwise_checks(tmp_path, capsys):
    for name, spec in [("a.toml", ">=1,<4,!=2.*"), ("b.toml", ">=2"), ("c.toml", "<3")]:
        _pyproject(tmp_path / name, [f"samplelib{spec}"])
    code, out = _run(tmp_path, _policy(tmp_path, ["a.toml", "b.toml", "c.toml"]), capsys)
    assert code == 1, out
    assert "CONFLICT samplelib" in out


@pytest.mark.parametrize(
    "bodies",
    [
        "dev = [{include-group = 'absent'}]",
        "dev = [{include-group = 'test'}]\ntest = [{include-group = 'dev'}]",
        "a_b = []\na-b = []\ndev = [{include-group = 'a.b'}]",
    ],
)
def test_invalid_group_references_fail_closed(tmp_path, capsys, bodies):
    (tmp_path / "a.toml").write_text("[dependency-groups]\n" + bodies + "\n", encoding="utf-8")
    code, out = _run(tmp_path, _policy(tmp_path, ["a.toml"]), capsys)
    assert code == 2, out


def test_conditional_floors_only_compare_matching_platforms(tmp_path, capsys):
    a = ["samplelib>=1; sys_platform == 'win32'", "samplelib>=2; sys_platform != 'win32'"]
    b = ["samplelib>=2; sys_platform != 'win32'", "samplelib>=1; sys_platform == 'win32'"]
    _pyproject(tmp_path / "a.toml", a)
    _pyproject(tmp_path / "b.toml", b)
    code, out = _run(tmp_path, _policy(tmp_path, ["a.toml", "b.toml"]), capsys)
    assert code == 0, out
    _pyproject(tmp_path / "b.toml", [b[0], "samplelib>=2; sys_platform == 'win32'"])
    code, out = _run(tmp_path, _policy(tmp_path, ["a.toml", "b.toml"]), capsys)
    assert code == 1, out
    assert "FLOOR-DRIFT samplelib: a.toml floor 1 trails 2" in out


def test_parsed_declarations_preserve_markers(tmp_path):
    _pyproject(tmp_path / "a.toml", ["samplelib==1; sys_platform == 'win32'"])
    decls = cdd.python_declarations(tmp_path, "a.toml")
    assert next(d for d in decls if d.package == "samplelib").marker == 'sys_platform == "win32"'


@pytest.mark.parametrize(
    ("left", "right", "witness"),
    [
        ("'3.12' > python_full_version", "python_full_version == '3.12rc1'", "3.12rc1"),
        ("'3.12rc1' < python_full_version", "python_full_version == '3.12rc2'", "3.12rc2"),
        ("'3.12.post1' > python_full_version", "python_full_version == '3.12.dev1'", "3.12.dev1"),
        ("'3.12' <= python_full_version", "python_full_version == '3.13'", "3.13"),
        ("'3.12' >= python_full_version", "python_full_version == '3.11'", "3.11"),
    ],
)
def test_reversed_version_comparisons_preserve_packaging_witnesses(left, right, witness):
    assert Marker(left).evaluate({"python_full_version": witness})
    assert Marker(right).evaluate({"python_full_version": witness})
    assert (0, 1) in constraints.active_groups([left, right])


@pytest.mark.parametrize(
    ("left", "right", "witness"),
    [
        ("'3.12rc1' < python_full_version", "python_full_version == '3.12'", "3.12"),
        ("'3.12.post1' > python_full_version", "python_full_version == '3.12'", "3.12"),
    ],
)
def test_reversed_comparisons_keep_special_pep440_exclusions(left, right, witness):
    assert not Marker(left).evaluate({"python_full_version": witness})
    assert Marker(right).evaluate({"python_full_version": witness})
    assert (0, 1) not in constraints.active_groups([left, right])


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ("python_version < '3.12'", "python_full_version >= '3.12'", False),
        ("python_version == '3.12'", "python_full_version == '3.12rc1'", True),
        ("python_version > '3.12'", "python_full_version < '3.13'", False),
        ("python_version in '3.12'", "python_full_version == '3.12.1'", True),
        ("python_version not in '3.12'", "python_full_version == '3.12.1'", False),
        ("python_version ~= '3.12'", "python_full_version == '4.0'", False),
        ("'3.12' ~= python_version", "python_full_version == '3.11'", True),
        ("python_version == '3.12.1'", "python_full_version == '3.12.1'", False),
    ],
)
def test_python_minor_and_full_versions_share_one_environment(left, right, expected):
    assert ((0, 1) in constraints.active_groups([left, right])) is expected


@pytest.mark.parametrize(
    "marker",
    [
        "'3.1' in python_full_version and python_full_version >= '3'",
        "'3.12' ~= python_full_version",
        "python_full_version ~= 'not-a-version'",
    ],
)
def test_unsupported_version_predicates_fail_explicitly(tmp_path, capsys, marker):
    _pyproject(tmp_path / "a.toml", [f"samplelib==1; {marker}"])
    code, out = _run(tmp_path, _policy(tmp_path, ["a.toml"]), capsys)
    assert code == 2, out
    assert "CONFIG ERROR" in out


def test_all_members_are_validated_after_a_valid_requirement(tmp_path, capsys):
    (tmp_path / "a.toml").write_text(
        "[project]\ndependencies = ['samplelib>=1', 123]\n", encoding="utf-8"
    )
    code, out = _run(tmp_path, _policy(tmp_path, ["a.toml"]), capsys)
    assert code == 2, out


@pytest.mark.parametrize(
    ("markers", "expected"),
    [
        (["platform_release == 'linux'", "platform_release != 'linux'"], {(0,), (1,)}),
        (["'a' in extras", "'a-b' in extras"], {(), (0,), (1,), (0, 1)}),
        (["'dev' in dependency_groups", "'dev' not in dependency_groups"], {(0,), (1,)}),
        (
            ["python_full_version in '3.12'", "python_full_version >= '3.12'"],
            {(), (0,), (1,), (0, 1)},
        ),
        (
            ["implementation_version not in '3.12'", "implementation_version >= '3.12'"],
            {(), (0,), (1,), (0, 1)},
        ),
    ],
)
def test_string_fallbacks_sets_and_full_version_membership(markers, expected):
    assert constraints.active_groups(markers) == expected


def test_floor_allow_identity_does_not_depend_on_rendered_text(tmp_path, capsys):
    _pyproject(tmp_path / "a floor project.toml", ["samplelib>=1"])
    _pyproject(tmp_path / "b.toml", ["samplelib>=2"])
    policy = _policy(
        tmp_path,
        ["a floor project.toml", "b.toml"],
        allow=[("samplelib", "a floor project.toml", "Deliberately wide floor.")],
    )
    code, out = _run(tmp_path, policy, capsys)
    assert code == 0, out


def test_arbitrary_equality_does_not_gain_alternate_numeric_spellings():
    markers = ["python_full_version not in '3.12'", "python_full_version === '3.12'"]
    expected = {
        tuple(
            i
            for i, marker in enumerate(markers)
            if Marker(marker).evaluate({"python_full_version": value})
        )
        for value in ["3.1", "3.12", "3.12.0"]
    }
    assert constraints.active_groups(markers) == expected
