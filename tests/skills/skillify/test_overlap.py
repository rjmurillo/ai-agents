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
    assert [s["reason"] for s in result["skipped"]] == ["no frontmatter name"]
    assert result["skipped"][0]["path"].endswith("SKILL.md")
    assert result["scanned"] == 0


def test_skips_unreadable_skill_file(skills_root):
    directory = skills_root / "binary"
    directory.mkdir()
    (directory / "SKILL.md").write_bytes(b"\xff\xfe\x00bad")
    result = skillify.evaluate_overlap(WORKFLOW, [skills_root])
    assert [s["reason"] for s in result["skipped"]] == ["unreadable"]


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


def test_procedure_text_counts_toward_coverage(skills_root):
    body = (
        "---\nname: opaque\ndescription: Misc helper.\n---\n\n## Triggers\n\n- go\n\n"
        "## Procedure\n\n1. Read the transcript.\n2. Extract action items.\n"
        "3. Write meeting notes.\n\n## Pitfalls\n\n- unrelated gotcha words\n"
    )
    make_skill(skills_root, "opaque", body=body)
    result = skillify.evaluate_overlap(WORKFLOW, [skills_root])
    assert result["status"] == "PATCH"
    assert result["skill"] == "opaque"


def test_text_outside_triggers_and_procedure_does_not_count(skills_root):
    body = (
        "---\nname: opaque\ndescription: Misc helper.\n---\n\n"
        "## Pitfalls\n\n- read transcript extract action items write meeting notes\n"
    )
    make_skill(skills_root, "opaque", body=body)
    assert skillify.evaluate_overlap(WORKFLOW, [skills_root])["status"] == "CREATE"


def test_too_few_workflow_terms_creates_with_reason(skills_root):
    make_skill(skills_root, "exact", description="alpha beta", trigger="alpha beta")
    result = skillify.evaluate_overlap({"terms": ["alpha beta"]}, [skills_root])
    assert result["status"] == "CREATE"
    assert result["skill"] is None
    assert "at least 3" in result["reason"]
    assert "distinct word" in result["reason"]
    assert result["matches"][0]["coverage"] == 1.0


def test_three_terms_is_enough_to_judge(skills_root):
    make_skill(skills_root, "exact", description="alpha beta gamma", trigger="zz")
    result = skillify.evaluate_overlap({"terms": ["alpha beta gamma"]}, [skills_root])
    assert (result["status"], result["reason"]) == ("PATCH", None)


def test_duplicate_headings_use_first_section(skills_root):
    body = (
        "---\nname: dup\ndescription: Misc.\n---\n\n## Procedure\n\n1. unrelated thing.\n\n"
        "## Procedure\n\n1. Read transcript extract action items write meeting notes.\n"
    )
    make_skill(skills_root, "dup", body=body)
    assert skillify.evaluate_overlap(WORKFLOW, [skills_root])["status"] == "CREATE"


def test_generic_words_alone_do_not_reach_patch(skills_root):
    broad = "skill skills file files write run use verify check"
    make_skill(skills_root, "broad", description=broad, trigger=broad)
    workflow = {"terms": ["skill file write run verify check", "triage flaky test", "bisect"]}
    result = skillify.evaluate_overlap(workflow, [skills_root])
    assert result["status"] == "CREATE"
    assert result["matches"][0]["covered"] == []


@pytest.mark.parametrize("word", ["skill", "skills", "file", "files", "write", "run", "use"])
def test_generic_words_are_not_tokens(word):
    assert skillify.tokenize(word) == frozenset()


STEPS = "1. Read the transcript.\n2. Extract action items.\n3. Write meeting notes.\n"


def host(heading):
    return (
        "---\nname: opaque\ndescription: Misc helper.\n---\n\n## Triggers\n\n- go\n\n"
        f"## {heading}\n\n{STEPS}"
    )


@pytest.mark.parametrize(
    "heading", ["Process", "Process Overview", "Process: Progressive Disclosure"]
)
def test_process_section_gives_same_coverage_as_procedure(skills_root, heading):
    make_skill(skills_root, "opaque", body=host(heading))
    got = skillify.evaluate_overlap(WORKFLOW, [skills_root])
    assert got["status"] == "PATCH"
    reference = skills_root.parent / "ref"
    reference.mkdir()
    make_skill(reference, "opaque", body=host("Procedure"))
    want = skillify.evaluate_overlap(WORKFLOW, [reference])
    assert got["matches"][0]["coverage"] == want["matches"][0]["coverage"]


def test_procedure_wins_over_process(skills_root):
    body = host("Process") + "\n## Procedure\n\n1. Unrelated thing.\n"
    make_skill(skills_root, "opaque", body=body)
    assert skillify.evaluate_overlap(WORKFLOW, [skills_root])["status"] == "CREATE"


def test_processing_heading_is_not_a_steps_section(skills_root):
    make_skill(skills_root, "opaque", body=host("Processing Notes"))
    assert skillify.evaluate_overlap(WORKFLOW, [skills_root])["status"] == "CREATE"
