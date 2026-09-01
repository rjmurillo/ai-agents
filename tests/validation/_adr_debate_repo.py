"""Staged-repository scaffolding for the ADR debate-log gate suites.

Two suites stage real files and call ``check_adr_review_policy`` end to end:
the evidence suite and the discovery suite. The scaffolding lived in the
evidence module until that module crossed the
500-line file-size rule for the third time on issue #5205. Copying it into the
new sibling would have put the same knowledge in two files, which is the
mistake the hardcoded-template copy made earlier on that issue, so it moved
here instead and the ``repo`` fixture moved to ``conftest.py`` beside it.

Issue #5205.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

ADR_42 = ".agents/architecture/ADR-042-python-migration-strategy.md"
ADR_05 = ".agents/architecture/ADR-005-powershell-only-scripting.md"

GENUINE_LOG = """# ADR Debate Log: Example

## Participants

- architect agent (primary reviewer)
- security agent

## Verdict: Accept

The architect reviewed ADR-042 and found no P0 or P1 issues. The decision
text matches the implementation and the alternatives considered are
reasonable. Template compliance confirmed against the canonical structure.

## Notes

P2 observation: evaluation order clarification added to the ADR text so a
later reader does not have to reconstruct it from the implementation.
"""


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    # encoding and errors are explicit to match the convention at
    # tests/test_lefthook_integration.py:107 and
    # tests/validation/test_session_log_optional.py:142. Without them, text
    # mode decodes with the locale codec, which on Windows can fail on git's
    # UTF-8 output and leave stdout unset.
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )


def _init_repo(repo: Path) -> None:
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    for relative in (ADR_42, ADR_05):
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Title\n\n## Status\n\nAccepted\n\n## Decision\n\nBaseline.\n")
    (repo / ".agents" / "critique").mkdir(parents=True, exist_ok=True)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base")


def _edit(repo: Path, relative: str, body: str) -> None:
    (repo / relative).write_text(f"# Title\n\n## Status\n\nAccepted\n\n## Decision\n\n{body}\n")


def _stage_log(repo: Path, name: str, content: str) -> str:
    relative = f".agents/critique/{name}"
    (repo / relative).write_text(content)
    _git(repo, "add", relative)
    return relative
