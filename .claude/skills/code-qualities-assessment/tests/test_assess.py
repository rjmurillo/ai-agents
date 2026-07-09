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

import builtins
import importlib.util
from pathlib import Path
from typing import Any

import pytest

_SCRIPT_DIR = Path(__file__).parent.parent / "scripts"

_spec = importlib.util.spec_from_file_location("assess", _SCRIPT_DIR / "assess.py")
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

assess_file = _mod.assess_file
check_thresholds = _mod.check_thresholds
detect_language = _mod.detect_language
get_files_to_assess = _mod.get_files_to_assess
generate_json_report = _mod.generate_json_report
generate_markdown_report = _mod.generate_markdown_report
load_config = _mod.load_config


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def _default_config() -> dict[str, Any]:
    # load_config with a nonexistent path returns the built-in defaults.
    config: dict[str, Any] = load_config(str(Path("/nonexistent/.qualityrc.json")))
    return config


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
    # no "min"; "warn" is an ignored unknown key
    legacy["thresholds"]["coupling"] = {"max": 3, "warn": 5}

    rc = check_thresholds([assessment], legacy, "production")
    assert rc == 0


def test_default_config_declares_no_unconsumed_threshold_keys() -> None:
    """The default config must not declare threshold keys the gate never reads.

    Only ``min`` (and legacy ``max`` for coupling) are consumed by
    ``check_thresholds`` and the report. A ``warn`` tier was declared for every
    quality but never implemented, which misled users into thinking a warning
    level existed. This guards the config contract so a future edit does not
    reintroduce an unimplemented key.
    """
    consumed = {"min", "max"}
    thresholds = _default_config()["thresholds"]
    for quality, spec in thresholds.items():
        unconsumed = set(spec) - consumed
        assert not unconsumed, f"{quality} declares unconsumed keys: {unconsumed}"


def test_gate_fails_tightly_coupled_file(tmp_path: Path) -> None:
    """Positive control: a heavily-imported file scores below coupling.min=7
    and the gate fails it."""
    heavy_body = "".join(f"import mod{i}\n" for i in range(9)) + "def f():\n    return 1\n"
    heavy = _write(tmp_path, "heavy.py", heavy_body)
    assessment = assess_file(heavy, "production", False)
    assert assessment.coupling.value < 7

    rc = check_thresholds([assessment], _default_config(), "production")
    assert rc == 11


# --------------------------------------------------------------------------- #
# Regression guards for GPT-5.5 adversarial review of PR #3000
# --------------------------------------------------------------------------- #


def test_go_import_block_not_overcounted(tmp_path: Path) -> None:
    """A Go ``import ( ... )`` block must count only the specs inside it, not
    the block opener. A 3-import block is 3 imports (coupling 7), not 4."""
    body = (
        "package main\n\n"
        "import (\n"
        '    "fmt"\n'
        '    "os"\n'
        '    "strings"\n'
        ")\n\n"
        "func main() {}\n"
    )
    path = _write(tmp_path, "main.go", body)
    coupling = assess_file(path, "production", False).coupling
    # 10 - 3 imports == 7; the block opener must not add a fourth.
    assert coupling.value == 7


def test_go_imports_with_trailing_comments_counted(tmp_path: Path) -> None:
    """Go import specs may carry a trailing ``// ...`` line comment, both for a
    single ``import "x"`` line and inside an ``import ( ... )`` block. The
    coupling regex must still count them; otherwise a tightly coupled file is
    under-counted and can slip through the gate."""
    single = _write(
        tmp_path,
        "single.go",
        'package main\n\nimport "fmt" // formatting\n\nfunc main() {}\n',
    )
    # One counted import => coupling 9 (10 - 1); a missed import would score 10.
    assert assess_file(single, "production", False).coupling.value == 9

    block = _write(
        tmp_path,
        "block.go",
        (
            "package main\n\n"
            "import (\n"
            '    "fmt" // formatting\n'
            '    "os"  // process env\n'
            '    _ "github.com/lib/pq" // sql driver, blank import\n'
            ")\n\n"
            "func main() {}\n"
        ),
    )
    # Three specs, each with a trailing comment => coupling 7 (10 - 3).
    assert assess_file(block, "production", False).coupling.value == 7


