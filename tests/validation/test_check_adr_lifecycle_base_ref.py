"""Base-ref provenance for the committed ADR lifecycle baseline (issue #5270).

A branch that hand-edits ``adr_lifecycle_baseline.json`` to raise a count,
without ever running ``--write-baseline``, must fail a plain run. The ceiling
is compared with its value at the fork point, not with how it was written.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

from check_adr_lifecycle import CHECKS, EXIT_CONFIG, EXIT_OK, EXIT_REGRESSION, main

_BAD_FRONTMATTER = "---\nid: ADR-002\nstatus: [unclosed\n---\n\n# ADR-002: Bad\n"
_GOOD = (
    "---\nid: ADR-001\nstatus: accepted\ndate: 2026-08-21\nsupersedes: []\n"
    "superseded-by: null\nimplemented: true\n---\n\n# ADR-001: Thing\n\n"
    "## Status\n\nAccepted (2026-08-21).\n"
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _set_baseline(baseline: Path, parse_count: int) -> None:
    counts = {name: 0 for name in CHECKS}
    counts["frontmatter-parses"] = parse_count
    baseline.write_text(json.dumps({"counts": counts}), encoding="utf-8")


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


def _repo(tmp_path: Path, parse_count: int | None = 0) -> tuple[Path, Path]:
    """A repo whose main commit holds one clean ADR and, optionally, a baseline."""
    adr_dir = tmp_path / ".project-toolkit" / "architecture"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-001-thing.md").write_text(_GOOD, encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    if parse_count is not None:
        _set_baseline(baseline, parse_count)
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    _commit(tmp_path, "base")
    return adr_dir, baseline


def _plain_run(repo: Path, baseline: Path) -> int:
    return main(["--repo-root", str(repo), "--baseline", str(baseline)])


def test_hand_edited_raise_of_the_baseline_fails_a_plain_run(tmp_path, capsys):
    adr_dir, baseline = _repo(tmp_path)
    _git(tmp_path, "checkout", "-q", "-b", "feature")
    (adr_dir / "ADR-002-bad.md").write_text(_BAD_FRONTMATTER, encoding="utf-8")
    _set_baseline(baseline, 1)
    _commit(tmp_path, "regress and raise the ceiling by hand")

    assert _plain_run(tmp_path, baseline) == EXIT_REGRESSION
    assert "frontmatter-parses" in capsys.readouterr().err


def test_uncommitted_hand_edit_also_fails(tmp_path):
    adr_dir, baseline = _repo(tmp_path)
    (adr_dir / "ADR-002-bad.md").write_text(_BAD_FRONTMATTER, encoding="utf-8")
    _set_baseline(baseline, 1)

    assert _plain_run(tmp_path, baseline) == EXIT_REGRESSION


def test_unchanged_baseline_passes(tmp_path):
    _, baseline = _repo(tmp_path)

    assert _plain_run(tmp_path, baseline) == EXIT_OK


def test_lowered_baseline_passes(tmp_path):
    _, baseline = _repo(tmp_path, parse_count=2)
    _set_baseline(baseline, 0)

    assert _plain_run(tmp_path, baseline) == EXIT_OK


def test_bootstrap_passes_when_the_base_ref_has_no_baseline(tmp_path):
    _, baseline = _repo(tmp_path, parse_count=None)
    _set_baseline(baseline, 5)

    assert _plain_run(tmp_path, baseline) == EXIT_OK


def test_baseline_outside_the_repo_skips_the_comparison(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _repo(repo)
    outside = tmp_path / "outside.json"
    _set_baseline(outside, 9)

    assert _plain_run(repo, outside) == EXIT_OK


def test_stale_branch_is_not_blamed_for_a_baseline_main_lowered_later(tmp_path):
    _, baseline = _repo(tmp_path, parse_count=3)
    _git(tmp_path, "checkout", "-q", "-b", "feature")
    _git(tmp_path, "checkout", "-q", "main")
    _set_baseline(baseline, 0)
    _commit(tmp_path, "main lowers the ceiling after the branch forked")
    _git(tmp_path, "checkout", "-q", "feature")

    assert _plain_run(tmp_path, baseline) == EXIT_OK


def test_unreadable_baseline_at_the_base_ref_is_a_config_error(tmp_path, capsys):
    _, baseline = _repo(tmp_path)
    baseline.write_text("not json", encoding="utf-8")
    _commit(tmp_path, "corrupt the base baseline")
    _git(tmp_path, "checkout", "-q", "-b", "feature")
    _set_baseline(baseline, 0)

    assert _plain_run(tmp_path, baseline) == EXIT_CONFIG
    assert "could not read the baseline" in capsys.readouterr().err


def test_no_resolvable_base_ref_skips_the_comparison(tmp_path):
    adr_dir = tmp_path / ".project-toolkit" / "architecture"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-001-thing.md").write_text(_GOOD, encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    _set_baseline(baseline, 0)

    assert _plain_run(tmp_path, baseline) == EXIT_OK
