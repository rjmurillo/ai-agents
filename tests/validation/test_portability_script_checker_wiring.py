"""Per-consumer wiring tests for `check_skill_portability.py` (#4252, #4454).

`main()` reaches the baseline guards down two independent paths, and each one
needs its own control. Every line number below is as of base `db5aab393`; the
function names are what actually anchor the claims. Verbatim from
`scripts/validation/check_skill_portability.py`::

    344:    baseline_path = _resolve_baseline_path(root, args.baseline)
    345:    if baseline_path is None:
    346:        return 2
    ...
    354:    if args.update_baseline:
    355:        return write_baseline(

`_resolve_baseline_path` delegates to `resolve_checked_baseline`, which runs
`if refuse_symlinked_baseline(root, resolved):` at
`scripts/validation/portability_common.py:190`. `write_baseline` reaches
`write_baseline_json` at `portability_common.py:217`, which runs
`if refuse_symlinked_baseline(repo_root, baseline_path):` again at
`scripts/validation/portability_baseline.py:428` and
`if refuse_dropped_entries(previous, counted, unit, allow_shrink, problem):` at
`:435`.

So the symlink condition is refused by *both* paths, and the resolver runs
first. A single symlinked-baseline control therefore observes neither: unwire
the writer and the resolver still returns 2, unwire the resolver and the writer
still returns 2. Each guard masks the other's removal. #4281 shipped exactly
that one control, and #4454 recorded the surviving mutant. Measured here on
`db5aab393`, both directions survived it::

    #4281 control with resolver unwired: rc=2 -> SURVIVED (test asserts ==2)
    #4281 control with writer unwired:   rc=2 -> SURVIVED (test asserts ==2)

Each path consequently gets a condition only that path can refuse, plus the
mutation that must kill it, asserted as a test rather than left in a commit
message. Exit code 2 alone is not evidence, because `main()` returns 2 from
several branches, so every control also asserts the refusing guard's own stderr
text and that the bytes it protects did not move.

The symlink refusal on the write path is not dropped, only tested where it can
be seen: `test_portability_baseline_destination.py::TestSymlinkedBaseline::
test_a_symlinked_parent_does_not_get_written_through` calls `write_baseline_json`
directly and asserts the victim still reads `DO NOT OVERWRITE`.

Exemplar for SHOULD-6 in `.claude/rules/testing.md`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.validation import check_skill_portability as csp  # noqa: E402

SYMLINK_REFUSAL = "Refusing a baseline reached through a symlink"
SHRINK_REFUSAL = "Refusing to write a baseline that reduces"


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


class TestScriptCheckerBaselineGuardWiring:
    """Drive `csp.main()` over conditions each guard alone can refuse."""

    def _populate(self, root: Path) -> None:
        skills = root / ".claude" / "skills"
        skills.mkdir(parents=True)
        (skills / "my-skill").mkdir()
        (skills / "my-skill" / "run.py").write_text(
            "# no upstream paths\nprint('hello')\n", encoding="utf-8"
        )
        _git(root, "init", "-q", "-b", "main")
        _git(root, "add", "-A")
        _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed")

    def _argv(self, root: Path, baseline: Path, *, update: bool) -> list[str]:
        argv = ["--repo-root", str(root), "--baseline", str(baseline)]
        return [*argv, "--update-baseline"] if update else argv

    def _symlinked_baseline(self, root: Path) -> tuple[Path, Path]:
        """Return `(link, target)`, skipping only when the platform refuses.

        Attempted rather than assumed: Windows creates symlinks under Developer
        Mode or an elevated shell, so skipping every `nt` run unconditionally
        gives up the coverage on the machines that do hold the privilege.
        """
        target = root / "real_baseline.json"
        target.write_text(json.dumps({"files": {}}), encoding="utf-8")
        link = root / "skill_portability_baseline.json"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f"symlink creation unavailable on this platform: {exc}")
        return link, target

    def _shrinking_baseline(self, root: Path) -> Path:
        """A real baseline recording debt the fresh scan cannot find.

        The fixture skill holds no upstream refs, so the replacement would drop
        `ghost/run.py` entirely. `read_previous_sections` reads the working-tree
        copy, so the entry does not need to be committed to be protected.
        """
        baseline = root / "skill_portability_baseline.json"
        baseline.write_text(
            json.dumps({"_comment": "seed", "files": {"ghost/run.py": 3}}, indent=2) + "\n",
            encoding="utf-8",
        )
        return baseline

    def test_positive_real_baseline_file_permits_write(self, tmp_path: Path) -> None:
        """Positive control: an ordinary baseline, both guards permit the write."""
        self._populate(tmp_path)
        baseline = tmp_path / "skill_portability_baseline.json"

        assert csp.main(self._argv(tmp_path, baseline, update=True)) == 0

        assert baseline.is_file()
        assert "files" in json.loads(baseline.read_text(encoding="utf-8"))

    def test_symlinked_baseline_is_refused_before_the_write_path(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Resolver wiring: the writer is unreachable, so only the resolver can refuse."""
        self._populate(tmp_path)
        link, target = self._symlinked_baseline(tmp_path)
        before = target.read_bytes()

        assert csp.main(self._argv(tmp_path, link, update=False)) == 2

        assert SYMLINK_REFUSAL in capsys.readouterr().err
        assert target.read_bytes() == before
        assert link.is_symlink()

    def test_unwiring_the_resolver_lets_the_symlinked_baseline_through(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Recorded mutation that must kill the control above.

        Replaces the consumer's resolver with one that hands the path back
        unvetted, which is what `check_skill_portability.py` no longer calling
        `resolve_checked_baseline` looks like. Measured on `db5aab393`: exit 0
        and no refusal on stderr. Without this the control is unfalsifiable,
        which is the defect #4454 records.
        """
        self._populate(tmp_path)
        link, _target = self._symlinked_baseline(tmp_path)
        monkeypatch.setattr(csp, "_resolve_baseline_path", lambda root, baseline: baseline)

        assert csp.main(self._argv(tmp_path, link, update=False)) == 0

        assert SYMLINK_REFUSAL not in capsys.readouterr().err

    def test_shrinking_baseline_is_refused_inside_the_writer(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Writer wiring: the resolver permits, so only the writer can refuse."""
        self._populate(tmp_path)
        baseline = self._shrinking_baseline(tmp_path)
        before = baseline.read_bytes()

        assert csp.main(self._argv(tmp_path, baseline, update=True)) == 2

        assert SHRINK_REFUSAL in capsys.readouterr().err
        assert baseline.read_bytes() == before

    def test_unwiring_the_writer_lets_the_shrinking_baseline_through(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Recorded mutation that must kill the control above.

        This is the exact mutation #4454 recorded as SURVIVING against the
        #4281 exemplar: `csp.write_baseline` replaced by a stub returning 0.
        Against a symlinked baseline it survived, because the resolver had
        already refused. Against this control, measured on `db5aab393`, it
        exits 0 and the guard's message is gone.
        """
        self._populate(tmp_path)
        baseline = self._shrinking_baseline(tmp_path)
        monkeypatch.setattr(csp, "write_baseline", lambda *args, **kwargs: 0)

        assert csp.main(self._argv(tmp_path, baseline, update=True)) == 0

        assert SHRINK_REFUSAL not in capsys.readouterr().err
