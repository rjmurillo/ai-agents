"""The shell locator is one recipe, and every tree that gets it ships the resolver (ADR-121).

`build/scripts/plugin_run_launcher.py` defines the locator text. These tests pin:

1. The renderer and its inverse: a round trip, bad paths, and arguments.
2. The locator equals the form printed in ADR-121 decision 3, byte for byte.
3. The target pattern equals the pattern of `copilot_launcher.py` and of the resolver.
4. Every plugin tree that ships `lib/` holds a byte-identical `lib/ptk_run.py`.

`tests/build_scripts/test_plugin_run_runtime_contract.py` runs the text under a shell.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import copilot_launcher  # noqa: E402
import lib_hand_files  # noqa: E402
import plugin_run_launcher  # noqa: E402
from plugin_run_launcher import LauncherError, render_locator, split_locator  # noqa: E402

RESOLVER_SOURCE = REPO_ROOT / "src" / "claude" / "lib" / "ptk_run.py"
ADR_GLOB = ".project-toolkit/architecture/ADR-121-*.md"
SCRIPT = "skills/x/scripts/y.py"


def _adr_locator_line() -> str:
    """Return the locator printed in ADR-121 decision 3 (the fenced `sh` block)."""
    adr = next(REPO_ROOT.glob(ADR_GLOB)).read_text(encoding="utf-8")
    block = re.search(
        r"^ *```sh\n *(?P<line>\( for d in [^\n]*exit 2 \))\n *```", adr, re.MULTILINE
    )
    assert block is not None, "ADR-121 no longer prints the locator in an sh block"
    return block.group("line")


@pytest.mark.parametrize(
    "script_rel",
    [SCRIPT, "skills/metrics/collect_metrics.py", "skills/a-b/scripts/c_d.v2.py"],
)
@pytest.mark.parametrize(
    "args",
    ["", "--flag", "'a b' -x; echo $?", "$(cmd) `cmd`", "line1\nline2", " leading", "a  b "],
)
def test_split_locator_is_the_inverse_of_render_locator(script_rel: str, args: str) -> None:
    assert split_locator(render_locator(script_rel, args)) == (script_rel, args)


def test_render_locator_matches_the_adr_decision_3_text_with_and_without_arguments() -> None:
    adr_text = _adr_locator_line().replace("skills/NAME/scripts/FILE.py", SCRIPT)
    assert render_locator(SCRIPT, "ARGS") == adr_text
    assert render_locator(SCRIPT) == adr_text.replace(" ARGS;", ";")


def test_locator_stays_inside_the_costs_the_adr_states() -> None:
    placeholder = render_locator("skills/NAME/scripts/FILE.py")
    assert len(placeholder) == 260
    assert "|" not in placeholder


def test_locator_names_both_roots_in_candidate_order_then_the_dogfood_root() -> None:
    text = render_locator(SCRIPT)
    tokens = ('"${CLAUDE_PLUGIN_ROOT}"', '"${COPILOT_PLUGIN_ROOT}"', " .claude;")
    order = [text.index(t) for t in tokens]
    assert order == sorted(order)


def test_locator_runs_in_a_subshell_so_exit_2_cannot_end_a_persistent_shell() -> None:
    text = render_locator(SCRIPT)
    assert text.startswith("( ") and text.endswith("exit 2 )")


@pytest.mark.parametrize(
    "script_rel",
    [
        "",
        "y.py",
        "skills/x/scripts/y.sh",
        "skills/../y.py",
        "skills/x/../../y.py",
        "/skills/x/y.py",
        "skills/x y/y.py",
        "skills/$X/y.py",
        'skills/"x"/y.py',
        "skills\\x\\y.py",
        "skills/x/y.py\n",
        "skills/x/y.py;ls",
        "other/x.py",
    ],
)
def test_render_locator_rejects_a_path_it_cannot_place(script_rel: str) -> None:
    with pytest.raises(LauncherError):
        render_locator(script_rel)


def test_launcher_error_is_a_value_error() -> None:
    assert issubclass(LauncherError, ValueError)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "python3 skills/x/scripts/y.py",
        'python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/x/scripts/y.py"',
        copilot_launcher.render_launcher(SCRIPT),
        render_locator(SCRIPT)[:-3],
        "x" + render_locator(SCRIPT),
        render_locator(SCRIPT) + " x",
    ],
)
def test_split_locator_returns_none_for_text_of_another_shape(text: str) -> None:
    assert split_locator(text) is None


def test_split_locator_returns_none_for_text_shorter_than_head_plus_tail() -> None:
    """Head and tail must not overlap: a bare head+tail with no path is not a locator."""
    text = render_locator(SCRIPT)
    head, _, tail = text.partition(SCRIPT)
    assert split_locator(head[:-1] + tail) is None


def test_split_locator_raises_for_a_locator_shape_with_a_bad_path() -> None:
    forged = render_locator(SCRIPT).replace(SCRIPT, "skills/../y.py")
    with pytest.raises(LauncherError):
        split_locator(forged)
    with pytest.raises(LauncherError):
        split_locator(render_locator(SCRIPT).replace(SCRIPT, ""))


def test_the_target_pattern_is_the_same_one_copilot_launcher_and_the_resolver_use() -> None:
    """A conformance test, not a copy: three definitions, one accepted language."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("ptk_run_conformance", RESOLVER_SOURCE)
    assert spec is not None and spec.loader is not None
    resolver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(resolver)

    samples = [
        SCRIPT,
        "skills/metrics/collect_metrics.py",
        "skills/x/scripts/y.PY",
        "skills/x/scripts/y.py ",
        "skills/x/scripts/y.py\n",
        "skills/x/scripts/y.sh",
        "skills/x y/y.py",
        "skills/$x/y.py",
        "skills\\x\\y.py",
        "skills/é/y.py",
        "/skills/x/y.py",
        "",
    ]
    patterns = (
        plugin_run_launcher._SCRIPT_REL_RE,
        copilot_launcher._SCRIPT_REL_RE,
        resolver.TARGET_RE,
    )
    for sample in samples:
        verdicts = {bool(p.fullmatch(sample)) for p in patterns}
        assert len(verdicts) == 1, sample


