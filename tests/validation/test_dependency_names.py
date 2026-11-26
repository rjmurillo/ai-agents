"""The two dependency gates must agree on what a declared package name is.

``dependency_names.py`` owns normalization, requirement-name parsing and table
reads. ``dependency_manifest.declared_packages`` (unused-dependency gate) and
``check_dependency_drift.python_declarations`` (drift gate) both build on it.
The conformance test reads every real manifest the drift policy names and fails
when the two disagree beyond their one documented scope difference, the
``[tool.uv]`` pins.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.validation import check_dependency_drift as drift
from scripts.validation import dependency_names as names

# The unused-dependency gate is loaded once by the shared support module. Importing its
# siblings bare here would bind a second PolicyError class and break that gate's tests
# when collection order changes.
from tests.validation._unused_dependencies_support import cud

REPO_ROOT = Path(__file__).resolve().parents[2]
PolicyError = cud.PolicyError
declared_packages = cud.declared_packages


class TestNormalize:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Foo_Bar", "foo-bar"),
            ("foo.bar", "foo-bar"),
            ("foo-_.bar", "foo-bar"),
            ("PyYAML", "pyyaml"),
        ],
    )
    def test_follows_pep_503(self, raw: str, expected: str) -> None:
        assert names.normalize(raw) == expected

    def test_both_gates_use_the_one_implementation(self) -> None:
        assert drift.normalize is names.normalize
        assert cud.normalize.__module__.rsplit(".", 1)[-1] == "dependency_names"
        assert cud.normalize("Foo_Bar.baz") == names.normalize("Foo_Bar.baz")


class TestRequirementName:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("pytest>=8", "pytest"),
            ("Foo_Bar[extra]>=1; python_version < '3.12'", "foo-bar"),
            ("pkg @ https://example.test/pkg-1.tar.gz", "pkg"),
            ("  spaced  ", "spaced"),
        ],
    )
    def test_parses_with_packaging(self, text: str, expected: str) -> None:
        assert names.requirement_name(text) == expected

    def test_falls_back_to_leading_name_when_packaging_rejects(self) -> None:
        # packaging rejects an empty specifier clause; the scan still needs the name.
        assert names.requirement_name("legacy-pkg >=1,,2") == "legacy-pkg"

    @pytest.mark.parametrize("text", ["", "   ", ">=1.0", "[extra]"])
    def test_returns_none_when_no_name_exists(self, text: str) -> None:
        assert names.requirement_name(text) is None


class TestTable:
    def test_missing_key_is_an_empty_table(self) -> None:
        assert names.table({}, "tool", "m", PolicyError) == {}

    def test_returns_the_table(self) -> None:
        assert names.table({"tool": {"a": 1}}, "tool", "m", PolicyError) == {"a": 1}

    @pytest.mark.parametrize("error", [PolicyError, drift.DriftConfigError])
    def test_non_table_raises_the_callers_error(self, error: type[Exception]) -> None:
        with pytest.raises(error, match="m: 'tool' must be a table"):
            names.table({"tool": []}, "tool", "m", error)


class TestGatesAgree:
    def test_uv_pins_are_the_only_scope_difference(self, tmp_path: Path) -> None:
        manifest = tmp_path / "pyproject.toml"
        manifest.write_text(
            '[project]\nname = "demo"\ndependencies = ["A_pkg>=1"]\n'
            '[tool.uv]\noverride-dependencies = ["Pinned.Only==2"]\n',
            encoding="utf-8",
        )
        assert declared_packages(manifest) == {"a-pkg"}
        assert declared_packages(manifest, include_uv_pins=True) == {"a-pkg", "pinned-only"}

    def test_real_manifests_yield_identical_names_in_both_gates(self) -> None:
        policy = drift.load_policy(REPO_ROOT / drift.DEFAULT_POLICY)
        assert policy.python_manifests, "the drift policy names no python manifest"
        for manifest in policy.python_manifests:
            from_drift = {
                d.package
                for d in drift.python_declarations(REPO_ROOT, manifest)
                if d.origin != "requires-python"
            }
            from_manifest = declared_packages(REPO_ROOT / manifest, include_uv_pins=True)
            assert from_manifest == from_drift, manifest
            assert from_drift, f"{manifest} declared no package, so the check proved nothing"

    def test_comparison_detects_a_gate_that_drops_uv_pins(self, tmp_path: Path) -> None:
        """Negative control: the comparison above must be able to fail."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "demo"\ndependencies = ["alpha>=1"]\n'
            '[tool.uv]\nconstraint-dependencies = ["beta<3"]\n',
            encoding="utf-8",
        )
        from_drift = {
            d.package
            for d in drift.python_declarations(tmp_path, "pyproject.toml")
            if d.origin != "requires-python"
        }
        assert from_drift == {"alpha", "beta"}
        assert declared_packages(tmp_path / "pyproject.toml") != from_drift
