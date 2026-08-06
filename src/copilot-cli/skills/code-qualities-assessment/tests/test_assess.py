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
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

_SCRIPT_DIR = Path(__file__).parent.parent / "scripts"

_spec = importlib.util.spec_from_file_location("assess", _SCRIPT_DIR / "assess.py")
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

assess_content = _mod.assess_content
assess_file = _mod.assess_file
build_comparisons = _mod.build_comparisons
ChangedFile = _mod.ChangedFile
check_regression = _mod.check_regression
check_thresholds = _mod.check_thresholds
compare_assessments = _mod.compare_assessments
get_changed_files = _mod.get_changed_files
get_file_at_revision = _mod.get_file_at_revision
main = _mod.main
resolve_gate_mode = _mod.resolve_gate_mode
resolve_revision = _mod.resolve_revision
detect_language = _mod.detect_language
get_files_to_assess = _mod.get_files_to_assess
classify_file_category = _mod.classify_file_category
generate_json_report = _mod.generate_json_report
generate_markdown_report = _mod.generate_markdown_report
load_config = _mod.load_config
_parse_changed_files = _mod._parse_changed_files
_resolve_target_path = _mod._resolve_target_path
parse_args = _mod.parse_args


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def _run_git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        encoding="utf-8",
    )


def _default_config() -> dict[str, Any]:
    # load_config with a nonexistent path returns the built-in defaults.
    # Use a path inside a fresh temp dir and assert it is absent so the
    # FileNotFoundError branch is exercised deterministically, independent
    # of host filesystem state.
    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / ".qualityrc.json"
        assert not missing.exists()
        config: dict[str, Any] = load_config(str(missing))
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
        "class Focused:\n    def a(self):\n        return 1\n    def b(self):\n        return 2\n",
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
        '    public static string Cache = "x";\n'
        "    public int Next() => _counter++;\n"
        "}\n",
    )

    clean_score = assess_file(clean_cs, "production", False).testability
    dirty_score = assess_file(dirty_cs, "production", False).testability

    assert clean_score.confidence > 0.0
    assert dirty_score.confidence > 0.0
    # Mutable static state hurts testability.
    assert dirty_score.value < clean_score.value


def test_csharp_using_static_not_counted_as_state(tmp_path: Path) -> None:
    """Regression: `using static` is an import (dependency), not mutable
    static state, so it must not lower testability."""
    plain = _write(
        tmp_path,
        "Plain.cs",
        "public class Plain {\n    public int Add(int a, int b) => a + b;\n}\n",
    )
    with_static_import = _write(
        tmp_path,
        "WithImport.cs",
        "using static System.Math;\n\n"
        "public class WithImport {\n"
        "    public double Hyp(double a, double b) => Sqrt(a * a + b * b);\n"
        "}\n",
    )

    plain_score = assess_file(plain, "production", False).testability
    import_score = assess_file(with_static_import, "production", False).testability

    assert import_score.value == plain_score.value


def test_java_import_static_not_counted_as_state(tmp_path: Path) -> None:
    """Regression: `import static` is an import (dependency), not mutable
    static state, so it must not lower testability."""
    plain = _write(
        tmp_path,
        "Plain.java",
        "public class Plain {\n    int add(int a, int b) { return a + b; }\n}\n",
    )
    with_static_import = _write(
        tmp_path,
        "WithImport.java",
        "import static org.junit.Assert.assertEquals;\n\n"
        "public class WithImport {\n"
        "    void check() { assertEquals(1, 1); }\n"
        "}\n",
    )

    plain_score = assess_file(plain, "production", False).testability
    import_score = assess_file(with_static_import, "production", False).testability

    assert import_score.value == plain_score.value


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
    body = 'package main\n\nimport (\n    "fmt"\n    "os"\n    "strings"\n)\n\nfunc main() {}\n'
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