# ---- Ship parity: every tree with a lib/ holds the same resolver ----------------------------


def _trees_with_lib() -> list[Path]:
    """Every shipped plugin tree that has a `lib/` directory, found on disk."""
    src = REPO_ROOT / "src"
    candidates = [*src.glob("*/lib"), *src.glob("hermes/*/lib")]
    return sorted(p for p in candidates if p.is_dir())


def test_every_tree_that_ships_lib_ships_a_byte_identical_resolver() -> None:
    trees = _trees_with_lib()
    names = {t.parent.name for t in trees}
    assert {"claude", "codex", "copilot-cli", "cursor", "muse"} <= names
    assert {
        "project-toolkit-delivery",
        "project-toolkit-knowledge",
        "project-toolkit-authoring",
        "project-toolkit-azure-devops",
    } <= names
    canonical = RESOLVER_SOURCE.read_bytes()
    drifted = [
        str(lib.relative_to(REPO_ROOT))
        for lib in trees
        if not (lib / "ptk_run.py").is_file() or (lib / "ptk_run.py").read_bytes() != canonical
    ]
    assert drifted == []


def test_the_dogfood_lib_reaches_the_resolver_through_a_link_to_the_claude_copy() -> None:
    linked = REPO_ROOT / ".claude" / "lib" / "ptk_run.py"
    tracked = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-s", "--", ".claude/lib/ptk_run.py"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    ).stdout
    if tracked:
        assert tracked.startswith("120000 "), f"git must track the link as mode 120000: {tracked!r}"
    if not linked.is_symlink():
        config = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "config", "--type=bool", "--get", "core.symlinks"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        ).stdout.strip()
        assert config == "false", f"{linked} must be a symlink unless core.symlinks=false"
        pytest.skip("core.symlinks=false: git wrote the link as a regular file")
    assert linked.read_bytes() == RESOLVER_SOURCE.read_bytes()
    assert linked.resolve() == RESOLVER_SOURCE.resolve()


