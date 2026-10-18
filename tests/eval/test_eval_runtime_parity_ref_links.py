"""ADR-119: instruction reads at a git ref follow tracked symlinks.

Shipped rules in `.claude/rules` are mode 120000 entries. `git show` at a
ref returns their link text, so the runtime parity eval follows each link to
its target at the same ref, inside the repository, within a hop limit.
"""

from __future__ import annotations

import pytest

from tests.eval._runtime_parity_test_support import runtime_parity


def test_resolve_instructions_at_a_ref_follows_a_tracked_rule_link() -> None:
    # ADR-119: .claude/rules/voice.md is a mode 120000 link into src/claude/rules.
    resolved = runtime_parity.resolve_instructions([".claude/rules/voice.md"], "HEAD")

    assert resolved[".claude/rules/voice.md"].startswith(b"---\n")


def test_link_target_resolves_relative_text_against_the_link_directory() -> None:
    target = runtime_parity._link_target(
        ".claude/rules/voice.md", "../../src/claude/rules/voice.md", "x"
    )

    assert target == "src/claude/rules/voice.md"


@pytest.mark.parametrize("text", ["/etc/passwd", "../../../outside.md"])
def test_link_target_refuses_absolute_or_escaping_text(text: str) -> None:
    with pytest.raises(runtime_parity.ParityConfigError, match="absolute|outside"):
        runtime_parity._link_target(".claude/rules/voice.md", text, "x")


def test_read_instruction_refuses_a_link_chain_past_the_hop_limit(monkeypatch) -> None:
    def fake_git(args, path, ref):
        if args[0] == "ls-tree":
            return b"120000 blob abc\tloop.md\n"
        return b"loop.md"

    monkeypatch.setattr(runtime_parity, "_git_at_ref", fake_git)

    with pytest.raises(runtime_parity.ParityConfigError, match="more than 8 links"):
        runtime_parity._read_instruction("loop.md", "HEAD")
