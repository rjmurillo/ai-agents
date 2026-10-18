"""Detector-level coverage for `scan_vulnerabilities.py` (CWE-78 scanner).

Scope: the regex detector and its helpers, complementary to the focused CLI
regression suite in `tests/test_security_scan_cli.py`. That file pins the
CWE-22-delegation behavior, path validation, and JSON envelope. This file
covers the detector itself: every CWE-78 pattern across Python, PowerShell,
Bash, and C#; negative cases that must NOT fire; the per-line suppression
mechanism; and the language-detection and file-reading helpers. The broad
coverage gap was tracked at issue #1849.

These tests assert what the detector does today (characterization), not what
an idealized detector would do. Where the regex has a known weakness (it
flags commented-out code, and its "string concatenation" pattern only fires
on a `+` inside the quoted argument rather than on real concatenation), the
test documents the actual behavior in its name and docstring rather than
encoding an imagined contract. See `.claude/rules/canonical-source-mirror.md`
and the working-with-legacy-code reference in `software-engineering-library`.

The module under test lives outside the package tree, so it is loaded by path
via `importlib`. `conftest.py` already puts the repo root on `sys.path`; the
scanner script imports only stdlib, so a path-based load is safe and avoids a
dependency on the script being importable as a package.

CLI exit-code tests invoke the scanner as a subprocess (the only way to
observe `sys.exit` codes) with `cwd=tmp_path` so the scanner's path-traversal
`allowed_base` resolves to the same directory the fixtures are written under.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCANNER_PATH = (
    REPO_ROOT / ".claude" / "skills" / "security-scan" / "scripts" / "scan_vulnerabilities.py"
)


def _load_scanner() -> ModuleType:
    """Load the scanner module by path (it is not on the package tree)."""
    spec = importlib.util.spec_from_file_location("scan_vulnerabilities", SCANNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scanner = _load_scanner()


def test_path_based_import_removes_temporary_sibling_import_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Path-based import must not leave the scanner directory on sys.path."""
    script_dir = str(SCANNER_PATH.parent)
    monkeypatch.setattr(
        sys,
        "path",
        [entry for entry in sys.path if entry != script_dir],
    )
    for module_name in [
        "scan_bash_lexer",
        "scan_constants",
        "scan_format",
        "scan_patterns",
        "scan_vulnerabilities_path_isolation",
    ]:
        monkeypatch.delitem(sys.modules, module_name, raising=False)

    spec = importlib.util.spec_from_file_location(
        "scan_vulnerabilities_path_isolation",
        SCANNER_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "scan_vulnerabilities_path_isolation", module)
    spec.loader.exec_module(module)

    assert script_dir not in sys.path


def _descriptions_for(language: str, line: str) -> list[str]:
    """Return descriptions of every CWE-78 pattern that matches `line`.

    This bypasses `scan_file`'s per-line `break` so a single line can be
    checked against the whole pattern set for a language. Used by the
    parametrized positive and negative pattern tests.
    """
    return _descriptions_for_lines(language, [line])[0]


def _descriptions_for_lines(language: str, lines: list[str]) -> list[list[str]]:
    """Return, per line, descriptions of every CWE-78 pattern that matches it.

    A pattern with a `scrub_lines` hook sees the whole `lines` list at once, so
    quote and here-document state carries across lines as it does in `scan_file`.
    """
    matched: list[list[str]] = [[] for _ in lines]
    for info in scanner.CWE78_PATTERNS[language]:
        pattern = cast(re.Pattern[str], info["pattern"])
        scrub_lines = cast(Callable[[Sequence[str]], list[str]] | None, info.get("scrub_lines"))
        prepared = scrub_lines(lines) if scrub_lines else lines
        for index, text in enumerate(prepared):
            if pattern.search(text):
                matched[index].append(str(info["description"]))
    return matched


def _write(tmp_path: Path, name: str, body: str) -> str:
    """Write `body` to `tmp_path/name` and return the bare filename.

    Returning the filename (not the absolute path) lets callers invoke the
    scanner with `cwd=tmp_path` so its `allowed_base` containment check
    accepts the file.
    """
    (tmp_path / name).write_text(body, encoding="utf-8")
    return name


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("module.py", "python"),
        ("Deploy.ps1", "powershell"),
        ("Helpers.psm1", "powershell"),
        ("setup.sh", "bash"),
        ("run.bash", "bash"),
        ("Program.cs", "csharp"),
        ("UPPER.PY", "python"),
        ("notes.txt", None),
        ("Dockerfile", None),
        ("archive.tar.gz", None),
    ],
)
def test_get_language_maps_extension(filename: str, expected: str | None) -> None:
    assert scanner.get_language(str(Path(__file__).parent / filename)) == expected


def test_get_language_detects_extensionless_bash_shebang(tmp_path: Path) -> None:
    hook = tmp_path / "pre-push"
    hook.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$msg\"\n", encoding="utf-8")

    assert scanner.get_language(str(hook)) == "bash"


def test_get_language_ignores_extensionless_non_bash_shebang(tmp_path: Path) -> None:
    script = tmp_path / "utility"
    script.write_text("#!/usr/bin/env python3\nprint('ok')\n", encoding="utf-8")

    assert scanner.get_language(str(script)) is None


# ---------------------------------------------------------------------------
# CWE-78 positive detections, one parametrize per language
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "description", "severity"),
    [
        (
            'subprocess.run(f"ls {target}")',
            "Subprocess with f-string command (potential injection)",
            "CRITICAL",
        ),
        (
            "subprocess.call(cmd, shell=True)",
            "Subprocess with shell=True",
            "HIGH",
        ),
        (
            'subprocess.Popen(f"echo {x}")',
            "Subprocess with f-string command (potential injection)",
            "CRITICAL",
        ),
        (
            "eval(user_input)",
            "eval() with potentially unvalidated input",
            "CRITICAL",
        ),
        (
            "exec(command_blob)",
            "exec() with potentially unvalidated input",
            "CRITICAL",
        ),
    ],
)
def test_python_patterns_match(line: str, description: str, severity: str) -> None:
    assert description in _descriptions_for("python", line)
    info = next(i for i in scanner.CWE78_PATTERNS["python"] if i["description"] == description)
    assert info["severity"] == severity


@pytest.mark.parametrize(
    ("line", "description", "severity"),
    [
        (
            'Invoke-Expression "run $thing"',
            "Invoke-Expression with variable interpolation",
            "CRITICAL",
        ),
        (
            "Invoke-Expression $userInput",
            "Invoke-Expression with potentially unvalidated input",
            "CRITICAL",
        ),
        (
            "& $commandPath",
            "Call operator with potentially unvalidated command",
            "HIGH",
        ),
        (
            "Start-Process notepad -ArgumentList $userArgs",
            "Start-Process with potentially unvalidated arguments",
            "HIGH",
        ),
    ],
)
def test_powershell_patterns_match(line: str, description: str, severity: str) -> None:
    assert description in _descriptions_for("powershell", line)
    info = next(i for i in scanner.CWE78_PATTERNS["powershell"] if i["description"] == description)
    assert info["severity"] == severity


@pytest.mark.parametrize(
    ("line", "description", "severity"),
    [
        ('eval "$cmd"', "eval with variable expansion", "CRITICAL"),
        (
            "result=$( $userCommand )",
            "Command substitution with potentially unvalidated input",
            "CRITICAL",
        ),
        (
            "result=`$userInput`",
            "Backtick command substitution with potentially unvalidated input",
            "CRITICAL",
        ),
        (
            "echo $unquoted",
            "Unquoted variable expansion (potential word splitting/injection)",
            "MEDIUM",
        ),
    ],
)
def test_bash_patterns_match(line: str, description: str, severity: str) -> None:
    assert description in _descriptions_for("bash", line)
    info = next(i for i in scanner.CWE78_PATTERNS["bash"] if i["description"] == description)
    assert info["severity"] == severity


