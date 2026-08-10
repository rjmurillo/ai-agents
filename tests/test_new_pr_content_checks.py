"""Content guard tests: dash check, escaped newlines, and output codec.

Split from the former single ``tests/test_new_pr.py`` (issue #4764), which had
grown to 1,390 lines and mixed unrelated responsibilities in one module. The
shared import of the script under test and the subprocess helpers live in
``tests/new_pr_harness.py`` so no module re-derives them.
"""

from __future__ import annotations

import ast
import codecs
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.new_pr_harness import (
    SCRIPTS_DIR,
    run_validations,
)
from tests.new_pr_harness import (
    completed as _completed,
)

_SCRIPTS_DIR = SCRIPTS_DIR


class TestValidation5DashCheck:
    """Tests for Validation 5: em/en-dash guard on PR title and body."""

    def test_clean_title_and_body_passes(self, tmp_path, capsys):
        """No dashes in either title or body, run_validations completes."""
        with patch(
            "subprocess.run",
            return_value=_completed(stdout="src/main.py\n", rc=0),
        ):
            run_validations(
                str(tmp_path), "main", "feat/branch",
                title="feat: clean title",
                body="body without dashes",
            )
        out = capsys.readouterr()
        assert "No prohibited characters" in out.out

    def test_em_dash_in_title_blocks(self, tmp_path):
        """Em-dash in title raises SystemExit(1)."""
        with patch(
            "subprocess.run",
            return_value=_completed(stdout="src/main.py\n", rc=0),
        ):
            try:
                run_validations(
                    str(tmp_path), "main", "feat/branch",
                    title=f"feat: bad {chr(0x2014)} title",
                    body="clean body",
                )
            except SystemExit as e:
                assert e.code == 1
                return
            raise AssertionError("Expected SystemExit(1)")

    def test_en_dash_in_body_blocks(self, tmp_path):
        """En-dash in body raises SystemExit(1)."""
        with patch(
            "subprocess.run",
            return_value=_completed(stdout="src/main.py\n", rc=0),
        ):
            try:
                run_validations(
                    str(tmp_path), "main", "feat/branch",
                    title="feat: clean",
                    body=f"range {chr(0x2013)} 10",
                )
            except SystemExit as e:
                assert e.code == 1
                return
            raise AssertionError("Expected SystemExit(1)")

    def test_dash_in_body_file_blocks(self, tmp_path):
        """Em-dash in body-file path raises SystemExit(1)."""
        body_file = tmp_path / "body.md"
        body_file.write_text(
            f"# Body\n\nLine with em-dash {chr(0x2014)} here\n",
            encoding="utf-8",
        )
        with patch(
            "subprocess.run",
            return_value=_completed(stdout="src/main.py\n", rc=0),
        ):
            try:
                run_validations(
                    str(tmp_path), "main", "feat/branch",
                    title="feat: clean",
                    body_file=str(body_file),
                )
            except SystemExit as e:
                assert e.code == 1
                return
            raise AssertionError("Expected SystemExit(1)")

    def test_em_dash_error_message_includes_line_number(self, tmp_path, capsys):
        """Error stderr includes specific line numbers for actionable output."""
        with patch(
            "subprocess.run",
            return_value=_completed(stdout="src/main.py\n", rc=0),
        ):
            try:
                run_validations(
                    str(tmp_path), "main", "feat/branch",
                    title="feat: clean",
                    body=f"line 1 clean\nline 2 has {chr(0x2014)} dash\nline 3 clean\n",
                )
            except SystemExit:
                pass
            stderr = capsys.readouterr().err
            assert "line 2" in stderr
            # After refactor (commit 467353d0) to use validate_no_dashes from
            # scripts.validation.pr_description, the error wording is
            # "PR description contains U+2014 or U+2013 (line N). ..."
            assert "U+2014" in stderr or "U+2013" in stderr


