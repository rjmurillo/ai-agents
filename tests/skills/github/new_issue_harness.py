"""Shared harness for the new_issue.py test modules.

Routes each gh call by subcommand and resolves every run to owner/repo.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/github/scripts/issue/new_issue.py")
main = mod.main
provenance = mod.provenance

ISSUE_URL = "https://github.com/owner/repo/issues/42\n"
BLOCKED_BY = "Alice on Payments, blocked on the webhook retry"
SIGNAL = "error count spiked to 40/min per PR #1234"
AGENT_ARGS = ["--source", "agent", "--blocked-by", BLOCKED_BY, "--signal", SIGNAL]
STEP0_BODY = (
    "Context line.\n\n## Step 0\n\n### Q3\n\nBob on CI, blocked on red main\n\n"
    "### Q5\n\nrun 123 failed 4 times today\n"
)


def _make_proc(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


class FakeGh:
    """Route each gh call by its subcommand and record every call."""

    def __init__(
        self,
        label_create: MagicMock | None = None,
        issue_create: MagicMock | None = None,
        issue_edit: MagicMock | None = None,
    ) -> None:
        self.routes = {
            ("label", "create"): label_create or _make_proc(),
            ("issue", "create"): issue_create or _make_proc(stdout=ISSUE_URL),
            ("issue", "edit"): issue_edit or _make_proc(),
        }
        self.calls: list[list[str]] = []

    def __call__(self, args, **_kwargs):
        self.calls.append(list(args))
        return self.routes[(args[1], args[2])]

    def find(self, group: str, verb: str) -> list[str]:
        return next(c for c in self.calls if c[1:3] == [group, verb])

    def verbs(self) -> list[tuple[str, str]]:
        return [(c[1], c[2]) for c in self.calls]


def _run(argv: list[str], gh: FakeGh | None = None) -> tuple[int, FakeGh]:
    gh = gh or FakeGh()
    with patch("subprocess.run", side_effect=gh):
        rc = main([*argv, "--output-format", "json"])
    return rc, gh


def _body_arg(create_call: list[str]) -> str:
    return create_call[create_call.index("--body") + 1]


def _error(capsys) -> str:
    data = json.loads(capsys.readouterr().out)
    assert data["Success"] is False
    return data["Error"]["Message"]


@pytest.fixture(autouse=True, name="resolve_repo")
def resolve_repo_fixture():
    """Resolve every run to owner/repo without touching git or gh."""
    with patch.object(mod, "resolve_repo_params") as mock_resolve:
        info = MagicMock()
        info.owner = "owner"
        info.repo = "repo"
        mock_resolve.return_value = info
        yield mock_resolve
