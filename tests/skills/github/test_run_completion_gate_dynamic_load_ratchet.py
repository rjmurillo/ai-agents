"""Ratchet: no shipped verifier reaches a dynamic-load route the gate cannot see.

Issue #6032. The gate's dynamic-load scanner is a denylist (see the comment
above ``_MODULE_LOADS`` in ``run_completion_gate.py``). A trusted verifier that
runs a PR-edited file through a route the denylist omits is dispatched
unverified. These tests scan the verifier closure of the shipped
``pr-review-config.yaml``, computed by the gate's own functions, and fail with
``file:line`` on any such route. The detector lives in
``dynamic_load_routes.py``; ``TestDetectorPositiveControls`` proves it fires on
each route, so a clean ratchet is not a detector that finds nothing.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.skills.github.dynamic_load_helpers import (
    REPO_ROOT,
    closure,
    gate,
    shipped_verifier_closure,
    write,
)
from tests.skills.github.dynamic_load_routes import ROUTES, unrecognised_routes

# Reviewed sites: (path, route, detail) -> (expected count, why the site is safe).
# A site not listed fails the ratchet. A listed site that disappears also
# fails, so the list can only shrink or be re-reviewed, never go stale. The
# detail is part of the key, so turning a reviewed script launch into a
# `python -c` launch is a new site.
_PR_DIR = ".claude/skills/github/scripts/pr"
_REVIEWED: dict[tuple[str, str, str], tuple[int, str]] = {
    (
        f"{_PR_DIR}/wait_for_unresolved_zero.py",
        "subprocess-python",
        "python launching a script or module",
    ): (
        1,
        "launches get_unresolved_review_threads.py, a sibling the config names, so it is "
        "byte-verified (see test_reviewed_launcher_target_is_itself_verified)",
    ),
}
_REVIEWED_LAUNCHER_TARGET = f"{_PR_DIR}/get_unresolved_review_threads.py"


def _scan(closure_paths: list[str]) -> tuple[int, list[tuple[str, int, str, str]]]:
    """``(python files scanned, [(path, line, route, detail), ...])``."""
    scanned = 0
    found: list[tuple[str, int, str, str]] = []
    for rel in closure_paths:
        if not rel.endswith(".py"):
            continue
        scanned += 1
        for hit in unrecognised_routes((REPO_ROOT / rel).read_bytes()):
            found.append((rel, hit.line, hit.route, hit.detail))
    return scanned, found


class TestShippedClosureRatchet:
    def test_closure_holds_no_unreviewed_unrecognised_route(self) -> None:
        _named, closure_paths = shipped_verifier_closure()
        scanned, found = _scan(closure_paths)
        assert scanned >= 20, f"only {scanned} python files scanned; the scope shrank"

        counts: dict[tuple[str, str, str], int] = {}
        unreviewed: list[str] = []
        for path, line, route, detail in found:
            key = (path, route, detail)
            counts[key] = counts.get(key, 0) + 1
            if key not in _REVIEWED:
                unreviewed.append(f"{path}:{line}: {route} ({detail})")

        assert unreviewed == [], (
            f"{scanned} files scanned. A verifier reaches a dynamic-load route the completion "
            "gate does not recognise (issue 6032). Load the file by a literal the gate "
            "resolves, or review the site and add it to _REVIEWED:\n" + "\n".join(unreviewed)
        )
        stale = {
            key: expected
            for key, (expected, _why) in _REVIEWED.items()
            if counts.get(key, 0) != expected
        }
        assert stale == {}, f"_REVIEWED entries no longer match the closure: {stale}"

    def test_closure_does_not_depend_on_the_callers_plugin_root(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The pre-push hook exports CLAUDE_PLUGIN_ROOT=src/copilot-cli (git_hook_policy.py)."""
        baseline = shipped_verifier_closure()
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(REPO_ROOT / "src" / "copilot-cli"))
        monkeypatch.setenv("COPILOT_PLUGIN_ROOT", str(REPO_ROOT / "src" / "copilot-cli"))

        assert shipped_verifier_closure() == baseline
        assert not any(path.startswith("src/") for path in baseline[1])

    def test_reviewed_launcher_target_is_itself_verified(self) -> None:
        named, closure_paths = shipped_verifier_closure()

        assert _REVIEWED_LAUNCHER_TARGET in named
        assert _REVIEWED_LAUNCHER_TARGET in closure_paths

    def test_every_closure_path_is_tracked_with_exact_case(self) -> None:
        """A wrong-case literal passes ``is_file()`` on a case-insensitive filesystem.

        Git reports such a path untracked, and the gate skips an untracked
        file as the operator's own state. The closure resolves paths against
        the disk, so compare each one to the tracked name byte for byte.
        """
        proc = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            pytest.skip(f"not a git checkout: {proc.stderr.decode(errors='replace').strip()}")
        tracked = set(proc.stdout.decode().split("\0"))
        _named, closure_paths = shipped_verifier_closure()

        assert [path for path in closure_paths if path not in tracked] == []