class TestValidation6EscapedNewlineCheck:
    """Validation 6 rejects an inline body whose line breaks are literal.

    Issue #3777. Two issues (#3598, #3646) shipped with every line break
    written as the two characters backslash and n, so GitHub rendered each as
    one unbroken paragraph and dropped every heading, list and table.

    new_pr.py carries a second copy of the predicate rather than importing
    scripts/github_core/validation.py::escaped_newline_body_error, because
    new_pr.py resolves only its own directory on sys.path and a lib bootstrap
    would hard-exit 2 whenever .claude/lib is absent on the push path. These
    tests pin the copy; tests/test_github_core.py pins the canonical version.
    """

    @staticmethod
    def _validate(tmp_path, *, body, body_file=None):
        with patch(
            "subprocess.run",
            return_value=_completed(stdout="src/main.py\n", rc=0),
        ):
            run_validations(
                str(tmp_path), "main", "feat/branch",
                title="feat: clean title",
                body=body,
                body_file=body_file,
            )

    def test_escaped_newlines_with_no_real_break_blocks(self, tmp_path):
        with pytest.raises(SystemExit) as excinfo:
            self._validate(tmp_path, body="## Summary\\n\\nDetail\\n- item")
        assert excinfo.value.code == 1

    def test_error_names_the_count_and_the_remedy(self, tmp_path, capsys):
        with pytest.raises(SystemExit):
            self._validate(tmp_path, body="a\\nb\\nc")
        err = capsys.readouterr().err
        assert "2 literal backslash-n" in err
        assert "--body-file" in err

    def test_trailing_newline_only_body_still_blocks(self, tmp_path):
        """The measured shape of #3598: 15 escapes plus 1 real newline."""
        with pytest.raises(SystemExit) as excinfo:
            self._validate(tmp_path, body="## Summary\\n\\nDetail\\n" + "\n")
        assert excinfo.value.code == 1

    def test_escaped_newline_inside_a_real_multiline_body_passes(
        self, tmp_path, capsys
    ):
        self._validate(
            tmp_path, body='## Notes\n\n```python\nprint("a\\nb")\n```\n'
        )
        assert "Body line breaks are real newlines" in capsys.readouterr().out

    def test_normal_body_passes(self, tmp_path, capsys):
        self._validate(tmp_path, body="## Summary\n\nDetail\n")
        assert "Body line breaks are real newlines" in capsys.readouterr().out

    def test_single_line_body_without_escapes_passes(self, tmp_path, capsys):
        self._validate(tmp_path, body="Just one line.")
        assert "Body line breaks are real newlines" in capsys.readouterr().out

    def test_body_file_contents_are_checked_too(self, tmp_path):
        """--body-file is the recommended remedy, so it must not be a bypass."""
        path = tmp_path / "body.md"
        path.write_text("## Summary\\n\\nDetail", encoding="utf-8")
        with pytest.raises(SystemExit) as excinfo:
            self._validate(tmp_path, body="", body_file=str(path))
        assert excinfo.value.code == 1

    def test_quoted_canonical_predicate_is_verbatim(self):
        """The docstring calls its quote verbatim, so check it against source.

        The first version of this quote was a fragment: it omitted the
        ``if not body`` guard, so "verbatim" was false. The docstring was
        also a non-raw string, which turned the quoted ``"\\n"`` into a real
        newline at runtime, so even the fragment was not reproduced. Both
        defects are invisible to a reader who trusts the word "verbatim",
        which is why this compares the two texts instead.
        """
        import ast
        import textwrap

        repo_root = Path(__file__).resolve().parent.parent
        canonical = repo_root / "scripts" / "github_core" / "validation.py"
        tree = ast.parse(canonical.read_text(encoding="utf-8"))
        func = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef)
            and n.name == "escaped_newline_body_error"
        )
        # Skip the docstring statement; the quote covers the code that follows.
        body_start = func.body[1].lineno
        lines = canonical.read_text(encoding="utf-8").splitlines()

        for mirror in (
            ".claude/skills/github/scripts/pr/validate_pr_description.py",
            "src/copilot-cli/skills/github/scripts/pr/validate_pr_description.py",
        ):
            mod = ast.parse((repo_root / mirror).read_text(encoding="utf-8"))
            copy = next(
                n
                for n in ast.walk(mod)
                if isinstance(n, ast.FunctionDef)
                and n.name == "validate_no_escaped_newlines"
            )
            doc = ast.get_docstring(copy, clean=False)
            assert doc is not None, mirror
            marker = "body::"
            assert marker in doc, f"{mirror}: citation marker missing"
            quoted = textwrap.dedent(
                doc.split(marker, 1)[1].split("\n\n", 2)[1]
            ).strip("\n")
            quoted_lines = quoted.splitlines()
            # Without this, an empty quote would compare [] to [] and pass.
            assert len(quoted_lines) >= 5, (
                f"{mirror}: quote too short to be the guard plus predicate: "
                f"{quoted_lines!r}"
            )
            actual = [
                line[4:] for line in lines[body_start - 1 : body_start - 1 + len(quoted_lines)]
            ]
            assert quoted_lines == actual, (
                f"{mirror}: quote is not verbatim.\n"
                f"quoted={quoted_lines!r}\nactual={actual!r}"
            )

    def test_chain_is_renumbered_to_six_steps(self, tmp_path, capsys):
        self._validate(tmp_path, body="## Summary\n\nDetail\n")
        out = capsys.readouterr().out
        for step in range(1, 7):
            assert f"[{step}/6]" in out, f"missing step {step}/6"


