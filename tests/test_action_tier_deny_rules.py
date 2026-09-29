"""Pins the consequential-tier deny rules ADR-112 owns (issue #5767).

ADR-112 sorts agent actions into four tiers. The highest tier, consequential
actions (history rewrite, hook bypass, recursive deletion, repository and
credential changes), is denied at the harness through `permissions.deny` in
`.claude/settings.json`. Claude Code evaluates deny before ask and allow and
honors it in `bypassPermissions` mode, so a deny rule is the one control that
holds when nothing prompts. Approval for a denied action is a human running it
in their own shell or through the `!` prefix.

This module proves four things against the committed settings, through the
shared matcher model in `tests/claude_permission_matcher.py`:

1. every probed consequential command is denied, including evasion shapes;
2. the legitimate neighbor of each rule stays allowed, so a rule cannot take
   out unrelated work the way the #5013 `Bash` matcher did;
3. every consequential rule denies at least one probed command, so no rule is
   dead weight that only looks like coverage;
4. the gaps ADR-112 records stay gaps. If one closes, this test fails and the
   ADR's gap table must be updated, so the document never overstates or
   understates protection.
"""

from __future__ import annotations

import pytest

from tests.claude_permission_matcher import _denied_by, _deny_rules

_SHA = "0123456789abcdef0123456789abcdef01234567"


def _consequential_rules() -> list[str]:
    """Deny rules outside the read-only-git config-injection set.

    Every config-injection rule starts with `Bash(git *`; the consequential
    tier never does.
    """
    return [rule for rule in _deny_rules() if not rule.startswith("Bash(git *")]


HISTORY_REWRITE = (
    "git push --force",
    "git push --force origin feat/x",
    "git push origin feat/x --force",
    "git push -f origin feat/x",
    "git push origin feat/x -f",
    "git push origin -f feat/x",
    "git push --force-with-lease",
    "git push --force-with-lease origin feat/x",
    "git push origin +feat/x",
    "git push origin +HEAD:refs/heads/main",
    "git push --mirror origin",
)

HOOK_BYPASS = (
    "git commit --no-verify -m fix",
    "git commit -m fix --no-verify",
    "git commit -n -m fix",
    "git commit -am fix -n",
    "git commit -a -n -m fix",
    "git push --no-verify origin feat/x",
    "git push origin feat/x --no-verify",
)

RECURSIVE_DELETE = (
    "rm -rf build",
    "rm -fr build",
    "rm -Rf build",
    "rm -fR build",
    "rm -r -f build",
    "rm -f -r build",
    "rm --recursive --force build",
    "rm --force --recursive build",
)

REPOSITORY_AND_CREDENTIAL = (
    "gh repo delete o/r --yes",
    "gh repo archive o/r --yes",
    "gh repo rename new-name",
    "gh repo edit --visibility public",
    "gh release delete v1.0.0 --yes",
    "gh issue delete 12 --yes",
    "gh label delete bug --yes",
    "gh secret set TOKEN --body x",
    "gh secret delete TOKEN",
    "gh variable set NAME --body x",
    "gh variable delete NAME",
    "gh pr merge 12 --squash --admin",
    "gh api -X DELETE repos/o/r/git/refs/heads/main",
    "gh api -XDELETE repos/o/r/issues/comments/1",
    "gh api --method DELETE repos/o/r/hooks/1",
    "gh api --method=DELETE repos/o/r/releases/1",
    "gh api repos/o/r/branches/main/protection -X PUT --input p.json",
    "gh api -X PUT repos/o/r/collaborators/someone",
)

CONSEQUENTIAL = HISTORY_REWRITE + HOOK_BYPASS + RECURSIVE_DELETE + REPOSITORY_AND_CREDENTIAL

EVASION_SHAPES = (
    "FOO=1 git push --force",
    "timeout 30 rm -rf build",
    "nohup gh repo delete o/r --yes",
    "git status && git push -f origin feat/x",
    "cd /tmp; gh secret set TOKEN --body x",
)

