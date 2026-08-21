# taste-lint: ignore file-size, one test module per module under test. The 51
# cases are the pos/neg/edge matrix TESTING-RIGOR requires for one contract;
# splitting them hides whether that one contract is fully covered.
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
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import generate_adr_index  # noqa: E402

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
        line
        for line in _section(_render(adr_dir), "Proposed").splitlines()
        if "ADR-002" in line
    )

    assert "Proposed." not in proposed_row


def test_accepted_row_carries_the_frontmatter_date(adr_dir: Path) -> None:
    accepted_row = next(
        line
        for line in _section(_render(adr_dir), "Accepted").splitlines()
        if "ADR-001" in line
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
    record = next(
        r for r in generate_adr_index.collect_records(adr_dir) if r.number == 6
    )

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


def test_non_mapping_frontmatter_exits_non_zero_naming_the_file(
    tmp_path: Path, capsys
) -> None:
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


def test_record_without_an_h1_exits_non_zero_naming_the_file(
    tmp_path: Path, capsys
) -> None:
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
        line
        for line in _section(_render(directory), "Accepted").splitlines()
        if "ADR-013" in line
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
        line
        for line in _section(_render(directory), "Accepted").splitlines()
        if "ADR-015" in line
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
        line
        for line in _section(_render(directory), "Accepted").splitlines()
        if "ADR-018" in line
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

    exit_code = generate_adr_index.main(
        ["--adr-dir", str(directory), "--output", str(output)]
    )

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


def test_check_fails_when_an_adr_changed_without_a_regeneration(
    tmp_path: Path, capsys
) -> None:
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

    generate_adr_index.main(
        ["--adr-dir", str(directory), "--output", str(output), "--check"]
    )

    assert not output.exists()


# The build_all.py registration ----------------------------------------------


def test_build_all_registers_the_adr_index_generator() -> None:
    sys.path.insert(0, str(REPO_ROOT / "build"))
    import build_all

    assert "adr-index" in dict(build_all.GENERATORS)


def test_build_all_owns_the_index_path_for_the_staleness_diff() -> None:
    sys.path.insert(0, str(REPO_ROOT / "build"))
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
        adr_dir, 79, "first",
        frontmatter="status: superseded\nsuperseded-by: ADR-091",
        body=_standard_body(79, "First"),
    )
    _write_adr(
        adr_dir, 91, "second",
        frontmatter="status: superseded\nsuperseded-by: ADR-092",
        body=_standard_body(91, "Second"),
    )
    _write_adr(
        adr_dir, 92, "third",
        frontmatter="status: accepted",
        body=_standard_body(92, "Third"),
    )

    retired = _section(_render(adr_dir), "Retired")
    row = next(line for line in retired.splitlines() if "ADR-079" in line)

    assert "ADR-092-third.md" in row
    assert "via ADR-091" in row


def test_supersession_cycle_terminates_instead_of_hanging(tmp_path: Path) -> None:
    """A cycle must not be discovered by this renderer looping forever.

    check_adr_lifecycle.py reports cycles as violations. The index has to survive
    one long enough for that gate to be read.
    """
    adr_dir = tmp_path / "architecture"
    _write_adr(
        adr_dir, 10, "alpha",
        frontmatter="status: superseded\nsuperseded-by: ADR-011",
        body=_standard_body(10, "Alpha"),
    )
    _write_adr(
        adr_dir, 11, "beta",
        frontmatter="status: superseded\nsuperseded-by: ADR-010",
        body=_standard_body(11, "Beta"),
    )

    retired = _section(_render(adr_dir), "Retired")

    assert "ADR-010" in retired
    assert "ADR-011" in retired


def test_proposed_row_renders_the_review_by_date(tmp_path: Path) -> None:
    """#5198 specifies the Proposed table carries the condition OR review date.

    `review-by` shipped in ADR-TEMPLATE.md in this campaign and nothing read it.
    A field no consumer reads is the shape ADR-073 warns about, and it is how the
    ADR-002/ADR-039 provisional window sat seven months past due unnoticed.
    """
    adr_dir = tmp_path / "architecture"
    _write_adr(
        adr_dir, 77, "timeboxed",
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
        adr_dir, 87, "both",
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
        adr_dir, 88, "nodate",
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
            adr_dir, 2, "provisional",
            frontmatter=f"status: proposed\nreview-by: {date}",
            body=_standard_body(2, "Provisional"),
        )
        return _section(_render(adr_dir), "Proposed")

    past = render_with("2026-01-17")
    future = render_with("2099-01-17")

    assert past.replace("2026-01-17", "DATE") == future.replace("2099-01-17", "DATE")
