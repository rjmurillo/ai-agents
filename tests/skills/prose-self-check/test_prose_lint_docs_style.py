"""Tests for the advisory `--docs-style` mode of prose_lint.

Every docs-style finding is INFO and never changes the exit code. The same
text without the flag must report none of these kinds.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TESTS_SKILLS_DIR = str(Path(__file__).resolve().parents[1])
if TESTS_SKILLS_DIR not in sys.path:
    sys.path.insert(0, TESTS_SKILLS_DIR)

from claude_skills_import import import_skill_script

mod = import_skill_script(".claude/skills/prose-self-check/scripts/prose_lint.py")
main = mod.main
INFO = mod.INFO

DOC_KINDS = {"heading-case", "link-text", "vague-opener", "example-email", "token-shaped"}
FAKE_TOKEN = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"

BAD_DOC = f"""# Guide

## Configure The Widget

This is used to set up the widget. See [this link](https://example.com/x) first.

Contact jane@contoso.com or use {FAKE_TOKEN} for the demo.
"""

GOOD_DOC = """# Guide

## Configure the widget

Use the widget to set things up. See [the setup guide](setup.md) first.

## Use GitHub Copilot

Run the tool.

## The `Widget Factory` API

Mail jane@example.com for help.
"""


def findings(tmp_path: Path, text: str, capsys: pytest.CaptureFixture[str], *flags: str):
    doc = tmp_path / "doc.md"
    doc.write_text(text, encoding="utf-8")
    rules = tmp_path / "voice.md"
    rules.write_text("# Voice\n\n## Banned Vocabulary\n\n`delve`\n", encoding="utf-8")
    code = main([str(doc), "--json", "--rules", str(rules), *flags])
    payload = json.loads(capsys.readouterr().out)
    return code, payload["files"][str(doc)]["findings"]


def docs_findings(items: list[dict]) -> list[dict]:
    return [f for f in items if f["kind"] in DOC_KINDS]


def test_each_docs_style_kind_is_reported_at_info_with_exit_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, items = findings(tmp_path, BAD_DOC, capsys, "--docs-style")

    found = docs_findings(items)

    assert code == 0
    assert {f["kind"] for f in found} == DOC_KINDS
    assert {f["severity"] for f in found} == {INFO}


def test_token_finding_does_not_echo_the_secret(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, items = findings(tmp_path, BAD_DOC, capsys, "--docs-style")

    token = next(f for f in items if f["kind"] == "token-shaped")

    assert FAKE_TOKEN not in json.dumps(items)
    assert token["match"] == "ghp_a1..."


def test_good_doc_produces_no_docs_style_findings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, items = findings(tmp_path, GOOD_DOC, capsys, "--docs-style")

    assert code == 0
    assert docs_findings(items) == []


def test_without_the_flag_no_docs_style_kind_appears(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, items = findings(tmp_path, BAD_DOC, capsys)

    assert code == 0
    assert docs_findings(items) == []


def test_docs_style_does_not_change_the_exit_code_of_a_high_finding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = BAD_DOC + "\nWe delve into it.\n"

    with_flag, _ = findings(tmp_path, text, capsys, "--docs-style")
    without_flag, _ = findings(tmp_path, text, capsys)

    assert with_flag == without_flag == 1


@pytest.mark.parametrize(
    "heading",
    [
        "## Configure the widget",
        "## Use GitHub Copilot",
        "## Run `Widget Factory` now",
        "## Install on Windows and Linux",
        "## Set up the CI API",
        "## Overview: The Big Picture",
        "## 1. Test the build",
        "## Why PowerShell and ConfigGen",
        "## Use [Claude](x.md) today",
        "# Title",
    ],
)
def test_sentence_case_headings_are_clean(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], heading: str
) -> None:
    _, items = findings(
        tmp_path, f"# Top\n\n{heading}\n\nBody text here.\n", capsys, "--docs-style"
    )

    assert [f for f in items if f["kind"] == "heading-case"] == []


@pytest.mark.parametrize(
    "heading",
    ["## Configure The Widget", "## Run Tests Now", "## 2. Install Dependencies"],
)
def test_title_case_headings_are_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], heading: str
) -> None:
    _, items = findings(
        tmp_path, f"# Top\n\n{heading}\n\nBody text here.\n", capsys, "--docs-style"
    )

    assert [f["kind"] for f in items if f["kind"] == "heading-case"] == ["heading-case"]


@pytest.mark.parametrize("text", ["this link", "link", "this page", "here", "click here"])
def test_vague_link_text_is_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], text: str
) -> None:
    _, items = findings(tmp_path, f"# Top\n\nBody with [{text}](a.md).\n", capsys, "--docs-style")

    assert [f["kind"] for f in items if f["kind"] == "link-text"] == ["link-text"]


def test_bare_url_link_text_is_reported_but_descriptive_text_is_not(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = "# Top\n\n[https://a.test/x](https://a.test/x) and [the API guide](a.md).\n"

    _, items = findings(tmp_path, text, capsys, "--docs-style")

    assert [f["match"] for f in items if f["kind"] == "link-text"] == ["https://a.test/x"]


@pytest.mark.parametrize(
    ("opener", "expected"),
    [
        ("This is used to run it.", 1),
        ("It does the work.", 1),
        ("This skill runs the check.", 0),
        ("Use this to run it.", 0),
        ("- This is a list item.", 0),
    ],
)
def test_vague_opener_only_when_pronoun_meets_verb(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], opener: str, expected: int
) -> None:
    _, items = findings(tmp_path, f"# Top\n\n## Section\n\n{opener}\n", capsys, "--docs-style")

    assert len([f for f in items if f["kind"] == "vague-opener"]) == expected


def test_vague_opener_is_judged_only_on_the_first_line_of_a_section(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    text = "# Top\n\n## Section\n\nUse the tool.\n\nThis is fine here.\n"

    _, items = findings(tmp_path, text, capsys, "--docs-style")

    assert [f for f in items if f["kind"] == "vague-opener"] == []


@pytest.mark.parametrize(
    "address",
    [
        "jane@contoso.com",
        "12345+bot@users.noreply.github.com",
        "x@noreply.github.com",
        "dev@anthropic.com",
    ],
)
def test_real_looking_emails_are_reported_inside_fences_too(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], address: str
) -> None:
    text = f"# Top\n\n```text\nFrom: {address}\n```\n"

    _, items = findings(tmp_path, text, capsys, "--docs-style")

    assert [f["match"] for f in items if f["kind"] == "example-email"] == [address]


@pytest.mark.parametrize(
    "address",
    [
        "jane@example.com",
        "a@mail.example.org",
        "noreply@anthropic.com",
        "photo@2x.png",
        "git@github.com:owner/repo.git",
    ],
)
def test_allowed_addresses_are_not_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], address: str
) -> None:
    _, items = findings(tmp_path, f"# Top\n\nWrite to {address} now.\n", capsys, "--docs-style")

    assert [f for f in items if f["kind"] == "example-email"] == []


@pytest.mark.parametrize(
    "token",
    [
        "github_pat_" + "A" * 22,
        "sk-ant-" + "a" * 24,
        "AKIA" + "ABCDEFGHIJKLMNOP",
    ],
)
def test_other_token_shapes_are_reported_in_fenced_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], token: str
) -> None:
    text = f"# Top\n\n```bash\nexport KEY={token}\n```\n"

    _, items = findings(tmp_path, text, capsys, "--docs-style")

    assert [f["kind"] for f in items if f["kind"] == "token-shaped"] == ["token-shaped"]


def test_prose_checks_skip_fenced_code(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    text = "# Top\n\n```md\n## Title Case Heading\n[click here](x.md)\n```\n"

    _, items = findings(tmp_path, text, capsys, "--docs-style")

    assert docs_findings(items) == []
