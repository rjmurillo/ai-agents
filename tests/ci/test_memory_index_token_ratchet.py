"""Tests for the memory-index token ratchet (issue #4441).

The gate under test answers one question: does every token count recorded in
``.serena/memories/memory-index.md`` match the file it points at? The repair
script has existed for a long time and runs as a ``pre-commit`` autofix, but
that autofix carries ``skip: merge`` and a ``SKIP_AUTOFIX`` escape, and nothing
downstream ever checked its result. Measured on pristine ``main``: two entries
were stale, one of them by 13 percent.

Coverage below is positive (a current index passes), negative (a stale index is
named and fails), and edge (missing count, absent target file, non-link lines,
missing tiktoken, missing index). The exit-code cases matter as much as the
detection: a verifier that cannot verify must say so rather than pass, because
a gate that goes green when it checked nothing is worse than no gate at all.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = _REPO_ROOT / "scripts" / "ci" / "memory_index_token_ratchet.py"

_spec = importlib.util.spec_from_file_location("memory_index_token_ratchet", _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
ratchet = importlib.util.module_from_spec(_spec)
sys.modules["memory_index_token_ratchet"] = ratchet
_spec.loader.exec_module(ratchet)


def _memory(memories_dir: Path, name: str, body: str) -> int:
    """Write a memory file and return its true token count."""
    path = memories_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    from update_memory_index_tokens import get_memory_token_count

    return int(get_memory_token_count(path))


@pytest.fixture
def memories_dir(tmp_path: Path) -> Path:
    scripts = str(_REPO_ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    target = tmp_path / "memories"
    target.mkdir()
    return target


class TestDriftedLines:
    """Detection: which index lines disagree with the files they point at."""

    def test_current_count_is_not_drift(self, memories_dir: Path) -> None:
        """Positive: an index whose counts are right reports nothing."""
        count = _memory(memories_dir, "alpha.md", "some memory body here\n")
        index = f"|topic: [alpha](alpha.md) ({count})"

        assert ratchet.drifted_lines(index, memories_dir) == []

    def test_stale_count_is_reported(self, memories_dir: Path) -> None:
        """Negative: the #4441 reproduction. A wrong count is named."""
        count = _memory(memories_dir, "alpha.md", "some memory body here\n")
        index = f"|topic: [alpha](alpha.md) ({count + 37})"

        drifted = ratchet.drifted_lines(index, memories_dir)

        assert len(drifted) == 1
        number, recorded, expected = drifted[0]
        assert number == 1
        assert f"({count + 37})" in recorded
        assert f"({count})" in expected

    def test_zero_placeholder_is_reported(self, memories_dir: Path) -> None:
        """Edge: ``(0)`` is the documented placeholder and must not survive.

        A reader budgeting context reads ``(0)`` as "this memory is empty, skip
        it", so the placeholder is worse than a merely stale number.
        """
        count = _memory(memories_dir, "alpha.md", "some memory body here\n")
        index = "|topic: [alpha](alpha.md) (0)"

        drifted = ratchet.drifted_lines(index, memories_dir)

        assert len(drifted) == 1
        assert f"({count})" in drifted[0][2]

    def test_missing_count_is_reported(self, memories_dir: Path) -> None:
        """Edge: a link with no count at all is drift, not an exemption."""
        count = _memory(memories_dir, "alpha.md", "some memory body here\n")
        index = "|topic: [alpha](alpha.md)"

        drifted = ratchet.drifted_lines(index, memories_dir)

        assert len(drifted) == 1
        assert f"({count})" in drifted[0][2]

    def test_absent_target_file_is_not_drift(self, memories_dir: Path) -> None:
        """Edge: an entry pointing at no file cannot have a countable size.

        Orphaned references are a different defect with its own validator. This
        gate reports only counts it can actually compute, so it never blocks a
        push on a condition it has no authority over.
        """
        index = "|topic: [ghost](ghost.md) (999)"

        assert ratchet.drifted_lines(index, memories_dir) == []

    def test_prose_lines_are_skipped(self, memories_dir: Path) -> None:
        """Edge: headings and prose carry no links and must not be scanned."""
        _memory(memories_dir, "alpha.md", "some memory body here\n")
        index = "# Memory Index\n\nPlain prose with no link at all.\n"

        assert ratchet.drifted_lines(index, memories_dir) == []

    def test_line_numbers_are_one_based(self, memories_dir: Path) -> None:
        """Edge: the reported line number must match an editor's own numbering."""
        count = _memory(memories_dir, "alpha.md", "some memory body here\n")
        index = "\n".join(["# Memory Index", "", f"|topic: [alpha](alpha.md) ({count + 5})"])

        drifted = ratchet.drifted_lines(index, memories_dir)

        assert [d[0] for d in drifted] == [3]

    def test_every_stale_entry_is_reported_not_just_the_first(
        self, memories_dir: Path
    ) -> None:
        """Negative: reporting one drift per run would hide the rest.

        Measured on pristine main, two entries were stale at once. A gate that
        stops at the first forces one push per drifted line to discover them.
        """
        a = _memory(memories_dir, "alpha.md", "alpha body\n")
        b = _memory(memories_dir, "beta.md", "beta body that is longer\n")
        index = "\n".join(
            [f"|one: [alpha](alpha.md) ({a + 1})", f"|two: [beta](beta.md) ({b + 2})"]
        )

        assert [d[0] for d in ratchet.drifted_lines(index, memories_dir)] == [1, 2]

    def test_several_links_on_one_line_are_all_corrected(
        self, memories_dir: Path
    ) -> None:
        """Edge: the real index packs many links per keyword line."""
        a = _memory(memories_dir, "alpha.md", "alpha body\n")
        b = _memory(memories_dir, "beta.md", "beta body that is longer\n")
        index = f"|topic: [alpha](alpha.md) ({a}), [beta](beta.md) ({b + 9})"

        drifted = ratchet.drifted_lines(index, memories_dir)

        assert len(drifted) == 1
        assert f"[beta](beta.md) ({b})" in drifted[0][2]
        assert f"[alpha](alpha.md) ({a})" in drifted[0][2]


