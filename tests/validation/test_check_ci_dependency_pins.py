"""Tests for the CI dependency pin gate (Issue #3377)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_validation_path = str(Path(__file__).resolve().parents[2] / "scripts" / "validation")
sys.path.insert(0, _validation_path)
try:
    import check_ci_dependency_pins as gate  # noqa: E402
finally:
    sys.path.remove(_validation_path)

_REPO_ROOT = Path(__file__).resolve().parents[2]

_PYPROJECT = """
[project]
name = "x"
dependencies = ["PyYAML==6.0.3", "requests"]

[project.optional-dependencies]
dev = ["pytest>=9.0.3", "pytest-cov>=7.1.0"]
eval = ["pytest>=8.0"]
"""


def _write(tmp_path: Path, body: str, name: str = "w.yml") -> Path:
    root = tmp_path / "gh"
    root.mkdir(exist_ok=True)
    (root / name).write_text(body, encoding="utf-8")
    return root


def _pyproject(tmp_path: Path, body: str = _PYPROJECT) -> Path:
    path = tmp_path / "pyproject.toml"
    path.write_text(body, encoding="utf-8")
    return path


class TestDeclaredConstraints:
    def test_it_merges_base_and_every_extra(self, tmp_path):
        c = gate.declared_constraints(_pyproject(tmp_path))
        assert set(c) == {"pyyaml", "pytest", "pytest-cov"}

    def test_a_package_in_two_groups_intersects_its_specifiers(self, tmp_path):
        """pytest is >=9.0.3 in dev and >=8.0 in eval. CI installs one version,
        so it has to satisfy both."""
        c = gate.declared_constraints(_pyproject(tmp_path))
        assert not c["pytest"].contains(gate.Version("8.3.3"), prereleases=True)
        assert c["pytest"].contains(gate.Version("9.0.3"), prereleases=True)

    def test_a_dependency_with_no_specifier_carries_no_constraint(self, tmp_path):
        """requests is declared bare; a pin cannot contradict nothing."""
        assert "requests" not in gate.declared_constraints(_pyproject(tmp_path))

    def test_an_unparseable_requirement_is_skipped_not_fatal(self, tmp_path):
        path = _pyproject(tmp_path, '[project]\nname="x"\ndependencies=["!!!", "pytest>=9"]\n')
        assert set(gate.declared_constraints(path)) == {"pytest"}


class TestFindPins:
    def test_it_reports_the_line_number(self, tmp_path):
        root = _write(tmp_path, "a: 1\nb: 2\nrun: pip install 'pytest==8.3.3'\n")
        (pin,) = gate.find_pins(root)
        assert (pin.line, pin.name, pin.version) == (3, "pytest", "8.3.3")

    def test_it_finds_several_pins_on_one_line(self, tmp_path):
        root = _write(tmp_path, "run: pip install 'PyYAML==6.0.3' 'pytest==9.0.3'\n")
        assert {p.name for p in gate.find_pins(root)} == {"PyYAML", "pytest"}

    def test_an_unquoted_pin_is_still_a_pin(self, tmp_path):
        """pip does not require the quotes, so neither can the gate.

        Keying on quotes made the coverage a spelling accident: the same pin
        one shell-quoting style over drifts silently.
        """
        root = _write(tmp_path, "run: pip install pytest==8.3.3\n")
        (pin,) = gate.find_pins(root)
        assert (pin.name, pin.version) == ("pytest", "8.3.3")

    def test_a_spaced_comparison_is_not_a_pin(self, tmp_path):
        """Negative control: a spaced == in a script body is a comparison."""
        root = _write(tmp_path, "run: if [ $x == 1.0 ]; then echo hi; fi\n")
        assert gate.find_pins(root) == []

    def test_a_github_expression_comparison_is_not_a_pin(self, tmp_path):
        """The shape that dropping the quote requirement could have caught."""
        root = _write(tmp_path, "if: ${{ github.ref == 'refs/heads/main' }}\n")
        assert gate.find_pins(root) == []

    def test_a_triple_equals_is_not_a_pin(self, tmp_path):
        """The lookbehind's job: === is an operator, not a pin."""
        assert gate.find_pins(_write(tmp_path, "run: test a===1.0\n")) == []

    def test_a_version_must_start_with_a_digit(self, tmp_path):
        """foo==bar is a comparison of two words, not a pinned release."""
        assert gate.find_pins(_write(tmp_path, "run: echo foo==bar\n")) == []

    def test_an_uppercase_suffix_is_still_yaml(self, tmp_path):
        """Suffix matching is casefolded so a .YML file is not skipped."""
        root = _write(tmp_path, "run: pip install 'pytest==8.3.3'\n", name="w.YML")
        assert len(gate.find_pins(root)) == 1

    def test_non_yaml_files_are_not_scanned(self, tmp_path):
        root = _write(tmp_path, "x = 'pytest==8.3.3'\n", name="s.py")
        assert gate.find_pins(root) == []

    def test_it_recurses_into_subdirectories(self, tmp_path):
        root = tmp_path / "gh"
        nested = root / "actions" / "a"
        nested.mkdir(parents=True)
        (nested / "action.yml").write_text("run: pip install 'pytest==8.3.3'\n", encoding="utf-8")
        assert len(gate.find_pins(root)) == 1


