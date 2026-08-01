"""Credit identity for the security-suppression gate (issue #4152).

A removed suppression may pay for an added one so that relocating a
suppression during a refactor stays net-zero. The credit key used to be the
matched directive token, which is identical for a Bandit B324 waiver and a
B605 waiver, so deleting a harmless suppression authorized adding a
dangerous one in the same file.

Directive tokens are assembled at runtime so this file does not trip the
gate it exercises. Explicit `+` concatenation is used rather than implicit
adjacency because `ruff format` folds adjacent literals back into one
string (issue filed separately).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = str(Path(__file__).resolve().parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.validation import git_hook_policy as policy  # noqa: E402

NOSEC = "# " + "nos" + "ec"
NOSEMGREP = "# " + "nosem" + "grep"
NOQA = "# " + "no" + "qa"
LGTM = "// " + "lg" + "tm"
CODEQL = "// " + "code" + "ql"

HEAD = "abcdef1234567890"


def _diff(path: str, removed: list[str], added: list[str], *, start: int = 1) -> str:
    """A unified diff for one file with the given removed and added lines."""
    body = "".join(f"-{line}\n" for line in removed)
    body += "".join(f"+{line}\n" for line in added)
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        f"@@ -{start},{len(removed)} +{start},{len(added)} @@\n"
        f"{body}"
    )


def _violations(diff_text: str) -> list[str]:
    return policy._suppression_violations_in_diff(HEAD, diff_text)


class TestFixtureBuilder:
    """The fixture format must actually parse, or every other test is vacuous."""

    def test_builder_yields_the_expected_changes(self) -> None:
        diff_text = _diff("pkg/alpha.py", ["old line"], ["new line"])
        changes = list(policy._iter_diff_changes(diff_text))
        assert changes == [
            ("pkg/alpha.py", "-", 1, "old line"),
            ("pkg/alpha.py", "+", 1, "new line"),
        ]

    def test_an_added_suppression_with_no_removal_is_a_violation(self) -> None:
        diff_text = _diff("pkg/alpha.py", [], [f"    os.system(x)  {NOSEC} B605"])
        assert _violations(diff_text) == [f"{HEAD[:12]}:pkg/alpha.py:1"]


class TestRuleIdentityIsLoadBearing:
    """Issue #4152: a credit must name the same rule."""

    def test_removing_a_weak_hash_waiver_does_not_authorize_a_command_injection_waiver(
        self,
    ) -> None:
        diff_text = _diff(
            "pkg/alpha.py",
            [f"import hashlib  {NOSEC} B324"],
            [f"    os.system(user_input)  {NOSEC} B605"],
        )
        assert _violations(diff_text) == [f"{HEAD[:12]}:pkg/alpha.py:1"]

    def test_a_bare_directive_does_not_authorize_a_ruled_one(self) -> None:
        diff_text = _diff(
            "pkg/alpha.py",
            [f"import hashlib  {NOSEC}"],
            [f"    os.system(user_input)  {NOSEC} B605"],
        )
        assert _violations(diff_text) == [f"{HEAD[:12]}:pkg/alpha.py:1"]

    def test_a_ruled_directive_does_not_authorize_a_bare_one(self) -> None:
        diff_text = _diff(
            "pkg/alpha.py",
            [f"import hashlib  {NOSEC} B324"],
            [f"    os.system(user_input)  {NOSEC}"],
        )
        assert _violations(diff_text) == [f"{HEAD[:12]}:pkg/alpha.py:1"]

    def test_semgrep_rule_ids_are_distinguished(self) -> None:
        diff_text = _diff(
            "pkg/alpha.py",
            [f"x = 1  {NOSEMGREP}: python.lang.audit.weak-hash"],
            [f"y = 2  {NOSEMGREP}: python.lang.audit.dangerous-system-call"],
        )
        assert _violations(diff_text) == [f"{HEAD[:12]}:pkg/alpha.py:1"]

    def test_bracketed_codeql_rules_are_distinguished(self) -> None:
        diff_text = _diff(
            "pkg/alpha.js",
            [f"const a = 1;  {LGTM}[js/weak-cryptographic-algorithm]"],
            [f"const b = 2;  {LGTM}[js/command-line-injection]"],
        )
        assert _violations(diff_text) == [f"{HEAD[:12]}:pkg/alpha.js:1"]

    def test_bracketed_lgtm_does_not_credit_bracketed_codeql(self) -> None:
        diff_text = _diff(
            "pkg/alpha.js",
            [f"const a = 1;  {LGTM}[js/command-line-injection]"],
            [f"const b = 2;  {CODEQL}[js/command-line-injection]"],
        )
        assert _violations(diff_text) == [f"{HEAD[:12]}:pkg/alpha.js:1"]

    def test_noqa_security_codes_are_distinguished(self) -> None:
        diff_text = _diff(
            "pkg/alpha.py",
            [f"x = 1  {NOQA}: S101"],
            [f"y = 2  {NOQA}: S602"],
        )
        assert _violations(diff_text) == [f"{HEAD[:12]}:pkg/alpha.py:1"]

    def test_a_reworded_justification_is_not_a_credit(self) -> None:
        """Changing a security waiver's text merits a human look."""
        diff_text = _diff(
            "pkg/alpha.py",
            [f"x = 1  {NOSEC} B324  # only hashes filenames"],
            [f"x = 1  {NOSEC} B324  # only hashes user-supplied filenames"],
        )
        assert _violations(diff_text) == [f"{HEAD[:12]}:pkg/alpha.py:1"]