def test_directory_scan_includes_all_supported_suffixes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Directory assessment must pick up every suffix detect_language supports,
    including .go, .tsx, .jsx, .mjs, .cjs (previously omitted)."""
    for name in ("a.go", "b.tsx", "c.jsx", "d.mjs", "e.cjs", "f.py"):
        _write(tmp_path, name, "x = 1\n")
    monkeypatch.chdir(tmp_path)
    found = {p.name for p in get_files_to_assess(".", False)}
    assert {"a.go", "b.tsx", "c.jsx", "d.mjs", "e.cjs", "f.py"} <= found


def test_parse_changed_files_retains_old_and_new_paths() -> None:
    raw = (
        b"M\0same.py\0"
        b"A\0new.py\0"
        b"D\0gone.py\0"
        b"R095\0old.py\0renamed.py\0"
    )

    assert _parse_changed_files(raw) == [
        ChangedFile("M", Path("same.py"), Path("same.py")),
        ChangedFile("A", None, Path("new.py")),
        ChangedFile("D", Path("gone.py"), None),
        ChangedFile("R095", Path("old.py"), Path("renamed.py")),
    ]


@pytest.mark.parametrize("raw", [b"M\0", b"R095\0old.py\0"])
def test_parse_changed_files_rejects_truncated_records(raw: bytes) -> None:
    with pytest.raises(ValueError, match="Malformed git"):
        _parse_changed_files(raw)


def test_changed_only_uses_base_for_clean_committed_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _run_git(tmp_path, "init")
    _run_git(tmp_path, "checkout", "-b", "main")
    _run_git(tmp_path, "config", "user.email", "test@example.com")
    _run_git(tmp_path, "config", "user.name", "Test")
    _write(tmp_path, "base.py", "def base():\n    return 1\n")
    _run_git(tmp_path, "add", "base.py")
    _run_git(tmp_path, "commit", "-m", "base")
    _run_git(tmp_path, "checkout", "-b", "feature")
    changed = _write(tmp_path, "changed.py", "def changed():\n    return 2\n")
    _run_git(tmp_path, "add", "changed.py")
    _run_git(tmp_path, "commit", "-m", "feature")
    monkeypatch.chdir(tmp_path)

    assert get_files_to_assess(".", True, "main") == [Path("changed.py")]
    assert changed.exists()


def test_changed_only_rejects_option_like_base() -> None:
    """CWE-88: an option-like --base is rejected before git runs."""
    with pytest.raises(ValueError):
        get_files_to_assess(".", True, "--output=/tmp/should_not_be_written")


@pytest.mark.parametrize("abbreviation", ["--bas=main", "--gate-m=regression"])
def test_cli_rejects_abbreviated_options(abbreviation: str) -> None:
    with pytest.raises(SystemExit):
        parse_args(["--target", ".", abbreviation])


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "-0.1"])
def test_cli_rejects_invalid_regression_tolerance(value: str) -> None:
    with pytest.raises(SystemExit):
        parse_args(["--target", ".", "--regression-tolerance", value])


def test_target_rejects_a_sibling_prefix_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "repo"
    sibling = tmp_path / "repo-other"
    workspace.mkdir()
    sibling.mkdir()
    monkeypatch.chdir(workspace)

    with pytest.raises(ValueError, match="escapes the workspace"):
        _resolve_target_path(str(sibling))


def test_candidate_rejects_a_symlink_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text(_FOCUSED, encoding="utf-8")
    (workspace / "escaped.py").symlink_to(outside)
    monkeypatch.chdir(workspace)

    with pytest.raises(ValueError, match="escapes the workspace"):
        get_files_to_assess(".", False)


def test_changed_only_passes_end_of_options_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CWE-88: the git invocation pins --end-of-options before the range."""
    captured: dict[str, list[str]] = {}

    class _Result:
        stdout = b""

    def _fake_run(cmd: list[str], **_kwargs: Any) -> _Result:
        captured["cmd"] = cmd
        return _Result()

    monkeypatch.setattr(subprocess, "run", _fake_run)
    get_files_to_assess(".", True, "origin/main")
    cmd = captured["cmd"]
    assert ["--name-status", "-M", "-z"] == cmd[2:5]
    assert "--end-of-options" in cmd
    assert cmd.index("--end-of-options") < cmd.index("origin/main...HEAD")