class TestViolations:
    def _v(self, tmp_path, body):
        c = gate.declared_constraints(_pyproject(tmp_path))
        return gate.violations(gate.find_pins(_write(tmp_path, body)), c)

    def test_a_pin_below_the_floor_is_a_violation(self, tmp_path):
        (v,) = self._v(tmp_path, "run: pip install 'pytest==8.3.3'\n")
        assert v.pin.version == "8.3.3"
        # dev says >=9.0.3 and eval says >=8.0; the message carries both so a
        # reader sees every declaration the pin has to satisfy.
        assert ">=9.0.3" in v.constraint and ">=8.0" in v.constraint

    def test_a_pin_at_the_floor_passes(self, tmp_path):
        assert self._v(tmp_path, "run: pip install 'pytest==9.0.3'\n") == []

    def test_a_pin_above_the_floor_passes(self, tmp_path):
        assert self._v(tmp_path, "run: pip install 'pytest==9.1.1'\n") == []

    def test_an_exact_match_passes(self, tmp_path):
        assert self._v(tmp_path, "run: pip install 'PyYAML==6.0.3'\n") == []

    def test_a_pin_contradicting_an_exact_declaration_is_a_violation(self, tmp_path):
        (v,) = self._v(tmp_path, "run: pip install 'PyYAML==6.0.2'\n")
        assert v.pin.name == "PyYAML"

    def test_an_undeclared_package_is_not_checked(self, tmp_path):
        """pip itself is installed by CI and is not a project dependency."""
        assert self._v(tmp_path, 'run: python -m pip install "pip==26.1.2"\n') == []

    def test_the_name_is_matched_case_insensitively(self, tmp_path):
        """pyproject declares PyYAML; a pin spelled pyyaml is the same
        distribution under PEP 503 normalization."""
        (v,) = self._v(tmp_path, "run: pip install 'pyyaml==6.0.2'\n")
        assert v.pin.canonical == "pyyaml"

    def test_separator_runs_normalize_to_one_hyphen(self, tmp_path):
        """PEP 503 collapses runs of -_. to a single hyphen, so pytest_cov and
        pytest.cov both reach the pytest-cov constraint."""
        (v,) = self._v(tmp_path, "run: pip install 'pytest_cov==7.0.0'\n")
        assert v.pin.canonical == "pytest-cov"

    def test_an_unparseable_version_is_a_violation_not_a_pass(self, tmp_path):
        (v,) = self._v(tmp_path, "run: pip install 'pytest==9.x.y'\n")
        assert v.pin.version == "9.x.y"

    def test_a_prerelease_is_judged_not_skipped(self, tmp_path):
        """Without prereleases=True a specifier excludes prereleases silently,
        so an 8.x release candidate would read as passing a >=9 floor."""
        (v,) = self._v(tmp_path, "run: pip install 'pytest==8.4.0rc1'\n")
        assert v.pin.version == "8.4.0rc1"


class TestCheck:
    def test_a_clean_tree_exits_zero(self, tmp_path, capsys):
        root = _write(tmp_path, "run: pip install 'pytest==9.0.3'\n")
        assert gate.check(root, _pyproject(tmp_path)) == gate.EXIT_OK
        assert capsys.readouterr().err == ""

    def test_a_violation_exits_one_and_names_the_file(self, tmp_path, capsys):
        root = _write(tmp_path, "run: pip install 'pytest==8.3.3'\n")
        assert gate.check(root, _pyproject(tmp_path)) == gate.EXIT_LOGIC
        err = capsys.readouterr().err
        assert "w.yml:1" in err
        assert "pytest==8.3.3" in err
        assert ">=9.0.3" in err

    def test_a_missing_pyproject_is_a_config_failure(self, tmp_path, capsys):
        root = _write(tmp_path, "x: 1\n")
        assert gate.check(root, tmp_path / "nope.toml") == gate.EXIT_CONFIG
        assert "pyproject.toml not found" in capsys.readouterr().err

    def test_a_missing_root_is_a_config_failure(self, tmp_path, capsys):
        assert gate.check(tmp_path / "nope", _pyproject(tmp_path)) == gate.EXIT_CONFIG
        assert "scan root not found" in capsys.readouterr().err

    def test_an_unparseable_pyproject_is_a_config_failure(self, tmp_path, capsys):
        bad = tmp_path / "pyproject.toml"
        bad.write_text("[project\n", encoding="utf-8")
        assert gate.check(_write(tmp_path, "x: 1\n"), bad) == gate.EXIT_CONFIG
        assert "cannot read constraints" in capsys.readouterr().err


class TestMain:
    def test_it_returns_the_check_exit_code(self, tmp_path):
        root = _write(tmp_path, "run: pip install 'pytest==8.3.3'\n")
        argv = ["--root", str(root), "--pyproject", str(_pyproject(tmp_path))]
        assert gate.main(argv) == gate.EXIT_LOGIC

    def test_the_defaults_point_at_this_repository(self):
        parser = gate.build_parser()
        args = parser.parse_args([])
        assert Path(args.root) == _REPO_ROOT / ".github"
        assert Path(args.pyproject) == _REPO_ROOT / "pyproject.toml"


class TestTheRealTree:
    def test_every_pin_in_this_repository_agrees_with_pyproject(self):
        """The gate's reason for existing: .github/ once carried pytest==8.3.3
        against a pytest>=9.0.3 floor and nothing noticed."""
        assert gate.check(_REPO_ROOT / ".github", _REPO_ROOT / "pyproject.toml") == gate.EXIT_OK

    def test_the_repository_actually_pins_something_the_gate_checks(self):
        """Negative control: a gate that scans nothing passes vacuously."""
        constraints = gate.declared_constraints(_REPO_ROOT / "pyproject.toml")
        checked = [p for p in gate.find_pins(_REPO_ROOT / ".github") if p.canonical in constraints]
        assert checked, "no CI pin is covered by a pyproject constraint"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