@pytest.mark.parametrize(
    ("line", "description", "severity"),
    [
        (
            "Process.Start(userCommand);",
            "Process.Start with potentially unvalidated command",
            "HIGH",
        ),
        (
            'var psi = new ProcessStartInfo { Arguments = $"-c {y}" };',
            "ProcessStartInfo with interpolated arguments",
            "HIGH",
        ),
        (
            "var p = new Process() { FileName = userCmd };",
            "Process with potentially unvalidated FileName",
            "HIGH",
        ),
    ],
)
def test_csharp_patterns_match(line: str, description: str, severity: str) -> None:
    assert description in _descriptions_for("csharp", line)
    info = next(i for i in scanner.CWE78_PATTERNS["csharp"] if i["description"] == description)
    assert info["severity"] == severity


# ---------------------------------------------------------------------------
# Severity is carried through to the Vulnerability record
# ---------------------------------------------------------------------------


def test_scan_file_populates_vulnerability_fields(tmp_path: Path) -> None:
    name = _write(
        tmp_path,
        "iex.ps1",
        "Invoke-Expression $userInput\n",
    )
    vulns, suppressed = scanner.scan_file(str(tmp_path / name))
    assert suppressed == []
    assert len(vulns) == 1
    vuln = vulns[0]
    assert vuln.cwe == "CWE-78"
    assert vuln.title == "Command Injection Vulnerability"
    assert vuln.line == 1
    assert vuln.severity == "CRITICAL"
    assert vuln.code == "Invoke-Expression $userInput"
    assert "Invoke-Expression" in vuln.pattern


# ---------------------------------------------------------------------------
# Negative cases: safe constructs must NOT be flagged
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("language", "line"),
    [
        ("python", 'subprocess.run(["ls", "-l"])'),
        ("python", "subprocess.run(args, shell=False)"),
        ("python", 'subprocess.run(["git", "status"], check=True)'),
        ("python", 'eval("1 + 1")'),
        ("python", "x = compute(value)"),
        ("powershell", 'Write-Output "done"'),
        ("powershell", "Get-ChildItem -Path $home"),
        ("bash", 'echo "$quoted"'),
        ("bash", 'printf "%s\\n" "$value"'),
        ("csharp", 'Console.WriteLine("hello");'),
        ("csharp", "var total = a + b;"),
    ],
)
def test_safe_lines_not_flagged(language: str, line: str) -> None:
    assert _descriptions_for(language, line) == []


# ---------------------------------------------------------------------------
# Bash unquoted-variable false positives (issue #6294)
# ---------------------------------------------------------------------------

UNQUOTED_VAR = "Unquoted variable expansion (potential word splitting/injection)"


@pytest.mark.parametrize(
    "line",
    [
        # Positive controls from the issue: comment, quoted argument, quoted assignment.
        "# Config lives under $HOME",
        'echo "Starting MCP for $server at $(date)"',
        'export X="${X:-$PWD/.hindsight}"',
        # Comment forms.
        "    # indented comment with $var",
        "cmd arg # trailing comment with $var",
        "\t# tab-indented comment $var",
        # Single quotes keep `$` literal.
        "echo 'literal $var here'",
        "grep -E '^foo$bar' file",
        # Escapes: an escaped quote does not close the span, an escaped `$` is literal.
        'echo "say \\"hi\\" to $name"',
        "echo \\$literal",
        # Mixed adjacent spans.
        'echo "$a" \'$b\' "$c"',
        # `#` that does not start a comment: `$#` is a variable, `${#x}` is a length.
        'echo "$#"',
        'echo "${#items[@]}"',
        # Quoted `$()` inside double quotes with only quoted variables in the body.
        'echo "at $(date +%s) for $user"',
        'result="$(basename "$path")"',
        # Quoted variable in a backtick body inside double quotes.
        'echo "files: `ls "$dir"` for $user"',
        'echo "at `date` for $user"',
        # `$'...'` ANSI-C quoting keeps `$` literal, escapes included.
        "echo $'literal $var here'",
        "echo $'it\\'s $var'",
    ],
)
def test_bash_unquoted_var_ignores_comments_and_quoted_spans(line: str) -> None:
    assert UNQUOTED_VAR not in _descriptions_for("bash", line)


@pytest.mark.parametrize(
    "line",
    [
        "rm $target",
        "echo $unquoted",
        "cmd arg$var",
        "cmd a#b $var",
        'echo "done" $after',
        "echo 'x' $after",
        # An unquoted variable sits in the body of a `$()` inside double quotes.
        'echo "files: $(ls $dir)"',
        'out="$(rm $target)"',
        # Nested parens in a command substitution still close at the right paren.
        'echo "$( (cd /x) ; ls $dir )"',
        # Backtick substitution inside double quotes runs as unquoted shell.
        'echo "files: `ls $dir`"',
        'out="`rm $target`"',
        # A stray `)` inside a backtick body does not end the body.
        'echo "`echo ) ; ls $dir`"',
        # `$'...'` ANSI-C quoting: `\\'` is an escaped quote, so `$x` is unquoted.
        "echo $'it\\'s' $x",
        # A line that closes a multi-line double-quoted string: the closing quote
        # is not an opening quote, so code after it stays visible.
        'closing words" ; rm $target',
        "closing words' ; rm $target",
        # A comment later in the line does not hide an earlier unquoted variable.
        "rm $target # cleanup",
        # `$#` followed by text; the `#` is not a comment start.
        "echo $#x $y",
    ],
)
def test_bash_unquoted_var_still_flags_real_unquoted_expansion(line: str) -> None:
    assert UNQUOTED_VAR in _descriptions_for("bash", line)


@pytest.mark.parametrize(
    "line",
    [
        "",
        "\n",
        "#",
        '"',
        "'",
        'echo "unterminated $var',
        "echo 'unterminated $var",
        "echo \\",
        "echo $(",
        "echo )",
    ],
)
def test_bash_scrub_handles_degenerate_lines(line: str) -> None:
    scrubbed = scanner.scrub_bash_line(line)
    assert len(scrubbed) <= len(line)


@pytest.mark.parametrize(
    "line",
    [
        'echo "unterminated $var',
        "echo 'unterminated $var",
        'echo "$(ls $dir',
        'echo "`ls $dir',
        "echo $'unterminated $var",
        'closing" ; rm $target',
    ],
)
def test_bash_scrub_returns_raw_line_when_quote_state_is_unresolved(line: str) -> None:
    """A quote left open at end of line may be an opener or a closer; do not guess."""
    assert scanner.scrub_bash_line(line) == line


def test_scan_file_flags_code_after_closing_quote_of_multiline_string(tmp_path: Path) -> None:
    body = 'echo "first $a\nsecond line" ; rm $target\n'
    name = _write(tmp_path, "multiline.sh", body)
    vulns, _ = scanner.scan_file(str(tmp_path / name))
    # Line 1 opens the string, so its `$a` is quoted. Only the code after the
    # closing quote on line 2 is unquoted.
    assert [v.line for v in vulns if v.pattern == UNQUOTED_VAR] == [2]


def test_bash_scrub_keeps_backtick_body_inside_double_quotes() -> None:
    assert scanner.scrub_bash_line('"a `ls $d` b"') == '"  `ls $d`  "'


def test_bash_scrub_blanks_ansi_c_quoted_body() -> None:
    assert scanner.scrub_bash_line("$'a\\'b' $x") == "$'    ' $x"


def test_bash_scrub_blanks_interiors_and_keeps_delimiters() -> None:
    assert scanner.scrub_bash_line("echo 'ab' \"cd\" $x") == "echo '  ' \"  \" $x"


def test_bash_scrub_keeps_command_substitution_body_inside_double_quotes() -> None:
    assert scanner.scrub_bash_line('"a $(ls $d) b"') == '"  $(ls $d)  "'


def test_bash_scrub_strips_comment_but_keeps_code_before_it() -> None:
    assert scanner.scrub_bash_line("rm $t # note $u").rstrip() == "rm $t"


def test_scan_file_does_not_flag_issue_6294_shapes(tmp_path: Path) -> None:
    body = (
        "#!/usr/bin/env bash\n"
        "# Config lives under $HOME\n"
        'echo "Starting MCP for $server at $(date)"\n'
        'export X="${X:-$PWD/.hindsight}"\n'
    )
    name = _write(tmp_path, "issue6294.sh", body)
    vulns, _ = scanner.scan_file(str(tmp_path / name))
    assert vulns == []


