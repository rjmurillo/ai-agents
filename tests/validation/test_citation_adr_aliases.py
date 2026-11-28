"""Deleted and renamed ADR files stay visible to inbound ADR-NNN cites."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# citation_adr_aliases imports its siblings by bare name (check_adr_links and
# others), so scripts/validation must be on sys.path first. Without this,
# collecting the file alone fails, serial or under pytest -n auto.
_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

from scripts.validation.citation_adr_aliases import _citation_aliases_across
from tests.validation.citation_freshness_helpers import TARGET_CONTENT, _git, _repo

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "validation" / "citation_reverse_pass.py"
)
_NUMBER = "907"
_OLD = "docs/architecture/ADR-907-old-title.md"
_NEW = "docs/architecture/ADR-907-new-title.md"


def _run_reverse(root: Path) -> tuple[int, str]:
    """Run the reverse pass CLI against one fixture repository."""
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), "--repo-root", str(root), "--base", "main"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    return proc.returncode, proc.stdout + proc.stderr


def _cite() -> str:
    return f"See ADR-{_NUMBER}:3 for `magic_token`.\n"


def _commit(root: Path, relpath: str, text: str, message: str) -> None:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


def test_ambiguous_adr_number_stays_unresolved() -> None:
    """Two files for one number on either side do not pick a winner."""
    base = {"docs/architecture/ADR-907-a.md", "docs/architecture/ADR-907-b.md"}
    head = {"docs/architecture/ADR-907-a.md"}
    assert _citation_aliases_across(base, head) == {}
    assert _citation_aliases_across(head, base) == {}


def test_deleted_adr_alias_is_still_judged(tmp_path: Path) -> None:
    """A deleted ADR file still fails the cite that names its number."""
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "main")
    _commit(root, _OLD, TARGET_CONTENT + "\n", "adr")
    _commit(root, "docs/notes.md", _cite(), "cite")
    _git(root, "checkout", "-q", "-B", "feature")
    _git(root, "rm", "-q", _OLD)
    _git(root, "commit", "-q", "-m", "delete adr")

    code, out = _run_reverse(root)

    assert code == 1, out
    assert "not tracked" in out


def test_renamed_adr_is_judged_at_the_new_path(tmp_path: Path) -> None:
    """A basename change keeps the number and judges the HEAD file."""
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "main")
    _commit(root, _OLD, TARGET_CONTENT + "\n", "adr")
    _commit(root, "docs/notes.md", _cite(), "cite")
    _git(root, "checkout", "-q", "-B", "feature")
    moved = TARGET_CONTENT.replace("def magic_token():", "def other_token():")
    _git(root, "mv", _OLD, _NEW)
    _commit(root, _NEW, moved + "\n", "rename adr")

    code, out = _run_reverse(root)

    assert code == 1, out
    assert "magic_token" in out


def test_added_cite_to_an_adr_deleted_on_the_branch_is_judged(tmp_path: Path) -> None:
    """The added-lines gate cannot alias a deleted number, so the reverse pass does."""
    root = _repo(tmp_path)
    _git(root, "checkout", "-q", "main")
    _commit(root, _OLD, TARGET_CONTENT + "\n", "adr")
    _git(root, "checkout", "-q", "-B", "feature")
    _git(root, "rm", "-q", _OLD)
    _commit(root, "docs/notes.md", _cite(), "delete adr and add a cite to it")

    code, out = _run_reverse(root)

    assert code == 1, out
    assert "not tracked" in out
