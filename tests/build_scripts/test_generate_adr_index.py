# taste-lint: ignore file-size, one test module per module under test. The
# cases here are the pos/neg/edge matrix TESTING-RIGOR requires for one
# contract; splitting them hides whether that one contract is fully
# covered. (Deliberately no exact case count: an earlier version cited "51"
# and it went stale after later rounds added cases without updating the
# number, Copilot, PR #5209 round-10 review.)
"""Tests for build/scripts/generate_adr_index.py (issue #5198, ADR-073 consumer).

Every fixture is a synthetic ADR under ``tmp_path``. The real corpus is never
read: it changes under the tests as records are backfilled, and a test that
asserts on it would encode a count that is wrong by the next merge.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS_PATH = str(REPO_ROOT / "build" / "scripts")
sys.path.insert(0, _SCRIPTS_PATH)
try:
    import generate_adr_index
finally:
    sys.path.remove(_SCRIPTS_PATH)

# Helpers --------------------------------------------------------------------


def _write_adr(
    adr_dir: Path,
    number: int,
    slug: str,
    *,
    frontmatter: str | None = None,
    body: str,
) -> Path:
    """Write one synthetic ADR and return its path."""
    adr_dir.mkdir(parents=True, exist_ok=True)
    path = adr_dir / f"ADR-{number:03d}-{slug}.md"
    content = f"---\n{frontmatter}\n---\n\n{body}" if frontmatter is not None else body
    path.write_text(content, encoding="utf-8")
    return path


def _standard_body(number: int, title: str, *, decision: str = "Do the thing.") -> str:
    return (
        f"# ADR-{number:03d}: {title}\n"
        "\n"
        "## Status\n"
        "\n"
        "Proposed. Waiting on the eval to land.\n"
        "\n"
        "## Decision\n"
        "\n"
        f"{decision} Second sentence that must not appear.\n"
    )


def _render(adr_dir: Path) -> str:
    return generate_adr_index.render_index(generate_adr_index.collect_records(adr_dir))


def _section(text: str, heading: str) -> str:
    """Return the body of one ``## <heading>`` section of the rendered index."""
    start = text.index(f"## {heading}\n")
    rest = text[start + len(f"## {heading}\n") :]
    nxt = rest.find("\n## ")
    return rest if nxt == -1 else rest[:nxt]


def _corpus(adr_dir: Path) -> None:
    """One record per lifecycle status, plus one with no frontmatter."""
    _write_adr(
        adr_dir,
        1,
        "accepted-one",
        frontmatter="id: ADR-001\nstatus: accepted\ndate: 2026-01-02\n",
        body=_standard_body(1, "Accepted One", decision="Adopt the accepted thing."),
    )
    _write_adr(
        adr_dir,
        2,
        "proposed-one",
        frontmatter="id: ADR-002\nstatus: proposed\ndate: 2026-02-03\n",
        body=_standard_body(2, "Proposed One", decision="Adopt the proposed thing."),
    )
    _write_adr(
        adr_dir,
        3,
        "superseded-one",
        frontmatter="id: ADR-003\nstatus: superseded\ndate: 2026-03-04\nsuperseded-by: ADR-001\n",
        body=_standard_body(3, "Superseded One"),
    )
    _write_adr(
        adr_dir,
        4,
        "deprecated-one",
        frontmatter="id: ADR-004\nstatus: deprecated\ndate: 2026-04-05\nsuperseded-by: ADR-002\n",
        body=_standard_body(4, "Deprecated One"),
    )
    _write_adr(
        adr_dir,
        5,
        "rejected-one",
        frontmatter="id: ADR-005\nstatus: rejected\ndate: 2026-05-06\n",
        body=_standard_body(5, "Rejected One", decision="Decline the rejected thing."),
    )
    _write_adr(adr_dir, 6, "no-frontmatter", body=_standard_body(6, "No Frontmatter"))


@pytest.fixture
def adr_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "architecture"
    _corpus(directory)
    return directory


# Positive: each status lands in its own section ------------------------------


@pytest.mark.parametrize(
    ("heading", "expected_id"),
    [
        ("Accepted", "ADR-001"),
        ("Proposed", "ADR-002"),
        ("Retired", "ADR-003"),
        ("Retired", "ADR-004"),
        ("Rejected", "ADR-005"),
        ("Needs backfill", "ADR-006"),
    ],
)
def test_record_lands_in_the_section_its_frontmatter_names(
    adr_dir: Path, heading: str, expected_id: str
) -> None:
    section = _section(_render(adr_dir), heading)

    assert expected_id in section


@pytest.mark.parametrize(
    ("heading", "absent_ids"),
    [
        ("Accepted", ("ADR-002", "ADR-003", "ADR-004", "ADR-005", "ADR-006")),
        ("Proposed", ("ADR-001", "ADR-003", "ADR-004", "ADR-005", "ADR-006")),
        ("Rejected", ("ADR-001", "ADR-002", "ADR-003", "ADR-004", "ADR-006")),
        ("Needs backfill", ("ADR-001", "ADR-002", "ADR-003", "ADR-004", "ADR-005")),
    ],
)
def test_section_excludes_every_other_status(
    adr_dir: Path, heading: str, absent_ids: tuple[str, ...]
) -> None:
    section = _section(_render(adr_dir), heading)

    for adr_id in absent_ids:
        assert adr_id not in section


def test_retired_row_names_the_successor(adr_dir: Path) -> None:
    retired = _section(_render(adr_dir), "Retired")

    superseded_row = next(line for line in retired.splitlines() if "ADR-003" in line)

    assert "ADR-001" in superseded_row


def test_retired_row_links_the_successor_file(adr_dir: Path) -> None:
    retired = _section(_render(adr_dir), "Retired")

    superseded_row = next(line for line in retired.splitlines() if "ADR-003" in line)

    assert "(ADR-001-accepted-one.md)" in superseded_row


def test_deprecated_record_is_retired_not_a_separate_section(adr_dir: Path) -> None:
    rendered = _render(adr_dir)

    assert "## Deprecated" not in rendered
    assert "ADR-004" in _section(rendered, "Retired")


def test_accepted_row_carries_the_decision_summary(adr_dir: Path) -> None:
    accepted = _section(_render(adr_dir), "Accepted")

    assert "Adopt the accepted thing." in accepted
    assert "Second sentence that must not appear" not in accepted


def test_proposed_row_carries_the_blocking_condition(adr_dir: Path) -> None:
    proposed = _section(_render(adr_dir), "Proposed")

    assert "Waiting on the eval to land." in proposed


def test_proposed_blocker_drops_the_redundant_status_token(adr_dir: Path) -> None:
    proposed_row = next(
        line for line in _section(_render(adr_dir), "Proposed").splitlines() if "ADR-002" in line
    )

    assert "Proposed." not in proposed_row


def test_accepted_row_carries_the_frontmatter_date(adr_dir: Path) -> None:
    accepted_row = next(
        line for line in _section(_render(adr_dir), "Accepted").splitlines() if "ADR-001" in line
    )

    assert "2026-01-02" in accepted_row


def test_rows_are_sorted_by_adr_number_not_by_slug(tmp_path: Path) -> None:
    directory = tmp_path / "architecture"
    for number, slug in ((10, "zulu"), (2, "alpha"), (100, "mike")):
        _write_adr(
            directory,
            number,
            slug,
            frontmatter=f"id: ADR-{number:03d}\nstatus: accepted\ndate: 2026-01-01\n",
            body=_standard_body(number, slug.title()),
        )

    accepted = _section(_render(directory), "Accepted")
    order = [line.split("]")[0] for line in accepted.splitlines() if line.startswith("| [")]

    assert order == ["| [ADR-002", "| [ADR-010", "| [ADR-100"]


