"""Quoted-heredoc masking tests for the ADR-006 run-block scanner (#3540).

Split from ``test_adr006_run_block_scanner.py`` to keep both modules under the
500-line taste-lint ceiling. The shared helpers stay in that module so the two
files build run blocks the same way.
"""

from __future__ import annotations

from scripts.ci import adr006_run_block_scanner as scanner
from tests.ci.test_adr006_run_block_scanner import REPO_ROOT, _run_block


class TestQuotedHeredocBodies:
    """A quoted heredoc body is data the shell copies out, not shell source.

    ``investigation-claim-backstop.yml`` writes a static remediation comment
    through ``cat <<'EOF'``. The comment closes with "See ADR-034 for
    details", and that lone ``for`` marked the block as shell logic.
    """

    def test_prose_in_a_quoted_heredoc_is_not_logic(self) -> None:
        """Positive: a quoted delimiter makes the body inert."""
        block = _run_block(
            "cat <<'EOF' > out.md",
            *(f"Check the log for item {i} if it is missing." for i in range(11)),
            "EOF",
            "cat out.md",
        )
        assert block.has_logic is False

    def test_an_unquoted_heredoc_still_expands(self) -> None:
        """Negative: without quotes the body evaluates, so it stays scanned."""
        block = _run_block(
            "cat <<EOF > out.md",
            "value is $(compute)",
            "EOF",
        )
        assert block.has_logic is True

    def test_the_opening_line_is_still_scanned(self) -> None:
        """Negative: only the body is inert; the command itself is not."""
        block = _run_block(
            'cat <<\'EOF\' > "$(mktemp)"',
            "plain text",
            "EOF",
        )
        assert block.has_logic is True

    def test_the_body_does_not_count_as_code(self) -> None:
        """Positive: inert text is data, so it must not inflate the metric."""
        block = _run_block(
            "cat <<'EOF' > out.md",
            *(f"line {i}" for i in range(20)),
            "EOF",
        )
        # Opener plus delimiter only.
        assert block.code_lines == 2

    def test_a_dash_delimiter_form_is_recognised(self) -> None:
        """Edge: ``<<-`` strips leading tabs but is still a heredoc."""
        block = _run_block(
            "cat <<-'EOF' > out.md",
            *(f"run the loop for step {i}" for i in range(11)),
            "EOF",
        )
        assert block.has_logic is False

    def test_a_second_heredoc_in_the_same_block_is_masked_too(self) -> None:
        """Edge: masking resumes after the first delimiter closes."""
        block = _run_block(
            "cat <<'A' > one.md",
            "wait for the first",
            "A",
            "cat <<'B' > two.md",
            "wait for the second",
            "B",
        )
        assert block.has_logic is False

    def test_shell_after_the_delimiter_is_scanned_again(self) -> None:
        """Edge: the mask must end, or real logic after it would be hidden."""
        block = _run_block(
            "cat <<'EOF' > out.md",
            "plain text",
            "EOF",
            'if [ -s out.md ]; then exit 1; fi',
        )
        assert block.has_logic is True

    def test_an_unterminated_heredoc_masks_to_the_end(self) -> None:
        """Edge: no closing delimiter means the body runs to the block end.

        The shell would reject this, so the conservative reading is that
        everything after the opener is still body text.
        """
        block = _run_block(
            "cat <<'EOF' > out.md",
            "plain text",
            'if [ -s out.md ]; then exit 1; fi',
        )
        assert block.has_logic is False

    def test_the_static_comment_workflow_is_clean(self) -> None:
        """Edge: the live block this fix clears reports no violation."""
        path = REPO_ROOT / ".github" / "workflows" / "investigation-claim-backstop.yml"
        violations = [
            block
            for block in scanner.scan_text(path.read_text(encoding="utf-8"))
            if scanner.is_violation(block, scanner._DEFAULT_THRESHOLD)
        ]
        assert violations == []


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
