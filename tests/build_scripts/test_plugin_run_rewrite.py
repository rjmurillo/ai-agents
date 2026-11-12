"""The legacy-to-locator rewrite keeps ARGS, refuses every site it cannot parse, and is idempotent.

`build/scripts/plugin_run_rewrite.py` is pure text in, text out (ADR-121 rollout step 3).
The command-line wrapper is covered by `test_plugin_run_fix.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import plugin_run_launcher  # noqa: E402
import plugin_run_rewrite as rewrite  # noqa: E402

from scripts.validation import plugin_root_interpreter_sites as sites  # noqa: E402

ROOT = rewrite.NESTED_ROOT
SCRIPT = "skills/memory/scripts/search_memory.py"


def _legacy(args: str = "", script: str = SCRIPT) -> str:
    return f'python3 "{ROOT}/{script}"' + (f" {args}" if args else "")


def _locator(args: str = "", script: str = SCRIPT) -> str:
    return plugin_run_launcher.render_locator(script, args)


def _fence(*body: str) -> str:
    return "```bash\n" + "\n".join(body) + "\n```\n"


def _refused(text: str) -> rewrite.Rewrite:
    result = rewrite.rewrite_text(text)
    assert result.text == text, "a refused site must stay byte for byte"
    assert result.fixed == 0
    return result


# --- round trip: ARGS survives, the locator reads back --------------------


@pytest.mark.parametrize(
    "args",
    [
        "",
        "--flag",
        '"a topic" --limit 5',
        "'single quoted; with semicolon' -x",
        '--note "a | b && c"',
        "--out $(mktemp)",
        'x "$(date +%F)"',
        "2>&1",
        "> out.txt",
        "--cc=#tag a#b",
        "-- -leading",
    ],
)
def test_args_survive_in_a_fenced_block(args: str) -> None:
    result = rewrite.rewrite_text(_fence(_legacy(args)))
    assert result.text == _fence(_locator(args))
    assert (result.fixed, result.refusals) == (1, ())
    [match] = plugin_run_launcher.find_locators(result.text.splitlines()[1])
    assert (match.script_rel, match.args) == (SCRIPT, args)


@pytest.mark.parametrize("args", ["", '"topic"', "--a 'b c' 2>&1"])
def test_inline_code_keeps_the_text_around_the_span(args: str) -> None:
    before = f"- Search: `{_legacy(args)}` then read the hit.\n"
    after = f"- Search: `{_locator(args)}` then read the hit.\n"
    result = rewrite.rewrite_text(before)
    assert (result.text, result.fixed, result.refusals) == (after, 1, ())


def test_two_code_spans_on_one_line_are_each_rewritten() -> None:
    before = f"`{_legacy('-a')}` or `{_legacy('-b', 'skills/x/y.py')}`\n"
    after = f"`{_locator('-a')}` or `{_locator('-b', 'skills/x/y.py')}`\n"
    assert rewrite.rewrite_text(before).text == after


@pytest.mark.parametrize(
    "prefix", ["", "  ", "- ", "1. ", "$ ", "> ", "cd src && ", "a || ", "a; ", "cat f | "]
)
def test_command_position_prefixes_are_accepted(prefix: str) -> None:
    text = _fence(f"{prefix}{_legacy('x')}")
    assert rewrite.rewrite_text(text).text == _fence(f"{prefix}{_locator('x')}")


def test_a_script_that_sits_beside_no_scripts_directory_is_rewritten() -> None:
    script = "skills/metrics/collect_metrics.py"
    assert rewrite.rewrite_text(_fence(_legacy("", script))).text == _fence(_locator("", script))


@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_line_endings_and_a_missing_final_newline_are_kept(eol: str) -> None:
    body = f"intro{eol}```{eol}{_legacy('x')}{eol}```{eol}tail"
    result = rewrite.rewrite_text(body)
    assert result.text == f"intro{eol}```{eol}{_locator('x')}{eol}```{eol}tail"


def test_text_with_no_site_is_returned_unchanged() -> None:
    text = "# Title\n\nNothing to see.\n\n```bash\nls -la\n```\n"
    assert rewrite.rewrite_text(text) == rewrite.Rewrite(text, 0, ())


# --- idempotence -----------------------------------------------------------


def test_rewriting_the_output_changes_nothing() -> None:
    text = f"Run `{_legacy('a')}`.\n" + _fence(
        _legacy("b 2>&1"), _legacy("c | head"), f'X="{ROOT}/skills/z"'
    )
    once = rewrite.rewrite_text(text)
    twice = rewrite.rewrite_text(once.text)
    assert twice.text == once.text
    assert twice.fixed == 0
    assert twice.refusals == once.refusals


def test_the_output_holds_no_legacy_invocation() -> None:
    once = rewrite.rewrite_text(_fence(_legacy("a"), _legacy("b", "skills/q/r.py")))
    assert sites.count_legacy_sites(once.text) == sites.LegacyCounts(0, 0)


# --- refusals: each shape stays as written and says why -------------------


def _shape(name: str, text: str, reason: str) -> object:
    return pytest.param(text, reason, id=name)


_BACKSLASH_ARG = "x \\"
_REFUSALS = [
    _shape(
        "line continuation",
        _fence(f"{_legacy('--pr 1')} \\", "    --branch x"),
        "line continuation",
    ),
    _shape("continuation at end of file", f"```\n{_legacy()} \\", "line continuation"),
    _shape("interpreter -I", _fence(f'python3 -I "{ROOT}/{SCRIPT}"'), "interpreter option"),
    _shape("interpreter -u", _fence(f'python3 -u "{ROOT}/{SCRIPT}" x'), "interpreter option"),
    _shape("uv run python", _fence(f'uv run python "{ROOT}/{SCRIPT}"'), "not python3"),
    _shape("pinned python", _fence(f'python3.11 "{ROOT}/{SCRIPT}"'), "not python3"),
    _shape(
        "bash -c",
        _fence(f"bash -c '{_legacy('x')}'"),
        "shell -c string",
    ),
    _shape("sh -c", _fence(f'sh -c "{_legacy()}"'), "shell -c string"),
    _shape("env assignment prefix", _fence(f"FOO=1 {_legacy()}"), "command position"),
    _shape("xargs", _fence(f"ls | xargs {_legacy()}"), "command position"),
    _shape("timeout", _fence(f"timeout 5 {_legacy()}"), "command position"),
    _shape("command substitution", _fence(f"OUT=$({_legacy('x')})"), "command position"),
    _shape("pipe in args", _fence(_legacy("x | head -5")), "operator '|'"),
    _shape("semicolon in args", _fence(_legacy("x; echo done")), "operator ';'"),
    _shape("and-and in args", _fence(_legacy("x && echo ok")), "bare '&'"),
    _shape("background in args", _fence(_legacy("x &")), "bare '&'"),
    _shape("parenthesis in args", _fence(_legacy("x (y)")), "parenthesis"),
    _shape("heredoc in args", _fence(_legacy("<<EOF")), "heredoc"),
    _shape("comment in args", _fence(_legacy("x # why")), "comment"),
    _shape(
        "trailing backslash in args", f"Run `{_legacy(_BACKSLASH_ARG)}`\n", "ends in a backslash"
    ),
    _shape("unclosed double quote", _fence(_legacy('"unclosed')), "unclosed quote"),
    _shape("unclosed single quote", _fence(_legacy("'unclosed")), "unclosed quote"),
    _shape("unclosed substitution", _fence(_legacy("$(echo")), "unclosed $("),
    _shape("prose outside code", f"You can run {_legacy('x')} to search.\n", "outside a code span"),
    _shape("indented code is not fenced", f"    {_legacy('x')}\n", "outside a code span"),
    _shape("code span left open", f"Run `{_legacy('x')}\n", "does not close"),
    _shape("quote closes early", _fence(f'python3 "{ROOT}"/{SCRIPT}'), "single quoted path"),
    _shape("bare operand", _fence(f"python3 {ROOT}/{SCRIPT}"), "single quoted path"),
    _shape("text glued to the path", _fence(f'python3 "{ROOT}/{SCRIPT}"x'), "no space"),
    _shape(
        "assignment",
        _fence(f'SCRIPTS_DIR="{ROOT}/skills/memory/scripts"'),
        "assignment from the nested form",
    ),
]


@pytest.mark.parametrize(("text", "reason"), _REFUSALS)
def test_a_site_it_cannot_parse_is_left_alone_and_reported(text: str, reason: str) -> None:
    result = _refused(text)
    assert result.refusals, "expected a refusal"
    assert any(reason in item.reason for item in result.refusals), result.refusals
    assert all(item.lineno >= 1 for item in result.refusals)


def test_a_refusal_names_the_line_of_the_site() -> None:
    text = f"one\ntwo\n```\nok\n{_legacy('a | b')}\n```\n"
    [refusal] = _refused(text).refusals
    assert refusal.lineno == 5


def test_a_refused_site_does_not_stop_its_neighbours() -> None:
    text = _fence(_legacy("good 1"), _legacy("bad | pipe"), _legacy("good 2"))
    result = rewrite.rewrite_text(text)
    assert result.fixed == 2
    assert len(result.refusals) == 1
    assert result.text == _fence(_locator("good 1"), _legacy("bad | pipe"), _locator("good 2"))


def test_the_locator_beside_a_refused_site_still_validates() -> None:
    """Negative control: the rewrite never emits text the launcher cannot read back."""
    result = rewrite.rewrite_text(_fence(_legacy("a"), _legacy("b | c")))
    locators = [
        m for line in result.text.splitlines() for m in plugin_run_launcher.find_locators(line)
    ]
    assert [(m.script_rel, m.problem) for m in locators] == [(SCRIPT, None)]


# --- args_refusal directly --------------------------------------------------


@pytest.mark.parametrize(
    "args",
    ["", "a b", "'a|b;c&d(e)'", '"a|b;c&d(e)"', "$(a | b; c)", "2>&1", "&>log", ">&2", "a\\;b",
     "--x=#y", "a#b", "$(echo \")\")"],
)  # fmt: skip
def test_args_the_locator_can_carry(args: str) -> None:
    assert rewrite.args_refusal(args) is None


@pytest.mark.parametrize(
    "args", ["a | b", "a; b", "a && b", "a &", "(a)", "a <<EOF", "# c", "a #c", "a\\", "'a", "$(a"]
)
def test_args_the_locator_cannot_carry(args: str) -> None:
    assert rewrite.args_refusal(args) is not None


def test_an_escaped_quote_inside_double_quotes_does_not_end_the_argument() -> None:
    args = 'say "a \\" ; b" done'
    assert rewrite.args_refusal(args) is None
    assert rewrite.rewrite_text(_fence(_legacy(args))).text == _fence(_locator(args))


def test_a_script_path_the_launcher_rejects_is_refused() -> None:
    text = _fence(f'python3 "{ROOT}/skills/../escape.py" x')
    result = _refused(text)
    assert [r.reason for r in result.refusals] == [
        "not a plugin-root script path: 'skills/../escape.py'"
    ]