class TestExitCodes:
    """The gate's contract with lefthook, per ADR-035."""

    def _point_at(self, monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
        monkeypatch.setattr(ratchet, "_REPO_ROOT", root)

    def test_returns_zero_when_every_count_is_current(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, memories_dir: Path
    ) -> None:
        """Positive: a clean index exits 0."""
        root = tmp_path / "repo"
        target = root / ".serena" / "memories"
        target.mkdir(parents=True)
        count = _memory(target, "alpha.md", "some memory body here\n")
        (target / "memory-index.md").write_text(
            f"|topic: [alpha](alpha.md) ({count})\n", encoding="utf-8"
        )
        self._point_at(monkeypatch, root)

        assert ratchet.main([]) == 0

    def test_returns_one_when_a_count_is_stale(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, memories_dir: Path
    ) -> None:
        """Negative: drift blocks the push."""
        root = tmp_path / "repo"
        target = root / ".serena" / "memories"
        target.mkdir(parents=True)
        count = _memory(target, "alpha.md", "some memory body here\n")
        (target / "memory-index.md").write_text(
            f"|topic: [alpha](alpha.md) ({count + 11})\n", encoding="utf-8"
        )
        self._point_at(monkeypatch, root)

        assert ratchet.main([]) == 1

    def test_returns_two_when_the_index_is_absent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Edge: no index means cannot-verify, not pass."""
        root = tmp_path / "repo"
        (root / ".serena" / "memories").mkdir(parents=True)
        self._point_at(monkeypatch, root)

        assert ratchet.main([]) == 2

    def test_returns_two_when_tiktoken_is_unavailable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Edge: an unusable counter must not report a green gate.

        tiktoken is a locked project dependency, so its absence is a broken
        environment rather than a routine skip. The repair script degrades to a
        warning here; the verifier must not, because degrading to success is
        exactly how the drift reached main.
        """
        root = tmp_path / "repo"
        target = root / ".serena" / "memories"
        target.mkdir(parents=True)
        (target / "memory-index.md").write_text("|t: [a](a.md) (1)\n", encoding="utf-8")
        self._point_at(monkeypatch, root)
        monkeypatch.setattr(ratchet, "HAS_TIKTOKEN", False)

        assert ratchet.main([]) == 2

    def test_stale_report_names_the_file_and_both_numbers(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Negative: the operator must be able to act without re-deriving it."""
        root = tmp_path / "repo"
        target = root / ".serena" / "memories"
        target.mkdir(parents=True)
        count = _memory(target, "alpha.md", "some memory body here\n")
        (target / "memory-index.md").write_text(
            f"|topic: [alpha](alpha.md) ({count + 11})\n", encoding="utf-8"
        )
        self._point_at(monkeypatch, root)

        ratchet.main([])

        err = capsys.readouterr().err
        assert "alpha.md" in err
        assert str(count) in err
        assert str(count + 11) in err
        assert "scripts/update_memory_index_tokens.py" in err


class TestRegisteredInBothGates:
    """The gate has to be reachable, which is the whole defect it closes.

    #4441 exists because a working repair script was wired only to an autofix
    that skips merges. A verifier registered in one place and not the other
    would repeat that mistake in a new shape.
    """

    def test_registered_in_the_pre_pr_ratchet_registry(self) -> None:
        sys.path.insert(0, str(_REPO_ROOT / "scripts" / "validation"))
        import checks_ratchet

        names = {r.job_name for r in checks_ratchet.RATCHETS}
        assert "memory-index-token-ratchet" in names

    def test_aggregate_registry_runner_is_the_pre_push_job(self) -> None:
        text = (_REPO_ROOT / "lefthook.yml").read_text(encoding="utf-8")
        assert "- name: count-ratchets" in text
        assert "scripts/validation/checks_ratchet.py" in text