# Negative: missing and malformed frontmatter ---------------------------------


def test_record_without_frontmatter_goes_to_needs_backfill(adr_dir: Path) -> None:
    backfill = _section(_render(adr_dir), "Needs backfill")

    assert "ADR-006" in backfill
    assert "No Frontmatter" in backfill


def test_record_without_frontmatter_is_assigned_no_status(adr_dir: Path) -> None:
    record = next(r for r in generate_adr_index.collect_records(adr_dir) if r.number == 6)

    assert record.status is None


def test_needs_backfill_table_has_no_status_column(adr_dir: Path) -> None:
    backfill = _section(_render(adr_dir), "Needs backfill")
    header = next(line for line in backfill.splitlines() if line.startswith("| ADR"))

    assert header == "| ADR | Title |"


def test_malformed_yaml_frontmatter_exits_non_zero(tmp_path: Path, capsys) -> None:
    directory = tmp_path / "architecture"
    _corpus(directory)
    _write_adr(
        directory,
        7,
        "broken-yaml",
        frontmatter="id: ADR-007\nstatus: [unclosed\ndate: 2026-01-01\n",
        body=_standard_body(7, "Broken YAML"),
    )

    exit_code = generate_adr_index.main(
        ["--adr-dir", str(directory), "--output", str(tmp_path / "README.md")]
    )

    assert exit_code != 0
    assert "ADR-007-broken-yaml.md" in capsys.readouterr().err


def test_malformed_yaml_does_not_silently_write_an_index(tmp_path: Path) -> None:
    directory = tmp_path / "architecture"
    _corpus(directory)
    _write_adr(
        directory,
        7,
        "broken-yaml",
        frontmatter="id: ADR-007\nstatus: [unclosed\n",
        body=_standard_body(7, "Broken YAML"),
    )
    output = tmp_path / "README.md"

    generate_adr_index.main(["--adr-dir", str(directory), "--output", str(output)])

    assert not output.exists()


def test_frontmatter_id_disagreeing_with_filename_exits_non_zero(tmp_path: Path, capsys) -> None:
    """A present `id` that disagrees with the filename must fail loudly.

    The filename is the authoritative id (module docstring: some backfilled
    records carry no `id` key at all, so a missing key is not an error). But
    a *present* `id` that names a different record is a distinct defect: a
    `superseded-by` elsewhere naming that frontmatter id would resolve to
    the wrong record or appear dangling, and this extraction ships no
    lifecycle validator that would otherwise catch the mismatch (Copilot,
    PR #5285 review).
    """
    directory = tmp_path / "architecture"
    _corpus(directory)
    _write_adr(
        directory,
        103,
        "mismatched",
        frontmatter="id: ADR-104\nstatus: accepted\n",
        body=_standard_body(103, "Mismatched"),
    )

    exit_code = generate_adr_index.main(
        ["--adr-dir", str(directory), "--output", str(tmp_path / "README.md")]
    )

    assert exit_code != 0
    err = capsys.readouterr().err
    assert "ADR-103-mismatched.md" in err
    assert "ADR-104" in err


def test_frontmatter_id_matching_the_filename_is_accepted(tmp_path: Path) -> None:
    """A present `id` that agrees with the filename is the common, valid case."""
    directory = tmp_path / "architecture"
    _corpus(directory)
    _write_adr(
        directory,
        105,
        "matched",
        frontmatter="id: ADR-105\nstatus: accepted\n",
        body=_standard_body(105, "Matched"),
    )

    exit_code = generate_adr_index.main(
        ["--adr-dir", str(directory), "--output", str(tmp_path / "README.md")]
    )

    assert exit_code == 0


def test_non_mapping_frontmatter_exits_non_zero_naming_the_file(tmp_path: Path, capsys) -> None:
    directory = tmp_path / "architecture"
    _write_adr(
        directory,
        8,
        "scalar-frontmatter",
        frontmatter="just a bare string",
        body=_standard_body(8, "Scalar Frontmatter"),
    )

    exit_code = generate_adr_index.main(
        ["--adr-dir", str(directory), "--output", str(tmp_path / "README.md")]
    )

    assert exit_code == 1
    assert "ADR-008-scalar-frontmatter.md" in capsys.readouterr().err


def test_parse_frontmatter_raises_on_an_unterminated_block(tmp_path: Path) -> None:
    """Opens with '---', never closes: a distinct defect from no block at all.

    `_FRONTMATTER_RE` cannot match without a closing fence, so both an absent
    block and an unterminated one previously collapsed to the same `None`,
    silently routing malformed lifecycle metadata into Needs backfill as if
    the record had never carried a schema (PR #5209 review,
    discussion_r3832255493).
    """
    path = tmp_path / "ADR-009-unterminated.md"
    content = "---\nid: ADR-009\nstatus: accepted\n\n# ADR-009: Unterminated\n"

    with pytest.raises(generate_adr_index.AdrIndexError, match="unterminated"):
        generate_adr_index.parse_frontmatter(content, path)


def test_unterminated_frontmatter_block_exits_non_zero(tmp_path: Path, capsys) -> None:
    directory = tmp_path / "architecture"
    _corpus(directory)
    (directory / "ADR-009-unterminated.md").write_text(
        "---\nid: ADR-009\nstatus: accepted\n\n# ADR-009: Unterminated\n", encoding="utf-8"
    )

    exit_code = generate_adr_index.main(
        ["--adr-dir", str(directory), "--output", str(tmp_path / "README.md")]
    )

    assert exit_code != 0
    assert "ADR-009-unterminated.md" in capsys.readouterr().err


def test_status_outside_the_adr_073_enum_exits_non_zero_naming_the_file(
    tmp_path: Path, capsys
) -> None:
    directory = tmp_path / "architecture"
    _write_adr(
        directory,
        9,
        "prose-status",
        frontmatter='id: ADR-009\nstatus: "Accepted (2026-06-19), pending review"\n',
        body=_standard_body(9, "Prose Status"),
    )

    exit_code = generate_adr_index.main(
        ["--adr-dir", str(directory), "--output", str(tmp_path / "README.md")]
    )

    assert exit_code == 1
    err = capsys.readouterr().err
    assert "ADR-009-prose-status.md" in err
    assert "proposed, accepted, rejected, deprecated, superseded" in err


def test_out_of_enum_status_is_never_silently_dropped(tmp_path: Path) -> None:
    directory = tmp_path / "architecture"
    _write_adr(
        directory,
        9,
        "prose-status",
        frontmatter="id: ADR-009\nstatus: archived\n",
        body=_standard_body(9, "Prose Status"),
    )

    with pytest.raises(generate_adr_index.AdrIndexError):
        generate_adr_index.collect_records(directory)


# Negative: a present-but-empty status is not the same defect as an absent key
#
# `frontmatter.get("status")` cannot distinguish "key absent" from "key present
# as null", so both used to return `None` silently and route indistinguishably
# from a record with zero frontmatter into Needs backfill (PR #5209 review).
# An explicit `status: null` or `status: ""` means the author touched the
# field and left it broken, which `_status_of` now raises on instead.