class TestClosureDoesNotFollowSubprocessLaunches:
    """Why the ratchet covers the subprocess route itself.

    If this class starts failing, the gate learned to follow launched scripts:
    re-review the ``subprocess-python`` route and ``_REVIEWED``.
    """

    def test_a_script_launched_by_argv_is_outside_the_closure(self, tmp_path: Path) -> None:
        write(
            tmp_path,
            "verify.py",
            """\
            import subprocess, sys
            subprocess.run([sys.executable, "-I", "launched.py"])
            """,
        )
        write(tmp_path, "launched.py", "X = 1\n")

        assert closure(tmp_path, "verify.py") == ["verify.py"]
        assert gate._unresolvable_dynamic_sites(["verify.py"], tmp_path) == []


_ROUTE_FIXTURES: dict[str, list[str]] = {
    "alias": [
        "import importlib\nm = importlib.import_module\nm('x')\n",
        "from importlib import import_module as im\nim('x')\n",
        "list(map(__import__, ['a', 'b']))\n",
        "run = exec\nrun('1')\n",
        "from runpy import run_path as rp\n",
    ],
    "getattr": [
        "import importlib\ngetattr(importlib, name)(x)\n",
        "import importlib\ngetattr(importlib, 'import_module')('x')\n",
        "getattr(anything, '__import__')('x')\n",
        "import runpy\ngetattr(runpy, name)('x')\n",
    ],
    "builtins": [
        "import builtins\nbuiltins.exec('1')\n",
        "import builtins\nbuiltins.eval('1')\n",
        "__builtins__['exec']('1')\n",
        "import builtins\nbuiltins.__import__('x')\n",
        "import builtins as b\nb.exec('1')\n",
    ],
    "loader-api": [
        "from importlib.machinery import ExtensionFileLoader\n",
        "import importlib.machinery as m\nm.SourcelessFileLoader('a', 'b')\n",
        "import importlib.util\nimportlib.util.spec_from_loader('a', loader)\n",
        "import zipimport\n",
        "from zipimport import zipimporter\n",
        "import pkgutil\n",
        "from pkgutil import get_data\n",
    ],
    "serialization-or-native": [
        "import pickle\n",
        "from pickle import loads\n",
        "__import__('pickle').loads(data)\n",
        "import importlib\nimportlib.import_module('ctypes.util')\n",
        "import marshal\n",
        "import ctypes\n",
        "import ctypes.util\n",
        "from ctypes import CDLL\n",
    ],
    "subprocess-python": [
        "import subprocess, sys\nsubprocess.run([sys.executable, '-c', 'import x'])\n",
        "import subprocess, sys\nsubprocess.run([sys.executable, '-I', 'other.py'])\n",
        "import subprocess\nsubprocess.run(['python3', 'other.py'])\n",
        "import subprocess\nsubprocess.run(('python', '-m', 'pkg'))\n",
        "import subprocess\nsubprocess.run(['/usr/bin/python3.14', 'other.py'])\n",
        "import subprocess\nsubprocess.run(['python3.14t', 'other.py'])\n",
    ],
    "sys-modules": [
        "import sys\nsys.modules['x'] = object()\n",
        "import sys\ndel sys.modules['x']\n",
        "import sys\nsys.modules.update({'x': object()})\n",
        "import sys\nsys.modules.setdefault('x', object())\n",
        "import sys as s\ns.modules['x'] = object()\n",
    ],
}

_CASES = [(route, source) for route, sources in _ROUTE_FIXTURES.items() for source in sources]


class TestDetectorPositiveControls:
    def test_fixtures_cover_every_route(self) -> None:
        assert set(_ROUTE_FIXTURES) == set(ROUTES)

    @pytest.mark.parametrize(("route", "source"), _CASES)
    def test_detector_flags_the_route(self, route: str, source: str) -> None:
        assert route in {hit.route for hit in unrecognised_routes(source)}, source

    def test_hits_carry_the_line_of_the_site(self) -> None:
        hits = unrecognised_routes("import os\n\nimport pickle\n")

        assert [(hit.line, hit.route) for hit in hits] == [(3, "serialization-or-native")]

    def test_hits_come_back_in_line_order_without_duplicates(self) -> None:
        hits = unrecognised_routes("import sys\nimport pickle\nimport ctypes\nimport pickle\n")

        assert [hit.line for hit in hits] == [2, 3, 4]

    @pytest.mark.parametrize(
        "source",
        [
            "import importlib\nimportlib.import_module('x')\n",
            "__import__('x')\n",
            "exec('1')\neval('2')\n",
            "import json, os, subprocess\nsubprocess.run(['git', 'status'])\n",
            "import sys\nsys.modules.get('x')\nsys.modules['x']\n",
            "import sys\nsys.path.insert(0, 'lib')\nprint(sys.executable)\n",
            "getattr(args, name)\n",
            "from importlib import import_module\nimport_module('x')\n",
            "subprocess.run(['git', '-c', 'core.x=y', 'status'])\n",
            "run_path = repo / 'x'\nimport_module = None\n",
            "importlib.import_module('json')\n__import__('os')\n",
        ],
    )
    def test_detector_ignores_shapes_the_gate_already_covers_or_that_are_benign(
        self, source: str
    ) -> None:
        assert unrecognised_routes(source) == []

    def test_uncalled_eval_attribute_is_flagged_by_design(self) -> None:
        assert [hit.route for hit in unrecognised_routes("fn = model.eval\n")] == ["alias"]

    def test_unparseable_source_raises_instead_of_reading_clean(self) -> None:
        with pytest.raises(SyntaxError):
            unrecognised_routes("def f(:\n")
