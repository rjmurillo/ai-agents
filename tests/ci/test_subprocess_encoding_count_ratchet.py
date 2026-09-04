"""Tests for the subprocess encoding count ratchet (issue #4261)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scripts.ci import subprocess_encoding_count_ratchet as ratchet
from scripts.validation import check_subprocess_encoding
from tests.ci.ratchet_test_helpers import make_baseline_writer


def _git(repo_root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo_root), *args], check=True)


_write_baseline = make_baseline_writer("subprocess_encoding_count_baseline.txt")


def test_count_equal_to_baseline_passes(tmp_path, monkeypatch):
    baseline = _write_baseline(tmp_path, "5")
    monkeypatch.setattr(ratchet, "current_count", lambda _root: 5)
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_OK


def test_count_above_baseline_is_regression(tmp_path, monkeypatch):
    baseline = _write_baseline(tmp_path, "5")
    monkeypatch.setattr(ratchet, "current_count", lambda _root: 6)
    rc = ratchet.main(["--baseline", str(baseline), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_REGRESSION


def test_missing_baseline_is_config_error(tmp_path, monkeypatch):
    monkeypatch.setattr(ratchet, "current_count", lambda _root: 5)
    rc = ratchet.main(["--baseline", str(tmp_path / "absent.txt"), "--repo-root", str(tmp_path)])
    assert rc == ratchet.EXIT_CONFIG


def test_current_count_counts_checker_findings(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    script_dir = tmp_path / "scripts"
    script_dir.mkdir()
    (script_dir / "bad.py").write_text(
        "import subprocess\n"
        "subprocess.run(['x'], capture_output=True, encoding='utf-8')\n",
        encoding="utf-8",
    )
    (script_dir / "good.py").write_text(
        "import subprocess\n"
        "subprocess.run(['x'], capture_output=True, encoding='utf-8', errors='replace')\n",
        encoding="utf-8",
    )
    _git(tmp_path, "add", "scripts/bad.py", "scripts/good.py")

    assert ratchet.current_count(tmp_path) == 1


def test_current_count_counts_pipe_captures_and_aliases(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    script_dir = tmp_path / "scripts"
    script_dir.mkdir()
    (script_dir / "bad_stdout.py").write_text(
        "import subprocess\n"
        "subprocess.run(['x'], stdout=subprocess.PIPE, encoding='utf-8')\n",
        encoding="utf-8",
    )
    (script_dir / "bad_alias.py").write_text(
        "from subprocess import PIPE as CAPTURE, run as srun\n"
        "srun(['x'], stderr=CAPTURE, encoding='utf-8')\n",
        encoding="utf-8",
    )
    (script_dir / "bad_module_alias.py").write_text(
        "import subprocess as sp\n"
        "sp.run(['x'], stderr=sp.PIPE, encoding='utf-8')\n",
        encoding="utf-8",
    )
    (script_dir / "bad_assigned_module_alias.py").write_text(
        "import subprocess\n"
        "sp = subprocess\n"
        "sp.run(['x'], stdout=sp.PIPE, encoding='utf-8')\n",
        encoding="utf-8",
    )
    (script_dir / "good_binary.py").write_text(
        "import subprocess\n"
        "subprocess.run(['x'], stdout=subprocess.PIPE)\n",
        encoding="utf-8",
    )
    _git(
        tmp_path,
        "add",
        "scripts/bad_stdout.py",
        "scripts/bad_alias.py",
        "scripts/bad_module_alias.py",
        "scripts/bad_assigned_module_alias.py",
        "scripts/good_binary.py",
    )

    assert ratchet.current_count(tmp_path) == 4


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))


class TestTheSubstringProbeChangesNothingButCost:
    """The probe in `_scan_all` must be a pure speedup, never a blind spot.

    Issue #4876. Registering this scanner against the whole tree (issue #5482)
    made it the critical path of the concurrent `count-ratchets` registry: 67.31s
    alone at load average 7.7, with the aggregate at 80s to 82s against its own
    85s deadline. The probe skips the AST parse for a file whose source does not
    contain the token `subprocess`, which no flaggable binding can omit.

    A probe that skips a file it should have parsed is a silent gate hole, which
    is the worst defect class in this repository, so the equivalence is replayed
    against the real corpus rather than argued from the visitor's rules.
    """

    def test_a_file_with_no_subprocess_token_is_skipped(self, tmp_path: Path) -> None:
        source = tmp_path / "quiet.py"
        source.write_text("def f() -> int:\n    return 1\n", encoding="utf-8")

        assert check_subprocess_encoding.find_all_violations(tmp_path, [source]) == []

    def test_a_violation_is_still_found_when_the_token_is_present(
        self, tmp_path: Path
    ) -> None:
        source = tmp_path / "loud.py"
        source.write_text(
            "import subprocess\n\n"
            "subprocess.run(['true'], text=True, encoding='utf-8')\n",
            encoding="utf-8",
        )

        found = check_subprocess_encoding.find_all_violations(tmp_path, [source])

        assert [lineno for _, lineno in found] == [3]

    def test_the_probe_does_not_hide_an_unparseable_file_that_names_subprocess(
        self, tmp_path: Path
    ) -> None:
        """Edge: the token is present, so the parse still runs and still raises.

        The probe only removes the parse for files it has proven cannot hold a
        violation. A file that names subprocess and does not parse must still
        fail closed rather than be waved through.
        """
        source = tmp_path / "broken.py"
        source.write_text("import subprocess\ndef (\n", encoding="utf-8")

        with pytest.raises(check_subprocess_encoding.ScanError):
            check_subprocess_encoding.find_all_violations(tmp_path, [source])

    @pytest.mark.integration
    @pytest.mark.timeout(600)
    def test_the_probe_matches_an_unprobed_scan_over_the_whole_corpus(self) -> None:
        """Negative control against the real tree, not a fixture.

        Replays `find_violations` over every tracked Python file with no probe
        and requires the probed scan to return the identical violation set.
        Measured when written: 2246 files, 989 naming subprocess, 238 violations
        both ways, 0 mismatches. If a future binding stops being anchored on the
        token, this fails rather than silently under-reporting.

        Marked `integration` and given a 600s timeout on purpose. Proving the
        equivalence costs the unprobed runtime, which is the 67s this change
        exists to remove, and the default `--timeout=120` kills it. Paying that
        in the local fast path would spend the saving to prove the saving. The
        merge-group suite runs it; pre-push deselects it with `-m "not
        integration"`. The three fixture cases above stay in the fast path, so a
        probe that skips a file it should parse still fails locally.
        """
        repo_root = Path(check_subprocess_encoding.__file__).resolve().parents[2]
        listing = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "-z", "*.py"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        files = [repo_root / rel for rel in listing.stdout.split("\0") if rel]
        assert len(files) > 1000, "corpus lookup returned too few files to be a real check"

        unprobed: set[tuple[str, int]] = set()
        for path in files:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            try:
                linenos = check_subprocess_encoding.find_violations(text, str(path))
            except SyntaxError:
                continue
            for lineno in linenos:
                unprobed.add((str(path.relative_to(repo_root)), lineno))

        probed = {
            (str(path.relative_to(repo_root)), lineno)
            for path, lineno in check_subprocess_encoding.find_all_violations(repo_root, files)
        }

        assert probed == unprobed
