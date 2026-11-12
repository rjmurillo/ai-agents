"""The committed locator runs under a real shell, from a directory that is not the plugin root.

ADR-121 and `generated-artifacts.md` (MUST 2): a customer-facing launcher needs a test
that executes it under the runtime contract, plus a negative control. Structure tests
shipped the PR #2205 incident for 33 days.

The harness builds a temporary plugin tree that holds a copy of the real
`src/claude/lib/ptk_run.py` and a stub `skills/x/scripts/y.py`. It runs
`plugin_run_launcher.render_locator(...)` through `sh -c` with a cwd that holds no
plugin. The stub prints its tag, `sys.argv`, and exits with `$STUB_EXIT`.

* Foreign roots: a plugin that exports `CLAUDE_PLUGIN_ROOT` (the context-mode case of
  issue #7281) has no `lib/ptk_run.py`, so the locator skips it.
* The accepted limit of ADR-121 decision 10: a foreign root that DOES hold a resolver
  wins when it is first.
* The negative control runs the legacy `${A:-${B:-.claude}}` form through the same
  harness and shows it fails where the locator succeeds.
* The quoting matrix records what happens when the host inlines a root path that holds
  `$`, a backtick, or a double quote into the locator's double quotes.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

from plugin_run_launcher import render_locator  # noqa: E402

RESOLVER_SOURCE = REPO_ROOT / "src" / "claude" / "lib" / "ptk_run.py"
SCRIPT = "skills/x/scripts/y.py"
TOKEN = "${CLAUDE_PLUGIN_ROOT}"
LEGACY = 'python3 "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/x/scripts/y.py"'
NO_ROOT_MESSAGE = "ptk_run: no plugin root holds lib/ptk_run.py\n"

SHELLS = [s for s in ("sh", "bash") if shutil.which(s)]
pytestmark = pytest.mark.skipif(os.name != "posix" or not SHELLS, reason="POSIX shell required")

STUB = """\
import json, os, sys
print(json.dumps({"tag": "TAG", "argv": sys.argv[1:]}))
sys.exit(int(os.environ.get("STUB_EXIT", "0")))
"""


@dataclass(frozen=True)
class World:
    base: Path
    ours: Path
    foreign_empty: Path
    foreign_script: Path
    foreign_resolver: Path
    cwd: Path
    bin_dir: Path


def _stub(root: Path, tag: str) -> None:
    script = root / SCRIPT
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(STUB.replace("TAG", tag), encoding="utf-8")


def _resolver(root: Path) -> None:
    (root / "lib").mkdir(parents=True, exist_ok=True)
    shutil.copy(RESOLVER_SOURCE, root / "lib" / "ptk_run.py")


@pytest.fixture
def world(tmp_path: Path) -> World:
    """Roots, none of them the cwd. `ours` has a space in its name on purpose."""
    ours = tmp_path / "our plugin"
    foreign_empty = tmp_path / "foreign-empty"
    foreign_script = tmp_path / "foreign-script"
    foreign_resolver = tmp_path / "foreign-resolver"
    cwd = tmp_path / "cwd"
    bin_dir = tmp_path / "bin"
    for directory in (foreign_empty, cwd, bin_dir):
        directory.mkdir()
    _resolver(ours)
    _stub(ours, "ours")
    _stub(foreign_script, "foreign")
    _resolver(foreign_resolver)
    _stub(foreign_resolver, "foreign-resolver")
    (bin_dir / "python3").symlink_to(sys.executable)
    return World(tmp_path, ours, foreign_empty, foreign_script, foreign_resolver, cwd, bin_dir)


def _run(
    world: World, text: str, *, shell: str = "sh", cwd: Path | None = None, **env: str
) -> subprocess.CompletedProcess[str]:
    """Run `text` as `<shell> -c`. `env` adds variables; the host's plugin roots are dropped."""
    base = {k: v for k, v in os.environ.items() if "PLUGIN_ROOT" not in k}
    base["PATH"] = f"{world.bin_dir}{os.pathsep}{base.get('PATH', '')}"
    return subprocess.run(
        [shutil.which(shell) or shell, "-c", text],
        cwd=cwd or world.cwd,
        env={**base, **env},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _tag(result: subprocess.CompletedProcess[str]) -> str:
    return str(json.loads(result.stdout)["tag"])


def _argv(result: subprocess.CompletedProcess[str]) -> list[str]:
    return list(json.loads(result.stdout)["argv"])


# ---- Root selection ----------------------------------------------------------------------


def test_foreign_root_is_skipped_and_ours_runs_via_copilot_plugin_root(world: World) -> None:
    result = _run(
        world,
        render_locator(SCRIPT),
        CLAUDE_PLUGIN_ROOT=str(world.foreign_script),
        COPILOT_PLUGIN_ROOT=str(world.ours),
    )
    assert (result.returncode, _tag(result)) == (0, "ours"), result.stderr


def test_foreign_root_without_our_script_is_skipped_the_same_way(world: World) -> None:
    result = _run(
        world,
        render_locator(SCRIPT),
        CLAUDE_PLUGIN_ROOT=str(world.foreign_empty),
        COPILOT_PLUGIN_ROOT=str(world.ours),
    )
    assert (result.returncode, _tag(result)) == (0, "ours"), result.stderr


def test_host_rewritten_token_runs_ours_whatever_the_environment_holds(world: World) -> None:
    """The host replaces the bare token with the loaded plugin's absolute path (ADR-121 row 2)."""
    text = render_locator(SCRIPT).replace(TOKEN, str(world.ours))
    result = _run(
        world,
        text,
        CLAUDE_PLUGIN_ROOT=str(world.foreign_script),
        COPILOT_PLUGIN_ROOT=str(world.foreign_resolver),
    )
    assert (result.returncode, _tag(result)) == (0, "ours"), result.stderr


def test_a_foreign_root_that_holds_a_resolver_wins_when_first_the_accepted_limit(
    world: World,
) -> None:
    """ADR-121 decision 10: the resolver is not an authentication boundary.

    Any root that holds `lib/ptk_run.py` passes the probe, including a second install of
    this plugin. This test documents that limit; it does not endorse it.
    """
    result = _run(
        world,
        render_locator(SCRIPT),
        CLAUDE_PLUGIN_ROOT=str(world.foreign_resolver),
        COPILOT_PLUGIN_ROOT=str(world.ours),
    )
    assert (result.returncode, _tag(result)) == (0, "foreign-resolver")


def test_both_variables_unset_falls_to_the_dogfood_root_under_the_cwd(world: World) -> None:
    dogfood = world.cwd / ".claude"
    _resolver(dogfood)
    _stub(dogfood, "dogfood")
    result = _run(world, render_locator(SCRIPT))
    assert (result.returncode, _tag(result)) == (0, "dogfood"), result.stderr


def test_empty_variables_are_skipped_not_probed_as_the_cwd(world: World) -> None:
    """`[ -n "$d" ]` keeps an empty variable from probing `/lib/ptk_run.py`."""
    dogfood = world.cwd / ".claude"
    _resolver(dogfood)
    _stub(dogfood, "dogfood")
    result = _run(world, render_locator(SCRIPT), CLAUDE_PLUGIN_ROOT="", COPILOT_PLUGIN_ROOT="")
    assert (result.returncode, _tag(result)) == (0, "dogfood"), result.stderr


def test_no_root_holds_the_resolver_exits_2_with_the_prefix_and_runs_nothing(
    world: World,
) -> None:
    result = _run(
        world,
        render_locator(SCRIPT),
        CLAUDE_PLUGIN_ROOT=str(world.foreign_script),
        COPILOT_PLUGIN_ROOT=str(world.foreign_empty),
    )
    assert result.returncode == 2
    assert result.stderr == NO_ROOT_MESSAGE
    assert result.stdout == ""


def test_a_root_whose_resolver_exists_but_whose_target_does_not_exits_2_loud(
    world: World,
) -> None:
    """ADR-121 version skew: the first root that passes the probe is final."""
    result = _run(
        world,
        render_locator("skills/x/scripts/other.py"),
        CLAUDE_PLUGIN_ROOT=str(world.ours),
        COPILOT_PLUGIN_ROOT=str(world.ours),
    )
    assert result.returncode == 2
    assert result.stderr.startswith("ptk_run: target is not a file")


def test_the_cwd_is_not_the_plugin_root_in_every_case(world: World) -> None:
    assert not (world.cwd / "lib").exists() and not (world.cwd / "skills").exists()


# ---- Arguments and exit codes ------------------------------------------------------------

AWKWARD_ARGS = [
    "two words",
    "-x",
    "--flag=a b",
    "a;b",
    "$(echo hi)",
    "`echo hi`",
    "line1\nline2",
    "it's",
    '"dq"',
    "*",
    "",
]


def test_arguments_with_spaces_dash_semicolon_substitution_and_newline_arrive_intact(
    world: World,
) -> None:
    args = " ".join(shlex.quote(a) for a in AWKWARD_ARGS)
    result = _run(world, render_locator(SCRIPT, args), COPILOT_PLUGIN_ROOT=str(world.ours))
    assert result.returncode == 0, result.stderr
    assert _argv(result) == AWKWARD_ARGS


@pytest.mark.parametrize("code", [0, 1, 3, 4])
def test_target_exit_codes_pass_through(world: World, code: int) -> None:
    result = _run(
        world, render_locator(SCRIPT), COPILOT_PLUGIN_ROOT=str(world.ours), STUB_EXIT=str(code)
    )
    assert result.returncode == code
    assert "ptk_run:" not in result.stderr


def test_a_target_exit_2_is_told_from_a_resolver_exit_2_by_the_prefix(world: World) -> None:
    target = _run(world, render_locator(SCRIPT), COPILOT_PLUGIN_ROOT=str(world.ours), STUB_EXIT="2")
    resolver = _run(world, render_locator(SCRIPT))
    assert target.returncode == resolver.returncode == 2
    assert "ptk_run:" not in target.stderr
    assert resolver.stderr.startswith("ptk_run:")


# ---- Targets that fail validation --------------------------------------------------------


def _with_target(target: str) -> str:
    """The locator with `target` swapped in, shell-quoted. The recipe refuses most of these."""
    return render_locator(SCRIPT).replace(SCRIPT, shlex.quote(target))


@pytest.mark.parametrize(
    "target",
    [
        "skills/../lib/ptk_run.py",
        "skills/x/../../lib/ptk_run.py",
        "/etc/passwd.py",
        f"/{SCRIPT}",
        "skills/x/scripts/y.sh",
        "skills/x/scripts/missing.py",
        "skills/x/scripts/dir.py",
        "skills\\x\\scripts\\y.py",
        "lib/ptk_run.py",
        "--help",
        "",
    ],
)
def test_a_target_that_fails_validation_exits_2_with_the_prefix(world: World, target: str) -> None:
    (world.ours / "skills" / "x" / "scripts" / "dir.py").mkdir()
    result = _run(world, _with_target(target), COPILOT_PLUGIN_ROOT=str(world.ours))
    assert result.returncode == 2
    assert result.stderr.startswith("ptk_run:")
    assert result.stdout == ""


# ---- Persistent shell --------------------------------------------------------------------


@pytest.mark.parametrize("shell", SHELLS)
def test_the_locator_survives_a_persistent_shell_on_failure_and_on_success(
    world: World, shell: str
) -> None:
    failed = _run(world, f"{render_locator(SCRIPT)}; echo alive=$?", shell=shell)
    assert failed.stdout == "alive=2\n"
    ran = _run(
        world,
        f"{render_locator(SCRIPT)}; echo alive=$?",
        shell=shell,
        COPILOT_PLUGIN_ROOT=str(world.ours),
    )
    assert ran.stdout.endswith("alive=0\n")


# ---- Negative control: the legacy form fails the same harness ----------------------------


def test_negative_control_the_legacy_form_fails_under_a_foreign_root(world: World) -> None:
    """Issue #7281: context-mode's `CLAUDE_PLUGIN_ROOT` hides our script from the legacy form."""
    legacy = _run(world, LEGACY, CLAUDE_PLUGIN_ROOT=str(world.foreign_empty))
    assert legacy.returncode != 0
    assert "No such file" in legacy.stderr
    located = _run(
        world,
        render_locator(SCRIPT),
        CLAUDE_PLUGIN_ROOT=str(world.foreign_empty),
        COPILOT_PLUGIN_ROOT=str(world.ours),
    )
    assert (located.returncode, _tag(located)) == (0, "ours")


def test_negative_control_the_legacy_form_runs_a_foreign_same_named_script(world: World) -> None:
    legacy = _run(world, LEGACY, CLAUDE_PLUGIN_ROOT=str(world.foreign_script))
    assert (legacy.returncode, _tag(legacy)) == (0, "foreign")
    located = _run(
        world,
        render_locator(SCRIPT),
        CLAUDE_PLUGIN_ROOT=str(world.foreign_script),
        COPILOT_PLUGIN_ROOT=str(world.ours),
    )
    assert _tag(located) == "ours"


def test_negative_control_the_harness_distinguishes_a_bare_relative_path(world: World) -> None:
    """A guard on the harness: a cwd-relative command must fail here, as in the incident."""
    bare = _run(world, f"python3 {SCRIPT}")
    assert bare.returncode != 0 and "No such file" in bare.stderr


# ---- Quoting matrix: a host-inlined root with shell metacharacters -----------------------


def _inlined(
    world: World, dirname: str, shell: str, **env: str
) -> subprocess.CompletedProcess[str]:
    """Plant a plugin under a root named `dirname`, then run the locator with it inlined.

    The host writes the absolute root into the double quotes of the first candidate.
    """
    root = world.base / dirname
    _resolver(root)
    _stub(root, "inlined")
    text = render_locator(SCRIPT).replace(TOKEN, str(root))
    return _run(world, text, shell=shell, **env)


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("dirname", ["a b", "back\\slash", "single'quote", "semi;colon"])
def test_quoting_matrix_survives_space_backslash_single_quote_and_semicolon(
    world: World, shell: str, dirname: str
) -> None:
    result = _inlined(world, dirname, shell)
    assert (result.returncode, _tag(result)) == (0, "inlined"), result.stderr


@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("dirname", ["root$HOME", "root$unset", "root${unset}"])
def test_quoting_matrix_dollar_expands_so_the_candidate_misses_and_fails_loud(
    world: World, shell: str, dirname: str
) -> None:
    """Observed: the shell expands `$` inside the double quotes, so the inlined path
    names a directory that does not exist. The loop skips it; with nothing else it exits 2."""
    alone = _inlined(world, dirname, shell)
    assert (alone.returncode, alone.stderr) == (2, NO_ROOT_MESSAGE)


@pytest.mark.parametrize("shell", SHELLS)
def test_quoting_matrix_dollar_falls_through_to_the_next_candidate(
    world: World, shell: str
) -> None:
    other = world.base / "next-root"
    _resolver(other)
    _stub(other, "next")
    result = _inlined(world, "root$unset", shell, COPILOT_PLUGIN_ROOT=str(other))
    assert (result.returncode, _tag(result)) == (0, "next")


@pytest.mark.parametrize("shell", SHELLS)
def test_quoting_matrix_backtick_runs_as_a_command_substitution_a_known_limit(
    world: World, shell: str
) -> None:
    """Observed: a backtick in the inlined root is command substitution, so the shell
    runs the text between the ticks (here `touch marker`, in the cwd) before probing.
    The form does NOT survive a backtick in the host's root path. The path is the
    host's own install directory, not model or repo input, which bounds the exposure."""
    result = _inlined(world, "root`touch marker`z", shell)
    assert (world.cwd / "marker").is_file()
    assert (result.returncode, result.stderr) == (2, NO_ROOT_MESSAGE)


@pytest.mark.parametrize("shell", SHELLS)
def test_quoting_matrix_double_quote_breaks_the_whole_command_with_a_shell_syntax_error(
    world: World, shell: str
) -> None:
    """Observed: an inlined `"` ends the candidate's quoting early and the command
    does not parse. It exits 2 from the shell (not the `ptk_run:` prefix) and runs
    nothing, even when a later candidate is valid."""
    other = world.base / "next-root"
    _resolver(other)
    _stub(other, "next")
    result = _inlined(world, 'root"q', shell, COPILOT_PLUGIN_ROOT=str(other))
    assert result.returncode == 2
    assert result.stdout == ""
    assert not result.stderr.startswith("ptk_run:")
    assert "rror" in result.stderr or "unexpected" in result.stderr