def test_scan_file_still_flags_rm_unquoted_target(tmp_path: Path) -> None:
    body = "# Config lives under $HOME\nrm $target\n"
    name = _write(tmp_path, "rm_target.sh", body)
    vulns, _ = scanner.scan_file(str(tmp_path / name))
    assert [(v.line, v.pattern) for v in vulns] == [(2, UNQUOTED_VAR)]


def test_scan_file_applies_scrub_only_to_unquoted_var_pattern(tmp_path: Path) -> None:
    """`eval "$cmd"` sits inside quotes yet must still be reported as CRITICAL."""
    name = _write(tmp_path, "evalq.sh", 'eval "$cmd"\n')
    vulns, _ = scanner.scan_file(str(tmp_path / name))
    assert [v.severity for v in vulns] == ["CRITICAL"]


# ---------------------------------------------------------------------------
# Bash multi-line quotes and here-documents (issue #6624)
# ---------------------------------------------------------------------------


def _unquoted_lines(tmp_path: Path, body: str) -> list[int]:
    """Scan `body` as a Bash file; return 1-based lines with the unquoted-variable finding."""
    name = _write(tmp_path, "case.sh", body)
    vulns, _ = scanner.scan_file(str(tmp_path / name))
    return [v.line for v in vulns if v.pattern == UNQUOTED_VAR]


def test_scan_file_does_not_flag_issue_6624_single_line_shapes(tmp_path: Path) -> None:
    body = (
        'mkdir -p "$root/home/$dest/skills"\n'
        'cp -r "$root/a/$dest" "$root/b/$dest/c"\n'
        'name="$root/$dest"\n'
        'target="${root}/home/${dest}"\n'
        'echo "Usage: \\$HOME/foo \\$1"\n'
        'echo "Usage: $0 --dest <dir>"\n'
        "count=$((count + 1))\n"
        'echo "$((count + 1))"\n'
    )
    assert _unquoted_lines(tmp_path, body) == []


@pytest.mark.parametrize(
    "body",
    [
        # Closing line of a multi-line double-quoted assignment.
        'msg="line one\ncopies to $dest/skills"\n',
        # Middle line of a three-line double-quoted string.
        'msg="one\ntwo $dest\nthree"\n',
        # Multi-line single-quoted jq program: `$repo` is a jq variable.
        "jq -n --arg repo \"$R\" '{\n  repo: $repo,\n  owner: $owner\n}'\n",
        # Multi-line `$'...'` string.
        "x=$'one\ntwo $dest'\n",
        # Multi-line double-quoted argument with a quoted variable after a continuation.
        'pwsh -Command "\n  Install-Module -RequiredVersion $VERSION -Force\n"\n',
        # Double-quoted string holding a quoted command substitution over several lines.
        'x="$(basename "$p")\nrest $dest"\n',
    ],
)
def test_scan_file_does_not_flag_expansions_inside_multiline_quotes(
    tmp_path: Path, body: str
) -> None:
    assert _unquoted_lines(tmp_path, body) == []


@pytest.mark.parametrize(
    "opener",
    [
        "cat <<'USAGE'",
        'cat <<"USAGE"',
        "cat <<\\USAGE",
        "cat << 'USAGE'",
        "cat > out.txt <<'USAGE'",
    ],
)
def test_scan_file_does_not_flag_quoted_heredoc_body(tmp_path: Path, opener: str) -> None:
    body = f"{opener}\nUsage: $0 --dest <dir>\ncopies to $dest/skills\nUSAGE\n"
    assert _unquoted_lines(tmp_path, body) == []


def test_scan_file_quoted_heredoc_with_dash_strips_leading_tabs_from_terminator(
    tmp_path: Path,
) -> None:
    body = "cat <<-'EOF'\n\tUsage: $0\n\tEOF\nrm $target\n"
    assert _unquoted_lines(tmp_path, body) == [4]


def test_scan_file_heredoc_terminator_with_trailing_blank_does_not_end_body(
    tmp_path: Path,
) -> None:
    """Bash treats `EOF ` as body text, so the body runs on and `rm $x` stays inert."""
    body = "cat <<'EOF'\nbody\nEOF \nrm $x\nEOF\nrm $y\n"
    assert _unquoted_lines(tmp_path, body) == [6]


def test_scan_file_two_heredocs_on_one_line_are_read_in_order(tmp_path: Path) -> None:
    body = "cat <<'A' <<'B'\n$one\nA\n$two\nB\nrm $after\n"
    assert _unquoted_lines(tmp_path, body) == [6]


def test_scan_file_heredoc_inside_command_substitution_hides_apostrophe(
    tmp_path: Path,
) -> None:
    """An apostrophe in the body must not open a quote that swallows later code."""
    body = "msg=$(cat <<EOF\nwhat's the minimum?\nEOF\n)\nrm $target\n"
    assert _unquoted_lines(tmp_path, body) == [5]


def test_scan_file_unquoted_heredoc_apostrophe_does_not_hide_later_code(
    tmp_path: Path,
) -> None:
    body = "cat <<EOF\ndon't panic\nEOF\nrm $target\n"
    assert _unquoted_lines(tmp_path, body) == [4]


def test_scan_file_flags_unquoted_variable_after_closed_multiline_string(
    tmp_path: Path,
) -> None:
    body = 'msg="line one\ncopies to $dest/skills"\nls $dest\n'
    assert _unquoted_lines(tmp_path, body) == [3]


def test_scan_file_flags_command_substitution_inside_multiline_double_quotes(
    tmp_path: Path,
) -> None:
    """`$( )` runs as shell even inside a double-quoted string, on any line of it."""
    body = 'msg="start\n$(rm $target) end\nlast"\n'
    assert _unquoted_lines(tmp_path, body) == [2]


def test_scan_file_flags_unquoted_heredoc_body_expansion_as_before(tmp_path: Path) -> None:
    """An unquoted delimiter expands the body. Keep the per-line behavior."""
    body = "cat <<EOF\nrm $target\nEOF\n"
    assert _unquoted_lines(tmp_path, body) == [2]


def test_scan_file_flags_code_after_heredoc_terminator(tmp_path: Path) -> None:
    body = "cat <<'EOF'\n$inert\nEOF\nrm $target\n"
    assert _unquoted_lines(tmp_path, body) == [4]


@pytest.mark.parametrize(
    "body",
    [
        # Arithmetic shift is not a here-document.
        "x=$((1<<n))\nrm $target\n",
        "(( x = 1 << n ))\nrm $target\n",
        # `<<<` is a here-string.
        "cat <<<$word\nrm $target\n",
        # `<<` inside quotes is text.
        'echo "<<EOF"\nrm $target\n',
        "echo '<<EOF'\nrm $target\n",
        # `<<` in a comment is text.
        "# cat <<EOF\nrm $target\n",
    ],
)
def test_scan_file_non_heredoc_shift_does_not_hide_following_code(
    tmp_path: Path, body: str
) -> None:
    flagged = _unquoted_lines(tmp_path, body)
    assert flagged[-1] == body.count("\n")


@pytest.mark.parametrize(
    "opener",
    ["cat <<!", "cat <<1", "echo 1<<2", "let x=1<<2", "cat <<-1"],
)
def test_scan_file_bare_punctuation_or_digit_delimiter_is_a_heredoc(
    tmp_path: Path, opener: str
) -> None:
    """Bash reads `<<!`, `<<1`, and `1<<2` as here-documents. An apostrophe in
    the body must not open a quote that hides the code after the terminator."""
    delimiter = opener.rsplit("<<", 1)[1].lstrip("-")
    body = f"{opener}\nit's here\n{delimiter}\nrm -rf $danger\n# that's all\n"
    assert _unquoted_lines(tmp_path, body) == [4]


def test_scan_file_digit_delimiter_body_keeps_per_line_scan(tmp_path: Path) -> None:
    """An unquoted delimiter expands the body, so a variable there is still flagged."""
    body = "echo 1<<2\nrm $inbody\n2\nrm $after\n"
    assert _unquoted_lines(tmp_path, body) == [2, 4]