def test_null_status_raises_instead_of_backfilling_silently(tmp_path: Path) -> None:
    directory = tmp_path / "architecture"
    _write_adr(
        directory,
        10,
        "null-status",
        frontmatter="id: ADR-010\nstatus: null\ndate: 2026-01-01\n",
        body=_standard_body(10, "Null Status"),
    )

    with pytest.raises(generate_adr_index.AdrIndexError, match="present but null"):
        generate_adr_index.collect_records(directory)


def test_empty_string_status_raises_instead_of_backfilling_silently(tmp_path: Path) -> None:
    directory = tmp_path / "architecture"
    _write_adr(
        directory,
        10,
        "empty-status",
        frontmatter='id: ADR-010\nstatus: ""\ndate: 2026-01-01\n',
        body=_standard_body(10, "Empty Status"),
    )

    with pytest.raises(generate_adr_index.AdrIndexError, match="present but empty"):
        generate_adr_index.collect_records(directory)


def test_absent_status_key_still_backfills_silently(tmp_path: Path) -> None:
    """The one legitimate `None`: the key was never addressed at all."""
    directory = tmp_path / "architecture"
    _write_adr(
        directory,
        10,
        "no-status-key",
        frontmatter="id: ADR-010\ndate: 2026-01-01\n",
        body=_standard_body(10, "No Status Key"),
    )

    (record,) = generate_adr_index.collect_records(directory)

    assert record.status is None


def test_record_without_an_h1_exits_non_zero_naming_the_file(tmp_path: Path, capsys) -> None:
    directory = tmp_path / "architecture"
    _write_adr(
        directory,
        11,
        "no-title",
        frontmatter="id: ADR-011\nstatus: accepted\n",
        body="## Decision\n\nSomething.\n",
    )

    exit_code = generate_adr_index.main(
        ["--adr-dir", str(directory), "--output", str(tmp_path / "README.md")]
    )

    assert exit_code == 1
    assert "ADR-011-no-title.md" in capsys.readouterr().err


def test_missing_adr_directory_is_a_config_error(tmp_path: Path) -> None:
    exit_code = generate_adr_index.main(
        ["--adr-dir", str(tmp_path / "absent"), "--output", str(tmp_path / "README.md")]
    )

    assert exit_code == 2


def test_empty_adr_directory_is_a_config_error(tmp_path: Path, capsys) -> None:
    """An emptied or misrouted corpus must fail loudly, not render an empty index.

    `collect_records()` on zero matches renders every index section as `None`
    and `main()` would otherwise exit 0: a missing corpus reads as valid
    generated output (Copilot, PR #5209 round-7 review).
    """
    directory = tmp_path / "architecture"
    directory.mkdir()

    exit_code = generate_adr_index.main(
        ["--adr-dir", str(directory), "--output", str(tmp_path / "README.md")]
    )

    assert exit_code == 2
    assert "no ADR records found" in capsys.readouterr().err


def test_adr_directory_with_only_a_template_is_a_config_error(tmp_path: Path, capsys) -> None:
    """`ADR-TEMPLATE.md` alone must not count as evidence records exist."""
    directory = tmp_path / "architecture"
    directory.mkdir()
    (directory / "ADR-TEMPLATE.md").write_text("# Template\n", encoding="utf-8")

    exit_code = generate_adr_index.main(
        ["--adr-dir", str(directory), "--output", str(tmp_path / "README.md")]
    )

    assert exit_code == 2
    assert "no ADR records found" in capsys.readouterr().err


# Edge: heading forms, list decisions, template exclusion ---------------------


def test_madr_decision_outcome_heading_yields_a_summary(tmp_path: Path) -> None:
    directory = tmp_path / "architecture"
    _write_adr(
        directory,
        12,
        "madr-shaped",
        frontmatter="id: ADR-012\nstatus: accepted\ndate: 2026-01-01\n",
        body=(
            "# ADR-012: MADR Shaped\n"
            "\n"
            "## Decision Drivers\n"
            "\n"
            "A driver that is not the decision.\n"
            "\n"
            "## Decision Outcome\n"
            "\n"
            "Chosen option: role-specific allocation.\n"
        ),
    )

    accepted = _section(_render(directory), "Accepted")

    assert "Chosen option: role-specific allocation." in accepted
    assert "A driver that is not the decision" not in accepted


