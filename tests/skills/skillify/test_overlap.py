"""Overlap scan: PATCH at 70 percent coverage, CREATE below it."""

from __future__ import annotations

import pytest
import skillify
from skill_fixtures import make_skill

WORKFLOW = {
    "actions": ["read transcript", "extract action items", "write meeting notes"],
    "terms": ["meeting"],
    "trigger_phrase": "ingest a meeting transcript",
}


def test_recommends_patch_when_existing_skill_covers_workflow(tmp_path, skills_root):
    make_skill(
        skills_root,
        "meeting-ingest",
        description="Read a meeting transcript, extract action items, write meeting notes.",
    )
    make_skill(skills_root, "unrelated", description="Rotate database credentials.")
    result = skillify.evaluate_overlap(WORKFLOW, [skills_root])
    assert result["status"] == "PATCH"
    assert result["skill"] == "meeting-ingest"
    assert result["matches"][0]["coverage"] >= 0.7
    assert result["scanned"] == 2


def test_recommends_create_when_nothing_overlaps(skills_root):
    make_skill(skills_root, "unrelated", description="Rotate database credentials.")
    result = skillify.evaluate_overlap(WORKFLOW, [skills_root])
    assert result["status"] == "CREATE"
    assert result["skill"] is None
    assert result["path"] is None


def test_create_when_no_skills_exist(skills_root):
    result = skillify.evaluate_overlap(WORKFLOW, [skills_root])
    assert result["status"] == "CREATE"
    assert result["matches"] == []
    assert result["scanned"] == 0


def test_threshold_is_inclusive_at_seventy_percent(skills_root):
    make_skill(
        skills_root, "seven", description="alpha beta gamma delta epsilon zeta eta", trigger="qq"
    )
    ten_terms = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
    result = skillify.evaluate_overlap({"terms": [ten_terms]}, [skills_root])
    assert result["workflow_terms"] == 10
    assert result["matches"][0]["hits"] == 7
    assert result["status"] == "PATCH"


def test_just_under_threshold_creates(skills_root):
    make_skill(skills_root, "partial", description="alpha beta gamma delta", trigger="zz")
    terms = {"terms": ["alpha beta gamma delta epsilon zeta eta theta iota kappa"]}
    result = skillify.evaluate_overlap(terms, [skills_root])
    assert result["matches"][0]["hits"] == 4
    assert result["status"] == "CREATE"


def test_triggers_section_counts_toward_coverage(skills_root):
    make_skill(
        skills_root,
        "by-trigger",
        description="Misc helper.",
        trigger="ingest meeting transcript action items notes",
    )
    result = skillify.evaluate_overlap(
        {"terms": ["ingest meeting transcript action items notes"]}, [skills_root]
    )
    assert result["status"] == "PATCH"


def test_scans_every_root_and_reports_missing_roots(tmp_path, skills_root):
    other = tmp_path / "other"
    other.mkdir()
    make_skill(other, "meeting-ingest", description="Ingest a meeting transcript into notes.")
    absent = tmp_path / "absent"
    result = skillify.evaluate_overlap(WORKFLOW, [skills_root, other, absent])
    assert result["missing_roots"] == [str(absent)]
    assert result["scanned"] == 1


def test_skips_skills_without_frontmatter_name(skills_root):
    make_skill(skills_root, "broken", body="# no frontmatter\n")
    result = skillify.evaluate_overlap(WORKFLOW, [skills_root])
    assert len(result["skipped"]) == 1
    assert result["scanned"] == 0


def test_skips_unreadable_skill_file(skills_root):
    directory = skills_root / "binary"
    directory.mkdir()
    (directory / "SKILL.md").write_bytes(b"\xff\xfe\x00bad")
    result = skillify.evaluate_overlap(WORKFLOW, [skills_root])
    assert len(result["skipped"]) == 1


def test_matches_capped_and_sorted_by_hits_then_name(skills_root):
    for index in range(7):
        make_skill(skills_root, f"s{index}", description="meeting notes", trigger="q")
    result = skillify.evaluate_overlap({"terms": ["meeting notes"]}, [skills_root])
    assert len(result["matches"]) == skillify.TOP_MATCHES
    names = [m["name"] for m in result["matches"]]
    assert names == sorted(names)


def test_crlf_and_folded_description_are_parsed(skills_root):
    text = (
        "---\r\nname: folded\r\ndescription: >-\r\n  Ingest a meeting\r\n  transcript.\r\n---\r\n"
        "\r\n## Triggers\r\n\r\n- ingest\r\n"
    )
    make_skill(skills_root, "folded", body=text)
    result = skillify.evaluate_overlap({"terms": ["ingest meeting transcript"]}, [skills_root])
    assert result["status"] == "PATCH"


def test_tokenize_drops_stopwords_short_words_and_folds_plural():
    assert skillify.tokenize("The notes AND an ox, status") == frozenset({"note", "status"})


@pytest.mark.parametrize(
    "workflow",
    [
        [],
        {"actions": "read"},
        {"terms": [1]},
        {"trigger_phrase": 3},
        {"terms": []},
        {"terms": ["a to of"]},
    ],
)
def test_bad_workflow_raises(workflow, skills_root):
    with pytest.raises(skillify.SkillifyError):
        skillify.evaluate_overlap(workflow, [skills_root])