@pytest.mark.parametrize(
    "first",
    [
        "cd /tmp;# don't care",
        "(cd /tmp)# it's",
        "(( 1 ))# it's",
        "ls |# it's",
        "sleep 1 &# it's",
        "ls;;# it's",
    ],
)
def test_scan_file_comment_after_metacharacter_does_not_open_a_quote(
    tmp_path: Path, first: str
) -> None:
    """Bash starts a comment after `;&|()<>`. A later apostrophe closes the
    phantom quote before end of file, so the EOF fallback cannot rescue line 2."""
    body = f"{first}\nrm -rf $danger\n# it's fine\n"
    assert _unquoted_lines(tmp_path, body) == [2]


@pytest.mark.parametrize("first", ["x=$(ls)# it's", "echo $((1))# it's", "arr=(a)# it's"])
def test_scan_file_hash_joining_a_word_leaves_the_apostrophe_a_real_quote(
    tmp_path: Path, first: str
) -> None:
    """After `$(...)`, `$((...))`, or `name=(...)` the `#` is part of the word, so
    bash reads the apostrophe as a real quote that runs to line 3. Line 2 is
    inside that quote and is not an unquoted expansion."""
    body = f"{first}\nrm -rf $danger\n# it's fine\n"
    assert _unquoted_lines(tmp_path, body) == []


@pytest.mark.parametrize(
    "line",
    [
        "echo $(date)#$y",
        "echo $((1))#$y",
        "arr=(a)#$y",
        "cat <(ls)#$y",
        "tee >(cat)#$y",
        "echo $(echo $((1)))#$y",
    ],
)
def test_bash_scrub_hash_after_word_paren_keeps_expansion_visible(line: str) -> None:
    """Bash joins the `#` to the word here, so `$y` expands and must stay flagged."""
    assert "$y" in scanner.scrub_bash_line(line)


@pytest.mark.parametrize(
    "line",
    [
        "(echo a)#$y",
        "( cd /tmp )#$y",
        "(( 1 ))#$y",
        "echo ok; (echo a)#$y",
        "case $x in a)#$y",
    ],
)
def test_bash_scrub_hash_after_subshell_close_is_a_comment(line: str) -> None:
    """A subshell, a `((` command, and a case pattern end the word, so `#` starts a comment."""
    assert "$y" not in scanner.scrub_bash_line(line)


@pytest.mark.parametrize("line", ["echo $(date)#$y", "echo $((1))#$y", "arr=(a)#$y"])
def test_scan_file_flags_expansion_after_word_paren_hash(tmp_path: Path, line: str) -> None:
    assert _unquoted_lines(tmp_path, f"{line}\n") == [1]


@pytest.mark.parametrize(
    ("line", "visible"),
    [
        # `#` after a metacharacter hides the rest of the line.
        ("ls;# $a", False),
        ("(ls)# $a", False),
        # `#` after `$(...)` joins the word, so the variable expands.
        ("x=$(ls)# $a", True),
        ("a|# $a", False),
        ("a&# $a", False),
        # An escaped backslash leaves the `;` live, so the comment still starts.
        ("echo \\\\;# $a", False),
        # An escaped metacharacter does not end the word, so `#` is plain text.
        ("echo \\;#x $a", True),
        # `$#`, `${#x}`, `a#b`, and a base-prefixed number are not comments.
        ("echo $# $a", True),
        ("echo ${#x} $a", True),
        ("echo a#b $a", True),
        ("echo $((16#ff)) $a", True),
        # `#` after a space inside `${...}` is pattern text, not a comment.
        ("echo ${x// #/_} $a", True),
    ],
)
def test_bash_scrub_comment_start_rules(line: str, visible: bool) -> None:
    assert ("$a" in scanner.scrub_bash_line(line)) is visible


def test_scan_file_param_expansion_pattern_is_not_a_heredoc(tmp_path: Path) -> None:
    """Bash runs the next line: `<<'x'` inside `${...}` is pattern text."""
    body = "echo ${s//<<'x'/}\nrm -rf $danger\nx\nrm $after\n"
    assert _unquoted_lines(tmp_path, body) == [2, 4]


@pytest.mark.parametrize(
    "body",
    [
        "echo ${x:-'a b'}\nrm $target\n",
        'echo ${x:-"a b"}\nrm $target\n',
        "echo ${x:-$(date)}\nrm $target\n",
        "echo ${s//(a/b}\nrm $target\n",
        "echo ${x//#/_} 'q'\nrm $target\n",
        'echo ${#x} "q"\nrm $target\n',
    ],
)
def test_scan_file_param_expansion_forms_resolve_and_keep_scanning(
    tmp_path: Path, body: str
) -> None:
    flagged = _unquoted_lines(tmp_path, body)
    assert flagged[-1] == body.count("\n")


def test_scan_file_misparsed_quote_closed_later_no_longer_hides_code(tmp_path: Path) -> None:
    """Regression for the fail-open gap: the EOF fallback only fires on state still
    open at end of file, so the lexer must not invent a quote in the first place."""
    body = "cd /tmp;# don't care\nrm -rf $danger\nwc -l 'f'\nrm $other\n# it's fine\n"
    assert _unquoted_lines(tmp_path, body) == [2, 4]


@pytest.mark.parametrize(
    "body",
    [
        # Bash nests quotes inside a double-quoted `${...}`: the inner `'` is literal.
        'a="${x:-"it\'s"}"\necho $target\nb="${y:-"that\'s"}"\necho "$a $b"\n',
        # Same shape with a `$(...)` default and a doubly nested expansion.
        'a="${x:-"it\'s $(date)"}"\necho $target\nb="${y:-"${z:-"that\'s"}"}"\n',
    ],
)
def test_scan_file_double_quoted_param_with_nested_quote_keeps_apostrophe_literal(
    tmp_path: Path, body: str
) -> None:
    """Regression for round 3: the inner `'` must not open a fake single quote
    that a later line closes, because that hid the unquoted `$target`."""
    assert _unquoted_lines(tmp_path, body) == [2]


@pytest.mark.parametrize(
    "body",
    [
        'a="${x:-"b $c"}"\n',
        'a="${x:-$c}"\n',
        "a=\"${x:-'it $c'}\"\n",
        'a="${x//\\}/ $c}"\n',
    ],
)
def test_scan_file_double_quoted_param_body_stays_quoted(tmp_path: Path, body: str) -> None:
    """Expansions inside a double-quoted `${...}` default are quoted, so not flagged."""
    assert _unquoted_lines(tmp_path, body) == []


@pytest.mark.parametrize(
    "body",
    [
        'a="${x:-"b"}" $t\n',
        'a="${x:-"b"}"\nrm $t\n',
        'a="${x:-"${y}"}" $t\n',
    ],
)
def test_scan_file_double_quoted_param_closes_and_scanning_resumes(
    tmp_path: Path, body: str
) -> None:
    flagged = _unquoted_lines(tmp_path, body)
    assert flagged == [body.count("\n")]


def test_scan_file_flags_command_substitution_inside_double_quoted_param(tmp_path: Path) -> None:
    assert _unquoted_lines(tmp_path, 'a="${x:-$(rm $t)}"\n') == [1]


def test_scan_file_escaped_quote_in_backtick_body_in_double_quotes_is_a_real_quote(
    tmp_path: Path,
) -> None:
    """Regression for round 3: bash strips the backslash from `\\"` in a backtick
    body inside double quotes, so the `'` between the two is literal."""
    body = (
        'msg="`echo \\"it\'s\\"`"\necho $target\nother="`echo \\"that\'s\\"`"\necho "$msg $other"\n'
    )
    assert _unquoted_lines(tmp_path, body) == [2]


def test_scan_file_escaped_quote_in_backtick_body_in_double_quotes_hides_quoted_text(
    tmp_path: Path,
) -> None:
    """`$a` sits inside the real double quotes of the backtick body, so it is quoted."""
    assert _unquoted_lines(tmp_path, 'm="`echo \\"$a\\"`"\n') == []


def test_scan_file_escaped_quote_in_plain_backtick_body_stays_inert(tmp_path: Path) -> None:
    """Outside double quotes bash keeps `\\"` as an escaped quote, so `$a` is unquoted."""
    assert _unquoted_lines(tmp_path, 'm=`echo \\"$a\\"`\n') == [1]