def test_record_with_neither_decision_heading_yields_the_title_alone(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "architecture"
    _write_adr(
        directory,
        13,
        "no-decision",
        frontmatter="id: ADR-013\nstatus: accepted\ndate: 2026-01-01\n",
        body="# ADR-013: No Decision Heading\n\n## Context\n\nSome context prose.\n",
    )

    row = next(
        line for line in _section(_render(directory), "Accepted").splitlines() if "ADR-013" in line
    )

    assert "No Decision Heading" in row
    assert "Some context prose" not in row


def test_decision_summary_is_empty_when_no_heading_exists(tmp_path: Path) -> None:
    directory = tmp_path / "architecture"
    _write_adr(
        directory,
        13,
        "no-decision",
        frontmatter="id: ADR-013\nstatus: accepted\n",
        body="# ADR-013: No Decision Heading\n\n## Context\n\nSome context prose.\n",
    )

    record = generate_adr_index.collect_records(directory)[0]

    assert record.summary == ""


def test_decision_section_opening_with_a_subsection_still_yields_a_summary(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "architecture"
    _write_adr(
        directory,
        14,
        "subsectioned",
        frontmatter="id: ADR-014\nstatus: accepted\n",
        body=(
            "# ADR-014: Subsectioned\n"
            "\n"
            "## Decision\n"
            "\n"
            "### 1. The first part\n"
            "\n"
            "Create the config file in the repository root.\n"
        ),
    )

    assert "Create the config file in the repository root." in _render(directory)


def test_numbered_decision_list_yields_only_its_first_item(tmp_path: Path) -> None:
    directory = tmp_path / "architecture"
    _write_adr(
        directory,
        15,
        "listed",
        frontmatter="id: ADR-015\nstatus: accepted\n",
        body=(
            "# ADR-015: Listed\n"
            "\n"
            "## Decision\n"
            "\n"
            "1. **Supersede ADR-044 in full.** Keep it unchanged otherwise.\n"
            "2. Treat configuration as the version record.\n"
        ),
    )

    row = next(
        line for line in _section(_render(directory), "Accepted").splitlines() if "ADR-015" in line
    )

    assert "Supersede ADR-044 in full." in row
    assert "Treat configuration as the version record" not in row


def test_yaml_comment_in_frontmatter_is_not_read_as_the_title(tmp_path: Path) -> None:
    directory = tmp_path / "architecture"
    _write_adr(
        directory,
        16,
        "commented-frontmatter",
        frontmatter=(
            "# taste-lint: ignore file-size, accepted append-only record\n"
            "id: ADR-016\nstatus: accepted\n"
        ),
        body="# ADR-016: Real Title\n\n## Decision\n\nDo it.\n",
    )

    accepted = _section(_render(directory), "Accepted")

    assert "Real Title" in accepted
    assert "taste-lint" not in accepted


def test_adr_template_is_excluded_from_the_index(tmp_path: Path) -> None:
    directory = tmp_path / "architecture"
    _corpus(directory)
    (directory / "ADR-TEMPLATE.md").write_text(
        "---\nid: ADR-NNN\nstatus: proposed\n---\n\n# ADR-NNN: Template\n",
        encoding="utf-8",
    )

    rendered = _render(directory)

    assert "ADR-NNN" not in rendered
    assert "ADR-TEMPLATE.md" not in rendered


def test_retired_record_without_a_successor_says_so(tmp_path: Path) -> None:
    directory = tmp_path / "architecture"
    _write_adr(
        directory,
        17,
        "dangling",
        frontmatter="id: ADR-017\nstatus: superseded\nsuperseded-by: null\n",
        body=_standard_body(17, "Dangling Supersession"),
    )

    retired = _section(_render(directory), "Retired")

    assert "not recorded" in retired


def test_pipe_in_a_title_is_escaped_so_the_table_survives(tmp_path: Path) -> None:
    directory = tmp_path / "architecture"
    _write_adr(
        directory,
        18,
        "piped-title",
        frontmatter="id: ADR-018\nstatus: accepted\n",
        body="# ADR-018: A | B Routing\n\n## Decision\n\nRoute it.\n",
    )

    row = next(
        line for line in _section(_render(directory), "Accepted").splitlines() if "ADR-018" in line
    )

    assert "A \\| B Routing" in row
    assert row.count("|") - row.count("\\|") == 5


def test_empty_section_renders_none_rather_than_an_empty_table(tmp_path: Path) -> None:
    directory = tmp_path / "architecture"
    _write_adr(
        directory,
        19,
        "only-accepted",
        frontmatter="id: ADR-019\nstatus: accepted\n",
        body=_standard_body(19, "Only Accepted"),
    )

    rejected = _section(_render(directory), "Rejected")

    assert rejected.strip().endswith("None.")
    assert "| ---" not in rejected


def test_every_lifecycle_section_is_present_even_when_empty(tmp_path: Path) -> None:
    directory = tmp_path / "architecture"
    _write_adr(
        directory,
        20,
        "solo",
        frontmatter="id: ADR-020\nstatus: accepted\n",
        body=_standard_body(20, "Solo"),
    )

    rendered = _render(directory)

    for heading in ("Accepted", "Proposed", "Retired", "Rejected", "Needs backfill"):
        assert f"## {heading}\n" in rendered


# Edge: determinism and the no-banner rule ------------------------------------


def test_two_runs_produce_byte_identical_output(tmp_path: Path) -> None:
    directory = tmp_path / "architecture"
    _corpus(directory)
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"

    generate_adr_index.generate(directory, first)
    generate_adr_index.generate(directory, second)

    assert first.read_bytes() == second.read_bytes()


def test_output_carries_no_timestamp(adr_dir: Path) -> None:
    rendered = _render(adr_dir)

    # Only the dates the records themselves declare may appear. Nothing that
    # changes between two runs of the same input.
    assert "T00:00:00" not in rendered
    for token in ("Generated on", "Last updated", "Generated at", "Timestamp"):
        assert token not in rendered


def test_output_carries_no_generated_file_banner(adr_dir: Path) -> None:
    """universal.md MUST-NOT-6: no banner, no 'do not edit', no timestamp."""
    lowered = _render(adr_dir).lower()

    for banner in (
        "generated file",
        "do not edit",
        "auto-generated",
        "autogenerated",
        "this file is generated",
    ):
        assert banner not in lowered


def test_output_uses_no_em_or_en_dash(adr_dir: Path) -> None:
    """universal.md MUST-NOT-5 binds generated prose the same as authored prose.

    The banned characters are written as escapes, not literals: the carve-out in
    that rule covers ``tests/hooks/fixtures/`` only, so a literal em dash here
    would itself violate the rule this test enforces.
    """
    rendered = _render(adr_dir)

    assert "\u2014" not in rendered  # em dash
    assert "\u2013" not in rendered  # en dash


# CLI: generate and --check ---------------------------------------------------


def test_generate_writes_the_index_and_exits_zero(tmp_path: Path) -> None:
    directory = tmp_path / "architecture"
    _corpus(directory)
    output = tmp_path / "README.md"

    exit_code = generate_adr_index.main(["--adr-dir", str(directory), "--output", str(output)])

    assert exit_code == 0
    assert output.read_text(encoding="utf-8").startswith("# Architecture Decision Records")


def test_check_passes_when_the_committed_index_is_current(tmp_path: Path) -> None:
    directory = tmp_path / "architecture"
    _corpus(directory)
    output = tmp_path / "README.md"
    generate_adr_index.main(["--adr-dir", str(directory), "--output", str(output)])

    exit_code = generate_adr_index.main(
        ["--adr-dir", str(directory), "--output", str(output), "--check"]
    )

    assert exit_code == 0


def test_check_reports_the_examined_record_count(tmp_path: Path, capsys) -> None:
    """The `OK` success line names how many ADR records were examined.

    Before this fix, a byte-for-byte match against an emptied or narrowed
    corpus printed the identical unqualified `OK: {path} matches {dir}` as a
    match against the full six-record corpus below, so a regression that
    silently narrowed the scan scope read as a clean, complete pass
    (Copilot, PR #5209 round-8 review).
    """
    directory = tmp_path / "architecture"
    _corpus(directory)
    output = tmp_path / "README.md"
    generate_adr_index.main(["--adr-dir", str(directory), "--output", str(output)])

    exit_code = generate_adr_index.main(
        ["--adr-dir", str(directory), "--output", str(output), "--check"]
    )

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "matches" in out
    assert "(6 ADR record(s))" in out


def test_check_fails_when_an_adr_changed_without_a_regeneration(tmp_path: Path, capsys) -> None:
    directory = tmp_path / "architecture"
    _corpus(directory)
    output = tmp_path / "README.md"
    generate_adr_index.main(["--adr-dir", str(directory), "--output", str(output)])
    _write_adr(
        directory,
        21,
        "late-arrival",
        frontmatter="id: ADR-021\nstatus: accepted\n",
        body=_standard_body(21, "Late Arrival"),
    )

    exit_code = generate_adr_index.main(
        ["--adr-dir", str(directory), "--output", str(output), "--check"]
    )

    assert exit_code == 1
    assert "DRIFT" in capsys.readouterr().err


def test_check_fails_when_the_index_does_not_exist(tmp_path: Path, capsys) -> None:
    directory = tmp_path / "architecture"
    _corpus(directory)

    exit_code = generate_adr_index.main(
        [
            "--adr-dir",
            str(directory),
            "--output",
            str(tmp_path / "absent.md"),
            "--check",
        ]
    )

    assert exit_code == 1
    assert "MISSING" in capsys.readouterr().err


def test_check_does_not_write_the_index(tmp_path: Path) -> None:
    directory = tmp_path / "architecture"
    _corpus(directory)
    output = tmp_path / "README.md"

    generate_adr_index.main(["--adr-dir", str(directory), "--output", str(output), "--check"])

    assert not output.exists()


# CLI: worktree-identity guard (.claude/rules/ci-scripts.md MUST 7) -----------
#
# _resolve() anchors relative --adr-dir/--output to _REPO_ROOT (a module
# constant derived from __file__), not to Path.cwd(). Every test above passes
# absolute paths, so it never exercises that anchoring; these two pin the
# guard that stops main() from writing into _REPO_ROOT when the caller's cwd
# is somewhere else entirely.


def test_cwd_inside_repo_root_permits_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "architecture"
    _corpus(directory)
    output = tmp_path / "README.md"
    monkeypatch.chdir(generate_adr_index._REPO_ROOT)

    exit_code = generate_adr_index.main(["--adr-dir", str(directory), "--output", str(output)])

    assert exit_code == 0
    assert output.exists()


def test_cwd_outside_repo_root_is_a_config_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """A bare, argument-less invocation resolves --adr-dir implicitly.

    Only the implicit-default resolution path (relative --adr-dir/--output,
    anchored to _REPO_ROOT by _resolve()) carries the silent-redirection risk
    this guard exists for, so this drives main() with no path overrides at
    all, matching a real bare `generate_adr_index.py` invocation from the
    wrong cwd. An absolute --adr-dir/--output is a stated write target the
    caller supplied explicitly and is exempt (Copilot, PR #5285 review; see
    test_check_mode_ignores_cwd_outside_the_repository_root and
    test_absolute_paths_from_outside_the_repository_root_write_normally below
    for that case).
    """
    monkeypatch.chdir(tmp_path)

    exit_code = generate_adr_index.main([])

    assert exit_code == 2
    assert "outside the repository root" in capsys.readouterr().err


def test_absolute_paths_from_outside_the_repository_root_write_normally(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """An explicit, absolute --adr-dir/--output is exempt from the guard.

    Companion to test_cwd_outside_repo_root_is_a_config_error above: cwd
    outside the repository root only blocks the implicit-default resolution
    path. build_all._build_adr_index always passes absolute paths, resolved
    from its own caller-supplied repo_root (itself build_all.py's --repo-root
    CLI flag), so this is the shape that call site actually exercises.
    Before this fix the guard ran unconditionally against _REPO_ROOT, so this
    call returned exit 2 for a legitimate write to an unrelated, explicitly
    named directory (Copilot, PR #5285 review).
    """
    directory = tmp_path / "architecture"
    _corpus(directory)
    output = tmp_path / "README.md"
    monkeypatch.chdir(tmp_path)

    exit_code = generate_adr_index.main(["--adr-dir", str(directory), "--output", str(output)])

    assert exit_code == 0
    assert "outside the repository root" not in capsys.readouterr().err
    assert output.is_file()


def test_check_mode_ignores_cwd_outside_the_repository_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """`--check` never writes, so the worktree-identity guard must not apply to it.

    Before this fix the guard ran unconditionally in `main()`, so a caller
    using absolute `--adr-dir`/`--output` paths from a cwd outside the
    repository got exit 2 for a check that reads and compares, never writes
    (Copilot, PR #5209 round-7 review).
    """
    directory = tmp_path / "architecture"
    _corpus(directory)
    output = tmp_path / "README.md"
    generate_adr_index.main(["--adr-dir", str(directory), "--output", str(output)])
    monkeypatch.chdir(tmp_path)

    exit_code = generate_adr_index.main(
        ["--adr-dir", str(directory), "--output", str(output), "--check"]
    )

    assert exit_code == 0
    assert "outside the repository root" not in capsys.readouterr().err


# The build_all.py registration ----------------------------------------------


def test_build_all_registers_the_adr_index_generator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT / "build" / "scripts"))
    import build_all

    assert "adr-index" in dict(build_all.GENERATORS)


def test_build_all_owns_the_index_path_for_the_staleness_diff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT / "build" / "scripts"))
    import build_all

    assert ".agents/architecture/README.md" in build_all.OWNED_PREFIXES


