"""Tests for scripts/validation/instruction_budget.py (issue #3419).

The validator measures the always-on instruction budget per language: the summed
bytes of ``.github/instructions/*.instructions.md`` files whose ``applyTo`` scopes
them to every file of a language (``**``, ``**/*``, or ``**/*.<ext>``). It gates growth via a
non-regression byte ceiling.

Tests use crafted temporary instruction trees so results are independent of the
live repo state, plus one anchor test against the real repo to guard the
measurement methodology from silent regressions.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.validation.instruction_budget as ib


def _write_rule(root: Path, name: str, apply_to: str, body: str = "body\n") -> int:
    """Create an instruction file and return its UTF-8 byte length."""
    inst_dir = root / ib.INSTRUCTIONS_SUBDIR
    inst_dir.mkdir(parents=True, exist_ok=True)
    content = f"---\napplyTo: {apply_to}\n---\n\n# {name}\n\n{body}"
    path = inst_dir / f"{name}.instructions.md"
    path.write_text(content, encoding="utf-8")
    return len(content.encode("utf-8"))


# --------------------------------------------------------------------------
# parse_applyto
# --------------------------------------------------------------------------


def test_parse_applyto_bare_string() -> None:
    text = "---\napplyTo: '**'\n---\n\nbody\n"
    assert ib.parse_applyto(text) == {"**"}


def test_parse_applyto_comma_separated_unquoted() -> None:
    text = "---\napplyTo: tests/**,**/*.py,docs/x.md\n---\nbody\n"
    assert ib.parse_applyto(text) == {"tests/**", "**/*.py", "docs/x.md"}


def test_parse_applyto_quoted_comma_list() -> None:
    text = "---\napplyTo: '**/*.py,**/*.cs'\n---\nbody\n"
    assert ib.parse_applyto(text) == {"**/*.py", "**/*.cs"}


def test_parse_applyto_flow_list_form() -> None:
    text = "---\napplyTo: ['**', '**/*.ts']\n---\nbody\n"
    assert ib.parse_applyto(text) == {"**", "**/*.ts"}


def test_parse_applyto_block_list_form() -> None:
    # A YAML block-style list must be read as list entries, not missed by a
    # single-line regex that only sees the empty value after 'applyTo:'.
    text = "---\napplyTo:\n  - '**/*.py'\n  - 'tests/**'\n---\nbody\n"
    assert ib.parse_applyto(text) == {"**/*.py", "tests/**"}


def test_parse_applyto_ignores_inline_comment() -> None:
    # A trailing '# comment' belongs to YAML, not to the glob. A line regex
    # would fold it into the pattern and never match a universal form.
    text = "---\napplyTo: '**/*.py' # only python\n---\nbody\n"
    assert ib.parse_applyto(text) == {"**/*.py"}
    assert ib.is_language_universal(ib.parse_applyto(text), ".py") is True


def test_parse_applyto_unsupported_scalar_raises() -> None:
    # A present-but-non-string/list applyTo (here an int) is a config error,
    # not a file to silently drop from the always-on budget.
    text = "---\napplyTo: 42\n---\nbody\n"
    with pytest.raises(ib.UnsupportedApplyToError):
        ib.parse_applyto(text)


def test_parse_applyto_invalid_yaml_raises() -> None:
    # An unquoted glob starting with '*' is a YAML alias indicator and fails to
    # parse. Failing closed (config error) beats returning an empty set, which
    # would let a malformed rule contribute zero bytes and dodge the ceiling.
    text = "---\napplyTo: **/*.py\n---\nbody\n"
    with pytest.raises(ib.UnsupportedApplyToError):
        ib.parse_applyto(text)


def test_parse_applyto_duplicate_key_raises() -> None:
    # PyYAML would keep the last 'applyTo', letting a trailing directory-scoped
    # value mask a universal one. Reject duplicate keys so the mask cannot hide
    # always-on bytes from the gate.
    text = "---\napplyTo: '**/*.py'\napplyTo: tests/**\n---\nbody\n"
    with pytest.raises(ib.UnsupportedApplyToError):
        ib.parse_applyto(text)


def test_parse_applyto_unhashable_key_raises() -> None:
    # A YAML complex key ('? [a, b]') builds an unhashable dict key. The strict
    # loader must surface that as a config error (exit 2), not let a raw
    # 'key in mapping' membership test raise an uncaught TypeError (exit 1).
    text = "---\napplyTo: '**/*.py'\n? [a, b]\n: c\n---\nbody\n"
    with pytest.raises(ib.UnsupportedApplyToError):
        ib.parse_applyto(text)


def test_parse_applyto_keeps_brace_group_intact() -> None:
    # A leading '**' forces quoting in YAML, so the realistic brace form is
    # quoted; an unquoted '**/*.{...}' is invalid YAML the harness would reject.
    # parse_applyto no longer textually expands braces: the brace group is kept
    # whole and compiled inline (VS Code semantics) by is_language_universal.
    text = "---\napplyTo: '**/*.{py,pyi},tests/**'\n---\nbody\n"
    assert ib.parse_applyto(text) == {"**/*.{py,pyi}", "tests/**"}


def test_parse_applyto_brace_form_is_language_universal() -> None:
    # A future rule scoped with a brace group must still be caught by the gate.
    patterns = ib.parse_applyto("---\napplyTo: '**/*.{py,pyi}'\n---\nbody\n")
    assert ib.is_language_universal(patterns, ".py") is True


def test_brace_option_with_path_syntax_is_language_universal() -> None:
    # ``{**/*}`` holds path syntax the old textual splitter could not expand
    # faithfully; inline compilation makes each choice a full glob, so the rule
    # is correctly seen as universal instead of being under-counted to 0 bytes.
    patterns = ib.parse_applyto("---\napplyTo: '{**/*}'\n---\nbody\n")
    assert ib.is_language_universal(patterns, ".py") is True


def test_nested_brace_group_is_language_universal() -> None:
    # A nested alternative ``{py,{pyi,pyc}}`` recurses through the compiler; the
    # ``py`` branch matches every ``.py`` path, so the rule is universal.
    patterns = ib.parse_applyto("---\napplyTo: '**/*.{py,{pyi,pyc}}'\n---\nbody\n")
    assert ib.is_language_universal(patterns, ".py") is True


def test_empty_brace_group_is_language_universal() -> None:
    # A future rule spelled with an empty brace group must still be caught.
    # VS Code compiles ``{}`` as an empty substitution, so ``p{}y`` is ``py``.
    patterns = ib.parse_applyto("---\napplyTo: '**/*.p{}y'\n---\nbody\n")
    assert ib.is_language_universal(patterns, ".py") is True


def test_trailing_empty_brace_option_is_not_language_universal() -> None:
    # Faithful to VS Code: ``splitGlobAware('x,', ',')`` DROPS the trailing empty,
    # so ``**/*.py{x,}`` compiles to ``(?:x)`` and matches only ``.pyx`` -- it is
    # genuinely NOT universal for ``.py``. The prior textual splitter kept the
    # empty option and over-counted this as universal. Reporting it non-universal
    # is not an under-count: no ``.py`` path matches ``**/*.pyx``.
    patterns = ib.parse_applyto("---\napplyTo: '**/*.py{x,}'\n---\nbody\n")
    assert ib.is_language_universal(patterns, ".py") is False


def test_glob_to_regex_char_class_fails_closed() -> None:
    # ``**/*.[p]y`` equals ``**/*.py`` under the harness (universal), but the
    # compiler does not model brackets. Treating ``[`` as a literal would
    # under-count (the one unsafe direction), so it fails closed instead.
    with pytest.raises(ib.UnsupportedApplyToError):
        ib._glob_to_regex("**/*.[p]y")


def test_char_class_applyto_fails_closed() -> None:
    # End to end: a rule whose ``applyTo`` uses a character class raises rather
    # than risk silently dodging the always-on budget ceiling.
    patterns = ib.parse_applyto("---\napplyTo: '**/*.[p]y'\n---\nbody\n")
    with pytest.raises(ib.UnsupportedApplyToError):
        ib.is_language_universal(patterns, ".py")


def test_all_files_form_short_circuits_before_bracket_compile() -> None:
    # Determinism guard (Finding 3): when a scope list mixes an all-files wildcard
    # with a bracket pattern, universality must be decided by the all-files form
    # BEFORE any pattern is compiled. Iterating the set and compiling per-pattern
    # made the result depend on set order (PYTHONHASHSEED): sometimes True via the
    # wildcard, sometimes UnsupportedApplyToError via the bracket. The two-pass
    # check compiles no regex once an all-files form is present, so the union is
    # deterministically universal regardless of iteration order.
    union = {"**/*", "**/*.[p]y"}
    for _ in range(50):
        assert ib.is_language_universal(set(union), ".py") is True


def test_parse_applyto_missing_frontmatter_returns_empty() -> None:
    assert ib.parse_applyto("# just a heading\n\nno frontmatter\n") == set()


def test_parse_applyto_missing_key_returns_empty() -> None:
    text = "---\ndescription: no applyTo here\n---\nbody\n"
    assert ib.parse_applyto(text) == set()


# --------------------------------------------------------------------------
# is_language_universal
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("patterns", "ext", "expected"),
    [
        ({"**"}, ".py", True),
        ({"**/*"}, ".py", True),
        ({"**/*.py"}, ".py", True),
        ({"**/**/*.py"}, ".py", True),
        ({"**/**/*"}, ".py", True),
        ({"**/**"}, ".py", True),
        # Relative '*.py' -> harness prepends '**/' -> '**/*.py' -> universal.
        ({"*.py"}, ".py", True),
        # Bare '*' is an all-files wildcard in the harness -> universal.
        ({"*"}, ".py", True),
        # A scoped relative glob prepends to '**/src/*.py' and stays situational.
        ({"src/*.py"}, ".py", False),
        ({"**/*.py", "**/*.pyi"}, ".py", True),
        ({"**/*.cs"}, ".py", False),
        ({"tests/**"}, ".py", False),
        ({"scripts/**", "build/**"}, ".py", False),
        ({"**/*.py", "**/*.cs"}, ".cs", True),
        (set(), ".py", False),
    ],
)
def test_is_language_universal(patterns: set[str], ext: str, expected: bool) -> None:
    assert ib.is_language_universal(patterns, ext) is expected


def test_is_language_universal_is_precise_not_endswith() -> None:
    # A *scoped* glob that merely ends with '*.py' is NOT language-universal:
    # the harness prepends '**/' to a relative pattern, so 'src/foo*.py' becomes
    # '**/src/foo*.py' (only under a src/ dir) and 'foo*.py' becomes
    # '**/foo*.py' (only basenames starting 'foo'). Neither matches every .py,
    # so neither is an always-on baseline.
    assert ib.is_language_universal({"src/foo*.py"}, ".py") is False
    assert ib.is_language_universal({"src/*.py"}, ".py") is False
    assert ib.is_language_universal({"foo*.py"}, ".py") is False
    # But a bare relative '*.py' prepends to '**/*.py' and IS universal.
    assert ib.is_language_universal({"*.py"}, ".py") is True


def test_is_language_universal_normalizes_equivalent_globs() -> None:
    # Padding an applyTo with equivalent '**/' segments, or spelling the file
    # segment with a doubled star, matches the same files as the minimal form,
    # so it must not dodge the always-on budget.
    assert ib.is_language_universal({"**/**/*.py"}, ".py") is True
    assert ib.is_language_universal({"**/**/**/*.py"}, ".py") is True
    # '**/**.py': segment '**.py' is a filename-segment match (minimatch folds
    # the doubled star to '*'), so the whole glob equals '**/*.py' == universal.
    assert ib.is_language_universal({"**/**.py"}, ".py") is True
    assert ib.is_language_universal({"**/**/*.cs"}, ".py") is False
    # '**.py' has no leading globstar, so the harness prepends '**/' ->
    # '**/**.py' -> folds to '**/*.py' -> universal (same as bare '*.py').
    assert ib.is_language_universal({"**.py"}, ".py") is True
    # A bare '*' is an all-files wildcard in VS Code's matcher (it is special-
    # cased alongside '**' and '**/*'), so a rule scoped '*' loads always-on.
    # Source: computeAutomaticInstructions.ts#L294-L310 (pinned in the module).
    assert ib.is_language_universal({"*"}, ".py") is True
    # The '**/' prepend is what promotes a relative language glob to universal;
    # every other equivalence is decided by matching, not string rewriting, so
    # the effective glob keeps its shape and '**.py' stays '**/**.py'.
    assert ib._vscode_effective_glob("*.py") == "**/*.py"
    assert ib._vscode_effective_glob("**.py") == "**/**.py"
    assert ib._vscode_effective_glob("src/*.py") == "**/src/*.py"
    assert ib._vscode_effective_glob("*") == "*"


def test_is_language_universal_is_case_insensitive() -> None:
    # VS Code matches applyTo globs with { ignoreCase: true }, so an uppercase
    # or mixed-case extension spelling still loads for every file of the type.
    # computeAutomaticInstructions.ts line 316 (pinned in the module).
    assert ib.is_language_universal({"**/*.PY"}, ".py") is True
    assert ib.is_language_universal({"*.Py"}, ".py") is True
    assert ib.is_language_universal({"**/*.PS1"}, ".ps1") is True
    # Case folding does not promote a scoped glob: '**/src/*.py' is still scoped.
    assert ib.is_language_universal({"SRC/*.py"}, ".py") is False
    # Nor does it collide across distinct extensions.
    assert ib.is_language_universal({"**/*.PYX"}, ".py") is False


def test_is_language_universal_matches_broad_vscode_forms() -> None:
    # VS Code's matcher makes several broader globs universal that an exact-form
    # membership test would miss. Universality is decided by matching probe
    # paths, so the whole class is covered, not a hand-listed subset. Each of
    # these loads for every .py file:
    #  - '**/*.*' matches any dotted basename (every .py has one).
    #  - '/**/*.py' is absolute; file paths are absolute, so it spans any dir.
    #  - '**/*.py/**' has a trailing globstar that matches zero segments,
    #    covering the .py file itself.
    #  - '**/*.p?' uses a single-char wildcard that still matches every .py.
    #  - '**/*.p*' matches any '.p'-prefixed extension, including '.py'.
    #  - '/*/**' is an absolute one-segment-plus-globstar all-files form.
    assert ib.is_language_universal({"**/*.*"}, ".py") is True
    assert ib.is_language_universal({"*.*"}, ".py") is True
    assert ib.is_language_universal({"/**/*.py"}, ".py") is True
    assert ib.is_language_universal({"**/*.py/**"}, ".py") is True
    assert ib.is_language_universal({"**/*.p?"}, ".py") is True
    assert ib.is_language_universal({"**/*.p*"}, ".py") is True
    assert ib.is_language_universal({"/*/**"}, ".py") is True
    # Absolute all-files and prefix wildcards are universal too.
    assert ib.is_language_universal({"/**"}, ".py") is True
    assert ib.is_language_universal({"/**/*"}, ".py") is True
    # Matching must not promote a scoped glob: a bounded prefix stays scoped
    # whether the breadth comes from a trailing globstar or an absolute anchor,
    # and a single-char wildcard that cannot reach '.py' stays out (a '.pyx'
    # rule is not universal for '.py').
    assert ib.is_language_universal({"src/**/*.py/**"}, ".py") is False
    assert ib.is_language_universal({"/src/**/*.py"}, ".py") is False
    assert ib.is_language_universal({"/src/*.py"}, ".py") is False
    assert ib.is_language_universal({"**/*.py?"}, ".py") is False
    assert ib.is_language_universal({"**/*.pyx"}, ".py") is False
    # Effective glob is prepend-only now; the breadth is resolved by matching.
    assert ib._vscode_effective_glob("/**/*.py") == "/**/*.py"
    assert ib._vscode_effective_glob("**/*.py/**") == "**/*.py/**"
    assert ib._vscode_effective_glob("/**") == "/**"
    assert ib._vscode_effective_glob("/**/*") == "/**/*"
    assert ib._vscode_effective_glob("**/*.*") == "**/*.*"


def test_glob_to_regex_segment_semantics() -> None:
    # The matcher is the load-bearing primitive: '**' spans zero+ segments, '*'
    # stays within a segment, '?' is exactly one non-separator char.
    globstar = ib._glob_to_regex("**/*.py")
    assert globstar.match("/probe.py")  # zero intermediate segments
    assert globstar.match("/a/b/c/probe.py")  # many segments
    star = ib._glob_to_regex("/src/*.py")
    assert star.match("/src/probe.py")
    assert not star.match("/src/sub/probe.py")  # '*' does not cross '/'
    assert not star.match("/probe.py")  # literal 'src/' segment required
    question = ib._glob_to_regex("/x?.py")
    assert question.match("/xy.py")  # exactly one char
    assert not question.match("/x.py")  # zero chars fails
    assert not question.match("/xyz.py")  # two chars fails
    # Trailing '/**' covers the prefix path itself (zero trailing segments).
    trailing = ib._glob_to_regex("/a/**")
    assert trailing.match("/a")
    assert trailing.match("/a/b/c")


def test_glob_to_regex_separator_before_nonterminal_globstar() -> None:
    # Regression (issue #3419 round-9 finding 2): the separator before a
    # non-terminal '**' is mandatory. VS Code's parseRegExp "Tail" rule emits the
    # '/' after '/*/' so a globstar cannot swallow the first directory. The old
    # hand-rolled joiner dropped it, letting '/*/**/*.py' match a root file.
    depth_scoped = ib._glob_to_regex("/*/**/*.py")
    assert depth_scoped.match("/a/probe.py")  # exactly one directory
    assert depth_scoped.match("/a/b/c/probe.py")  # many directories
    assert not depth_scoped.match("/probe.py")  # root file has no first directory
    # A sibling folder must not match on a shared prefix: 'some/**/*.js' keeps
    # the '/' after 'some' so 'something/x.js' cannot match.
    sibling = ib._glob_to_regex("**/some/**/*.js")
    assert sibling.match("/pkg/some/x.js")
    assert not sibling.match("/pkg/something/x.js")


def test_is_language_universal_is_or_union_over_patterns() -> None:
    # Regression (issue #3419 round-9 finding 1): universality is a property of
    # the UNION of the comma-split patterns, not any single pattern. VS Code
    # attaches a rule to a file if ANY comma-split pattern matches it
    # (computeAutomaticInstructions.ts _matches). Three disjoint per-depth globs
    # whose union covers every depth make the rule load for every .py file, so
    # it must be scored universal even though no single member is.
    union = {"/*.py", "/*/*.py", "/*/*/**/*.py"}
    assert ib.is_language_universal(union, ".py") is True
    # No single member is universal on its own; scoring per-pattern (the old
    # behavior) would under-count this rule and let it dodge the budget.
    assert ib.is_language_universal({"/*.py"}, ".py") is False
    assert ib.is_language_universal({"/*/*.py"}, ".py") is False
    assert ib.is_language_universal({"/*/*/**/*.py"}, ".py") is False
    # The same OR-union holds through the frontmatter parser for a comma-joined
    # applyTo, the shape a real rule file would carry.
    text = "---\napplyTo: '/*.py, /*/*.py, /*/*/**/*.py'\n---\nbody\n"
    assert ib.is_language_universal(ib.parse_applyto(text), ".py") is True
    # A union that leaves a depth uncovered stays scoped: dropping the globstar
    # member leaves depth >=2 (e.g. '/a/b/x.py') unmatched, so not universal.
    bounded = {"/*.py", "/*/*.py"}
    assert ib.is_language_universal(bounded, ".py") is False


def test_is_language_universal_single_scoped_pattern_not_universal() -> None:
    # The OR-union change must not regress the common single-pattern case: a lone
    # '/*/**/*.py' does not match a root file, so a depth-0 .py file is uncovered
    # and the rule is not universal (finding 2 and finding 1 interact here).
    assert ib.is_language_universal({"/*/**/*.py"}, ".py") is False


# --------------------------------------------------------------------------
# measure_extension / evaluate (positive)
# --------------------------------------------------------------------------


def test_measure_extension_sums_only_matching_files(tmp_path: Path) -> None:
    b_all = _write_rule(tmp_path, "universal", "'**'")
    b_py = _write_rule(tmp_path, "python", "'**/*.py'")
    _write_rule(tmp_path, "csharp", "'**/*.cs'")
    _write_rule(tmp_path, "tests", "tests/**")

    files = ib.load_instruction_files(tmp_path)
    result = ib.measure_extension(files, ".py", ceiling_bytes=10_000)

    assert set(result.matched_files) == {"universal.instructions.md", "python.instructions.md"}
    assert result.total_bytes == b_all + b_py
    assert result.over_budget is False
    assert result.estimated_tokens > 0


def test_evaluate_covers_all_configured_extensions(tmp_path: Path) -> None:
    _write_rule(tmp_path, "universal", "'**'")
    results = ib.evaluate(tmp_path, ib.DEFAULT_CEILINGS_BYTES)
    exts = {r.extension for r in results}
    assert exts == set(ib.DEFAULT_CEILINGS_BYTES)
    # The universal rule counts toward every extension baseline.
    assert all(r.matched_files == ("universal.instructions.md",) for r in results)


# --------------------------------------------------------------------------
# over-budget / gate (negative)
# --------------------------------------------------------------------------


def test_over_budget_flag_when_bytes_exceed_ceiling(tmp_path: Path) -> None:
    _write_rule(tmp_path, "universal", "'**'", body="x" * 5000)
    result = ib.evaluate(tmp_path, {".py": 100})[0]
    assert result.over_budget is True
    assert result.usage_percent > 100.0


def test_main_ci_returns_1_when_over_budget(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_rule(tmp_path, "universal", "'**'")
    code = ib.main(["--path", str(tmp_path), "--ci", "--ceiling", ".py:10", "--ceiling", ".md:10"])
    assert code == 1
    assert "FAIL" in capsys.readouterr().out


def test_main_non_ci_returns_0_even_when_over_budget(tmp_path: Path) -> None:
    _write_rule(tmp_path, "universal", "'**'")
    code = ib.main(["--path", str(tmp_path), "--ceiling", ".py:10"])
    assert code == 0


def test_main_returns_2_when_instructions_dir_missing(tmp_path: Path) -> None:
    assert ib.main(["--path", str(tmp_path)]) == 2


def test_main_returns_2_when_path_not_a_directory(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    assert ib.main(["--path", str(missing)]) == 2


def test_main_returns_2_on_malformed_frontmatter(tmp_path: Path) -> None:
    # End-to-end fail-closed: a real instruction file with a duplicate applyTo
    # key must surface as a config error (exit 2), not silently score as zero
    # always-on bytes.
    inst_dir = tmp_path / ib.INSTRUCTIONS_SUBDIR
    inst_dir.mkdir(parents=True, exist_ok=True)
    (inst_dir / "dup.instructions.md").write_text(
        "---\napplyTo: '**/*.py'\napplyTo: tests/**\n---\n\nbody\n",
        encoding="utf-8",
    )
    assert ib.main(["--path", str(tmp_path)]) == 2


# --------------------------------------------------------------------------
# parse_ceiling_override (edge)
# --------------------------------------------------------------------------


def test_parse_ceiling_override_adds_leading_dot() -> None:
    assert ib.parse_ceiling_override("py:200000") == (".py", 200_000)


def test_parse_ceiling_override_keeps_leading_dot() -> None:
    assert ib.parse_ceiling_override(".cs:5000") == (".cs", 5_000)


@pytest.mark.parametrize("bad", ["nocolon", ".py:abc", ".py:0", ".py:-5"])
def test_parse_ceiling_override_rejects_bad(bad: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        ib.parse_ceiling_override(bad)


def test_ceiling_override_merges_with_defaults(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_rule(tmp_path, "universal", "'**'")
    # Override only .py; other extensions keep default ceilings and pass.
    code = ib.main(["--path", str(tmp_path), "--ci", "--format", "json", "--ceiling", ".py:5"])
    assert code == 1
    out = capsys.readouterr().out
    assert '"extension": ".py"' in out


# --------------------------------------------------------------------------
# edge: no-frontmatter file is not counted
# --------------------------------------------------------------------------


def test_file_without_frontmatter_is_not_matched(tmp_path: Path) -> None:
    inst_dir = tmp_path / ib.INSTRUCTIONS_SUBDIR
    inst_dir.mkdir(parents=True)
    (inst_dir / "loose.instructions.md").write_text("# no frontmatter\n", encoding="utf-8")
    result = ib.evaluate(tmp_path, {".py": 1_000})[0]
    assert result.matched_files == ()
    assert result.total_bytes == 0


# --------------------------------------------------------------------------
# anchor: real repo methodology guard
# --------------------------------------------------------------------------


def test_real_repo_python_baseline_is_under_ceiling_and_nonzero() -> None:
    results = {r.extension: r for r in ib.evaluate(REPO_ROOT, ib.DEFAULT_CEILINGS_BYTES)}
    py = results[".py"]
    # Methodology guard, not a debt floor. The instrument must detect the
    # always-on universal rules and stay under the ratchet ceiling. It must
    # NOT assert a minimum size: the deferred rescoping phase legitimately
    # shrinks this corpus, and a lower bound would fail on that success.
    matched = set(py.matched_files)
    core_universal = {
        "universal.instructions.md",
        "voice.instructions.md",
        "builder-ethos.instructions.md",
    }
    missing = core_universal - matched
    assert not missing, f"matcher missed core always-on rules: {sorted(missing)}"
    assert py.total_bytes > 0
    assert py.total_bytes <= py.ceiling_bytes


def test_committed_lsp_first_scope_matches_code_not_markdown() -> None:
    rule = REPO_ROOT / ib.INSTRUCTIONS_SUBDIR / "lsp-first.instructions.md"
    patterns = ib.parse_applyto(rule.read_text(encoding="utf-8"))

    assert any(ib._glob_to_regex(pattern).fullmatch("src/app.py") for pattern in patterns)
    assert not any(
        ib._glob_to_regex(pattern).fullmatch("docs/guide.md") for pattern in patterns
    )


# --------------------------------------------------------------------------
# reserve band (issue #4345)
#
# Required checks on this repo are not strict, so two branches measured against
# the same base can each pass the ceiling check and still breach once both
# merge. Measured instance on main: three merges at +891, +339, and +259 bytes
# landed a .md corpus of 83201 against an 83000 ceiling. The reserve is the
# headroom kept free so the second merge lands under the ceiling instead of
# over it.
# --------------------------------------------------------------------------


def _result(total: int, ceiling: int, reserve: int = 0) -> ib.ExtensionResult:
    """Build an ExtensionResult directly, bypassing the filesystem."""
    return ib.ExtensionResult(
        extension=".md",
        matched_files=("a.instructions.md",),
        total_bytes=total,
        estimated_tokens=total // 4,
        ceiling_bytes=ceiling,
        reserve_bytes=reserve,
    )


def test_headroom_is_positive_below_ceiling() -> None:
    assert _result(900, 1000).headroom_bytes == 100


def test_headroom_is_zero_exactly_at_ceiling() -> None:
    assert _result(1000, 1000).headroom_bytes == 0


def test_headroom_is_negative_once_breached() -> None:
    assert _result(1200, 1000).headroom_bytes == -200


def test_reserve_defaults_to_zero_so_behavior_is_unchanged() -> None:
    r = _result(999, 1000)
    assert r.reserve_bytes == 0
    assert r.under_reserve is False
    assert r.over_budget is False


def test_under_reserve_is_true_when_headroom_is_below_the_band() -> None:
    assert _result(950, 1000, reserve=100).under_reserve is True


def test_under_reserve_is_false_when_headroom_exactly_equals_the_band() -> None:
    # Boundary: 100 bytes of headroom satisfies a 100-byte reserve.
    assert _result(900, 1000, reserve=100).under_reserve is False


def test_under_reserve_is_false_one_byte_above_the_band() -> None:
    assert _result(899, 1000, reserve=100).under_reserve is False


def test_under_reserve_is_false_once_over_budget_so_fail_wins() -> None:
    # A breach is already FAIL. Reporting WARN too would mask the harder verdict.
    r = _result(1200, 1000, reserve=100)
    assert r.over_budget is True
    assert r.under_reserve is False


def test_under_reserve_is_false_for_a_negative_or_zero_band() -> None:
    assert _result(999, 1000, reserve=0).under_reserve is False


def test_status_of_prefers_fail_over_warn() -> None:
    # A stub is required here, not an ExtensionResult. The real type guards
    # under_reserve on over_budget, so both flags can never be true together
    # and an ExtensionResult cannot observe the ordering inside _status_of.
    # A mutation swapping the two branches survived against the real type.
    # _status_of must prefer the harder verdict on its own, so that a future
    # caller which reports both flags cannot silently downgrade a breach.
    class _BothFlags:
        over_budget = True
        under_reserve = True

    assert ib._status_of(_BothFlags()) == "FAIL"


def test_extension_result_never_reports_both_flags() -> None:
    # The structural invariant that made the ordering test vacuous. Assert it
    # directly so a future edit to under_reserve cannot break it unnoticed.
    for total in (999, 1000, 1001, 5000):
        r = _result(total, 1000, reserve=100)
        assert not (r.over_budget and r.under_reserve)


def test_status_of_reports_warn_inside_the_band() -> None:
    assert ib._status_of(_result(950, 1000, reserve=100)) == "WARN"


def test_status_of_reports_pass_outside_the_band() -> None:
    assert ib._status_of(_result(500, 1000, reserve=100)) == "PASS"


def test_evaluate_threads_the_reserve_into_every_result(tmp_path: Path) -> None:
    _write_rule(tmp_path, "u", "'**'")
    results = ib.evaluate(tmp_path, {".py": 10_000}, 250)
    assert results[0].reserve_bytes == 250


def test_evaluate_reserve_is_optional_and_defaults_to_zero(tmp_path: Path) -> None:
    _write_rule(tmp_path, "u", "'**'")
    results = ib.evaluate(tmp_path, {".py": 10_000})
    assert results[0].reserve_bytes == 0


def test_json_output_exposes_headroom_and_reserve() -> None:
    import json

    payload = json.loads(ib.format_json([_result(950, 1000, reserve=100)]))
    assert payload[0]["headroom_bytes"] == 50
    assert payload[0]["reserve_bytes"] == 100
    assert payload[0]["under_reserve"] is True
    assert payload[0]["over_budget"] is False


def test_table_output_shows_headroom_column_and_warn_status() -> None:
    table = ib.format_table([_result(950, 1000, reserve=100)])
    assert "Headroom" in table
    assert "WARN" in table


def test_parse_reserve_accepts_zero_and_positive() -> None:
    assert ib.parse_reserve("0") == 0
    assert ib.parse_reserve("2048") == 2048


def test_parse_reserve_rejects_negative() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="non-negative"):
        ib.parse_reserve("-1")


def test_parse_reserve_rejects_non_integer() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="integer"):
        ib.parse_reserve("1.5")


def test_main_exits_one_when_ci_and_headroom_is_inside_the_reserve(
    tmp_path: Path,
) -> None:
    size = _write_rule(tmp_path, "u", "'**'")
    rc = ib.main(
        [
            "--path",
            str(tmp_path),
            "--ci",
            "--ceiling",
            f".py:{size + 10}",
            "--reserve",
            "100",
        ]
    )
    assert rc == 1


def test_main_exits_zero_without_ci_even_when_inside_the_reserve(
    tmp_path: Path,
) -> None:
    # Reserve is advisory outside CI, matching how over_budget already behaves.
    size = _write_rule(tmp_path, "u", "'**'")
    rc = ib.main(
        [
            "--path",
            str(tmp_path),
            "--ceiling",
            f".py:{size + 10}",
            "--reserve",
            "100",
        ]
    )
    assert rc == 0


def test_main_exits_zero_when_headroom_clears_the_reserve(tmp_path: Path) -> None:
    size = _write_rule(tmp_path, "u", "'**'")
    rc = ib.main(
        [
            "--path",
            str(tmp_path),
            "--ci",
            "--ceiling",
            f".py:{size + 500}",
            "--reserve",
            "100",
        ]
    )
    assert rc == 0


def test_default_reserve_is_600_bytes() -> None:
    assert ib.DEFAULT_RESERVE_BYTES == 600


def test_main_default_reserve_blocks_ci_inside_band(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("INSTRUCTION_BUDGET_RESERVE", raising=False)
    size = _write_rule(tmp_path, "u", "'**'")
    rc = ib.main(
        [
            "--path",
            str(tmp_path),
            "--ci",
            "--ceiling",
            f".py:{size + 599}",
        ]
    )
    assert rc == 1


def test_main_default_reserve_passes_at_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("INSTRUCTION_BUDGET_RESERVE", raising=False)
    size = _write_rule(tmp_path, "u", "'**'")
    rc = ib.main(
        [
            "--path",
            str(tmp_path),
            "--ci",
            "--ceiling",
            f".py:{size + 600}",
        ]
    )
    assert rc == 0


def test_main_explicit_zero_disables_default_reserve(tmp_path: Path) -> None:
    size = _write_rule(tmp_path, "u", "'**'")
    rc = ib.main(
        [
            "--path",
            str(tmp_path),
            "--ci",
            "--ceiling",
            f".py:{size + 1}",
            "--reserve",
            "0",
        ]
    )
    assert rc == 0


def test_reserve_reads_the_environment_when_the_flag_is_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    size = _write_rule(tmp_path, "u", "'**'")
    monkeypatch.setenv("INSTRUCTION_BUDGET_RESERVE", "100")
    rc = ib.main(["--path", str(tmp_path), "--ci", "--ceiling", f".py:{size + 10}"])
    assert rc == 1