# ---------------------------------------------------------------------------
# Tests: _resolve_validation_base (issues #4461, #4489)
# ---------------------------------------------------------------------------


class TestCapturedOutputPinsItsCodec:
    """Every capturing subprocess.run must pin utf-8, on both mirrors.

    subprocess.run(text=True) with no encoding decodes with
    locale.getpreferredencoding(False). On Windows that is cp1252, and the
    reader thread raises UnicodeDecodeError on the UTF-8 bytes git and gh
    routinely emit (branch names, commit subjects, gh's status glyphs). The
    exception surfaces in a helper thread rather than the caller, so
    subprocess.run returns with stdout set to None instead of raising. Callers
    that then do result.stdout.strip() die with AttributeError; callers that
    check truthiness silently treat a crashed tool as one that printed nothing.

    That last shape is the exact failure issue #3391 exists to prevent, so this
    file must not reintroduce it. An AST check rather than a grep so a new call
    site is covered the day it is written.

    Scoped to calls that both capture and decode. A run() with no capture
    inherits the parent's stdio and never decodes, so text= is inert there and
    the codec is not its concern.
    """

    # Every file in the push-pr bundle that spawns a capturing subprocess.
    # pr_validations.py joined the list in issue #4764 when new_pr.py was split
    # for cohesion: two capturing calls moved with the validation pipeline, and
    # a mirror list that did not follow them would have silently stopped
    # checking the moved code while every assertion here stayed green.
    _MIRRORS = (
        Path(__file__).resolve().parents[1]
        / ".claude" / "skills" / "github" / "scripts" / "pr" / "new_pr.py",
        Path(__file__).resolve().parents[1]
        / "src" / "copilot-cli" / "skills" / "github" / "scripts" / "pr" / "new_pr.py",
        Path(__file__).resolve().parents[1]
        / ".claude" / "skills" / "github" / "scripts" / "pr" / "pr_validations.py",
        Path(__file__).resolve().parents[1]
        / "src" / "copilot-cli" / "skills" / "github" / "scripts" / "pr"
        / "pr_validations.py",
    )

    @staticmethod
    def _set_true(kwargs: dict[str, ast.expr], name: str) -> bool:
        """True when the keyword is present and spelled as a truthy literal."""
        value = kwargs.get(name)
        return isinstance(value, ast.Constant) and bool(value.value)

    @staticmethod
    def _pins_utf8(encoding: ast.expr | None) -> bool:
        """True when encoding= resolves to the canonical UTF-8 codec."""
        if not isinstance(encoding, ast.Constant) or not isinstance(encoding.value, str):
            return False
        try:
            return codecs.lookup(encoding.value).name == "utf-8"
        except LookupError:
            return False

    @staticmethod
    def _capturing_runs(source: str):
        """(lineno, {kwarg names}) for each subprocess.run that decodes output."""
        found = []
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "run"):
                continue
            if not (isinstance(func.value, ast.Name) and func.value.id == "subprocess"):
                continue
            kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
            set_true = TestCapturedOutputPinsItsCodec._set_true
            captures = (
                set_true(kwargs, "capture_output")
                or "stdout" in kwargs
                or "stderr" in kwargs
            )
            decodes = (
                set_true(kwargs, "text")
                or set_true(kwargs, "universal_newlines")
                or "encoding" in kwargs
                or "errors" in kwargs
            )
            if captures and decodes:
                present = set(kwargs)
                if not TestCapturedOutputPinsItsCodec._pins_utf8(kwargs.get("encoding")):
                    present.discard("encoding")
                found.append((node.lineno, present))
        return found

    @pytest.mark.parametrize("mirror", _MIRRORS, ids=lambda p: p.parts[-6])
    def test_every_capturing_run_pins_utf8(self, mirror):
        offenders = [
            lineno
            for lineno, kwargs in self._capturing_runs(mirror.read_text(encoding="utf-8"))
            if "encoding" not in kwargs
        ]
        assert not offenders, (
            f"{mirror}: subprocess.run at line(s) {offenders} captures and decodes "
            "output without encoding='utf-8'; this crashes the reader thread on "
            "Windows cp1252 and returns stdout=None"
        )

    @pytest.mark.parametrize("mirror", _MIRRORS, ids=lambda p: p.parts[-6])
    def test_every_capturing_run_survives_undecodable_bytes(self, mirror):
        """errors= must be set too: a pinned codec still raises without it."""
        offenders = [
            lineno
            for lineno, kwargs in self._capturing_runs(mirror.read_text(encoding="utf-8"))
            if "errors" not in kwargs
        ]
        assert not offenders, (
            f"{mirror}: subprocess.run at line(s) {offenders} pins a codec but no "
            "errors= policy, so undecodable bytes raise instead of degrading"
        )

    def test_the_check_finds_something_to_check(self):
        """Vacuity control: an AST walk that matches nothing proves nothing.

        Counts across the whole bundle rather than one file. new_pr.py held six
        capturing calls before issue #4764 split it; two moved to
        pr_validations.py, so a per-file threshold would now fail for a reason
        that has nothing to do with the property under test.
        """
        total = sum(
            len(self._capturing_runs(mirror.read_text(encoding="utf-8")))
            for mirror in self._MIRRORS
        )
        assert total >= 10, f"walker found only {total} capturing subprocess.run calls"

    def test_a_bare_text_run_is_reported(self):
        """Negative control on the walker itself."""
        offenders = self._capturing_runs(
            "import subprocess\nsubprocess.run(['x'], capture_output=True, text=True)\n"
        )
        assert offenders == [(2, {"capture_output", "text"})]

    def test_errors_alone_run_is_reported(self):
        """errors= alone enables text mode through the locale codec."""
        offenders = self._capturing_runs(
            "import subprocess\nsubprocess.run(['x'], capture_output=True, errors='ignore')\n"
        )
        assert offenders == [(2, {"capture_output", "errors"})]

    def test_errors_with_encoding_is_not_an_encoding_offender(self):
        """errors= with encoding= pins the codec and stays quiet."""
        runs = self._capturing_runs(
            "import subprocess\n"
            "subprocess.run(['x'], capture_output=True, encoding='utf-8', errors='ignore')\n"
        )
        offenders = [lineno for lineno, kwargs in runs if "encoding" not in kwargs]
        assert offenders == []

    def test_utf8_codec_aliases_are_not_encoding_offenders(self):
        """Python codec aliases that resolve to UTF-8 still pin the codec."""
        source = "\n".join(
            [
                "import subprocess",
                *(
                    "subprocess.run(['x'], capture_output=True, "
                    f"encoding={alias!r}, errors='replace')"
                    for alias in ("UTF-8", "utf8", "UTF8", "utf_8", "U8")
                ),
            ]
        )
        runs = self._capturing_runs(source)

        offenders = [lineno for lineno, kwargs in runs if "encoding" not in kwargs]

        assert len(runs) == 5
        assert offenders == []

    @pytest.mark.parametrize("codec", ("latin-1", "utf-8-sig", "not-a-codec"))
    def test_non_utf8_codecs_are_encoding_offenders(self, codec):
        """Non-UTF-8 codecs still fail the pinned-codec guard."""
        runs = self._capturing_runs(
            "import subprocess\n"
            f"subprocess.run(['x'], capture_output=True, encoding={codec!r}, errors='replace')\n"
        )
        offenders = [lineno for lineno, kwargs in runs if "encoding" not in kwargs]

        assert offenders == [2]

    def test_a_non_capturing_run_is_out_of_scope(self):
        """text= without capture never decodes, so it is not this rule's business."""
        assert self._capturing_runs(
            "import subprocess\nsubprocess.run(['x'], text=True, check=False)\n"
        ) == []


# ---------------------------------------------------------------------------
# Tests: Validation 6 (escaped-newline check on body, Issue #3777)
# ---------------------------------------------------------------------------
