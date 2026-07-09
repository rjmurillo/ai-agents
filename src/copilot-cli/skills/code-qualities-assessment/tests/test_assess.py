"""Direction and gate tests for the code-qualities-assessment assess.py heuristics.

These tests pin the SCORE DIRECTION (which of two files should score higher for
a quality) and the threshold-gate behavior, not exact numeric values. They guard
the bugs fixed for issue #2994:

- Coupling threshold inversion: loosely coupled files no longer fail the gate.
- Language-blind testability/encapsulation: non-Python files are no longer
  scored as a constant 10; unsupported languages are marked unscored
  (confidence 0.0) and skipped by the gate instead of false-passing or
  false-failing.
- Cohesion measured size+definitions instead of size alone.
- Import counting recognizes C#/Java/Go imports, not just Python.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT_DIR = Path(__file__).parent.parent / "scripts"

_spec = importlib.util.spec_from_file_location("assess", _SCRIPT_DIR / "assess.py")
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

assess_file = _mod.assess_file
check_thresholds = _mod.check_thresholds
detect_language = _mod.detect_language
load_config = _mod.load_config


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def _default_config() -> dict:
    # load_config with a nonexistent path returns the built-in defaults.
    return load_config(str(Path("/nonexistent/.qualityrc.json")))


# --------------------------------------------------------------------------- #
# detect_language
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("a.py", "python"),
        ("a.ts", "typescript"),
        ("a.tsx", "typescript"),
        ("a.js", "javascript"),
        ("a.cs", "csharp"),
        ("a.java", "java"),
        ("a.go", "go"),
        ("a.rb", None),
        ("a.txt", None),
    ],
)
def test_detect_language(name: str, expected: str | None) -> None:
    assert detect_language(Path(name)) == expected


# --------------------------------------------------------------------------- #
# Coupling: direction + threshold is no longer inverted
# --------------------------------------------------------------------------- #


def test_coupling_direction_python(tmp_path: Path) -> None:
    standalone = _write(tmp_path, "standalone.py", "def f():\n    return 1\n")
    heavy_body = "".join(f"import mod{i}\n" for i in range(15)) + "def f():\n    return 1\n"
    heavy = _write(tmp_path, "heavy.py", heavy_body)

    standalone_score = assess_file(standalone, "production", False).coupling.value
    heavy_score = assess_file(heavy, "production", False).coupling.value

    # Fewer imports => looser coupling => higher score (10 is best).
    assert standalone_score > heavy_score


def test_loosely_coupled_file_passes_gate(tmp_path: Path) -> None:
    """The inversion bug: a loosely coupled file (coupling score ~10) used to
    FAIL because the gate compared coupling > max=3. It must now pass."""
    standalone = _write(tmp_path, "standalone.py", "def f():\n    return 1\n")
    assessment = assess_file(standalone, "production", False)
    assert assessment.coupling.value >= 9  # loosely coupled, near-perfect

    rc = check_thresholds([assessment], _default_config(), "production")
    # Coupling alone must not fail this file. (Other qualities on a trivial
    # one-function file are all high, so the overall gate passes.)
    assert rc == 0


def test_csharp_imports_counted(tmp_path: Path) -> None:
    """C# `using` directives count toward coupling; previously only Python
    `import ` did, so every C# file looked maximally decoupled."""
    body = (
        "using System;\n"
        "using System.Linq;\n"
        "using System.Collections.Generic;\n"
        "public class Foo { public int X; }\n"
    )
    path = _write(tmp_path, "Foo.cs", body)
    score = assess_file(path, "production", False).coupling.value
    # 3 usings => coupling score 7, strictly below the perfect 10.
    assert score < 10


# --------------------------------------------------------------------------- #
# Cohesion: god object scores lower than a focused class
# --------------------------------------------------------------------------- #


def test_cohesion_god_object_lower_than_focused(tmp_path: Path) -> None:
    focused = _write(
        tmp_path,
        "focused.py",
        "class Focused:\n"
        "    def a(self):\n        return 1\n"
        "    def b(self):\n        return 2\n",
    )
    god_methods = "".join(
        f"    def m{i}(self):\n        x = {i}\n        return x\n" for i in range(40)
    )
    god = _write(tmp_path, "god.py", "class God:\n" + god_methods)

    focused_score = assess_file(focused, "production", False).cohesion.value
    god_score = assess_file(god, "production", False).cohesion.value

    assert god_score < focused_score


# --------------------------------------------------------------------------- #
# Testability: not a constant across languages
# --------------------------------------------------------------------------- #