def test_generated_matcher_shim_is_classified_as_generated(tmp_path: Path) -> None:
    generated = _write(
        tmp_path,
        "invoke_guard__Bash_123.py",
        "# AUTO-GENERATED MATCHER SHIM (REQ-003-007)\n# END MATCHER SHIM\n",
    )

    assert classify_file_category(generated) == "generated"


def test_generated_assessment_is_unscored(tmp_path: Path) -> None:
    generated = _write(
        tmp_path,
        "invoke_guard__Bash_123.py",
        "# AUTO-GENERATED MATCHER SHIM (REQ-003-007)\ndef generated():\n    return 1\n",
    )

    assessment = assess_file(generated, "production", False)

    assert assessment.category == "generated"
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


def test_template_qualityrc_uses_coupling_min(tmp_path: Path) -> None:
    """The shipped template config must use coupling.min (matching
    check_thresholds), not the legacy coupling.max that disabled the gate."""
    import json

    template = Path(__file__).parent.parent / "templates" / ".qualityrc.json"
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
        "package main\n\nfunc main() {\n    var (\n        local int\n    )\n    _ = local\n}\n",
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


def test_marker_below_header_window_is_authored(tmp_path: Path) -> None:
    # A generated marker string that appears only deep in the body (past the
    # header window) must NOT reclassify an authored file as generated.
    body = "\n".join(f"# line {n}" for n in range(30))
    body += '\n_MARKERS = ("DO NOT EDIT BY HAND - regenerated",)\n'
    authored = _write(tmp_path, "generator_like.py", body)

    assert classify_file_category(authored) == "authored"


def test_marker_in_header_window_is_generated(tmp_path: Path) -> None:
    generated = _write(
        tmp_path,
        "shim.py",
        "#!/usr/bin/env python3\n# GENERATED -- DO NOT EDIT\n\ndef x():\n    return 1\n",
    )

    assert classify_file_category(generated) == "generated"


def test_github_instructions_path_is_generated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # .github/instructions/*.instructions.md are generated mirrors of
    # .claude/rules/* and carry no in-file markers; classify by path.
    # _GENERATED_PATH_SEGMENTS are repo-root-anchored, so the path must be
    # rooted at CWD the way a real diff-supplied path is.
    path = tmp_path / ".github" / "instructions" / "universal.instructions.md"
    path.parent.mkdir(parents=True)
    path.write_text("# Universal Rules\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert classify_file_category(path) == "generated"
    assert (
        classify_file_category(Path(".github") / "instructions" / "universal.instructions.md")
        == "generated"
    )


def test_classify_ignores_checkout_path_segments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Regression: a clone whose checkout directory itself contains a generated
    # segment (e.g. .../src/copilot-cli/...) must not misclassify authored files
    # as generated. classify uses CWD-relative parts, so the checkout prefix is
    # stripped before the segment scan.
    checkout = tmp_path / "src" / "copilot-cli" / "clone"
    pkg = checkout / "pkg"
    pkg.mkdir(parents=True)
    authored = pkg / "module.py"
    authored.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.chdir(checkout)

    # Absolute path under the checkout: relative parts are pkg/module.py.
    assert classify_file_category(authored) == "authored"
    # A genuinely repo-relative generated path is still caught.
    assert classify_file_category(Path("src") / "copilot-cli" / "skill.py") == "generated"
    # A non-UTF-8 file read with content=None must not raise UnicodeDecodeError;
    # unreadable content classifies as authored (no markers detectable).
    binary = tmp_path / "blob.py"
    binary.write_bytes(b"\xff\xfe\x00\x01 not valid utf-8 \x80\x81")

    assert classify_file_category(binary) == "authored"


def test_assess_non_utf8_file_does_not_crash(tmp_path: Path) -> None:
    binary = tmp_path / "blob.py"
    binary.write_bytes(b"\xff\xfe\x00\x01 not valid utf-8 \x80\x81")

    assessment = assess_file(binary, "production", False)

    assert assessment.category in {"authored", "test"}


# --------------------------------------------------------------------------- #
# Regression gate mode (issue #4364)
#
# --changed-only used to select changed files and then apply absolute
# thresholds, so a comment-only edit to a legacy file failed the gate on debt
# it did not introduce. Exit 10 was documented and unreachable.
# --------------------------------------------------------------------------- #

_FOCUSED = "def alpha():\n    return 1\n"
# 21 definitions: enough to score cohesion well below the default minimum of 7.
_SPRAWLING = _FOCUSED + "".join(f"def f{i}():\n    return {i}\n" for i in range(20))


def _init_repo(tmp_path: Path) -> None:
    _run_git(tmp_path, "init")
    _run_git(tmp_path, "checkout", "-b", "main")
    _run_git(tmp_path, "config", "user.email", "test@example.com")
    _run_git(tmp_path, "config", "user.name", "Test")


def _commit(tmp_path: Path, name: str, body: str, message: str) -> Path:
    path = _write(tmp_path, name, body)
    _run_git(tmp_path, "add", name)
    _run_git(tmp_path, "commit", "-m", message)
    return path


def _repo_with_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    base_body: str,
    head_body: str,
    name: str = "legacy.py",
) -> None:
    _init_repo(tmp_path)
    _commit(tmp_path, name, base_body, "base")
    _run_git(tmp_path, "checkout", "-b", "feature")
    _commit(tmp_path, name, head_body, "head")
    monkeypatch.chdir(tmp_path)


