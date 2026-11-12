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
    assert {"project-toolkit-delivery", "project-toolkit-knowledge"} <= names
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
            ["git", "-C", str(REPO_ROOT), "config", "--get", "core.symlinks"],
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