def test_scan_file_flags_arithmetic_operand_variable(tmp_path: Path) -> None:
    """`$a` inside `$(( ))` is still scanned: arithmetic evaluates variable text."""
    assert _unquoted_lines(tmp_path, "x=$(( $a + 1 ))\n") == [1]


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        # A quote that never closes: both lines fall back to the raw per-line scrub.
        ('echo "open $a\nrm $b\n', [1, 2]),
        ("echo 'open $a\nrm $b\n", [1, 2]),
        # A command substitution that never closes.
        ("x=$(\nrm $b\n", [2]),
        # A quoted here-document that never ends: the body falls back to per-line scrub.
        ("cat <<'EOF'\n$a\nrm $b\n", [2, 3]),
        # A parameter expansion that never closes.
        ("echo ${x\nrm $b\n", [2]),
        # A double-quoted parameter expansion that never closes.
        ('echo "${x\nrm $b\n', [2]),
        # A backtick body in double quotes whose nested quote never closes.
        ('echo "`echo \\"open\nrm $b\n', [2]),
    ],
)
def test_scan_file_unresolved_state_at_eof_falls_back_to_per_line_scrub(
    tmp_path: Path, body: str, expected: list[int]
) -> None:
    """A stray opener must not hide the rest of the file."""
    assert _unquoted_lines(tmp_path, body) == expected


def test_scan_file_unresolved_quote_only_widens_from_where_it_opened(tmp_path: Path) -> None:
    body = 'msg="closed $a"\nrm $kept\necho "open\nrm $b\n'
    assert _unquoted_lines(tmp_path, body) == [2, 4]


@pytest.mark.parametrize(
    "lines",
    [
        [],
        ["\n"],
        ['echo "a\n', 'b"\n'],
        ["cat <<'E'\n", "x $y\n", "E\n"],
        ["cat <<'E'\n", "x $y\n"],
        ["x=$(\n", "y\n"],
        ["echo \\\n", "rm $x\n"],
    ],
)
def test_bash_scrub_lines_preserves_line_count_and_width(lines: list[str]) -> None:
    scrubbed = scanner.scrub_bash_lines(lines)
    assert len(scrubbed) == len(lines)
    assert all(len(out) <= len(raw) for out, raw in zip(scrubbed, lines, strict=True))


def test_bash_scrub_lines_blanks_multiline_double_quote_interior() -> None:
    out = scanner.scrub_bash_lines(['echo "a $x\n', 'b $y" $z\n'])
    assert [line.rstrip() for line in out] == ['echo "', '    " $z']


def test_bash_scrub_lines_blanks_quoted_heredoc_body() -> None:
    out = scanner.scrub_bash_lines(["cat <<'E'\n", "a $b\n", "E\n", "ls $c\n"])
    assert [line.strip() for line in out] == ["cat <<' '", "", "E", "ls $c"]


def test_bash_scrub_lines_matches_per_line_scrub_when_no_state_crosses_lines() -> None:
    lines = ["echo 'ab' \"cd\" $x\n", "rm $t # note $u\n", "# only a comment $v\n"]
    assert scanner.scrub_bash_lines(lines) == [scanner.scrub_bash_line(line) for line in lines]


def _blank_lines(lines: list[str]) -> list[bool]:
    """Per line: True when `scrub_bash_lines` left no `$` expansion visible."""
    return ["$" not in out for out in scanner.scrub_bash_lines(lines)]


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        # A case pattern `)` inside a multi-line "$(...)" must not close the substitution.
        ('out="$(case "$m" in\n  fast) rm -rf $target ;;\nesac)"\n', [2]),
        # The same case inside a bare group.
        ('(case "$m" in\n  fast) rm $t ;;\nesac)\n', [2]),
        # An optional leading paren on the pattern opens and closes its own group.
        ('out="$(case "$m" in\n  (fast) rm $t ;;\nesac)"\n', [2]),
        # A nested case keeps both frames: the inner `esac` leaves the outer open.
        (
            'out="$(case "$a" in\n x) case "$b" in\n y) rm $t ;;\n esac ;;\n z) rm $u ;;\nesac)"\n',
            [3, 5],
        ),
        # One line, no frame needed at the end.
        ('echo "$(case "$m" in a) rm $t ;; esac)"\n', [1]),
        # A quoted body after the closed substitution is still blanked.
        ('x="$(case "$m" in\n a) echo hi ;;\nesac)"\nmsg="a\nb $y"\n', []),
        # `case` as an argument is not a keyword: the substitution closes normally.
        ('x="$(echo case)"\nmsg="a\nb $y"\nrm $z\n', [4]),
        # A case with no `esac` stays unresolved and falls back to the per-line scrub.
        ('x="$(case a in\n b) rm $c ;;\n', [2]),
    ],
)
def test_scan_file_case_patterns_inside_substitutions(
    tmp_path: Path, body: str, expected: list[int]
) -> None:
    """A case-pattern `)` must not end a `$( )` and hide the case body (issue #6624 review)."""
    assert _unquoted_lines(tmp_path, body) == expected


def test_bash_scrub_lines_case_in_substitution_keeps_body_visible() -> None:
    lines = ['out="$(case "$m" in\n', "  fast) rm -rf $target ;;\n", 'esac)"\n']
    assert scanner.scrub_bash_lines(lines)[1] == lines[1]


def test_bash_scrub_case_esac_requires_command_position() -> None:
    assert scanner.scrub_bash_line("echo $(echo esac) # tail $x") == "echo $(echo esac) "


@pytest.mark.parametrize(
    "lines",
    [
        # Grouped arithmetic shift in a `((...))` command.
        ["(( flags |= (1 << n) ))\n", "msg='a\n", "b $x'\n"],
        # Grouped shift in `$((...))`, closed by `)))`.
        ["echo $(( (1 << n)))\n", "msg='a\n", "b $x'\n"],
        # Doubled parens inside arithmetic are two groups.
        ["(( v = ((1 << n) + 1) ))\n", "msg='a\n", "b $x'\n"],
        # A plain `$(( ))` still closes at `))`.
        ["echo $(( 1 << n ))\n", "msg='a\n", "b $x'\n"],
    ],
)
def test_bash_scrub_lines_grouped_arithmetic_shift_is_not_a_heredoc(lines: list[str]) -> None:
    """`(1 << n)` must not queue a fake here-document that unblanks a later quote."""
    assert _blank_lines(lines)[1:] == [True, True]


def test_bash_scrub_lines_grouped_shift_does_not_swallow_a_real_heredoc() -> None:
    lines = ["(( f |= (1 << n) ))\n", "cat <<'Q'\n", "hi $x\n", "Q\n", "ls $y\n"]
    out = scanner.scrub_bash_lines(lines)
    assert out[2].strip() == ""
    assert out[4] == "ls $y\n"


def test_bash_scrub_lines_arithmetic_group_inside_command_substitution() -> None:
    lines = ["x=$(( (a) + $(echo $b) ))\n", "rm $c\n"]
    assert scanner.scrub_bash_lines(lines) == lines


def test_bash_scrub_lines_backtick_in_param_expansion_hides_comment_quote() -> None:
    """A comment in a backtick body inside `${...}` must not open a quote."""
    lines = ["y=${x:-`ls # it's`}\n", "rm $z\n", "msg='a\n", "b $q'\n"]
    out = scanner.scrub_bash_lines(lines)
    assert out[1] == "rm $z\n"
    assert [line.rstrip() for line in out[2:]] == ["msg='", "    '"]


def test_bash_scrub_unquoted_backtick_body_ends_comment_at_closing_tick() -> None:
    assert scanner.scrub_bash_line("echo `ls # note` $v") == "echo `ls ` $v"


def test_bash_scrub_backtick_body_stays_visible_and_balanced() -> None:
    assert scanner.scrub_bash_line("rm `date` $v 'q $w'") == "rm `date` $v '    '"


def test_bash_scrub_lines_unclosed_backtick_falls_back_to_per_line_scrub() -> None:
    lines = ["echo `date\n", "rm $v\n"]
    assert scanner.scrub_bash_lines(lines) == lines