def _regression_argv() -> list[str]:
    return ["--target", ".", "--changed-only", "--base", "main", "--format", "json"]


def test_regression_mode_passes_a_comment_only_change_to_a_legacy_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reported repro: legacy debt plus one comment must not fail the gate."""
    _repo_with_change(tmp_path, monkeypatch, _SPRAWLING, "# added note\n" + _SPRAWLING)

    assert main(_regression_argv()) == 0


def test_absolute_mode_still_fails_the_same_legacy_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Control for the test above: the two modes disagree on the same tree."""
    _repo_with_change(tmp_path, monkeypatch, _SPRAWLING, "# added note\n" + _SPRAWLING)

    assert main([*_regression_argv(), "--gate-mode", "absolute"]) == 11


def test_regression_mode_passes_an_improved_legacy_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repo_with_change(tmp_path, monkeypatch, _SPRAWLING, _FOCUSED)

    assert main(_regression_argv()) == 0


def test_regression_mode_passes_a_deletion_only_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _init_repo(tmp_path)
    _commit(tmp_path, "deleted.py", _FOCUSED, "base")
    _run_git(tmp_path, "checkout", "-b", "feature")
    _run_git(tmp_path, "rm", "deleted.py")
    _run_git(tmp_path, "commit", "-m", "delete")
    monkeypatch.chdir(tmp_path)

    assert main(_regression_argv()) == 0
    assert json.loads(capsys.readouterr().out)["summary"]["file_count"] == 0