def test_testability_not_constant_across_languages(tmp_path: Path) -> None:
    """Regression guard: previously testability was 10 for every non-Python
    file because global-state detection was Python-only."""
    clean_cs = _write(
        tmp_path,
        "Clean.cs",
        "public class Clean {\n    public int Add(int a, int b) => a + b;\n}\n",
    )
    dirty_cs = _write(
        tmp_path,
        "Dirty.cs",
        "public class Dirty {\n"
        "    private static int _counter = 0;\n"
        "    public static string Cache = \"x\";\n"
        "    public int Next() => _counter++;\n"
        "}\n",
    )

    clean_score = assess_file(clean_cs, "production", False).testability
    dirty_score = assess_file(dirty_cs, "production", False).testability

    assert clean_score.confidence > 0.0
    assert dirty_score.confidence > 0.0
    # Mutable static state hurts testability.
    assert dirty_score.value < clean_score.value


def test_testability_python_global_state(tmp_path: Path) -> None:
    clean = _write(tmp_path, "clean.py", "def f():\n    return 1\n")
    dirty = _write(
        tmp_path,
        "dirty.py",
        "_x = 0\n\n\ndef f():\n    global _x\n    _x += 1\n    return _x\n",
    )
    assert (
        assess_file(dirty, "production", False).testability.value
        < assess_file(clean, "production", False).testability.value
    )


def test_testability_unscored_for_unknown_language(tmp_path: Path) -> None:
    path = _write(tmp_path, "thing.rb", "def foo\n  1\nend\n")
    score = assess_file(path, "production", False).testability
    assert score.confidence == 0.0


# --------------------------------------------------------------------------- #
# Encapsulation: unscored where visibility cannot be detected reliably
# --------------------------------------------------------------------------- #


def test_encapsulation_unscored_for_javascript(tmp_path: Path) -> None:
    path = _write(tmp_path, "a.js", "function f() { return 1; }\n")
    score = assess_file(path, "production", False).encapsulation
    assert score.confidence == 0.0


def test_encapsulation_scored_for_python(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "a.py",
        "class C:\n    def _helper(self):\n        return 1\n"
        "    def public(self):\n        return self._helper()\n",
    )
    score = assess_file(path, "production", False).encapsulation
    assert score.confidence > 0.0
    assert score.value == 10.0  # methods-only API, no exposed fields


def test_encapsulation_public_fields_lower_score(tmp_path: Path) -> None:
    hidden = _write(
        tmp_path,
        "hidden.py",
        "class C:\n    def __init__(self):\n        self._x = 0\n"
        "    def value(self):\n        return self._x\n",
    )
    exposed = _write(
        tmp_path,
        "exposed.py",
        "class C:\n    def __init__(self):\n        self.x = 0\n        self.y = 1\n",
    )
    assert (
        assess_file(exposed, "production", False).encapsulation.value
        < assess_file(hidden, "production", False).encapsulation.value
    )


# --------------------------------------------------------------------------- #
# Gate skips unscored qualities (confidence 0.0) instead of false-failing
# --------------------------------------------------------------------------- #


def test_gate_skips_unscored_qualities(tmp_path: Path) -> None:
    """An unknown-language file leaves testability and encapsulation unscored.
    The gate must not fail on a quality it could not measure."""
    path = _write(tmp_path, "thing.rb", "def foo\n  1\nend\n")
    assessment = assess_file(path, "production", False)
    assert assessment.testability.confidence == 0.0
    assert assessment.encapsulation.confidence == 0.0

    rc = check_thresholds([assessment], _default_config(), "production")
    assert rc == 0


def test_gate_legacy_coupling_max_only_config_does_not_crash(tmp_path: Path) -> None:
    """A legacy config specifying only coupling.max (no min) must not KeyError;
    coupling gating is simply skipped for it."""
    path = _write(tmp_path, "standalone.py", "def f():\n    return 1\n")
    assessment = assess_file(path, "production", False)

    legacy = _default_config()
    legacy["thresholds"]["coupling"] = {"max": 3, "warn": 5}  # no "min"

    rc = check_thresholds([assessment], legacy, "production")
    assert rc == 0


def test_gate_fails_tightly_coupled_file(tmp_path: Path) -> None:
    """Positive control: a heavily-imported file scores below coupling.min=7
    and the gate fails it."""
    heavy_body = "".join(f"import mod{i}\n" for i in range(9)) + "def f():\n    return 1\n"
    heavy = _write(tmp_path, "heavy.py", heavy_body)
    assessment = assess_file(heavy, "production", False)
    assert assessment.coupling.value < 7

    rc = check_thresholds([assessment], _default_config(), "production")
    assert rc == 11
