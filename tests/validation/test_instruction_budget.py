"""Tests for scripts/validation/instruction_budget.py (issue #3419).

The validator measures the always-on instruction budget per language: the summed
bytes of ``.github/instructions/*.instructions.md`` files whose ``applyTo`` scopes
them to every file of a language (``**`` or ``**/*.<ext>``). It gates growth via a
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

import scripts.validation.instruction_budget as ib  # noqa: E402


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


def test_parse_applyto_expands_brace_group() -> None:
    # A leading '**' forces quoting in YAML, so the realistic brace form is
    # quoted; an unquoted '**/*.{...}' is invalid YAML the harness would reject.
    text = "---\napplyTo: '**/*.{py,pyi},tests/**'\n---\nbody\n"
    assert ib.parse_applyto(text) == {"**/*.py", "**/*.pyi", "tests/**"}


def test_parse_applyto_brace_form_is_language_universal() -> None:
    # A future rule scoped with a brace group must still be caught by the gate.
    patterns = ib.parse_applyto("---\napplyTo: '**/*.{py,pyi}'\n---\nbody\n")
    assert ib.is_language_universal(patterns, ".py") is True


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
        ({"*.py"}, ".py", False),
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
    # A directory-or-prefix glob that merely ends with '*.py' is NOT
    # language-universal; only '**', '**/*', and '**/*.py' count. The
    # root-only '*.py' form is situational, not an always-on baseline.
    assert ib.is_language_universal({"src/foo*.py"}, ".py") is False
    assert ib.is_language_universal({"*.py"}, ".py") is False


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
    # A doubled star inside the filename segment alone is root-only (no leading
    # globstar), so it is NOT the always-on baseline, matching bare '*.py'.
    assert ib.is_language_universal({"**.py"}, ".py") is False
    # A bare '*' is root-only too (minimatch '*' does not cross '/'), so a rule
    # scoped '*' does not load when editing a nested file: not always-on. This
    # is the same deliberate decision as '*.py' above, recorded so a future
    # "but '*' means all files" change is a conscious one, not an accident.
    assert ib.is_language_universal({"*"}, ".py") is False
    assert ib._normalize_glob("**/**/*.py") == "**/*.py"
    assert ib._normalize_glob("**/**.py") == "**/*.py"
    assert ib._normalize_glob("**/**") == "**"
    assert ib._normalize_glob("**.py") == "*.py"


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