# Legitimate neighbors. Each sits next to a rule above and is work this
# repository runs every day: the AGENTS.md End gate, the pr-autofix pinned
# lease, merge_pr.py, and ordinary reads.
NEIGHBORS = (
    "git push origin feat/x",
    "git push -u origin feat/x",
    "git push --set-upstream origin feat/x",
    "git push --follow-tags origin feat/x",
    "git push origin fix-f",
    f"git push --force-with-lease=refs/heads/feat/x:{_SHA} origin HEAD:refs/heads/feat/x",
    f"git push --force-with-lease=refs/heads/feat/x:{_SHA} --force-if-includes origin HEAD",
    "git commit -m fix",
    "git commit --amend --no-edit",
    "git commit -F message.txt",
    "git commit -S -m fix",
    "rm file.txt",
    "rm -f file.txt",
    "rm -r empty-dir",
    "gh repo view o/r",
    "gh repo clone o/r",
    "gh release list",
    "gh release view v1.0.0",
    "gh issue view 12",
    "gh label list",
    "gh variable list",
    "gh auth status",
    # The GOTCHAS.md pre-push recipe provisions the Copilot token this way.
    'COPILOT_GITHUB_TOKEN="$(gh auth token)" git push origin HEAD:feat/x',
    "gh pr merge 12 --squash --match-head-commit abc123",
    "gh api repos/o/r",
    "gh api repos/o/r/rules/branches/main",
    "gh api -X POST repos/o/r/issues/1/comments -f body=x",
    "gh api --method PATCH repos/o/r/pulls/1 -f title=x",
)

# Gaps ADR-112 records under "Open enforcement gaps". A command-text matcher
# cannot close them without denying legitimate work, and each has another
# plane (server ruleset, pre-push policy, CI hook-bypass audit) or none.
KNOWN_GAPS = (
    "git push origin :feat/x",
    "git push origin HEAD:main",
    "git commit -anm fix",
    "LEFTHOOK=0 git commit -m fix",
    "git -c core.hooksPath=/dev/null commit -m fix",
    "find build -delete",
    "rm -rfv build",
    "rm -vrf build",
    "rm build -rf",
    "git push --force-with-lease=feat/x origin feat/x",
    "gh auth token",
    "gh api repos/o/r/git/refs/heads/x -X PATCH -f sha=abc -F force=true",
)


@pytest.mark.parametrize("command", CONSEQUENTIAL)
def test_consequential_command_is_denied(command: str) -> None:
    assert _denied_by(command, _deny_rules()), (
        f"{command!r} is a consequential action (ADR-112) and no rule in "
        f".claude/settings.json denies it. Add the rule to "
        f"templates/hooks/settings.tmpl and regenerate."
    )


@pytest.mark.parametrize("command", EVASION_SHAPES)
def test_evasion_shape_is_still_denied(command: str) -> None:
    assert _denied_by(command, _deny_rules()), (
        f"{command!r} hides a consequential command behind an assignment, "
        f"wrapper, or compound separator, and slipped past every rule."
    )


@pytest.mark.parametrize("command", NEIGHBORS)
def test_legitimate_neighbor_is_not_denied(command: str) -> None:
    assert not _denied_by(command, _deny_rules()), (
        f"{command!r} is ordinary work and is denied by "
        f"{_denied_by(command, _deny_rules())}. A session-wide deny that "
        f"reaches normal work is the #5013 failure shape."
    )


def test_every_consequential_rule_denies_a_probed_command() -> None:
    corpus = CONSEQUENTIAL + EVASION_SHAPES
    dead = [
        rule
        for rule in _consequential_rules()
        if not any(_denied_by(command, [rule]) for command in corpus)
    ]

    assert dead == [], (
        f"Rules no probed command exercises: {dead}. Add the exploit each one "
        f"exists for, or delete the rule."
    )


def test_consequential_tier_is_present() -> None:
    """Negative control: the parametrized tests above are not vacuous."""
    assert len(_consequential_rules()) >= 40
    assert _denied_by("git push --force", []) == []


@pytest.mark.parametrize("command", KNOWN_GAPS)
def test_recorded_gap_stays_recorded(command: str) -> None:
    assert not _denied_by(command, _deny_rules()), (
        f"{command!r} is now denied. Remove it from ADR-112's open "
        f"enforcement gaps and from KNOWN_GAPS here, so the gap table stays "
        f"accurate."
    )


def test_matcher_would_detect_a_closed_gap() -> None:
    """Negative control for the absence test above."""
    assert _denied_by("git push origin :feat/x", ["Bash(git push * :*)"])
