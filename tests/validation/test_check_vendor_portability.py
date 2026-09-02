# taste-lint: ignore file-size
# All tests for a single script belong in one file for discoverability;
# splitting across files would obscure which cases are covered and add
# import overhead without reducing complexity. The file grew to 849 lines
# because the #4046 fix added 9 new test classes for three new exemption
# mechanisms (regex-metachar, prose string, tests-dir exclusion), each
# requiring a positive, negative, and edge case per exemption type.
"""Tests for scripts/validation/check_vendor_portability.py.

Issue #2050. The check fails CI when a vendor-shipped skill script
hard-codes an upstream-only path (.agents/ or .claude/lib/) without
routing through the portability helper, unless the offender is recorded
in the baseline. Tests use temporary file trees rather than the live
repo so the result is independent of how clean the repo happens to be.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "validation" / "check_vendor_portability.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_vendor_portability", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cvp = _load_module()


def _write(repo: Path, relpath: str, content: str) -> Path:
    target = repo / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """Create the scan root the script inspects."""
    (tmp_path / ".claude" / "skills").mkdir(parents=True, exist_ok=True)
    return tmp_path


# --- collect_offenders: positive (clean) -----------------------------------


def test_clean_script_is_not_an_offender(fake_repo: Path) -> None:
    _write(
        fake_repo,
        ".claude/skills/foo/scripts/clean.py",
        "from pathlib import Path\n\nx = Path('output.json')\n",
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert offenders == []


def test_script_routing_through_helper_is_exempt(fake_repo: Path) -> None:
    # References .agents/ but imports the helper, so it is presumed portable.
    _write(
        fake_repo,
        ".claude/skills/foo/scripts/portable.py",
        "from paths import resolve_artifact_root\n\n"
        "root = resolve_artifact_root('analysis')  # default <cwd>/.agents/\n",
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert offenders == []


def test_script_using_paths_module_helper_is_exempt(fake_repo: Path) -> None:
    _write(
        fake_repo,
        ".claude/skills/foo/scripts/portable_module.py",
        "import paths\n\nroot = paths.resolve_artifact_root('analysis')\ndefault = '.agents'\n",
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert offenders == []


def test_comments_with_upstream_paths_are_not_offenders(fake_repo: Path) -> None:
    _write(
        fake_repo,
        ".claude/skills/foo/scripts/comment.py",
        "# writes to .agents/analysis when running upstream\nvalue = 'safe'\n",
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert offenders == []


def test_docstrings_with_upstream_paths_are_not_offenders(fake_repo: Path) -> None:
    _write(
        fake_repo,
        ".claude/skills/foo/scripts/docstring.py",
        '"""Mentions .claude/lib/paths.py in prose."""\n\nvalue = "safe"\n',
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert offenders == []


# --- collect_offenders: false-positive guards (Issue #2510) ----------------


def test_raw_string_regex_pattern_is_not_an_offender(fake_repo: Path) -> None:
    """Raw-string regex pattern (r"\\.agents/") is a path-matcher, not a path dep.

    Evidence: .claude/skills/metrics/collect_metrics.py:42 carries `r"\\.agents/"`
    inside a list of regex patterns the script uses to scan commit messages. The
    literal never participates in an I/O call and cannot be migrated through
    `paths.py`. Flagging it inflates the #2050 baseline and hides genuine offenders.
    """
    _write(
        fake_repo,
        ".claude/skills/foo/scripts/regex.py",
        'import re\n\nBANNED = [\n    r"docker-compose",\n    r"\\.agents/",\n]\n',
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert offenders == []


def test_raw_string_regex_pattern_with_anchor_is_not_an_offender(fake_repo: Path) -> None:
    """Anchored regex pattern (r"^\\.agents/sessions/") is still a pattern."""
    _write(
        fake_repo,
        ".claude/skills/foo/scripts/anchored.py",
        'PATTERNS = [\n    r"^\\.agents/sessions/",\n    r"^\\.agents/analysis/",\n]\n',
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert offenders == []


def test_raw_fstring_regex_pattern_is_not_an_offender(fake_repo: Path) -> None:
    """Raw f-string regex pattern (rf"\\.agents/{cat}/") is a pattern, not a path.

    On Python 3.12+ an f-string tokenizes as FSTRING_START/MIDDLE/END; the
    MIDDLE token carries the `\\.agents/` text without the `rf` prefix, so the
    raw-ness must be read from the enclosing FSTRING_START token.
    """
    _write(
        fake_repo,
        ".claude/skills/foo/scripts/raw_fstring.py",
        'category = "sessions"\npat = rf"\\.agents/{category}/"\n',
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert offenders == []


def test_fr_prefixed_raw_string_regex_is_not_an_offender(fake_repo: Path) -> None:
    """The `fr` prefix spelling (f before r) is also a raw string."""
    _write(
        fake_repo,
        ".claude/skills/foo/scripts/fr_prefix.py",
        'category = "sessions"\npat = fr"\\.agents/{category}/"\n',
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert offenders == []


def test_raw_fstring_without_escape_is_still_an_offender(fake_repo: Path) -> None:
    """A raw f-string without `\\.` escape is a real path and stays flagged."""
    _write(
        fake_repo,
        ".claude/skills/foo/scripts/raw_fstring_path.py",
        'day = "today"\nout = rf".agents/analysis/{day}.md"\n',
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert len(offenders) == 1
    assert offenders[0].relpath == ".claude/skills/foo/scripts/raw_fstring_path.py"


def test_raw_string_without_escape_is_still_an_offender(fake_repo: Path) -> None:
    """A raw string without `\\.` escape is a real path, not a regex pattern.

    Keeps the guard narrow: only escaped-dot patterns are presumed regex. Someone
    writing r".agents/x" (no backslash) is constructing a literal path and must
    still be flagged.
    """
    _write(
        fake_repo,
        ".claude/skills/foo/scripts/raw_path.py",
        'out = r".agents/analysis/x.md"\n',
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert len(offenders) == 1
    assert offenders[0].relpath == ".claude/skills/foo/scripts/raw_path.py"


def test_argparse_help_text_is_not_an_offender(fake_repo: Path) -> None:
    """An argparse `help=` value containing `.agents/` is prose, not a path.

    Evidence: .claude/skills/orphan-ref-validator/scripts/scan.py:563 references
    `.agents/architecture/` only inside `help=` to document a flag. The string is
    rendered by argparse onto stderr and never opens or writes a file.
    """
    _write(
        fake_repo,
        ".claude/skills/foo/scripts/argparse_help.py",
        "import argparse\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument(\n"
        "    '--episode-path',\n"
        "    help='Path to episode file or directory (default: .agents/memory/episodes/)',\n"
        ")\n",
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert offenders == []


def test_argparse_epilog_text_is_not_an_offender(fake_repo: Path) -> None:
    """An argparse `epilog=` value (often a concatenated string) is prose.

    Evidence: .claude/skills/security-scan/scripts/scan_vulnerabilities.py:337
    references `.agents/architecture/ADR-054-...` only inside the parser's
    `epilog=` tuple. Both `description=` and `metavar=` follow the same
    prose-not-IO contract.
    """
    _write(
        fake_repo,
        ".claude/skills/foo/scripts/argparse_epilog.py",
        "import argparse\n"
        "parser = argparse.ArgumentParser(\n"
        "    description='Scan code for CWE-78.',\n"
        "    epilog=(\n"
        "        'Exit codes:\\n'\n"
        "        '  0  no vulnerabilities\\n'\n"
        "        '\\n'\n"
        "        'See .agents/architecture/ADR-054-local-security-scanning.md.'\n"
        "    ),\n"
        ")\n",
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert offenders == []


def test_argparse_description_text_is_not_an_offender(fake_repo: Path) -> None:
    """An argparse `description=` value is prose."""
    _write(
        fake_repo,
        ".claude/skills/foo/scripts/argparse_desc.py",
        "import argparse\n"
        "p = argparse.ArgumentParser(\n"
        "    description='Reads from .agents/sessions/ and reports stats.',\n"
        ")\n",
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert offenders == []


def test_hardcoded_path_outside_help_kwarg_is_still_offender(fake_repo: Path) -> None:
    """A real path on a different line of the same file is still flagged.

    Guard against over-broadening: the prose exemption must be scoped to the
    string literals that *are* the help/description/epilog values, not the
    whole file containing an `argparse` call.
    """
    _write(
        fake_repo,
        ".claude/skills/foo/scripts/mixed.py",
        "import argparse\n"
        "p = argparse.ArgumentParser(description='Innocent description.')\n"
        "p.add_argument('--out', help='Output file.')\n"
        "OUT = '.agents/analysis/x.md'\n",
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert len(offenders) == 1
    assert offenders[0].relpath == ".claude/skills/foo/scripts/mixed.py"
    assert ".agents/analysis/x.md" in offenders[0].excerpt


def test_non_argparse_help_kwarg_is_also_exempt(fake_repo: Path) -> None:
    """Other CLI libraries (Click, Typer) use the same `help=` convention.

    The exemption is keyed on the kwarg name, not on importing argparse, so
    Click-style decorators get the same treatment.
    """
    _write(
        fake_repo,
        ".claude/skills/foo/scripts/click_help.py",
        "import click\n\n"
        "@click.option('--path', help='Defaults to .agents/sessions/')\n"
        "def cmd(path):\n"
        "    pass\n",
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert offenders == []


# --- collect_offenders: negative (offending) -------------------------------


def test_hardcoded_agents_path_is_offender(fake_repo: Path) -> None:
    _write(
        fake_repo,
        ".claude/skills/bar/scripts/bad.py",
        "from pathlib import Path\n\nout = Path('.agents/analysis/x.md')\n",
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert len(offenders) == 1
    assert offenders[0].relpath == ".claude/skills/bar/scripts/bad.py"
    assert ".agents/" in offenders[0].excerpt


def test_import_pathspec_does_not_exempt_offender(fake_repo: Path) -> None:
    _write(
        fake_repo,
        ".claude/skills/bar/scripts/pathspec_bad.py",
        "import pathspec\n\nout = '.agents/analysis/x.md'\n",
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert len(offenders) == 1
    assert offenders[0].relpath == ".claude/skills/bar/scripts/pathspec_bad.py"


def test_unused_paths_import_does_not_exempt_offender(fake_repo: Path) -> None:
    _write(
        fake_repo,
        ".claude/skills/bar/scripts/unused_paths.py",
        "import paths\n\nout = '.agents/analysis/x.md'\n",
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert len(offenders) == 1
    assert offenders[0].relpath == ".claude/skills/bar/scripts/unused_paths.py"


def test_standalone_agents_segment_is_offender(fake_repo: Path) -> None:
    _write(
        fake_repo,
        ".claude/skills/bar/scripts/standalone.py",
        "out = os.path.join('.agents', 'analysis', 'x.md')\n",
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert len(offenders) == 1
    assert offenders[0].relpath == ".claude/skills/bar/scripts/standalone.py"


def test_windows_claude_lib_path_is_offender(fake_repo: Path) -> None:
    _write(
        fake_repo,
        ".claude/skills/bar/scripts/windows.py",
        r"spec = '.claude\\lib\\paths.py'" + "\n",
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert len(offenders) == 1
    assert offenders[0].relpath == ".claude/skills/bar/scripts/windows.py"


def test_fstring_agents_path_is_offender(fake_repo: Path) -> None:
    _write(
        fake_repo,
        ".claude/skills/bar/scripts/fstring.py",
        "out = f'.agents/{subdir}/x.md'\n",
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert len(offenders) == 1
    assert offenders[0].relpath == ".claude/skills/bar/scripts/fstring.py"


def test_hardcoded_claude_lib_path_is_offender(fake_repo: Path) -> None:
    _write(
        fake_repo,
        ".claude/skills/baz/scripts/bad.py",
        "spec = '.claude/lib/ai_review_common/verdict.py'\n",
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert len(offenders) == 1
    assert offenders[0].relpath == ".claude/skills/baz/scripts/bad.py"


def test_offender_line_number_points_at_first_hit(fake_repo: Path) -> None:
    _write(
        fake_repo,
        ".claude/skills/bar/scripts/bad.py",
        "import os\n\n\nout = '.agents/sessions/log.json'\n",
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert offenders[0].line == 4


# --- baseline ratchet ------------------------------------------------------


def test_baselined_offender_does_not_fail(fake_repo: Path) -> None:
    rel = ".claude/skills/bar/scripts/bad.py"
    _write(fake_repo, rel, "out = '.agents/analysis/x.md'\n")
    offenders = cvp.collect_offenders(fake_repo)

    new, known = cvp.split_offenders(offenders, {rel})

    assert new == []
    assert len(known) == 1


def test_new_offender_outside_baseline_fails(fake_repo: Path) -> None:
    _write(
        fake_repo,
        ".claude/skills/bar/scripts/new_bad.py",
        "out = '.agents/analysis/x.md'\n",
    )
    offenders = cvp.collect_offenders(fake_repo)

    new, known = cvp.split_offenders(offenders, {".claude/skills/old/x.py"})

    assert len(new) == 1
    assert known == []


def test_load_baseline_ignores_comments_and_blanks(tmp_path: Path) -> None:
    bpath = tmp_path / "baseline.txt"
    bpath.write_text(
        "# header comment\n\n.claude/skills/a/x.py\n  # indented comment\n.claude/skills/b/y.py\n",
        encoding="utf-8",
    )

    entries = cvp.load_baseline(bpath)

    assert entries == {".claude/skills/a/x.py", ".claude/skills/b/y.py"}


def test_load_baseline_missing_file_returns_empty(tmp_path: Path) -> None:
    assert cvp.load_baseline(tmp_path / "nope.txt") == set()


# --- main / CLI exit codes -------------------------------------------------


def test_main_passes_when_no_offenders(fake_repo: Path) -> None:
    _write(fake_repo, ".claude/skills/foo/scripts/clean.py", "x = 1\n")

    rc = cvp.main(["--repo-root", str(fake_repo)])

    assert rc == 0


def test_main_fails_on_new_offender(fake_repo: Path) -> None:
    _write(
        fake_repo,
        ".claude/skills/bar/scripts/bad.py",
        "out = '.agents/analysis/x.md'\n",
    )

    rc = cvp.main(["--repo-root", str(fake_repo)])

    assert rc == 1


def test_main_passes_when_offender_in_baseline(fake_repo: Path) -> None:
    rel = ".claude/skills/bar/scripts/bad.py"
    _write(fake_repo, rel, "out = '.agents/analysis/x.md'\n")
    bpath = cvp.baseline_path(fake_repo)
    bpath.parent.mkdir(parents=True, exist_ok=True)
    bpath.write_text(rel + "\n", encoding="utf-8")

    rc = cvp.main(["--repo-root", str(fake_repo)])

    assert rc == 0


def test_main_update_baseline_writes_offenders(fake_repo: Path) -> None:
    rel = ".claude/skills/bar/scripts/bad.py"
    _write(fake_repo, rel, "out = '.agents/analysis/x.md'\n")

    rc = cvp.main(["--repo-root", str(fake_repo), "--update-baseline"])

    assert rc == 0
    written = cvp.load_baseline(cvp.baseline_path(fake_repo))
    assert written == {rel}


def test_main_skips_when_no_scan_root(tmp_path: Path) -> None:
    # No .claude/skills directory present.
    rc = cvp.main(["--repo-root", str(tmp_path)])

    assert rc == 0


def test_main_config_error_on_missing_repo_root(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist"

    rc = cvp.main(["--repo-root", str(missing)])

    assert rc == 2


# --- edge: pycache excluded, baselined-then-removed --------------------------


def test_pycache_files_are_skipped(fake_repo: Path) -> None:
    _write(
        fake_repo,
        ".claude/skills/foo/scripts/__pycache__/bad.py",
        "out = '.agents/analysis/x.md'\n",
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert offenders == []


def test_helper_function_set_matches_paths_module() -> None:
    """`_HELPER_FUNCTIONS` lists every public resolver `paths.py` exposes.

    The set is how the checker decides a file routes through the portability
    helper. When `paths.py` grew `artifact_dir` and a skill switched to it,
    the checker stopped recognizing the file and reported a pre-existing line
    as a new offender. Drift here produces a false positive that pressures the
    next author into baselining code that is already portable.
    """
    paths_source = (Path(__file__).resolve().parents[2] / ".claude" / "lib" / "paths.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(paths_source)
    exposed = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_")
    }

    assert exposed == set(cvp._HELPER_FUNCTIONS), (
        "check_vendor_portability._HELPER_FUNCTIONS has drifted from the public "
        f"functions in .claude/lib/paths.py: only in paths.py "
        f"{sorted(exposed - set(cvp._HELPER_FUNCTIONS))}, only in the checker "
        f"{sorted(set(cvp._HELPER_FUNCTIONS) - exposed)}"
    )


def test_a_file_using_only_artifact_dir_is_not_an_offender(fake_repo: Path) -> None:
    """A skill that resolves without creating still counts as portable."""
    _write(
        fake_repo,
        ".claude/skills/demo/scripts/reader.py",
        "from paths import artifact_dir\n\n\n"
        "def where(sub):\n"
        '    return artifact_dir(sub) or ".agents/fallback"\n',
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert not [o for o in offenders if o.relpath.endswith("reader.py")]


# --- scripts/ detection (issue #4013) -------------------------------------


def test_hardcoded_scripts_path_is_offender(fake_repo: Path) -> None:
    """A skill that references scripts/ directly is flagged as an offender.

    Isolating negative control: removing scripts[\\/] from _BANNED_PATH causes
    collect_offenders to return [] for this file, failing the assertion.
    The file contains no .agents/, .claude/lib/, or other banned prefix, so
    only the scripts/ component can trigger detection.
    """
    _write(
        fake_repo,
        ".claude/skills/foo/scripts/bad.py",
        "path = 'scripts/validation/check_vendor_portability.py'\n",
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert len(offenders) == 1
    assert "scripts/" in offenders[0].excerpt


def test_scripts_path_after_slash_prefix_is_not_offender(fake_repo: Path) -> None:
    """A path where scripts is a subdirectory (build/scripts/) is not flagged.

    The lookbehind that excludes a slash before "scripts" means
    build/scripts/x.py does not register as an upstream-only path.
    """
    _write(
        fake_repo,
        ".claude/skills/foo/scripts/ok.py",
        "path = 'build/scripts/generate_rules.py'\n",
    )

    assert cvp.collect_offenders(fake_repo) == []


def test_scripts_as_word_suffix_is_not_offender(fake_repo: Path) -> None:
    """A word like test_scripts/ is not flagged (word char before scripts).

    The lookbehind that excludes a word character before "scripts"
    means test_scripts/x.py does not collide with the upstream scripts/ tree.
    """
    _write(
        fake_repo,
        ".claude/skills/foo/scripts/ok.py",
        "path = 'test_scripts/x.py'\n",
    )

    assert cvp.collect_offenders(fake_repo) == []


def test_dot_slash_scripts_path_is_offender(fake_repo: Path) -> None:
    """./scripts/x.py is flagged; the ./ prefix does not launder the reference.

    Regression test for the bypass found in PR #4029 review. The lookbehind
    alone (`(?<![/\\\\\\w])`) saw the slash in `./` and rejected the match, so a
    shell-style invocation string sailed past the gate while the bare form was
    caught. Isolating negative control: dropping `(?:\\.[\\\\/])?` from
    _BANNED_PATH makes this assertion fail.
    """
    _write(
        fake_repo,
        ".claude/skills/foo/scripts/bad.py",
        'subprocess.run(["python3", "./scripts/validation/pre_pr.py"])\n',
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert len(offenders) == 1
    assert offenders[0].relpath == ".claude/skills/foo/scripts/bad.py"


def test_dot_backslash_scripts_path_is_offender(fake_repo: Path) -> None:
    """.\\scripts\\x.py (Windows current-dir prefix) is flagged like ./scripts/."""
    _write(
        fake_repo,
        ".claude/skills/foo/scripts/bad.py",
        r"path = r'.\scripts\validation\pre_pr.py'" + "\n",
    )

    offenders = cvp.collect_offenders(fake_repo)

    assert len(offenders) == 1
    assert offenders[0].relpath == ".claude/skills/foo/scripts/bad.py"


def test_parent_relative_scripts_path_is_not_offender(fake_repo: Path) -> None:
    """../scripts/x.py is not flagged.

    Bounding case for the current-directory prefix: a parent-relative path can
    legitimately name a skill-internal sibling directory rather than the
    upstream tree, so the `.` in the lookbehind class keeps it out of scope.
    """
    _write(
        fake_repo,
        ".claude/skills/foo/scripts/ok.py",
        "path = '../scripts/x.py'\n",
    )

    assert cvp.collect_offenders(fake_repo) == []


def test_nested_dot_slash_scripts_path_is_not_offender(fake_repo: Path) -> None:
    """build/./scripts/x.py is not flagged; scripts is still not at the path root.

    Negative control proving the current-directory prefix did not widen the
    match to nested paths: the slash before `./` still rejects it.
    """
    _write(
        fake_repo,
        ".claude/skills/foo/scripts/ok.py",
        "path = 'build/./scripts/generate_rules.py'\n",
    )

    assert cvp.collect_offenders(fake_repo) == []


# ---------------------------------------------------------------------------
# Issue #4046 - exemption gaps for the scripts/ prefix
# ---------------------------------------------------------------------------


class TestRegexMetacharExemption:
    """Raw-string regexes with metacharacters other than ``\\.`` are exempt.

    The original ``_is_raw_string_regex`` checked only for ``\\.``, which works
    for ``.agents/`` and ``.claude/lib/`` (both start with a dot the regex must
    escape).  It failed silently for ``scripts/`` (no dot), so
    ``r"^scripts/"`` and ``r'python\\s+scripts/'`` were flagged as real paths.
    Issue #4046 broadens the test to any regex metachar.  Isolating negative
    control: restoring the old ``"\\\\." in token_text`` check breaks these
    assertions.
    """

    def test_raw_string_with_caret_is_exempt(self, fake_repo: Path) -> None:
        """r"^scripts/" contains the anchor metachar ``^`` and must be exempt."""
        _write(
            fake_repo,
            ".claude/skills/foo/collect_metrics.py",
            'BANNED = re.compile(r"^scripts/")\n',
        )
        assert cvp.collect_offenders(fake_repo) == []

    def test_raw_string_with_backslash_escape_is_exempt(self, fake_repo: Path) -> None:
        r"""r'python\s+scripts/' has ``\s`` (a backslash-escape) and must be exempt."""
        _write(
            fake_repo,
            ".claude/skills/foo/validate_skill.py",
            "count = re.findall(r'python\\s+scripts/', content)\n",
        )
        assert cvp.collect_offenders(fake_repo) == []

    def test_plain_scripts_path_without_metachar_is_still_offender(self, fake_repo: Path) -> None:
        """r"scripts/foo.py" has no metachar and must still be flagged.

        Isolating negative control: this proves the broader metachar check
        does not accidentally exempt simple path strings written as raw strings.
        """
        _write(
            fake_repo,
            ".claude/skills/foo/bad.py",
            'path = r"scripts/validation/check.py"\n',
        )
        offenders = cvp.collect_offenders(fake_repo)
        assert len(offenders) == 1
        assert offenders[0].relpath == ".claude/skills/foo/bad.py"


class TestProseStringExemption:
    """Sentence-like and multi-line literals are treated as prose, not paths.

    Recommendation strings, error messages, and template constants that
    mention ``scripts/`` as a concept (not a path to open) should not be
    flagged.  Isolating negative control: adding a ``not _is_prose_string``
    guard removal breaks these assertions.
    """

    def test_space_containing_string_is_exempt(self, fake_repo: Path) -> None:
        """A recommendation string with a space is exempt."""
        _write(
            fake_repo,
            ".claude/skills/foo/audit.py",
            'recs.append("Extract logic to scripts/ subdirectory.")\n',
        )
        assert cvp.collect_offenders(fake_repo) == []

    def test_diagnostic_message_without_punctuation_is_exempt(self, fake_repo: Path) -> None:
        """A validator diagnostic may mention scripts/ without punctuation."""
        _write(
            fake_repo,
            ".claude/skills/foo/validate.py",
            'self.check("presence", False, "scripts/ directory does not exist")\n',
        )
        assert cvp.collect_offenders(fake_repo) == []

    def test_no_space_scripts_path_is_offender(self, fake_repo: Path) -> None:
        """A path string with no space is still flagged.

        Isolating negative control: proves the prose exemption does not
        cover compact paths like ``"scripts/run.py"`` that could be a real
        file the program opens.
        """
        _write(
            fake_repo,
            ".claude/skills/foo/bad.py",
            'result = open("scripts/run.py")\n',
        )
        offenders = cvp.collect_offenders(fake_repo)
        assert len(offenders) == 1
        assert offenders[0].relpath == ".claude/skills/foo/bad.py"

    def test_shell_command_with_spaces_is_offender(self, fake_repo: Path) -> None:
        """Spaces do not exempt a path passed to a shell command."""
        _write(
            fake_repo,
            ".claude/skills/foo/bad.py",
            'subprocess.run(".claude/lib/paths.py --check", shell=True)\n',
        )

        offenders = cvp.collect_offenders(fake_repo)

        assert len(offenders) == 1
        assert offenders[0].relpath == ".claude/skills/foo/bad.py"

    def test_os_system_command_with_spaces_is_offender(self, fake_repo: Path) -> None:
        """A command prefix before scripts/ remains visible to the gate."""
        _write(
            fake_repo,
            ".claude/skills/foo/bad.py",
            'os.system("python scripts/session_log.py")\n',
        )

        offenders = cvp.collect_offenders(fake_repo)

        assert len(offenders) == 1
        assert offenders[0].relpath == ".claude/skills/foo/bad.py"

    def test_fstring_command_with_spaces_is_offender(self, fake_repo: Path) -> None:
        """An f-string command does not become prose because it has spaces."""
        _write(
            fake_repo,
            ".claude/skills/foo/bad.py",
            'cmd = f"cat .agents/AGENT-INSTRUCTIONS.md {mode}"\n',
        )

        offenders = cvp.collect_offenders(fake_repo)

        assert len(offenders) == 1
        assert offenders[0].relpath == ".claude/skills/foo/bad.py"


class TestTestsDirectoryExclusion:
    """Files in ``tests/`` directories are excluded from the scan.

    Test files run only in the development checkout where all upstream paths
    are present.  A hard-coded path in a test fixture cannot fail a consumer
    install, so scanning them produces only false positives.
    Issue #4046 adds an explicit exclusion.
    Isolating negative control: removing ``"tests" in py_file.parts`` from
    ``collect_offenders`` breaks the first assertion here.
    """

    def test_scripts_path_in_tests_dir_is_not_offender(self, fake_repo: Path) -> None:
        """A hard-coded scripts/ path inside a tests/ subdir is not flagged."""
        _write(
            fake_repo,
            ".claude/skills/foo/tests/test_foo.py",
            'threads.append(_thread("sess", "scripts/session_log.py", body))\n',
        )
        assert cvp.collect_offenders(fake_repo) == []

    def test_agents_path_in_tests_dir_is_not_offender(self, fake_repo: Path) -> None:
        """.agents/ inside a tests/ subdir is also excluded."""
        _write(
            fake_repo,
            ".claude/skills/foo/tests/test_bar.py",
            'assert is_valid(".agents/AGENT-INSTRUCTIONS.md")\n',
        )
        assert cvp.collect_offenders(fake_repo) == []

    def test_scripts_path_outside_tests_dir_is_offender(self, fake_repo: Path) -> None:
        """The same compact path in a non-test file is still flagged.

        Isolating negative control: the tests/ exclusion is scoped to the
        ``tests`` directory component, not to file names starting with ``test_``.
        A ``scripts/test_foo.py`` file (in the scripts/ dir) is still scanned.
        """
        _write(
            fake_repo,
            ".claude/skills/foo/scripts/worker.py",
            'path = "scripts/session_log.py"\n',
        )
        offenders = cvp.collect_offenders(fake_repo)
        assert len(offenders) == 1
        assert offenders[0].relpath == ".claude/skills/foo/scripts/worker.py"

    def test_tests_ancestor_does_not_disable_scan(self, tmp_path: Path) -> None:
        """Only repo-relative tests directories are excluded."""
        repo_root = tmp_path / "tests" / "repo"
        _write(
            repo_root,
            ".claude/skills/foo/scripts/worker.py",
            'path = "scripts/session_log.py"\n',
        )

        offenders = cvp.collect_offenders(repo_root)

        assert len(offenders) == 1
        assert offenders[0].relpath == ".claude/skills/foo/scripts/worker.py"