def test_regression_mode_fails_a_degraded_file_and_names_the_quality(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _repo_with_change(tmp_path, monkeypatch, _FOCUSED, _SPRAWLING)

    assert main(_regression_argv()) == 10
    assert "cohesion regressed" in capsys.readouterr().err


def test_regression_mode_gates_a_new_file_absolutely(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file absent at base has no delta, so absolute thresholds decide."""
    _init_repo(tmp_path)
    _commit(tmp_path, "seed.py", _FOCUSED, "base")
    _run_git(tmp_path, "checkout", "-b", "feature")
    _commit(tmp_path, "newly_added.py", _SPRAWLING, "add file")
    monkeypatch.chdir(tmp_path)

    assert main(_regression_argv()) == 11


def test_regression_mode_passes_a_new_file_that_meets_thresholds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(tmp_path)
    _commit(tmp_path, "seed.py", _FOCUSED, "base")
    _run_git(tmp_path, "checkout", "-b", "feature")
    _commit(tmp_path, "newly_added.py", _FOCUSED, "add file")
    monkeypatch.chdir(tmp_path)

    assert main(_regression_argv()) == 0


def test_regression_mode_reads_a_renamed_files_old_base_blob(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(tmp_path)
    _commit(tmp_path, "legacy.py", _FOCUSED, "base")
    _run_git(tmp_path, "checkout", "-b", "feature")
    _run_git(tmp_path, "mv", "legacy.py", "renamed.py")
    _run_git(tmp_path, "commit", "-m", "rename")
    monkeypatch.chdir(tmp_path)

    changes = get_changed_files("main")
    files = get_files_to_assess(".", True, "main", changes)
    assessment = assess_file(files[0], "production", False)
    comparisons, new_files = build_comparisons(
        [assessment],
        "main",
        changed_files=changes,
    )

    assert files == [Path("renamed.py")]
    assert new_files == []
    assert comparisons[0].is_new_file is False
    assert comparisons[0].base_file_path == "legacy.py"
    assert comparisons[0].change_status.startswith("R")
    payload = json.loads(
        generate_json_report([assessment], comparisons, "regression")
    )
    assert payload["comparisons"][0]["base_file_path"] == "legacy.py"
    assert payload["comparisons"][0]["file_path"] == "renamed.py"


def test_unscored_r095_rename_is_gated_absolutely(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(tmp_path)
    _commit(tmp_path, "legacy.txt", _SPRAWLING, "base")
    _run_git(tmp_path, "checkout", "-b", "feature")
    _run_git(tmp_path, "mv", "legacy.txt", "renamed.py")
    with (tmp_path / "renamed.py").open("a", encoding="utf-8") as stream:
        stream.write("#xxxxxxxxxxxxxxxxxxxx\n")
    _run_git(tmp_path, "add", "renamed.py")
    _run_git(tmp_path, "commit", "-m", "rename to scored code")
    monkeypatch.chdir(tmp_path)

    changes = get_changed_files("main")
    assert changes == [
        ChangedFile(
            "R095",
            Path("legacy.txt"),
            Path("renamed.py"),
        )
    ]
    assessment = assess_file(Path("renamed.py"), "production", False)
    comparisons, absolute_assessments = build_comparisons(
        [assessment],
        "main",
        changed_files=changes,
    )

    assert comparisons[0].is_new_file is False
    assert comparisons[0].absolute_gate_reason == "base_unscored"
    assert absolute_assessments == [assessment]
    assert main(_regression_argv()) == 11


def test_json_report_carries_base_head_and_delta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _repo_with_change(tmp_path, monkeypatch, _FOCUSED, _SPRAWLING)

    main(_regression_argv())

    payload = json.loads(capsys.readouterr().out)
    assert payload["gate_mode"] == "regression"
    cohesion = next(
        d
        for c in payload["comparisons"]
        for d in c["deltas"]
        if d["quality"] == "cohesion"
    )
    assert cohesion["base"] is not None
    assert cohesion["head"] is not None
    assert cohesion["delta"] < 0
    assert cohesion["status"] == "compared"


def test_regression_mode_rejects_a_missing_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    rc = main(["--target", ".", "--changed-only", "--gate-mode", "regression"])

    assert rc == 1


def test_regression_mode_rejects_a_missing_changed_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    rc = main(["--target", ".", "--base", "main", "--gate-mode", "regression"])

    assert rc == 1


def test_unresolvable_base_is_an_error_not_a_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A typo in --base must not read as 'every file is new' and pass."""
    _repo_with_change(tmp_path, monkeypatch, _FOCUSED, _SPRAWLING)

    with pytest.raises(ValueError):
        resolve_revision("no-such-ref")


def test_no_common_ancestor_uses_the_resolved_base() -> None:
    result = subprocess.CompletedProcess(
        args=[],
        returncode=1,
        stdout="",
        stderr="",
    )
    with patch.object(_mod, "resolve_revision", return_value="abc123"), patch(
        "subprocess.run",
        return_value=result,
    ):
        assert _mod.resolve_comparison_base("main") == "abc123"


def test_regression_mode_handles_unrelated_histories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _init_repo(tmp_path)
    _commit(tmp_path, "base.py", _FOCUSED, "base")
    _run_git(tmp_path, "checkout", "--orphan", "feature")
    _run_git(tmp_path, "rm", "-f", "base.py")
    _commit(tmp_path, "new.py", _FOCUSED, "unrelated head")
    monkeypatch.chdir(tmp_path)

    assert main(_regression_argv()) == 0


@pytest.mark.parametrize(
    "result",
    [
        subprocess.CompletedProcess(
            args=[],
            returncode=2,
            stdout="",
            stderr="fatal: repository unavailable",
        ),
        subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="",
            stderr="",
        ),
    ],
)
def test_merge_base_operational_failures_do_not_fall_back(
    result: subprocess.CompletedProcess[str],
) -> None:
    with patch.object(_mod, "resolve_revision", return_value="abc123"), patch(
        "subprocess.run",
        return_value=result,
    ):
        with pytest.raises(RuntimeError, match="git merge-base"):
            _mod.resolve_comparison_base("main")


def test_regression_mode_returns_1_when_base_blob_read_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _repo_with_change(tmp_path, monkeypatch, _FOCUSED, _SPRAWLING)

    with patch.object(
        _mod,
        "get_file_at_revision",
        side_effect=RuntimeError("blob read failed"),
    ):
        assert main(_regression_argv()) == 1
    assert "blob read failed" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("gate_mode", "changed_only", "base", "expected"),
    [
        ("auto", True, "main", "regression"),
        ("auto", True, None, "absolute"),
        ("auto", False, "main", "absolute"),
        ("auto", False, None, "absolute"),
        ("absolute", True, "main", "absolute"),
        ("regression", True, "main", "regression"),
    ],
)
def test_resolve_gate_mode(
    gate_mode: str, changed_only: bool, base: str | None, expected: str
) -> None:
    assert resolve_gate_mode(gate_mode, changed_only, base) == expected


