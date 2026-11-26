"""Reference-split guards retain their original section boundaries."""

from pathlib import Path

import pytest

from tests.agent_reference_helpers import reference_loading_section


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("prefix ## Reference Loading body", " body"),
        ("## Reference Loading body ## Other hidden", " body"),
        ("## Reference Loading ### Detail body", " ### Detail body"),
        ("## Reference Loading", ""),
    ],
)
def test_loading_section_preserves_original_heading_boundary(text: str, expected: str) -> None:
    assert reference_loading_section(text, Path("agent.md")) == expected


@pytest.mark.parametrize("text", ["## Other", "## Reference Loading ## Reference Loading"])
def test_loading_section_rejects_missing_or_repeated_heading(text: str) -> None:
    with pytest.raises(AssertionError, match="agent.md must carry"):
        reference_loading_section(text, Path("agent.md"))