def test_bash_scrub_lines_multiline_backtick_body_is_shell_text() -> None:
    lines = ["x=`cat <<'E'\n", "a $b\n", "E\n", "`\n", "rm $c\n"]
    out = scanner.scrub_bash_lines(lines)
    assert out[1].strip() == ""
    assert out[4] == "rm $c\n"


def test_cli_exit_success_on_quoted_multiline_and_heredoc_shapes(tmp_path: Path) -> None:
    body = (
        '#!/usr/bin/env bash\nmsg="copies to\n$dest/skills"\n'
        "cat <<'USAGE'\nUsage: $0 --dest <dir>\nUSAGE\n"
    )
    name = _write(tmp_path, "quoted.sh", body)
    result = _run_cli(name, cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_python_string_concat_pattern_requires_plus_inside_literal() -> None:
    """Characterization: the 'string concatenation' regex fires only on a `+`
    inside the opening quoted argument, NOT on real concatenation.

    `subprocess.run("a + b")` matches (a `+` sits inside the literal); the
    real-injection shape `subprocess.run("cmd " + arg)` does NOT, because the
    closing quote ends the `[^"']*` run before the `+`. This is a known
    weakness of the detector. The test pins the current behavior so a future
    regex change is a deliberate, reviewed decision rather than a silent one.
    """
    assert "Subprocess with string concatenation" in _descriptions_for(
        "python", 'subprocess.run("a + b")'
    )
    assert "Subprocess with string concatenation" not in _descriptions_for(
        "python", 'subprocess.run("cmd " + arg)'
    )


def test_commented_out_code_is_still_flagged(tmp_path: Path) -> None:
    """Characterization: the line-based regex has no comment stripping, so a
    commented-out dangerous call is still reported.

    This is a known false-positive source. The test documents it; it does not
    bless it. If the detector later learns to skip comments, this assertion
    flips and the change is reviewable.
    """
    name = _write(
        tmp_path,
        "commented.py",
        "# subprocess.run(f'ls {x}')  # disabled for now\n",
    )
    vulns, _ = scanner.scan_file(str(tmp_path / name))
    assert len(vulns) == 1
    assert vulns[0].cwe == "CWE-78"


# ---------------------------------------------------------------------------
# One vulnerability per line: scan_file breaks after the first match
# ---------------------------------------------------------------------------


def test_scan_file_reports_one_vulnerability_per_line(tmp_path: Path) -> None:
    """A bash line can match both the command-substitution and the
    unquoted-variable patterns. `scan_file` `break`s after the first match,
    so it reports exactly one finding for that line."""
    name = _write(tmp_path, "multi.sh", "result=$( $userInput )\n")
    vulns, _ = scanner.scan_file(str(tmp_path / name))
    assert len(vulns) == 1


# ---------------------------------------------------------------------------
# Suppression mechanism
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "cwe", "expected"),
    [
        ("eval(user_input)  # security-scan: ignore CWE-78", "CWE-78", True),
        ("eval(user_input)  # security-scan: ignore CWE-22", "CWE-78", False),
        ("eval(user_input)  # SECURITY-SCAN: IGNORE cwe-78", "CWE-78", True),
        ("eval(user_input)", "CWE-78", False),
        ("eval(user_input)  # ignore CWE-78", "CWE-78", False),
    ],
)
def test_is_line_suppressed(line: str, cwe: str, expected: bool) -> None:
    assert scanner.is_line_suppressed(line, cwe) is expected


def test_correct_suppression_moves_finding_to_suppressed(tmp_path: Path) -> None:
    name = _write(
        tmp_path,
        "suppressed.py",
        "eval(user_input)  # security-scan: ignore CWE-78\n",
    )
    vulns, suppressed = scanner.scan_file(str(tmp_path / name))
    assert vulns == []
    assert len(suppressed) == 1
    assert "CWE-78 suppressed" in suppressed[0]
    assert "suppressed.py:1" in suppressed[0]


def test_wrong_cwe_suppression_does_not_silence_finding(tmp_path: Path) -> None:
    """A suppression for the wrong CWE must NOT hide a CWE-78 finding."""
    name = _write(
        tmp_path,
        "wrong_suppress.py",
        "eval(user_input)  # security-scan: ignore CWE-22\n",
    )
    vulns, suppressed = scanner.scan_file(str(tmp_path / name))
    assert len(vulns) == 1
    assert suppressed == []


# ---------------------------------------------------------------------------
# scan_file edge cases
# ---------------------------------------------------------------------------


def test_scan_file_unsupported_extension_returns_empty(tmp_path: Path) -> None:
    name = _write(tmp_path, "readme.txt", "subprocess.run(f'ls {x}')\n")
    vulns, suppressed = scanner.scan_file(str(tmp_path / name))
    assert vulns == []
    assert suppressed == []


def test_scan_file_missing_file_returns_error(tmp_path: Path) -> None:
    target = tmp_path / "does_not_exist.py"
    vulns, errors = scanner.scan_file(str(target))
    assert vulns == []
    assert len(errors) == 1
    assert "Error reading" in errors[0]


def test_scan_file_clean_python_file_has_no_findings(tmp_path: Path) -> None:
    name = _write(
        tmp_path,
        "clean.py",
        "def add(a: int, b: int) -> int:\n    return a + b\n",
    )
    vulns, suppressed = scanner.scan_file(str(tmp_path / name))
    assert vulns == []
    assert suppressed == []


def test_cwe_filter_excluding_78_skips_detection(tmp_path: Path) -> None:
    """`scan_file(..., cwe_filter=[22])` must not run the CWE-78 patterns."""
    name = _write(tmp_path, "filtered.py", "eval(user_input)\n")
    vulns, _ = scanner.scan_file(str(tmp_path / name), cwe_filter=[22])
    assert vulns == []


def test_cwe_filter_including_78_runs_detection(tmp_path: Path) -> None:
    name = _write(tmp_path, "included.py", "eval(user_input)\n")
    vulns, _ = scanner.scan_file(str(tmp_path / name), cwe_filter=[78])
    assert len(vulns) == 1


# ---------------------------------------------------------------------------
# CLI exit codes (observed via subprocess; complements test_security_scan_cli)
# ---------------------------------------------------------------------------


def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCANNER_PATH), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=cwd,
        check=False,
    )


def test_cli_exit_success_on_clean_file(tmp_path: Path) -> None:
    name = _write(tmp_path, "ok.py", "x = 1 + 1\n")
    result = _run_cli(name, cwd=tmp_path)
    assert result.returncode == scanner.EXIT_SUCCESS
    assert "No vulnerabilities found" in result.stdout


def test_cli_exit_vulnerabilities_on_dirty_file(tmp_path: Path) -> None:
    name = _write(tmp_path, "bad.py", "subprocess.run(cmd, shell=True)\n")
    result = _run_cli(name, cwd=tmp_path)
    assert result.returncode == scanner.EXIT_VULNERABILITIES
    assert "CWE-78" in result.stdout
    assert "Command Injection" in result.stdout


def test_cli_console_exit_line_matches_errors_with_findings(tmp_path: Path) -> None:
    name = _write(tmp_path, "bad.py", "subprocess.run(cmd, shell=True)\n")
    result = _run_cli(name, "missing.py", cwd=tmp_path)

    assert result.returncode == scanner.EXIT_ERROR
    assert "Errors:" in result.stdout
    assert "Error reading missing.py" in result.stdout
    assert "Exit code: 1 (scan error)" in result.stdout
    assert "CWE-78" in result.stdout
    assert "Exit code: 1 (scan error)" in result.stdout


def test_cli_exit_error_when_no_files_given(tmp_path: Path) -> None:
    result = _run_cli(cwd=tmp_path)
    assert result.returncode == scanner.EXIT_ERROR
    assert "No files to scan" in result.stdout


def test_cli_exit_success_when_only_unsupported_files(tmp_path: Path) -> None:
    name = _write(tmp_path, "notes.txt", "subprocess.run(cmd, shell=True)\n")
    result = _run_cli(name, cwd=tmp_path)
    assert result.returncode == scanner.EXIT_SUCCESS
    assert "No supported files found" in result.stdout