def test_web_indented_local_var_not_counted_as_global(tmp_path: Path) -> None:
    """An indented function-local ``var`` is not global state; only a
    module-scope (unindented) ``var`` lowers JS testability."""
    local_only = _write(
        tmp_path,
        "local.js",
        "function f() {\n    var x = 1;\n    return x;\n}\n",
    )
    module_scope = _write(
        tmp_path,
        "global.js",
        "var x = 1;\nfunction f() {\n    return x;\n}\n",
    )
    local_score = assess_file(local_only, "production", False).testability
    global_score = assess_file(module_scope, "production", False).testability
    # The local-only file has no global state, so it scores strictly higher.
    assert local_score.value > global_score.value


def test_directory_scan_includes_all_supported_suffixes(tmp_path: Path) -> None:
    """Directory assessment must pick up every suffix detect_language supports,
    including .go, .tsx, .jsx, .mjs, .cjs (previously omitted)."""
    for name in ("a.go", "b.tsx", "c.jsx", "d.mjs", "e.cjs", "f.py"):
        _write(tmp_path, name, "x = 1\n")
    found = {p.name for p in get_files_to_assess(str(tmp_path), False)}
    assert {"a.go", "b.tsx", "c.jsx", "d.mjs", "e.cjs", "f.py"} <= found


def test_template_qualityrc_uses_coupling_min(tmp_path: Path) -> None:
    """The shipped template config must use coupling.min (matching
    check_thresholds), not the legacy coupling.max that disabled the gate."""
    import json

    template = (
        Path(__file__).parent.parent / "templates" / ".qualityrc.json"
    )
    config = json.loads(template.read_text(encoding="utf-8"))
    coupling = config["thresholds"]["coupling"]
    assert "min" in coupling
    assert "max" not in coupling


# --------------------------------------------------------------------------- #
# PR #3000 adversarial-review fixes (GPT-5.5 / Copilot findings)
# --------------------------------------------------------------------------- #


def test_go_aliased_and_dot_imports_counted(tmp_path: Path) -> None:
    """Aliased (`m "math"`) and dot (`. "strings"`) imports in a Go block must
    count, or coupling is inflated and the gate can pass when it should fail."""
    body = (
        "package main\n\n"
        "import (\n"
        '    "fmt"\n'
        '    _ "database/sql"\n'
        '    m "math"\n'
        '    . "strings"\n'
        ")\n\n"
        "func main() {}\n"
    )
    path = _write(tmp_path, "main.go", body)
    coupling = assess_file(path, "production", False).coupling
    # 4 import specs: plain, blank, aliased, dot. 10 - 4 == 6.
    assert coupling.value == 6


@pytest.mark.parametrize(
    "import_line",
    [
        'import _ "fmt"\n',
        'import myfmt "fmt"\n',
        'import . "fmt"\n',
    ],
)
def test_go_single_line_named_blank_and_dot_imports_counted(
    tmp_path: Path, import_line: str
) -> None:
    body = "package main\n\n" + import_line + "\nfunc main() {}\n"
    path = _write(tmp_path, "main.go", body)

    coupling = assess_file(path, "production", False).coupling

    assert coupling.value == 9


def test_go_named_blank_and_dot_imports_counted_inside_block(tmp_path: Path) -> None:
    body = (
        "package main\n\n"
        "import (\n"
        '    myfmt "fmt"\n'
        '    _ "database/sql"\n'
        '    . "strings"\n'
        ")\n\n"
        "func main() {}\n"
    )
    path = _write(tmp_path, "main.go", body)

    coupling = assess_file(path, "production", False).coupling

    assert coupling.value == 7


