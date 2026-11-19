"""Row links and nested fences for the agent and skill docs gate."""

from __future__ import annotations

import importlib.util

from scripts.validation import check_agent_skill_docs as gate
from scripts.validation import check_agent_skill_docs_rows as rows
from tests.validation.test_check_agent_skill_docs import (
    REPO_ROOT,
    _page,
    _page_text,
    _repo,
    _row,
    _skill,
)


def test_titled_local_readme_link_counts_as_a_row(tmp_path):
    repo = _repo(tmp_path)
    _skill(repo, "alpha")
    _page(repo, "skills", "alpha")
    readme = repo / "docs" / "skills" / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# skills",
                "",
                "| Page | Use |",
                "| --- | --- |",
                '| [alpha](alpha.md "alpha") | Does alpha |',
                '| [remote](https://example.com/remote.md "remote") | Elsewhere |',
                "",
            ]
        ),
        encoding="utf-8",
    )

    report = gate.find_page_findings(repo)

    assert report.findings == []
    assert gate.readme_rows(readme.read_text(encoding="utf-8")) == {"alpha"}
    assert gate.readme_rows("| [beta](./beta.md#part) | x |\n| [gamma](<gamma.md> 'g') | x |") == {
        "beta",
        "gamma",
    }


def test_readme_row_pattern_matches_the_scaffold():
    path = REPO_ROOT / "src" / "claude" / "skills" / "skillforge" / "scripts" / "_docs_page.py"
    spec = importlib.util.spec_from_file_location("skillforge_docs_page", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module._ROW_LINK.pattern == rows.ROW_LINK.pattern
    assert gate.readme_rows is rows.readme_rows


def test_heading_inside_a_longer_fence_is_ignored(tmp_path):
    repo = _repo(tmp_path)
    _skill(repo, "alpha")
    _row(repo, "skills", "alpha")
    sample = "````markdown\n```text\n## Related\n```\n````\n"
    page = repo / "docs" / "skills" / "alpha.md"
    page.write_text(
        _page_text("alpha").replace("## Advanced use\n\nText.", "## Advanced use\n\n" + sample),
        encoding="utf-8",
    )

    assert gate.find_page_findings(repo).findings == []


def test_exit_code_scan_skips_headings_inside_fences():
    sample = "\n".join(
        [
            "# Tool",
            "",
            "```markdown",
            "## Exit Codes",
            "- 9: sample only",
            "```",
            "",
            "## Exit Codes",
            "",
            "- 0: success",
            "",
            "```text",
            "# not a heading",
            "```",
            "",
            "## Next",
            "- unrelated",
        ]
    )

    assert gate.exit_code_lines(sample) == [
        "- 0: success",
        "```text",
        "# not a heading",
        "```",
    ]