def test_resolve_revision_rejects_option_like_base() -> None:
    """CWE-88: an option-like --base is rejected before git runs."""
    with pytest.raises(ValueError):
        resolve_revision("--output=/tmp/should_not_be_written")


def test_get_file_at_revision_rejects_option_like_revision() -> None:
    with pytest.raises(ValueError):
        get_file_at_revision(Path("a.py"), "--upload-pack=touch")


def test_get_file_at_revision_returns_none_for_an_absent_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(tmp_path)
    _commit(tmp_path, "seed.py", _FOCUSED, "base")
    monkeypatch.chdir(tmp_path)

    assert get_file_at_revision(Path("seed.py"), "main") == _FOCUSED.encode("utf-8")
    assert get_file_at_revision(Path("never_existed.py"), "main") is None


def test_get_file_at_revision_raises_when_tree_lookup_fails() -> None:
    failure = subprocess.CompletedProcess(
        args=[],
        returncode=128,
        stdout=b"",
        stderr=b"tree failure",
    )
    with patch("subprocess.run", return_value=failure):
        with pytest.raises(RuntimeError, match="git ls-tree failed"):
            get_file_at_revision(Path("seed.py"), "main")


def test_get_file_at_revision_raises_when_blob_read_fails() -> None:
    present = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=b"entry",
        stderr=b"",
    )
    failure = subprocess.CompletedProcess(
        args=[],
        returncode=128,
        stdout=b"",
        stderr=b"show failure",
    )
    with patch("subprocess.run", side_effect=[present, failure]):
        with pytest.raises(RuntimeError, match="git show failed"):
            get_file_at_revision(Path("seed.py"), "main")