def test_go_package_var_block_counts_as_global_state(tmp_path: Path) -> None:
    clean = _write(tmp_path, "clean.go", "package main\n\nfunc main() {}\n")
    dirty = _write(
        tmp_path,
        "dirty.go",
        "package main\n\n"
        "var (\n"
        "    counter int\n"
        "    cache = map[string]string{}\n"
        ")\n\n"
        "func main() {}\n",
    )

    clean_score = assess_file(clean, "production", False).testability
    dirty_score = assess_file(dirty, "production", False).testability

    assert dirty_score.value < clean_score.value


def test_go_indented_local_var_block_not_counted_as_global_state(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "local.go",
        "package main\n\n"
        "func main() {\n"
        "    var (\n"
        "        local int\n"
        "    )\n"
        "    _ = local\n"
        "}\n",
    )

    testability = assess_file(path, "production", False).testability

    assert testability.value == 10


def test_python_public_fields_are_deduplicated_by_name(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "fields.py",
        "class C:\n"
        "    def first(self):\n"
        "        self.x = 1\n"
        "    def second(self):\n"
        "        self.x = 2\n",
    )

    encapsulation = assess_file(path, "production", False).encapsulation

    assert encapsulation.reasons[0] == "1 exposed public field(s)"


@pytest.mark.parametrize(
    ("name", "body"),
    [
        ("Constants.cs", "public class C {\n    public const int Answer = 42;\n}\n"),
        ("Readonly.cs", "public class C {\n    public readonly int Answer = 42;\n}\n"),
        ("Final.java", "public class C {\n    public final int answer = 42;\n}\n"),
    ],
)
def test_public_immutable_fields_do_not_lower_encapsulation(
    tmp_path: Path, name: str, body: str
) -> None:
    path = _write(tmp_path, name, body)

    encapsulation = assess_file(path, "production", False).encapsulation

    assert encapsulation.value == 10


def test_untuned_language_coupling_not_gated(tmp_path: Path) -> None:
    """A language without a tuned import pattern is counted only for the report
    (confidence 0.0), so check_thresholds skips it rather than gating on an
    untuned heuristic (honors the file-header contract)."""
    # .rb has no tuned pattern; detect_language returns None.
    lines = [f"require 'lib{i}'" for i in range(12)]
    body = "\n".join(lines) + "\n"
    path = _write(tmp_path, "many_imports.rb", body)
    coupling = assess_file(path, "production", False).coupling
    assert coupling.confidence == 0.0
    assert all(
        score.confidence == 0.0
        for score in (
            assess_file(path, "production", False).cohesion,
            assess_file(path, "production", False).coupling,
            assess_file(path, "production", False).encapsulation,
            assess_file(path, "production", False).testability,
            assess_file(path, "production", False).non_redundancy,
        )
    )
    # Even a low coupling score must not fail the gate when unscored.
    config = _default_config()
    config["thresholds"]["coupling"] = {"min": 7}
    assert check_thresholds([assess_file(path, "production", False)], config, "production") == 0


def test_unreadable_file_is_unscored_not_passed(tmp_path: Path) -> None:
    """A file that cannot be read must come back all-unscored (confidence 0.0)
    so the gate skips it, instead of scoring empty content as a perfect 10."""
    missing = tmp_path / "gone.py"  # never created -> open() raises OSError
    assessment = assess_file(missing, "production", False)
    for score in (
        assessment.cohesion,
        assessment.coupling,
        assessment.encapsulation,
        assessment.testability,
        assessment.non_redundancy,
    ):
        assert score.confidence == 0.0
    # An unreadable file must not fail (or pass by scoring) any threshold.
    assert check_thresholds([assessment], _default_config(), "production") == 0