def test_is_adr_filename_accepts_canonical_names_only() -> None:
    assert generate_adr_index.is_adr_filename("ADR-073-adr-lifecycle-frontmatter.md")
    assert not generate_adr_index.is_adr_filename("ADR-TEMPLATE.md")
    assert not generate_adr_index.is_adr_filename("DESIGN-REVIEW-template.md")


def test_two_hop_supersession_redirects_to_the_terminal_record(tmp_path: Path) -> None:
    """A reader following a stale citation must not land on another retired record.

    ADR-079 names ADR-091 as its immediate successor, and ADR-091 is itself
    retired in favour of ADR-092. The frontmatter is right to name the immediate
    successor, because supersession is an edge and the chain is the history. The
    index is a redirect, and a redirect onto another redirect has not redirected.
    """
    adr_dir = tmp_path / "architecture"
    _write_adr(
        adr_dir,
        79,
        "first",
        frontmatter="status: superseded\nsuperseded-by: ADR-091",
        body=_standard_body(79, "First"),
    )
    _write_adr(
        adr_dir,
        91,
        "second",
        frontmatter="status: superseded\nsuperseded-by: ADR-092",
        body=_standard_body(91, "Second"),
    )
    _write_adr(
        adr_dir,
        92,
        "third",
        frontmatter="status: accepted",
        body=_standard_body(92, "Third"),
    )

    retired = _section(_render(adr_dir), "Retired")
    row = next(line for line in retired.splitlines() if "ADR-079" in line)

    assert "ADR-092-third.md" in row
    assert "via ADR-091" in row


def test_chain_ending_at_a_missing_successor_is_reported_unresolved(tmp_path: Path) -> None:
    """A chain must not link through a retired record whose own citation is dead.

    ADR-050 names ADR-051 as its successor; ADR-051 is itself retired but
    names "ADR-999", which has no record in this corpus. Before this fix,
    ADR-050's row fell through to `terminal = chain[-1]` and linked to
    ADR-051 as though it were resolved, even though ADR-051's own citation
    is a dangling reference the reader would only discover on the next click
    (AI Spec Validator, PR #5285 review). The row must instead say the chain
    is unresolved and name the missing reference.
    """
    adr_dir = tmp_path / "architecture"
    _write_adr(
        adr_dir,
        50,
        "first",
        frontmatter="status: superseded\nsuperseded-by: ADR-051",
        body=_standard_body(50, "First"),
    )
    _write_adr(
        adr_dir,
        51,
        "second",
        frontmatter="status: superseded\nsuperseded-by: ADR-999",
        body=_standard_body(51, "Second"),
    )

    retired = _section(_render(adr_dir), "Retired")
    row = next(line for line in retired.splitlines() if line.startswith("| [ADR-050]"))

    assert "unresolved (ADR-050 -> ADR-051 -> ADR-999)" in row
    # Must not read as a resolved redirect to ADR-051's file.
    assert "ADR-051-second.md" not in row


def test_chain_ending_at_a_retired_record_with_no_successor_is_unresolved(
    tmp_path: Path,
) -> None:
    """A chain must not link through a retired intermediate with nowhere to go.

    ADR-060 names ADR-061 as its successor; ADR-061 is itself retired but
    names no successor at all (`superseded-by: null`), the same dangling
    supersession `test_retired_record_without_a_successor_says_so` covers
    for a record's own first hop. Before this fix, ADR-060's row fell
    through to `terminal = chain[-1]` and linked to ADR-061 as though it
    were resolved (Copilot, PR #5285 review). The row must instead say the
    chain is unresolved.
    """
    adr_dir = tmp_path / "architecture"
    _write_adr(
        adr_dir,
        60,
        "first",
        frontmatter="status: superseded\nsuperseded-by: ADR-061",
        body=_standard_body(60, "First"),
    )
    _write_adr(
        adr_dir,
        61,
        "second",
        frontmatter="status: superseded\nsuperseded-by: null",
        body=_standard_body(61, "Second"),
    )

    retired = _section(_render(adr_dir), "Retired")
    row = next(line for line in retired.splitlines() if line.startswith("| [ADR-060]"))

    assert "unresolved (ADR-060 -> ADR-061, no successor recorded)" in row
    # Must not read as a resolved redirect to ADR-061's file.
    assert "ADR-061-second.md" not in row