def test_cli_exit_error_when_supported_file_cannot_be_read(tmp_path: Path) -> None:
    result = _run_cli("missing.py", cwd=tmp_path)

    assert result.returncode == scanner.EXIT_ERROR
    assert "Errors:" in result.stdout
    assert "Error reading missing.py" in result.stdout


def test_cli_json_reports_read_errors_fail_closed(tmp_path: Path) -> None:
    result = _run_cli("--format", "json", "missing.py", cwd=tmp_path)

    assert result.returncode == scanner.EXIT_ERROR
    payload = json.loads(result.stdout)
    assert payload["exit_code"] == scanner.EXIT_ERROR
    assert len(payload["errors"]) == 1
    assert payload["errors"][0].startswith("Error reading missing.py:")


def test_cli_json_output_reports_findings(tmp_path: Path) -> None:
    name = _write(tmp_path, "bad.py", "eval(user_input)\n")
    result = _run_cli("--format", "json", name, cwd=tmp_path)
    assert result.returncode == scanner.EXIT_VULNERABILITIES
    payload = json.loads(result.stdout)
    assert payload["files_scanned"] == 1
    assert len(payload["vulnerabilities"]) == 1
    assert payload["vulnerabilities"][0]["cwe"] == "CWE-78"
    assert payload["summary"]["by_cwe"]["CWE-78"] == 1
    assert payload["exit_code"] == scanner.EXIT_VULNERABILITIES
    # Pin the JSON envelope contract so schema changes are deliberate and
    # reviewable for this security-critical scanner: the version marker and the
    # delegated-CWE map that tells consumers CWE-22 is handled by CodeQL, not here.
    assert payload["schema_version"] == scanner._JSON_SCHEMA_VERSION
    delegated = payload["summary"]["delegated_cwes"]["CWE-22"]
    assert delegated["tool"] == "codeql"
    assert delegated["workflow"] == ".github/workflows/codeql-analysis.yml"


def test_cli_suppressed_finding_exits_success(tmp_path: Path) -> None:
    name = _write(
        tmp_path,
        "supp.py",
        "eval(user_input)  # security-scan: ignore CWE-78\n",
    )
    result = _run_cli(name, cwd=tmp_path)
    assert result.returncode == scanner.EXIT_SUCCESS
    assert "Suppressed findings: 1" in result.stdout


def test_cli_directory_scan_finds_nested_file(tmp_path: Path) -> None:
    nested = tmp_path / "src"
    nested.mkdir()
    (nested / "dirty.sh").write_text('eval "$cmd"\n', encoding="utf-8")
    result = _run_cli("--directory", "src", cwd=tmp_path)
    assert result.returncode == scanner.EXIT_VULNERABILITIES
    assert "CWE-78" in result.stdout


def test_cli_directory_scan_finds_extensionless_bash_hook(tmp_path: Path) -> None:
    hooks = tmp_path / "scripts" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "pre-push").write_text(
        '#!/usr/bin/env bash\neval "$cmd"\n',
        encoding="utf-8",
    )

    result = _run_cli("--directory", "scripts/hooks", cwd=tmp_path)

    assert result.returncode == scanner.EXIT_VULNERABILITIES
    assert "pre-push:2" in result.stdout
    assert "CWE-78" in result.stdout


def test_cli_explicit_extensionless_bash_hook_is_scanned(tmp_path: Path) -> None:
    name = _write(
        tmp_path,
        "pre-commit",
        '#!/bin/bash\neval "$cmd"\n',
    )

    result = _run_cli(name, cwd=tmp_path)

    assert result.returncode == scanner.EXIT_VULNERABILITIES
    assert "pre-commit:2" in result.stdout
    assert "CWE-78" in result.stdout


def test_cli_output_file_written(tmp_path: Path) -> None:
    name = _write(tmp_path, "bad.py", "eval(user_input)\n")
    result = _run_cli("--format", "json", "--output", "out.json", name, cwd=tmp_path)
    assert result.returncode == scanner.EXIT_VULNERABILITIES
    out = tmp_path / "out.json"
    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert len(payload["vulnerabilities"]) == 1


# In-process CLI (main) coverage.
#
# The exit-code tests above run the scanner as a subprocess, which exercises the
# real entry point but does not count toward in-process line coverage for this
# security-critical module. The tests below invoke `scanner.main()` directly with
# a patched argv so the argument handling, the --cwe delegation notice, and the
# path-traversal guard are covered in-process. `main()` calls `sys.exit()`, so
# each case asserts on the raised `SystemExit`.


def _run_main_in_process(monkeypatch: pytest.MonkeyPatch, *args: str, cwd: Path) -> int:
    """Invoke scanner.main() in-process under cwd with argv=args; return exit code."""
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(sys, "argv", ["scan_vulnerabilities.py", *args])
    with pytest.raises(SystemExit) as excinfo:
        scanner.main()
    code = excinfo.value.code
    return 0 if code is None else int(code)


def test_main_cwe22_warns_and_notes_delegation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange: a clean supported file so the scan succeeds with no findings.
    _write(tmp_path, "clean.py", 'subprocess.run(["ls", "-l"])\n')
    # Act
    code = _run_main_in_process(monkeypatch, "--cwe", "22", "clean.py", cwd=tmp_path)
    captured = capsys.readouterr()
    # Assert: --cwe 22 is accepted (no error exit) but warns on stderr and notes
    # the CodeQL delegation in stdout, so a zero-finding result is not mistaken
    # for path-traversal coverage.
    assert code == scanner.EXIT_SUCCESS
    assert "WARNING: --cwe 22" in captured.err
    assert "CWE-22: delegated to CodeQL" in captured.out


def test_main_unsupported_cwe_exits_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, "clean.py", 'subprocess.run(["ls", "-l"])\n')
    code = _run_main_in_process(monkeypatch, "--cwe", "99", "clean.py", cwd=tmp_path)
    captured = capsys.readouterr()
    assert code == scanner.EXIT_ERROR
    assert "not supported by this" in captured.err


def test_main_directory_path_traversal_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange: cwd is a nested dir so "../" escapes the allowed base.
    work = tmp_path / "work"
    work.mkdir()
    # Act
    code = _run_main_in_process(monkeypatch, "--directory", "../outside", cwd=work)
    captured = capsys.readouterr()
    # Assert: containment check rejects the escaping --directory with EXIT_ERROR.
    assert code == scanner.EXIT_ERROR
    assert "Path traversal" in captured.err


def test_main_git_staged_scans_staged_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Arrange: a vulnerable staged file, with get_staged_files stubbed so the test
    # does not depend on a real git index.
    name = _write(tmp_path, "staged.py", "subprocess.run(cmd, shell=True)\n")
    monkeypatch.setattr(scanner, "get_staged_files", lambda: [name])
    # Act
    code = _run_main_in_process(monkeypatch, "--git-staged", cwd=tmp_path)
    captured = capsys.readouterr()
    # Assert: --git-staged feeds the staged file into the scan and reports CWE-78.
    assert code == scanner.EXIT_VULNERABILITIES
    assert "CWE-78" in captured.out


def test_main_git_staged_no_files_exits_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A successful staged-file enumeration that yields zero files is a clean pass,
    # not an error. Only a git enumeration *failure* fails closed (see below).
    monkeypatch.setattr(scanner, "get_staged_files", lambda: [])
    code = _run_main_in_process(monkeypatch, "--git-staged", cwd=tmp_path)
    captured = capsys.readouterr()
    assert code == scanner.EXIT_SUCCESS
    assert "No files to scan" in captured.out


def test_main_directory_missing_exits_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A --directory that does not exist is a mis-specified scan root, not a clean
    # scan. os.walk silently yields nothing for a missing path, so without an
    # explicit is_dir() guard this fails OPEN (exits 0, "all clean"). Pin the
    # fail-closed contract: missing --directory exits EXIT_ERROR before walking.
    missing = tmp_path / "does-not-exist"
    code = _run_main_in_process(monkeypatch, "--directory", str(missing), cwd=tmp_path)
    captured = capsys.readouterr()
    assert code == scanner.EXIT_ERROR
    assert "not found or not a directory" in captured.err


