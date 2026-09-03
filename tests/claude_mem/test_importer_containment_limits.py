"""What `expand_home` deliberately does NOT guarantee.

Its own module because this pins a NEGATIVE claim, and a negative claim needs a
findable home. The retrospective and the function docstring both state that the
invariant is narrow: an expanded current-user `~` must not silently discard the
injected `home`. That is not containment.

An earlier revision of the retrospective said the result "stays under `home`",
which is false in three ways shown below. The wording is corrected; these tests
keep it corrected, so a later reader does not "fix" the escapes here as bugs, and
does not cite this helper as a path sandbox (CWE-22) it was never built to be.

If containment is ever actually required, `_is_within` in
`.claude/skills/skillforge/scripts/quick_validate.py` is the repo's real
containment check and uses `commonpath` rather than a prefix match.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

# Import the module under test by file path since it lives outside scripts/.

_base = os.path.join(os.path.dirname(__file__), "..", "..", ".claude-mem", "scripts")


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_base, filename))
    assert spec is not None, f"Failed to find {filename}"
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None, f"Module spec for {filename} has no loader"
    # dataclasses resolves a class's module through sys.modules, so a module
    # executed without registration raises AttributeError at class creation.
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_import_mem = _load("import_claude_mem_memories", "import_claude_mem_memories.py")


class TestExpandHomeIsNotAContainmentCheck:
    """Three inputs that leave `home`, each on purpose."""

    def test_dot_dot_in_the_suffix_still_escapes(self, tmp_path: Path) -> None:
        """The guard stops a suffix from REPLACING home, not from walking out of it."""
        result = _import_mem.expand_home("~/../outside", tmp_path)

        assert result == tmp_path / ".." / "outside"
        assert not result.resolve().is_relative_to(tmp_path.resolve())

    def test_an_absolute_path_is_returned_as_given(self, tmp_path: Path) -> None:
        """No tilde, so nothing to expand. A caller may legitimately name any path."""
        result = _import_mem.expand_home("/etc/passwd", tmp_path)

        assert result == Path("/etc/passwd")
        assert not result.is_relative_to(tmp_path)

    def test_other_user_tilde_is_left_relative_rather_than_contained(
        self, tmp_path: Path
    ) -> None:
        """`~otheruser` is a non-expansion, not a rejection and not a containment."""
        result = _import_mem.expand_home("~otheruser/x", tmp_path)

        assert result == Path("~otheruser/x")
        assert not result.is_absolute()

    def test_the_narrow_invariant_that_does_hold(self, tmp_path: Path) -> None:
        """The positive half, stated next to the negatives so the line is visible.

        A rooted suffix cannot replace home during tilde expansion. This is the
        whole of what the guard promises.
        """
        result = _import_mem.expand_home("~//importer.ts", tmp_path)

        assert result == tmp_path / "importer.ts"