def test_successor_lookup_accepts_non_padded_and_bare_int_references(tmp_path: Path) -> None:
    """A non-padded or bare-integer ``superseded-by`` value must still resolve.

    ``_ADR_REFERENCE_RE`` (this module's own contract, not a mirror of any
    other file, per ``.claude/rules/canonical-source-mirror.md``) accepts
    ``ADR-91`` (non-padded) and a bare integer ``91`` as valid references to
    ADR-091, not only the zero-padded ``ADR-091`` this index's own ``adr_id``
    keys use. Before this fix, the successor lookup compared the raw
    uppercased string against the padded key and missed both, printing the
    reference as unlinked plain text instead of resolving it (Copilot, PR
    #5209; citation to the absent ``check_adr_lifecycle.py`` removed per
    Copilot, PR #5285 review).
    """
    adr_dir = tmp_path / "architecture"
    _write_adr(
        adr_dir,
        79,
        "first",
        frontmatter="status: superseded\nsuperseded-by: ADR-91",
        body=_standard_body(79, "First"),
    )
    _write_adr(
        adr_dir,
        80,
        "second",
        # YAML parses this as an int; _scalar() renders it "91", the bare form.
        frontmatter="status: superseded\nsuperseded-by: 91",
        body=_standard_body(80, "Second"),
    )
    _write_adr(
        adr_dir,
        91,
        "third",
        frontmatter="status: accepted",
        body=_standard_body(91, "Third"),
    )

    retired = _section(_render(adr_dir), "Retired")
    row_79 = next(line for line in retired.splitlines() if "ADR-079" in line)
    row_80 = next(line for line in retired.splitlines() if "ADR-080" in line)

    assert "ADR-091-third.md" in row_79
    assert "ADR-091-third.md" in row_80


def test_successor_lookup_accepts_a_five_digit_adr_number(tmp_path: Path) -> None:
    """A ``superseded-by`` reference past 4 digits must still resolve.

    ``_ADR_REFERENCE_RE`` capped its digit group at ``\\d{1,4}``, four digits,
    while ``_ADR_FILENAME_RE`` (the filename-matching pattern that decides
    which files are records at all) accepts any 2+ digit run, unbounded. A
    5-digit ADR id, such as ``ADR-10000``, was therefore a valid record file
    but an unmatchable successor reference: the lookup would fail to find it
    and print the raw reference as unlinked text instead of a link (Copilot,
    PR #5285 review).
    """
    adr_dir = tmp_path / "architecture"
    _write_adr(
        adr_dir,
        95,
        "old",
        frontmatter="status: superseded\nsuperseded-by: ADR-10000",
        body=_standard_body(95, "Old"),
    )
    _write_adr(
        adr_dir,
        10000,
        "new",
        frontmatter="status: accepted",
        body=_standard_body(10000, "New"),
    )

    retired = _section(_render(adr_dir), "Retired")
    row_95 = next(line for line in retired.splitlines() if "ADR-095" in line)

    assert "ADR-10000-new.md" in row_95


def test_supersession_cycle_terminates_instead_of_hanging(tmp_path: Path) -> None:
    """A cycle must not be discovered by this renderer looping forever.

    No gate elsewhere in this branch rejects a cyclic superseded-by pair
    before it reaches the renderer (this extraction's scope stops short of
    check_adr_lifecycle.py, which lives on a separate, unmerged branch), so
    the renderer itself must survive one without hanging.
    """
    adr_dir = tmp_path / "architecture"
    _write_adr(
        adr_dir,
        10,
        "alpha",
        frontmatter="status: superseded\nsuperseded-by: ADR-011",
        body=_standard_body(10, "Alpha"),
    )
    _write_adr(
        adr_dir,
        11,
        "beta",
        frontmatter="status: superseded\nsuperseded-by: ADR-010",
        body=_standard_body(11, "Beta"),
    )

    retired = _section(_render(adr_dir), "Retired")

    assert "ADR-010" in retired
    assert "ADR-011" in retired


def test_supersession_cycle_is_reported_not_silently_redirected(tmp_path: Path) -> None:
    """A cycle must not print as a redirect to another dead end.

    Before this fix, walking A -> B -> A stopped at the first revisited node
    and printed it as if it were the terminal record: A's row said "read
    instead: B", B's row said "read instead: A", and neither destination was
    live. Both rows must instead say the pair is an unresolved cycle
    (Copilot, PR #5285 review).
    """
    adr_dir = tmp_path / "architecture"
    _write_adr(
        adr_dir,
        20,
        "alpha",
        frontmatter="status: superseded\nsuperseded-by: ADR-021",
        body=_standard_body(20, "Alpha"),
    )
    _write_adr(
        adr_dir,
        21,
        "beta",
        frontmatter="status: superseded\nsuperseded-by: ADR-020",
        body=_standard_body(21, "Beta"),
    )

    retired = _section(_render(adr_dir), "Retired")
    # Match on the row's own leading link, not a bare substring: the cycle
    # description in either row's own cell names both IDs, so a substring
    # search for "ADR-021 in line" matches ADR-020's row too.
    row_20 = next(line for line in retired.splitlines() if line.startswith("| [ADR-020]"))
    row_21 = next(line for line in retired.splitlines() if line.startswith("| [ADR-021]"))

    assert "cycle, unresolved" in row_20
    assert "cycle, unresolved" in row_21
    # Neither row's "Read instead" cell may read as a resolved link to the
    # other dead end (a leading "| [ADR-021]" link cell, not the cycle
    # description's own mention of the ID).
    assert "| [ADR-021]" not in row_20
    assert "| [ADR-020]" not in row_21


def test_self_referencing_supersession_is_reported_as_a_cycle(tmp_path: Path) -> None:
    """A record naming itself as its own successor is the one-hop cycle case.

    The chain accumulator is empty on this path (the walk never advances
    past the starting record), so the rendered loop must still name the
    record rather than printing an empty parenthetical.
    """
    adr_dir = tmp_path / "architecture"
    _write_adr(
        adr_dir,
        30,
        "self-referential",
        frontmatter="status: superseded\nsuperseded-by: ADR-030",
        body=_standard_body(30, "Self Referential"),
    )

    retired = _section(_render(adr_dir), "Retired")
    row = next(line for line in retired.splitlines() if "ADR-030" in line and "|" in line)

    assert "cycle, unresolved (ADR-030 -> ADR-030)" in row


def test_cycle_reached_through_a_tail_closes_on_the_real_cycle_not_the_entry(
    tmp_path: Path,
) -> None:
    """A record that only leads into a cycle must not be shown as part of it.

    ADR-040 -> ADR-041 -> ADR-042 -> ADR-043 -> ADR-042 is a tail (040, 041)
    feeding into a two-record cycle (042 <-> 043). 040 and 041 are not on the
    cycle: closing their printed loop back on their own id would invent an
    edge (043 -> 040) that does not exist in the frontmatter. The loop must
    close on the node actually revisited, ADR-042 (Cursor Bugbot, PR #5285
    review).
    """
    adr_dir = tmp_path / "architecture"
    _write_adr(
        adr_dir,
        40,
        "tail-alpha",
        frontmatter="status: superseded\nsuperseded-by: ADR-041",
        body=_standard_body(40, "Tail Alpha"),
    )
    _write_adr(
        adr_dir,
        41,
        "tail-beta",
        frontmatter="status: superseded\nsuperseded-by: ADR-042",
        body=_standard_body(41, "Tail Beta"),
    )
    _write_adr(
        adr_dir,
        42,
        "cycle-gamma",
        frontmatter="status: superseded\nsuperseded-by: ADR-043",
        body=_standard_body(42, "Cycle Gamma"),
    )
    _write_adr(
        adr_dir,
        43,
        "cycle-delta",
        frontmatter="status: superseded\nsuperseded-by: ADR-042",
        body=_standard_body(43, "Cycle Delta"),
    )

    retired = _section(_render(adr_dir), "Retired")
    row_40 = next(line for line in retired.splitlines() if line.startswith("| [ADR-040]"))

    assert "cycle, unresolved (ADR-040 -> ADR-041 -> ADR-042 -> ADR-043 -> ADR-042)" in row_40