def test_a_tree_with_no_lib_ships_no_resolver_and_keeps_the_legacy_form() -> None:
    """ADR-121 decision 2: a tree without `lib/` is not a locator target yet."""
    no_lib = REPO_ROOT / "src" / "vs-code-agents"
    assert not (no_lib / "lib").exists()
    assert not list(no_lib.rglob("ptk_run.py"))


def test_the_multi_tree_mechanism_names_the_resolver() -> None:
    assert "ptk_run.py" in lib_hand_files.PLUGIN_LIB_FILES
    copies = {dst for _, dst in lib_hand_files.PLUGIN_LIB_COPIES if dst.endswith("ptk_run.py")}
    assert copies == {f"{root}/ptk_run.py" for root in lib_hand_files.PLUGIN_LIB_COPY_ROOTS}


# --- find_locators: how the validator reads a target out of a line of a file ---


def test_find_locators_reads_every_locator_in_a_line() -> None:
    first = render_locator("skills/a/scripts/one.py", "--x 'y z'")
    second = render_locator("skills/b/two.py")
    line = f"Run `{first}` or `{second}` today."
    found = list(plugin_run_launcher.find_locators(line))
    assert [(m.script_rel, m.args, m.problem) for m in found] == [
        ("skills/a/scripts/one.py", "--x 'y z'", None),
        ("skills/b/two.py", "", None),
    ]
    assert [line[m.start : m.end] for m in found] == [first, second]


def test_find_locators_agrees_with_split_locator_on_every_rendered_text() -> None:
    for args in ("", "--flag", "a  b", "$(cmd)"):
        text = render_locator(SCRIPT, args)
        [match] = plugin_run_launcher.find_locators(text)
        assert (match.script_rel, match.args) == split_locator(text)


@pytest.mark.parametrize(
    "line", ["", "plain text", 'python3 "${CLAUDE_PLUGIN_ROOT}/skills/x/y.py"']
)
def test_find_locators_ignores_text_that_is_not_a_locator(line: str) -> None:
    assert list(plugin_run_launcher.find_locators(line)) == []


@pytest.mark.parametrize(
    ("script_rel", "problem"),
    [("skills/../y.py", "not a plugin-root script path"), ("tools/y.py", "not a plugin-root")],
)
def test_find_locators_reports_a_bad_target_instead_of_raising(
    script_rel: str, problem: str
) -> None:
    text = render_locator(SCRIPT).replace(SCRIPT, script_rel)
    [match] = plugin_run_launcher.find_locators(f"x {text} y")
    assert match.script_rel is None
    assert match.problem is not None
    assert problem in match.problem


def test_find_locators_reports_a_head_with_no_tail() -> None:
    cut = render_locator(SCRIPT).split("; fi;")[0]
    [match] = plugin_run_launcher.find_locators(cut)
    assert (match.script_rel, match.problem) == (None, "locator has no closing text")


# ---- ADR-121 decision 12: the closed interpreter set -------------------------------------


@pytest.mark.parametrize("interpreter", plugin_run_launcher.INTERPRETERS)
def test_every_interpreter_renders_and_reads_back(interpreter: str) -> None:
    text = plugin_run_launcher.render_locator(
        "skills/x/scripts/y.py", '-a "b c"', interpreter=interpreter
    )
    assert f'exec {interpreter} "$d/lib/ptk_run.py" skills/x/scripts/y.py' in text
    assert plugin_run_launcher.split_locator(text) == ("skills/x/scripts/y.py", '-a "b c"')
    [match] = list(plugin_run_launcher.find_locators(f"run `{text}` now"))
    assert (match.script_rel, match.interpreter, match.problem) == (
        "skills/x/scripts/y.py",
        interpreter,
        None,
    )