def test_csharp_public_brace_initializer_field_lowers_encapsulation(tmp_path: Path) -> None:
    """A C# public field declared with a brace initializer
    (``public int[] xs = {1, 2};``) is still exposed public state and must
    lower encapsulation, not be skipped as a property or type body."""
    exposed = _write(
        tmp_path,
        "Exposed.cs",
        "public class C\n{\n    public int[] xs = {1, 2};\n}\n",
    )
    hidden = _write(
        tmp_path,
        "Hidden.cs",
        "public class C\n{\n    private int[] xs = {1, 2};\n}\n",
    )
    assert (
        assess_file(exposed, "production", False).encapsulation.value
        < assess_file(hidden, "production", False).encapsulation.value
    )


def test_unreadable_assessment_scores_are_not_aliased(tmp_path: Path) -> None:
    """Each quality of an unreadable file must be an independent QualityScore;
    mutating one metric's reasons must not bleed into the others."""
    missing = tmp_path / "gone.py"  # never created -> open() raises OSError
    assessment = assess_file(missing, "production", False)
    assessment.cohesion.reasons.append("mutated")
    for score in (
        assessment.coupling,
        assessment.encapsulation,
        assessment.testability,
        assessment.non_redundancy,
    ):
        assert "mutated" not in score.reasons


def test_read_error_is_reported_as_unscored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _write(tmp_path, "broken.py", "def f():\n    return 1\n")
    real_open: Any = builtins.open

    def raise_permission_error(file: Any, *args: Any, **kwargs: Any) -> Any:
        if file == path:
            raise PermissionError("blocked")
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", raise_permission_error)

    assessment = assess_file(path, "production", False)

    assert assessment.overall == 0.0
    assert all(
        score.confidence == 0.0
        for score in (
            assessment.cohesion,
            assessment.coupling,
            assessment.encapsulation,
            assessment.testability,
            assessment.non_redundancy,
        )
    )
    assert "blocked" in assessment.cohesion.reasons[0]
    assert check_thresholds([assessment], _default_config(), "production") == 0


def test_markdown_report_displays_unscored_metrics_as_na(tmp_path: Path) -> None:
    path = _write(tmp_path, "unknown.rb", "require 'x'\n")
    assessment = assess_file(path, "production", False)

    report = generate_markdown_report([assessment], _default_config())

    assert "**Overall**: n/a" in report
    assert "- **Cohesion**: unscored (n/a)" in report
    assert "**Average Cohesion**: n/a" in report
    assert "10.0/10" not in report


def test_json_report_excludes_unscored_metrics_from_average(tmp_path: Path) -> None:
    import json

    path = _write(tmp_path, "unknown.rb", "require 'x'\n")
    assessment = assess_file(path, "production", False)

    report = json.loads(generate_json_report([assessment]))

    assert report["summary"]["average_scores"]["cohesion"] is None


def test_overall_ignores_unscored_metrics(tmp_path: Path) -> None:
    path = _write(tmp_path, "mixed.py", "def f():\n    return 1\n")
    assessment = assess_file(path, "production", False)
    assessment.encapsulation.confidence = 0.0
    assessment.encapsulation.value = 10.0
    assessment.coupling.value = 4.0

    scored_values = [
        assessment.cohesion.value,
        assessment.coupling.value,
        assessment.testability.value,
        assessment.non_redundancy.value,
    ]

    assert assessment.overall == pytest.approx(sum(scored_values) / len(scored_values))


def test_markdown_report_uses_configured_thresholds(tmp_path: Path) -> None:
    path = _write(tmp_path, "imports.py", "import a\nimport b\n\ndef f():\n    return 1\n")
    assessment = assess_file(path, "production", False)
    config = _default_config()
    config["thresholds"]["coupling"] = {"min": 9}

    report = generate_markdown_report([assessment], config)

    assert "**Coupling Issues**:" in report
    assert "2 import/dependency statements" in report


def test_load_config_reads_utf8_json(tmp_path: Path) -> None:
    config_path = tmp_path / ".qualityrc.json"
    config_path.write_text('{"thresholds": {}, "label": "café"}', encoding="utf-8")

    config = load_config(str(config_path))

    assert config["label"] == "café"