def test_proposed_row_renders_the_review_by_date(tmp_path: Path) -> None:
    """#5198 specifies the Proposed table carries the condition OR review date.

    `review-by` shipped in ADR-TEMPLATE.md in this campaign and nothing read it.
    A field no consumer reads is the shape ADR-073 warns about, and it is how the
    ADR-002/ADR-039 provisional window sat seven months past due unnoticed.
    """
    adr_dir = tmp_path / "architecture"
    _write_adr(
        adr_dir,
        77,
        "timeboxed",
        frontmatter="status: proposed\nreview-by: 2026-09-27",
        body=_standard_body(77, "Timeboxed"),
    )

    proposed = _section(_render(adr_dir), "Proposed")

    assert "review by 2026-09-27" in proposed


def test_review_by_and_prose_blocker_both_render(tmp_path: Path) -> None:
    adr_dir = tmp_path / "architecture"
    body = _standard_body(87, "Both").replace(
        "## Status\n\nProposed", "## Status\n\nProposed. Awaiting a held-out eval."
    )
    _write_adr(
        adr_dir,
        87,
        "both",
        frontmatter="status: proposed\nreview-by: 2026-10-18",
        body=body,
    )

    proposed = _section(_render(adr_dir), "Proposed")

    assert "review by 2026-10-18" in proposed
    assert "held-out eval" in proposed


def test_proposed_row_without_review_by_is_unchanged(tmp_path: Path) -> None:
    """Negative control: the optional field absent must not alter the old output."""
    adr_dir = tmp_path / "architecture"
    _write_adr(
        adr_dir,
        88,
        "nodate",
        frontmatter="status: proposed",
        body=_standard_body(88, "No Date"),
    )

    proposed = _section(_render(adr_dir), "Proposed")

    assert "review by" not in proposed
    assert "ADR-088" in proposed


def test_review_by_rendering_does_not_read_the_wall_clock(tmp_path: Path) -> None:
    """Determinism guard: a long-past date renders the same as a far-future one.

    The renderer must be byte-identical for identical input. Past-due detection
    belongs in the lifecycle gate, where a test can freeze the clock.
    """

    def render_with(date: str) -> str:
        adr_dir = tmp_path / f"arch-{date}"
        _write_adr(
            adr_dir,
            2,
            "provisional",
            frontmatter=f"status: proposed\nreview-by: {date}",
            body=_standard_body(2, "Provisional"),
        )
        return _section(_render(adr_dir), "Proposed")

    past = render_with("2026-01-17")
    future = render_with("2099-01-17")

    assert past.replace("2026-01-17", "DATE") == future.replace("2099-01-17", "DATE")


# ── Duplicate frontmatter keys must fail loudly, not resolve last-wins ────────
#
# PyYAML keeps the last value and reports nothing, so a record declaring two
# conflicting statuses would be rendered in the index as one of them with no
# indication the other exists. That contradicts this generator's stated
# fail-loud contract for malformed frontmatter. Reported by Copilot on PR #5209.


def test_duplicate_status_key_raises_rather_than_picking_one(tmp_path):
    """The index must not silently choose between two declared statuses."""
    from generate_adr_index import AdrIndexError, build_record

    adr = tmp_path / "ADR-001-thing.md"
    adr.write_text(
        "---\nid: ADR-001\nstatus: proposed\nstatus: accepted\n---\n\n"
        "# ADR-001: Thing\n\n## Decision\n\nDo the thing.\n",
        encoding="utf-8",
    )

    with pytest.raises(AdrIndexError) as excinfo:
        build_record(adr)

    assert "duplicate key" in str(excinfo.value)
    assert "ADR-001-thing.md" in str(excinfo.value)


def test_a_record_without_duplicates_still_builds(tmp_path):
    """Negative control: the strict loader does not reject valid frontmatter.

    A loader that raised on every mapping would pass the test above and be
    indistinguishable from a correct one.
    """
    from generate_adr_index import build_record

    adr = tmp_path / "ADR-001-thing.md"
    adr.write_text(
        "---\nid: ADR-001\nstatus: accepted\ndate: 2026-08-21\n---\n\n"
        "# ADR-001: Thing\n\n## Decision\n\nDo the thing.\n",
        encoding="utf-8",
    )

    assert build_record(adr).status == "accepted"


def test_a_repeated_key_inside_a_nested_mapping_is_also_rejected(tmp_path):
    """The loader hooks the parser, so nesting does not hide a duplicate.

    A line-scanning check would miss this. Recording the difference because it
    is the reason a loader was used here rather than the regex helper
    detect_adr_changes.py carries.
    """
    from generate_adr_index import AdrIndexError, build_record

    adr = tmp_path / "ADR-001-thing.md"
    adr.write_text(
        "---\nid: ADR-001\nstatus: accepted\nmeta:\n  note: a\n  note: b\n---\n\n"
        "# ADR-001: Thing\n\n## Decision\n\nDo the thing.\n",
        encoding="utf-8",
    )

    with pytest.raises(AdrIndexError):
        build_record(adr)


# The documented query recipe --------------------------------------------------


def _documented_recipe() -> str:
    """The python block from the index intro, extracted rather than restated.

    Restating it here would pin the recipe to a copy of itself: the test would
    keep passing while the shipped recipe drifted. `canonical-source-mirror.md`
    names that shape ("self-referential test that mirrors the producer's own
    output") and requires exercising the contract independently instead.
    """
    from generate_adr_index import _INTRO

    opening = "```python\n"
    start = _INTRO.index(opening) + len(opening)
    return _INTRO[start : _INTRO.index("```", start)]


def _accepted_ids_via_recipe(adr_dir: Path) -> list[str]:
    """Run the documented recipe against `adr_dir` and collect what it prints."""
    printed: list[str] = []
    source = _documented_recipe().replace("'.agents/architecture'", repr(str(adr_dir)))
    # exec is the point: the contract under test is that the shipped recipe
    # RUNS and agrees with the generator. Asserting on its text would pin the
    # recipe to a copy of itself. Input is our own module constant, never
    # user data. (No suppression needed; ruff's S rules are not enabled here.)
    exec(
        compile(source, "<documented-recipe>", "exec"),
        {"print": printed.append},
    )
    return printed


def _accepted_ids_via_generator(adr_dir: Path) -> list[str]:
    from generate_adr_index import build_record

    return [
        record.adr_id
        for path in sorted(adr_dir.glob("ADR-[0-9]*.md"))
        if (record := build_record(path)).status == "accepted"
    ]