def test_the_default_interpreter_text_is_unchanged() -> None:
    """Every site migrated before the amendment keeps its bytes."""
    assert plugin_run_launcher.render_locator(
        "skills/x/scripts/y.py"
    ) == plugin_run_launcher.render_locator("skills/x/scripts/y.py", interpreter="python3")
    assert (
        'exec python3 "$d/lib/ptk_run.py" skills/x/scripts/y.py;'
        in plugin_run_launcher.render_locator("skills/x/scripts/y.py")
    )


@pytest.mark.parametrize("interpreter", ["python", "python3 -u", "uv run python", "python3.11"])
def test_an_interpreter_outside_the_set_is_refused(interpreter: str) -> None:
    with pytest.raises(plugin_run_launcher.LauncherError, match="interpreter is not one of"):
        plugin_run_launcher.render_locator("skills/x/scripts/y.py", interpreter=interpreter)


def test_a_committed_locator_with_an_unknown_interpreter_is_reported() -> None:
    text = plugin_run_launcher.render_locator("skills/x/scripts/y.py").replace(
        "exec python3 ", "exec python3.11 "
    )
    [match] = list(plugin_run_launcher.find_locators(text))
    assert match.script_rel is None
    assert match.problem is not None and "python3.11" in match.problem
    assert plugin_run_launcher.split_locator(text) is None


# --- text after the closing parenthesis: arguments there never reach the script ---

_STRAY_ARGUMENTS = [
    " -x",
    ' --head "$BRANCH"',
    " --flag value",
    " somefile.txt",
    " skills/x/y.txt",
    ' "$VAR"',
    " $VAR",
    "  \t--flag",
    ' "quoted"',
    " 'quoted'",
    " 5",
    " ../input.json",
    " .env",
    " ..hidden",
    " thenable",
    " done.txt",
]

# A redirect is legal after a subshell. Text after its target is still stray.
_STRAY_AFTER_REDIRECT = [
    (" > out.txt --flag", "--flag"),
    (" 2>&1 --flag", "--flag"),
    (" >> out.txt 2> err.log somefile.txt", "somefile.txt"),
    (' < in.txt "$VAR"', '"$VAR"'),
    (">out.txt ../input.json", "../input.json"),
]

_NOT_ARGUMENTS = [
    "",
    " ",
    ")",
    " )",
    '"',
    "'",
    "`",
    "` and then prose after the code span",
    " |",
    "|",
    " && echo ok",
    " || true",
    " ; echo ok",
    ";",
    " | head -n 5",
    " > out.txt",
    " >> out.txt",
    " 2>&1",
    " 2> err.log",
    " < in.txt",
    " # a comment",
    " -->",
    " --!>",
    ".",
    "...",
    ". Then read the output.",
    ", then more",
    " > out.txt 2>&1",
    " > out.txt && echo ok",
    " 2>&1 | head -n 5",
    " then echo ok; fi",
    " then",
    " do",
    " done",
    " fi",
    " else echo no; fi",
    " elif true; then echo ok; fi",
    " esac",
]

# The quote after the locator closes the wrapper that holds it.
_WRAPPERS = [("bash -c '", " ' --"), ("bash -c '", "' --"), ('sh -c "', ' "'), ("x=' ", " '")]


@pytest.mark.parametrize("after", _STRAY_ARGUMENTS)
def test_find_locators_flags_arguments_after_the_closing_parenthesis(after: str) -> None:
    text = render_locator(SCRIPT)
    [match] = plugin_run_launcher.find_locators(f"run {text}{after} end")
    assert match.trailing is not None
    assert match.trailing == after.lstrip(" \t") + " end"