def test_build_comparisons_separates_new_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _init_repo(tmp_path)
    _commit(tmp_path, "seed.py", _FOCUSED, "base")
    monkeypatch.chdir(tmp_path)
    existing = assess_file(Path("seed.py"), "production", False)
    fresh = assess_content(Path("brand_new.py"), _FOCUSED)

    comparisons, new_files = build_comparisons([existing, fresh], "main")

    assert [c.is_new_file for c in comparisons] == [False, True]
    assert [a.file_path for a in new_files] == ["brand_new.py"]


# --------------------------------------------------------------------------- #
# compare_assessments: per-quality independence
# --------------------------------------------------------------------------- #


def _delta(comparison: Any, quality: str) -> Any:
    return next(d for d in comparison.deltas if d.quality == quality)


def test_unscored_qualities_are_never_compared() -> None:
    """A quality unscored in both revisions produces no delta and no verdict."""
    base = assess_content(Path("a.rb"), "puts 1\n")
    head = assess_content(Path("a.rb"), "puts 2\n")

    comparison = compare_assessments(base, head)

    assert _delta(comparison, "testability").status == "not_scored"
    assert _delta(comparison, "testability").delta is None
    assert comparison.regressions == []


def test_newly_scored_quality_reports_no_fabricated_delta() -> None:
    unscored = assess_content(Path("a.py"), "x = 1\n")
    unscored.cohesion.confidence = 0.0
    head = assess_content(Path("a.py"), "x = 1\n")

    comparison = compare_assessments(unscored, head)

    delta = _delta(comparison, "cohesion")
    assert delta.status == "newly_scored"
    assert delta.base is None
    assert delta.delta is None
    assert comparison.regressions == []


def test_scored_to_unscored_is_evidence_loss() -> None:
    base = assess_content(Path("a.py"), _FOCUSED)
    head = assess_content(Path("a.py"), _FOCUSED)
    head.cohesion.confidence = 0.0

    comparison = compare_assessments(base, head)

    assert comparison.evidence_loss == ["cohesion"]
    assert check_regression([comparison], [], _default_config(), "production") == 10


def test_evidence_loss_is_forgiven_for_a_generated_artifact() -> None:
    base = assess_content(Path("a.py"), _FOCUSED)
    head = assess_content(Path("a.py"), _FOCUSED)
    head.category = "generated"
    head.cohesion.confidence = 0.0

    comparison = compare_assessments(base, head)

    assert comparison.evidence_loss == []
    assert check_regression([comparison], [], _default_config(), "production") == 0


def test_tolerance_absorbs_a_small_drop() -> None:
    base = assess_content(Path("a.py"), _FOCUSED)
    head = assess_content(Path("a.py"), _FOCUSED)
    head.cohesion.value = base.cohesion.value - 0.2

    assert compare_assessments(base, head, tolerance=0.0).regressions == ["cohesion"]
    assert compare_assessments(base, head, tolerance=0.5).regressions == []


def test_an_improvement_is_never_a_regression() -> None:
    base = assess_content(Path("a.py"), _SPRAWLING)
    head = assess_content(Path("a.py"), _FOCUSED)

    comparison = compare_assessments(base, head)

    assert comparison.regressions == []
    assert _delta(comparison, "cohesion").delta > 0


# --------------------------------------------------------------------------- #
# Inputs a real pull request produces and the fixture above does not: a base
# branch that moved after the fork, a changed file with no language, a base
# revision that is not UTF-8, and ordinary additive work (issue #4364).
# --------------------------------------------------------------------------- #