class TestRelocationStillCredits:
    """The case the credit exists for must keep working."""

    def test_moving_an_identical_suppression_is_net_zero(self) -> None:
        diff_text = _diff(
            "pkg/alpha.py",
            [f"import hashlib  {NOSEC} B324"],
            [f"    return hashlib.md5(b'x')  {NOSEC} B324"],
        )
        assert _violations(diff_text) == []

    def test_reindentation_still_credits(self) -> None:
        diff_text = _diff(
            "pkg/alpha.py",
            [f"x = 1  {NOSEC} B324"],
            [f"        x = 1  {NOSEC} B324"],
        )
        assert _violations(diff_text) == []

    def test_spacing_inside_the_directive_still_credits(self) -> None:
        compact = NOSEC.replace(" ", "") + "  B324"
        diff_text = _diff(
            "pkg/alpha.py",
            [f"x = 1  {compact}"],
            [f"y = 2  {NOSEC} B324"],
        )
        assert _violations(diff_text) == []

    def test_an_identical_relocated_bare_directive_still_credits(self) -> None:
        diff_text = _diff(
            "pkg/alpha.py",
            [f"x = 1  {NOSEC}"],
            [f"y = 2  {NOSEC}"],
        )
        assert _violations(diff_text) == []

    def test_two_removals_pay_for_two_identical_additions(self) -> None:
        diff_text = _diff(
            "pkg/alpha.py",
            [f"a = 1  {NOSEC} B324", f"b = 2  {NOSEC} B324"],
            [f"c = 3  {NOSEC} B324", f"d = 4  {NOSEC} B324"],
        )
        assert _violations(diff_text) == []

    def test_one_removal_pays_for_only_one_identical_addition(self) -> None:
        diff_text = _diff(
            "pkg/alpha.py",
            [f"a = 1  {NOSEC} B324"],
            [f"c = 3  {NOSEC} B324", f"d = 4  {NOSEC} B324"],
        )
        assert _violations(diff_text) == [f"{HEAD[:12]}:pkg/alpha.py:2"]


class TestCreditsStayWithinOneFile:
    def test_a_removal_in_another_file_is_not_a_credit(self) -> None:
        diff_text = _diff("pkg/alpha.py", [f"a = 1  {NOSEC} B324"], []) + _diff(
            "pkg/beta.py", [], [f"b = 2  {NOSEC} B324"]
        )
        assert _violations(diff_text) == [f"{HEAD[:12]}:pkg/beta.py:1"]


class TestSuppressionIdentity:
    def test_identity_includes_the_rule_id(self) -> None:
        text = f"import hashlib  {NOSEC} B324"
        match = policy.SECURITY_SUPPRESSION_RE.search(text)
        assert match is not None
        identity = policy.suppression_identity(text, match)
        assert "B324" in identity
        assert identity != match.group(0)

    def test_identity_drops_whitespace(self) -> None:
        left = f"x = 1  {NOSEC}   B324"
        right = f"y = 2  {NOSEC} B324"
        left_match = policy.SECURITY_SUPPRESSION_RE.search(left)
        right_match = policy.SECURITY_SUPPRESSION_RE.search(right)
        assert left_match is not None and right_match is not None
        assert policy.suppression_identity(left, left_match) == policy.suppression_identity(
            right, right_match
        )

    def test_identity_differs_across_rule_ids(self) -> None:
        left = f"x = 1  {NOSEC} B324"
        right = f"y = 2  {NOSEC} B605"
        left_match = policy.SECURITY_SUPPRESSION_RE.search(left)
        right_match = policy.SECURITY_SUPPRESSION_RE.search(right)
        assert left_match is not None and right_match is not None
        assert policy.suppression_identity(left, left_match) != policy.suppression_identity(
            right, right_match
        )


class TestEndToEndThroughGit:
    """Prove the unit fixtures match what real `git diff` produces."""

    @staticmethod
    def _run(repo: Path, *args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    @pytest.fixture
    def repo(self, tmp_path: Path) -> Path:
        repo = tmp_path / "probe"
        (repo / "pkg").mkdir(parents=True)
        self._run(repo.parent, "init", "-q", str(repo))
        self._run(repo, "config", "user.email", "t@example.com")
        self._run(repo, "config", "user.name", "t")
        return repo

    def _commit_pair(self, repo: Path, base_text: str, head_text: str) -> tuple[str, str]:
        target = repo / "pkg" / "alpha.py"
        target.write_text(base_text, encoding="utf-8")
        self._run(repo, "add", "-A")
        self._run(repo, "commit", "-qm", "base")
        base = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()
        target.write_text(head_text, encoding="utf-8")
        self._run(repo, "add", "-A")
        self._run(repo, "commit", "-qm", "head")
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout.strip()
        return base, head

    def _real_diff(self, repo: Path, base: str, head: str) -> str:
        return subprocess.run(
            ["git", "diff", "--unified=0", f"{base}..{head}"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout

    def test_escalation_is_blocked_against_a_real_git_diff(self, repo: Path) -> None:
        base, head = self._commit_pair(
            repo,
            f"import hashlib  {NOSEC} B324\n",
            f"import os\n\n\ndef g(x):\n    return os.system(x)  {NOSEC} B605\n",
        )
        violations = policy._suppression_violations_in_diff(head, self._real_diff(repo, base, head))
        assert violations, "escalation must be reported against a real diff"
        assert violations[0].endswith("pkg/alpha.py:5")

    def test_relocation_is_credited_against_a_real_git_diff(self, repo: Path) -> None:
        base, head = self._commit_pair(
            repo,
            f"import hashlib  {NOSEC} B324\n",
            f"import os\n\nimport hashlib  {NOSEC} B324\n",
        )
        assert policy._suppression_violations_in_diff(head, self._real_diff(repo, base, head)) == []