@pytest.mark.parametrize("after", _NOT_ARGUMENTS)
def test_find_locators_accepts_text_that_is_not_arguments_after_the_tail(after: str) -> None:
    [match] = plugin_run_launcher.find_locators(render_locator(SCRIPT) + after)
    assert match.trailing is None


@pytest.mark.parametrize(("after", "stray"), _STRAY_AFTER_REDIRECT)
def test_find_locators_reads_past_a_redirect_to_the_stray_argument(after: str, stray: str) -> None:
    [match] = plugin_run_launcher.find_locators(render_locator(SCRIPT) + after)
    assert match.trailing == stray


@pytest.mark.parametrize(("before", "after"), _WRAPPERS)
def test_find_locators_accepts_the_quote_that_closes_a_wrapper(before: str, after: str) -> None:
    [match] = plugin_run_launcher.find_locators(before + render_locator(SCRIPT) + after)
    assert match.trailing is None


@pytest.mark.parametrize("after", [" 'quoted'", ' "quoted"'])
def test_find_locators_flags_a_quoted_argument_after_a_closed_wrapper(after: str) -> None:
    line = "echo 'done' && " + render_locator(SCRIPT) + after
    [match] = plugin_run_launcher.find_locators(line)
    assert match.trailing == after.strip()


@pytest.mark.parametrize(
    "template",
    [
        "if {loc} then echo ok; fi",
        "if {loc} then echo ok; else echo no; fi",
        "for f in a b; do {loc} done",
        "while {loc} do sleep 1; done",
        "bash -c '{loc} ' --",
    ],
)
def test_the_accepted_shell_forms_parse(template: str) -> None:
    """The shapes the scan accepts are shell a POSIX parser accepts too."""
    line = template.replace("{loc}", render_locator(SCRIPT))
    assert [m.trailing for m in plugin_run_launcher.find_locators(line)] == [None]
    parsed = subprocess.run(["sh", "-n", "-c", line], capture_output=True, check=False)
    assert parsed.returncode == 0, parsed.stderr


@pytest.mark.parametrize("after", [" > out.txt --flag", " ../input.json", " .env"])
def test_the_flagged_shell_forms_do_not_parse(after: str) -> None:
    line = render_locator(SCRIPT) + after
    parsed = subprocess.run(["sh", "-n", "-c", line], capture_output=True, check=False)
    assert parsed.returncode != 0


def test_find_locators_flags_the_whole_rest_of_the_line_with_a_limit() -> None:
    long_rest = " --flag " + "x" * 200
    [match] = plugin_run_launcher.find_locators(render_locator(SCRIPT) + long_rest)
    assert match.trailing is not None
    assert match.trailing.startswith("--flag x")
    assert len(match.trailing) <= 60


def test_stray_arguments_leave_the_drift_scan_fields_unchanged() -> None:
    plain = render_locator(SCRIPT, "--a")
    [clean] = plugin_run_launcher.find_locators(plain)
    [stray] = plugin_run_launcher.find_locators(plain + " --b")
    assert (stray.start, stray.end, stray.script_rel, stray.args, stray.problem) == (
        clean.start,
        clean.end,
        clean.script_rel,
        clean.args,
        None,
    )


def test_stray_arguments_after_the_first_of_two_locators_are_found_per_locator() -> None:
    first = render_locator("skills/a/scripts/one.py")
    second = render_locator("skills/b/two.py")
    found = list(plugin_run_launcher.find_locators(f"{first} --x then {second}"))
    assert [m.trailing is None for m in found] == [False, True]


def test_stray_arguments_after_a_locator_with_a_problem_are_not_added() -> None:
    bad = render_locator(SCRIPT).replace(SCRIPT, "tools/y.py")
    [match] = plugin_run_launcher.find_locators(bad + " --x")
    assert match.problem is not None
    assert match.trailing is None