def test_a_base_that_moved_after_the_fork_is_not_charged_to_the_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Selection uses the merge base, so scoring must use it too.

    Main improves the file after the fork. Scored against main's tip the branch
    looks like it sprawled a focused file; scored against the fork point it
    added one comment, which is what it actually did.
    """
    _init_repo(tmp_path)
    _commit(tmp_path, "legacy.py", _SPRAWLING, "base")
    _run_git(tmp_path, "checkout", "-b", "feature")
    _commit(tmp_path, "legacy.py", "# added note\n" + _SPRAWLING, "comment only")
    _run_git(tmp_path, "checkout", "main")
    _commit(tmp_path, "legacy.py", _FOCUSED, "main focuses the file")
    _run_git(tmp_path, "checkout", "feature")
    monkeypatch.chdir(tmp_path)

    assert main(_regression_argv()) == 0


def test_a_changed_binary_file_does_not_fail_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reported repro plus one PNG: 26 binary files are tracked in this repo."""
    _init_repo(tmp_path)
    _commit(tmp_path, "legacy.py", _SPRAWLING, "base")
    (tmp_path / "img.png").write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(range(256)))
    _run_git(tmp_path, "add", "img.png")
    _run_git(tmp_path, "commit", "-m", "add image")
    _run_git(tmp_path, "checkout", "-b", "feature")
    _commit(tmp_path, "legacy.py", "# added note\n" + _SPRAWLING, "head")
    (tmp_path / "img.png").write_bytes(b"\x89PNG\r\n\x1a\nchanged")
    _run_git(tmp_path, "add", "img.png")
    _run_git(tmp_path, "commit", "-m", "change image")
    monkeypatch.chdir(tmp_path)

    assert main(_regression_argv()) == 0


def test_a_source_file_that_is_not_utf8_at_base_is_gated_absolutely(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unreadable base has no comparison evidence, so head thresholds apply."""
    _init_repo(tmp_path)
    (tmp_path / "legacy.py").write_bytes(b"# caf\xe9 latin-1\n" + _SPRAWLING.encode("utf-8"))
    _run_git(tmp_path, "add", "legacy.py")
    _run_git(tmp_path, "commit", "-m", "base")
    _run_git(tmp_path, "checkout", "-b", "feature")
    _commit(tmp_path, "legacy.py", "# added note\n" + _SPRAWLING, "head")
    monkeypatch.chdir(tmp_path)

    assert main(_regression_argv()) == 11


def test_a_new_supported_source_that_is_not_utf8_fails_the_absolute_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _init_repo(tmp_path)
    _commit(tmp_path, "seed.py", _FOCUSED, "base")
    _run_git(tmp_path, "checkout", "-b", "feature")
    (tmp_path / "new.py").write_bytes(b"# caf\xe9 latin-1\n")
    _run_git(tmp_path, "add", "new.py")
    _run_git(tmp_path, "commit", "-m", "add unreadable source")
    monkeypatch.chdir(tmp_path)

    assert main(_regression_argv()) == 11


def test_adding_one_small_function_is_not_a_regression(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ordinary additive work moves a size-derived score by tenths."""
    healthy = "".join(f'def f{i}(a, b):\n    """Doc."""\n    return a + b\n\n' for i in range(5))
    _repo_with_change(
        tmp_path, monkeypatch, healthy, healthy + 'def g(a):\n    """Doc."""\n    return a\n'
    )

    assert main(_regression_argv()) == 0


def test_the_default_tolerance_still_fails_a_real_degradation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Control for the test above: half a point separates noise from signal."""
    _repo_with_change(tmp_path, monkeypatch, _FOCUSED, _SPRAWLING)

    assert main(_regression_argv()) == 10


def test_get_file_at_revision_returns_bytes_it_did_not_decode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Locale must not decide how the base revision is read."""
    _init_repo(tmp_path)
    (tmp_path / "a.py").write_bytes(b"S = 'caf\xc3\xa9'\n")
    _run_git(tmp_path, "add", "a.py")
    _run_git(tmp_path, "commit", "-m", "base")
    monkeypatch.chdir(tmp_path)

    raw = get_file_at_revision(Path("a.py"), resolve_revision("HEAD"))

    assert raw == b"S = 'caf\xc3\xa9'\n"