def test_main_git_staged_failure_exits_external(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        scanner,
        "get_staged_files",
        lambda: (_ for _ in ()).throw(scanner.GitEnumerationError("git diff failed: fatal")),
    )
    code = _run_main_in_process(monkeypatch, "--git-staged", cwd=tmp_path)
    captured = capsys.readouterr()
    assert code == scanner.EXIT_EXTERNAL
    assert "git diff failed: fatal" in captured.err


def test_get_staged_files_raises_on_git_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_git(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(
            returncode=128,
            cmd=["git", "diff", "--staged", "--name-only"],
            stderr="fatal: not a git repository",
        )

    monkeypatch.setattr(scanner.subprocess, "run", fail_git)
    with pytest.raises(scanner.GitEnumerationError, match="not a git repository"):
        scanner.get_staged_files()


def test_get_staged_files_raises_when_git_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing_git(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("git")

    monkeypatch.setattr(scanner.subprocess, "run", missing_git)
    with pytest.raises(scanner.GitEnumerationError, match="git executable not found"):
        scanner.get_staged_files()


def test_main_json_format_in_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Arrange: a vulnerable file so the JSON envelope carries a finding.
    name = _write(tmp_path, "vuln.py", "subprocess.run(cmd, shell=True)\n")
    # Act: exercise format_json_output() in-process (subprocess-only before).
    code = _run_main_in_process(monkeypatch, "--format", "json", name, cwd=tmp_path)
    captured = capsys.readouterr()
    # Assert: pinned envelope shape, a CWE-78 finding, and the delegated-CWE map.
    assert code == scanner.EXIT_VULNERABILITIES
    data = json.loads(captured.out)
    assert data["schema_version"] == scanner._JSON_SCHEMA_VERSION
    assert data["files_scanned"] == 1
    assert data["summary"]["total"] >= 1
    assert data["summary"]["by_cwe"].get("CWE-78", 0) >= 1
    assert any(v["cwe"] == "CWE-78" for v in data["vulnerabilities"])
    assert data["summary"]["delegated_cwes"]["CWE-22"]["tool"] == "codeql"


def test_main_directory_scan_in_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Arrange: a nested project dir with one vulnerable file, so the successful
    # get_directory_files() walk is exercised in-process (subprocess-only before).
    proj = tmp_path / "proj"
    (proj / "pkg").mkdir(parents=True)
    (proj / "pkg" / "vuln.py").write_text("subprocess.run(cmd, shell=True)\n", encoding="utf-8")
    (proj / "notes.txt").write_text("not scannable\n", encoding="utf-8")
    # Act: cwd is tmp_path so the relative --directory passes the containment guard.
    code = _run_main_in_process(monkeypatch, "--directory", "proj", cwd=tmp_path)
    captured = capsys.readouterr()
    # Assert: the directory walk found and scanned only the supported file and
    # reported the CWE-78 finding.
    assert code == scanner.EXIT_VULNERABILITIES
    assert "CWE-78" in captured.out


# ---------------------------------------------------------------------------
# Extensionless shebang detection (issue #2367)
# ---------------------------------------------------------------------------
# Extensionless executables advertise their interpreter only via a shebang.
# The detector must read the first line and treat bash/sh-family shebangs as
# bash, otherwise directory scans and explicit file scans silently skip them.


@pytest.mark.parametrize(
    ("shebang", "expected"),
    [
        ("#!/usr/bin/env bash\n", "bash"),
        ("#!/usr/bin/env -S bash\n", "bash"),
        ("#!/usr/bin/env -i sh\n", "bash"),
        ("#!/bin/bash\n", "bash"),
        ("#!/bin/sh\n", "bash"),
        ("#!/usr/bin/env sh\n", "bash"),
        ("#! /usr/bin/env bash\n", "bash"),
        ("#!/usr/bin/env dash\n", "bash"),
        ("#!/usr/bin/env ksh\n", "bash"),
        ("#!/usr/bin/env python3\n", None),
        ("#!/usr/bin/env -S python3\n", None),
        ("#!/usr/bin/env node\n", None),
        ("#!/usr/bin/env pwsh\n", None),
        ("plain text, no shebang\n", None),
        ("", None),
    ],
)
def test_get_language_shebang_fallback(tmp_path: Path, shebang: str, expected: str | None) -> None:
    """Extensionless files classify by shebang interpreter; non-shell shebangs reject."""
    f = tmp_path / "pre-push"
    f.write_text(shebang + "echo hi\n", encoding="utf-8")
    assert scanner.get_language(str(f)) == expected


def test_get_language_extension_wins_over_shebang(tmp_path: Path) -> None:
    """A known suffix never triggers the shebang path; suffix is authoritative."""
    f = tmp_path / "thing.txt"
    f.write_text("#!/usr/bin/env bash\necho hi\n", encoding="utf-8")
    assert scanner.get_language(str(f)) is None


def test_get_language_missing_file_returns_none(tmp_path: Path) -> None:
    """Unreadable extensionless paths don't raise; they classify as unsupported."""
    assert scanner.get_language(str(tmp_path / "does-not-exist")) is None


def test_get_language_invalid_utf8_shebang_returns_none(tmp_path: Path) -> None:
    """Invalid UTF-8 in a shebang is treated as unsupported, not replaced."""
    hook = tmp_path / "pre-push"
    hook.write_bytes(b"#!\xff\xfe\n")
    assert scanner.get_language(str(hook)) is None


def test_get_directory_files_includes_extensionless_bash(tmp_path: Path) -> None:
    """Directory walk surfaces extensionless bash scripts under `scripts/hooks/`-style layouts."""
    hooks = tmp_path / "scripts" / "hooks"
    hooks.mkdir(parents=True)
    bash_hook = hooks / "pre-push"
    bash_hook.write_text("#!/usr/bin/env bash\necho hi\n", encoding="utf-8")
    (hooks / "README").write_text("just docs\n", encoding="utf-8")
    py_hook = hooks / "py-hook"
    py_hook.write_text("#!/usr/bin/env python3\nprint('x')\n", encoding="utf-8")

    found = scanner.get_directory_files(str(tmp_path))
    assert str(bash_hook) in found
    assert str(hooks / "README") not in found
    assert str(py_hook) not in found


def test_get_directory_files_prunes_noisy_directories(tmp_path: Path) -> None:
    """Directory walk skips dependency and metadata trees before shebang reads."""
    git_objects = tmp_path / ".git" / "objects"
    git_objects.mkdir(parents=True)
    git_object = git_objects / "abcdef"
    git_object.write_text("#!/usr/bin/env bash\neval $payload\n", encoding="utf-8")

    node_bin = tmp_path / "node_modules" / ".bin"
    node_bin.mkdir(parents=True)
    node_script = node_bin / "tool"
    node_script.write_text("#!/usr/bin/env bash\neval $payload\n", encoding="utf-8")

    mixed_case = tmp_path / "Node_Modules" / ".bin"
    mixed_case.mkdir(parents=True)
    mixed_case_script = mixed_case / "tool"
    mixed_case_script.write_text("#!/usr/bin/env bash\neval $payload\n", encoding="utf-8")

    hooks = tmp_path / "scripts" / "hooks"
    hooks.mkdir(parents=True)
    hook = hooks / "pre-push"
    hook.write_text("#!/usr/bin/env bash\neval $payload\n", encoding="utf-8")

    found = scanner.get_directory_files(str(tmp_path))

    assert str(hook) in found
    assert str(git_object) not in found
    assert str(node_script) not in found
    assert str(mixed_case_script) not in found


def test_scan_extensionless_bash_hook_emits_cwe78(tmp_path: Path) -> None:
    """End-to-end: an extensionless bash hook with a CWE-78 pattern is detected."""
    hook = tmp_path / "pre-push"
    hook.write_text(
        '#!/usr/bin/env bash\nFILE=$1\necho "running $FILE"\neval $FILE\n',
        encoding="utf-8",
    )
    vulns, _suppressed = scanner.scan_file(str(hook))
    assert any(v.cwe == "CWE-78" for v in vulns), (
        f"expected at least one CWE-78 finding, got {[v.cwe for v in vulns]}"
    )
