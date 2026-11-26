"""adr_drift.py: ADR file names, unread formats, the per-file size cap, and status lines."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import adr_corpus
import adr_text
import pytest
from adr_drift_helpers import ADR_DIR, kinds, run_cli, scan, seeded_repo
from adr_drift_helpers import adr_text as adr_body

REPO_ROOT = Path(__file__).resolve().parents[3]
BOOTSTRAP_LOCATE = REPO_ROOT / "src/claude/skills/skill-bootstrap/scripts/adr_locate.py"


def _bootstrap_name_pattern() -> re.Pattern[str]:
    """skill-bootstrap's `_ADR_NAME`, compiled from its source with the flags it names."""
    tree = ast.parse(BOOTSTRAP_LOCATE.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_ADR_NAME" for t in node.targets
        ):
            call = node.value
            assert isinstance(call, ast.Call) and isinstance(call.args[0], ast.Constant)
            flags = ast.unparse(call.args[1])
            assert flags == "re.IGNORECASE | re.ASCII", flags
            pattern = call.args[0].value
            assert isinstance(pattern, str)
            return re.compile(pattern, re.IGNORECASE | re.ASCII)
    raise AssertionError("skill-bootstrap adr_locate.py has no _ADR_NAME")


NAMES = [
    "ADR-001-use-uv.md",
    "adr-001-use-uv.md",
    "Adr-12_use-uv.md",
    "0002-use-x.md",
    "0002_use-x.md",
    "0003-z.MD",
    "1234567-too-long.md",
    "README.md",
    "notes.md",
    "0004-no-ext",
]


@pytest.mark.parametrize("name", NAMES)
def test_markdown_names_match_what_skill_bootstrap_reads(name):
    bootstrap = _bootstrap_name_pattern().match(name) is not None

    assert (adr_corpus.parse_name(name) is not None) == bootstrap


def test_a_date_named_record_is_the_one_deliberate_difference():
    name = "2024-01-15-use-x.md"

    assert _bootstrap_name_pattern().match(name) is not None
    assert adr_corpus.parse_name(name) is None


def test_a_folder_of_date_named_records_is_listed_not_called_missing(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo", {"docs/adr/2024-01-15-use-x.md": "# Use X\n"})

    result = scan(capsys, repo)

    assert kinds(result, "no-adr-directory") == []
    assert result["locate"]["rejected"] == [
        {"path": "docs/adr/2024-01-15-use-x.md", "reason": "a date-named record, not numbered"}
    ]


@pytest.mark.parametrize("name", ["0005-z.mdx", "adr-006-z.adoc"])
def test_bootstrap_reads_the_unread_formats(name):
    assert _bootstrap_name_pattern().match(name) is not None
    assert adr_corpus.UNREAD_NAME.match(name) is not None


def test_lowercase_prefix_and_underscore_names_are_read_as_adrs(tmp_path, capsys):
    repo = seeded_repo(
        tmp_path / "repo",
        {"docs/adr/adr-001-use-x.md": "# 1. X\n", "docs/adr/0002_use-y.md": "# 2. Y\n"},
    )

    result = scan(capsys, repo)

    assert kinds(result, "no-adr-directory") == []
    assert [(d["path"], d["count"]) for d in result["locate"]["adr_dirs"]] == [("docs/adr", 2)]


def test_a_folder_of_unread_formats_is_listed_not_called_missing(tmp_path, capsys):
    repo = seeded_repo(tmp_path / "repo", {"docs/adr/0001-a.mdx": "# 1. A\n"})

    result = scan(capsys, repo)

    assert kinds(result, "no-adr-directory") == []
    assert result["locate"]["rejected"] == [
        {"path": "docs/adr/0001-a.mdx", "reason": "a format this scan does not read"}
    ]


def test_an_adr_over_the_size_cap_is_a_read_error_not_read(tmp_path, capsys, monkeypatch):
    big = f"{ADR_DIR}/ADR-002-big.md"
    repo = seeded_repo(
        tmp_path / "repo",
        {f"{ADR_DIR}/ADR-001-small.md": adr_body(1), big: adr_body(2, body="x" * 400)},
    )
    monkeypatch.setattr(adr_corpus, "ADR_MAX_BYTES", 300)

    result = scan(capsys, repo)

    errors = {e["path"]: e["error"] for e in result["read_errors"]}
    assert list(errors) == [big] and "300-byte limit" in errors[big]


def test_locate_records_a_style_read_failure(tmp_path, capsys, monkeypatch):
    repo = seeded_repo(tmp_path / "repo")

    def refuse(file):
        raise OSError("denied")

    monkeypatch.setattr(adr_corpus, "read_doc", refuse)
    code, out, err = run_cli(capsys, "locate", "--repo", str(repo))

    assert code == 0, err
    assert f'"path": "{ADR_DIR}/ADR-001-decision.md"' in out and '"error": "denied"' in out


@pytest.mark.parametrize(
    ("lines", "status"),
    [
        (["# ADR-1: x", "", "* Status: accepted"], "accepted"),
        (["# ADR-1: x", "", "| Status | Accepted |"], "accepted"),
        (["# ADR-1: x", "<!--", "Status: draft", "-->", "Status: accepted"], "accepted"),
        (["# ADR-1: x", "", "Nothing here"], ""),
        (["# ADR-1: x", "", "| Status | Deciders | Date |", "| --- | --- | --- |"], ""),
        (["# ADR-1: x", "", "| Status | Owner |", "|---|---|", "| Accepted | me |"], ""),
        (["# ADR-1: x", "", "| Status | Accepted |", "|---|---|", "| Date | 2024 |"], "accepted"),
    ],
    ids=[
        "inline",
        "table-row",
        "commented-out",
        "none",
        "wide-header",
        "two-cell-header",
        "key-value-first-row",
    ],
)
def test_status_lines_in_prose(lines, status):
    assert adr_text.status_word(adr_text.doc_status({}, lines, 0)) == status


def test_every_active_status_is_a_status_word():
    import adr_checks

    assert adr_checks.ACTIVE_STATUSES - {""} <= adr_text.STATUS_WORDS


def test_a_finding_key_with_undecodable_file_name_bytes_still_gets_an_id():
    name = b"ADR-002-caf\xe9.md".decode("utf-8", errors="surrogateescape")

    finding = adr_corpus.make_finding(
        "adr-number-mismatch", "Numbering", "low", "deterministic", {"path": name}, "fix", (name,)
    )

    assert re.fullmatch(r"[0-9a-f]{12}", finding["id"])


def test_an_ordinary_finding_key_keeps_its_id():
    finding = adr_corpus.make_finding("k", "Setup", "info", "deterministic", {}, "fix", ("é",))

    assert finding["id"] == "031f59a0e23a"