def test_the_documented_recipe_agrees_with_the_generator_on_lowercase_status(tmp_path):
    """Positive control: the two agree on the shape the corpus actually has."""
    adr_dir = tmp_path / "architecture"
    _write_adr(
        adr_dir,
        1,
        "yes",
        frontmatter="id: ADR-001\nstatus: accepted",
        body=_standard_body(1, "Yes"),
    )
    _write_adr(
        adr_dir, 2, "no", frontmatter="id: ADR-002\nstatus: proposed", body=_standard_body(2, "No")
    )

    assert _accepted_ids_via_recipe(adr_dir) == _accepted_ids_via_generator(adr_dir)
    assert _accepted_ids_via_generator(adr_dir) == ["ADR-001"]


@pytest.mark.parametrize("raw_status", ["Accepted", "ACCEPTED", '" accepted "'])
def test_the_documented_recipe_agrees_with_the_generator_on_odd_casing(tmp_path, raw_status):
    """The case Copilot found: a bare `== 'accepted'` misses these, this parser does not.

    `_status_of` (`build/scripts/generate_adr_index.py:285-...`, this
    module's own contract, not a mirror of `check_adr_lifecycle.py`, which
    does not exist in this branch: citation removed per Copilot, PR #5285
    review) lower-cases and strips the raw frontmatter value before
    validating it against the enum, so `status: Accepted` is bucketed as
    accepted. A recipe comparing the raw value would print nothing and read
    as "no accepted ADRs" rather than as a query bug.

    This test fails against the recipe as first shipped, on all three inputs.
    Every record in the real corpus carries a lowercase value, which is why the
    mismatch was latent and had to be found by reading rather than by running.

    The whitespace case is quoted on purpose. An unquoted `status: accepted `
    is NOT a discriminating input: YAML strips a trailing space from a plain
    scalar, so the old recipe passed it too, and a probe that cannot move the
    thing it measures reports nothing while looking like a control. Quoting
    forces the space through the parser so `.strip()` is actually load-bearing.
    """
    adr_dir = tmp_path / "architecture"
    _write_adr(
        adr_dir,
        1,
        "odd",
        frontmatter=f"id: ADR-001\nstatus: {raw_status}",
        body=_standard_body(1, "Odd"),
    )

    assert _accepted_ids_via_generator(adr_dir) == ["ADR-001"]
    assert _accepted_ids_via_recipe(adr_dir) == ["ADR-001"]


def test_the_documented_recipe_skips_a_record_with_no_frontmatter(tmp_path):
    """Negative control for the `continue` the intro tells readers to notice."""
    adr_dir = tmp_path / "architecture"
    _write_adr(adr_dir, 1, "bare", frontmatter=None, body=_standard_body(1, "Bare"))

    assert _accepted_ids_via_recipe(adr_dir) == []


def test_the_documented_recipe_agrees_with_the_generator_on_a_padded_closing_fence(tmp_path):
    """Copilot's line-643 finding: the recipe's fence search does not require
    the closing delimiter to occupy its own line, unlike `_FRONTMATTER_RE`.

    `_FRONTMATTER_RE` is ``r"^---\\r?\\n([\\s\\S]*?)\\r?\\n---\\r?\\n([\\s\\S]*)$"``
    (generate_adr_index.py, module scope): the closing fence must be exactly
    three dashes immediately followed by `\\r?\\n`, nothing else. A closing
    line with one trailing space, ``"--- \\n"`` instead of ``"---\\n"``, fails
    that match. `parse_frontmatter` then finds no closing fence anywhere
    (the trailing-space line does not qualify, and there is no other), so it
    raises `AdrIndexError` for "opens with '---' but has no closing '---'
    fence" (the same branch the already-documented "unterminated frontmatter"
    paragraph above describes; this is a padded fence, not an absent one, but
    the real parser treats both as the identical defect).

    The recipe as first shipped used ``text.index('\\n---', 3)``, which finds
    ANY "\\n---" substring, trailing space or not, and slices there with no
    error. Against this fixture the old recipe printed ``['ADR-001']`` with
    no sign anything was wrong, silently disagreeing with the generator's
    correctly-loud rejection of the same file. This test fails against the
    recipe as first shipped for that reason: it asserts the recipe raises
    too, matching `AdrIndexError`, rather than asserting on a return value
    the old recipe could satisfy by accident.
    """
    from generate_adr_index import AdrIndexError

    adr_dir = tmp_path / "architecture"
    adr_dir.mkdir(parents=True)
    (adr_dir / "ADR-001-padded.md").write_text(
        "---\nid: ADR-001\nstatus: accepted\n--- \n"
        "# ADR-001: Padded\n\n## Decision\n\nDo it.\n",
        encoding="utf-8",
    )

    with pytest.raises(AdrIndexError):
        _accepted_ids_via_generator(adr_dir)

    with pytest.raises(ValueError):
        _accepted_ids_via_recipe(adr_dir)


# Unhashable YAML keys -------------------------------------------------------


def test_an_unhashable_key_raises_inside_the_error_contract(tmp_path):
    """`? [a, b]` builds a list key. It must not escape as a raw TypeError.

    The duplicate guard first kept keys in a set, which raises `TypeError` on an
    unhashable key. It caught that around the membership test only, under a
    `# pragma: no cover - unhashable keys are not valid here` comment asserting
    the case was unreachable. It is reachable, so `seen.add(key)` raised the same
    TypeError one line later, past `parse_frontmatter`'s YAMLError conversion
    and past `main`'s exit-code handling: a traceback instead of the documented
    exit 1. Copilot found it on PR #5230.
    """
    from generate_adr_index import AdrIndexError, build_record

    adr = tmp_path / "ADR-001-thing.md"
    adr.write_text(
        "---\n? [a, b]\n: value\nstatus: accepted\n---\n\n"
        "# ADR-001: Thing\n\n## Decision\n\nDo the thing.\n",
        encoding="utf-8",
    )

    with pytest.raises(AdrIndexError):
        build_record(adr)


def test_a_duplicated_unhashable_key_is_caught_as_a_duplicate(tmp_path):
    """The set-based guard could not have caught this; the list-based one does.

    With `except TypeError: duplicate = False`, an unhashable key was declared
    not-a-duplicate by construction, so a repeated one was never reported. `==`
    is defined for every constructed value, so the comparison both works and
    never raises.
    """
    from generate_adr_index import AdrIndexError, build_record

    adr = tmp_path / "ADR-001-thing.md"
    adr.write_text(
        "---\n? [a, b]\n: one\n? [a, b]\n: two\n---\n\n"
        "# ADR-001: Thing\n\n## Decision\n\nDo the thing.\n",
        encoding="utf-8",
    )

    with pytest.raises(AdrIndexError):
        build_record(adr)


@pytest.mark.parametrize(
    "first_line", ['"status": proposed', "'status': proposed", "status : proposed"]
)
def test_quoting_does_not_launder_a_duplicate_past_the_strict_loader(tmp_path, first_line):
    """Parser-level detection sees one key regardless of how it is spelled."""
    from generate_adr_index import AdrIndexError, build_record

    adr = tmp_path / "ADR-001-thing.md"
    adr.write_text(
        f"---\nid: ADR-001\n{first_line}\nstatus: accepted\n---\n\n"
        "# ADR-001: Thing\n\n## Decision\n\nDo the thing.\n",
        encoding="utf-8",
    )

    with pytest.raises(AdrIndexError):
        build_record(adr)
