"""Tests for scripts/eval/_adr_catch_rate_core.py (issue #5248)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_EVAL_DIR = _REPO / "scripts" / "eval"
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

import _adr_catch_rate_core as core  # noqa: E402

CORPUS_PATH = _REPO / "evals" / "adr-review-catch-rate" / "corpus.json"
PROMPTS_PATH = _REPO / ".claude" / "skills" / "adr-review" / "references" / "agent-prompts.md"


def _raw_entry(**overrides):
    raw = {
        "id": "T01",
        "fix_commit": "f" * 40,
        "base_commit": "b" * 40,
        "doc_path": "docs/adr.md",
        "anchor": "the sky is green",
        "kind": "factual-overclaim",
        "defect": "The sky is blue, not green.",
        "match": {"all_of": [["sky"], ["blue", "colour"]]},
        "topic": ["the sky"],
        "evidence": [],
    }
    raw.update(overrides)
    return raw


def _payload(*entries):
    return {
        "schema_version": 1,
        "selection": {"rule": "every fix commit"},
        "entries": list(entries) or [_raw_entry()],
    }


# --- MatchRule ---------------------------------------------------------------


def test_match_requires_every_group():
    rule = core.MatchRule((("sky",), ("blue", "colour")))
    assert rule.matches("The SKY colour is wrong")


def test_match_fails_when_one_group_is_absent():
    rule = core.MatchRule((("sky",), ("blue",)))
    assert not rule.matches("The sky is fine")


def test_match_is_case_insensitive_on_the_finding():
    assert core.MatchRule((("cwe-269",),)).matches("Trust boundary (CWE-269)")


# --- corpus parsing ----------------------------------------------------------


def test_parse_corpus_accepts_a_valid_payload():
    corpus = core.parse_corpus(_payload())
    assert [e.id for e in corpus.entries] == ["T01"]
    assert corpus.entries[0].match.all_of == (("sky",), ("blue", "colour"))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update(schema_version=2),
        lambda p: p.update(selection={}),
        lambda p: p.update(selection={"rule": ""}),
        lambda p: p.update(entries=[]),
        lambda p: p.update(entries="nope"),
    ],
)
def test_parse_corpus_rejects_bad_envelopes(mutate):
    payload = _payload()
    mutate(payload)
    with pytest.raises(core.CorpusError):
        core.parse_corpus(payload)


def test_parse_corpus_rejects_duplicate_ids():
    with pytest.raises(core.CorpusError, match="unique"):
        core.parse_corpus(_payload(_raw_entry(), _raw_entry()))


@pytest.mark.parametrize("field", core.ENTRY_FIELDS)
def test_parse_entry_requires_every_field(field):
    raw = _raw_entry()
    del raw[field]
    with pytest.raises(core.CorpusError, match="missing field"):
        core.parse_entry(raw)


@pytest.mark.parametrize(
    "match",
    [None, {}, {"all_of": []}, {"all_of": ["sky"]}, {"all_of": [[]]}, {"all_of": [[""]]}],
)
def test_parse_entry_rejects_bad_match_rules(match):
    with pytest.raises(core.CorpusError):
        core.parse_entry(_raw_entry(match=match))


@pytest.mark.parametrize("topic", [None, [], [""], "sky"])
def test_parse_entry_rejects_bad_topics(topic):
    with pytest.raises(core.CorpusError, match="topic"):
        core.parse_entry(_raw_entry(topic=topic))


def test_parse_entry_lowercases_the_topic():
    assert core.parse_entry(_raw_entry(topic=["The SKY"])).topic == ("the sky",)


def test_parse_entry_reads_evidence():
    entry = core.parse_entry(_raw_entry(evidence=[{"path": "a.py", "find": "x", "lines": 3}]))
    assert entry.evidence == (core.Evidence("a.py", "x", 3),)


@pytest.mark.parametrize(
    "evidence",
    [
        [{"path": "a.py"}],
        [{"path": "a.py", "find": "x", "lines": "many"}],
        [{"path": "a", "find": "x", "lines": 0}],
    ],
)
def test_parse_entry_rejects_bad_evidence(evidence):
    with pytest.raises(core.CorpusError):
        core.parse_entry(_raw_entry(evidence=evidence))


def test_load_corpus_reads_a_file(tmp_path):
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps(_payload()), encoding="utf-8")
    assert len(core.load_corpus(path).entries) == 1


def test_load_corpus_reports_missing_and_invalid_files(tmp_path):
    with pytest.raises(core.CorpusError, match="cannot read"):
        core.load_corpus(tmp_path / "absent.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(core.CorpusError, match="cannot read"):
        core.load_corpus(bad)


# --- materialization ---------------------------------------------------------


def _show(files):
    return lambda commit, path: files.get((commit, path))


def test_extract_evidence_returns_lines_from_the_first_hit():
    text = "a\nneedle one\nsecond\nthird\nfourth"
    assert core.extract_evidence(text, "needle", 2) == "needle one\nsecond"


def test_extract_evidence_returns_none_without_a_hit():
    assert core.extract_evidence("a\nb", "zzz", 2) is None


def test_materialize_reads_pre_fix_post_fix_and_evidence():
    entry = core.parse_entry(
        _raw_entry(evidence=[{"path": "src/x.py", "find": "def f", "lines": 2}])
    )
    show = _show(
        {
            ("b" * 40, "docs/adr.md"): "intro the sky is green end",
            ("f" * 40, "docs/adr.md"): "intro the sky is blue end",
            ("b" * 40, "src/x.py"): "pre\ndef f():\n    return 1\n",
        }
    )
    item = core.materialize(entry, show)
    assert "green" in item.base_text and "blue" in item.fixed_text
    assert "def f():" in item.evidence_text and "src/x.py" in item.evidence_text


def test_materialize_rejects_a_missing_anchor():
    entry = core.parse_entry(_raw_entry())
    show = _show({("b" * 40, "docs/adr.md"): "nothing here", ("f" * 40, "docs/adr.md"): "x"})
    with pytest.raises(core.CorpusError, match="anchor not found"):
        core.materialize(entry, show)


def test_materialize_names_the_fetch_hint_when_a_commit_is_unreadable():
    entry = core.parse_entry(_raw_entry())
    with pytest.raises(core.CorpusError, match="fetch_hint"):
        core.materialize(entry, _show({}))


def test_materialize_rejects_evidence_that_is_not_in_the_file():
    entry = core.parse_entry(_raw_entry(evidence=[{"path": "x.py", "find": "gone", "lines": 1}]))
    show = _show(
        {
            ("b" * 40, "docs/adr.md"): "the sky is green",
            ("f" * 40, "docs/adr.md"): "fixed",
            ("b" * 40, "x.py"): "other",
        }
    )
    with pytest.raises(core.CorpusError, match="evidence"):
        core.materialize(entry, show)


# --- prompts -----------------------------------------------------------------


@pytest.fixture(scope="module")
def prompts_md():
    return PROMPTS_PATH.read_text(encoding="utf-8")


def test_phase1_prompts_exist_for_all_six_roles(prompts_md):
    prompts = core.parse_phase1_prompts(prompts_md)
    assert set(prompts) == set(core.ROLES)
    for body in prompts.values():
        assert "{adr_content}" in body
        assert "Paste the Factual Claim Verification Block here." in body


def test_claim_block_is_the_verification_block(prompts_md):
    block = core.parse_claim_block(prompts_md)
    assert block.startswith("## Factual Claim Verification (mandatory for every seat)")
    assert "REFUTED" in block


def test_build_user_prompt_fills_text_and_claim_block(prompts_md):
    template = core.parse_phase1_prompts(prompts_md)["critic"]
    prompt = core.build_user_prompt(template, "CLAIM BLOCK", "ADR BODY", "")
    assert "ADR BODY" in prompt and "CLAIM BLOCK" in prompt
    assert "{adr_content}" not in prompt
    assert "no shell, repository, or network access" in prompt
    assert "Repository evidence" not in prompt


def test_build_user_prompt_appends_evidence_for_the_assisted_arm(prompts_md):
    template = core.parse_phase1_prompts(prompts_md)["security"]
    prompt = core.build_user_prompt(template, "CLAIM BLOCK", "ADR BODY", "EXCERPT")
    assert prompt.endswith("EXCERPT")
    assert "read-only extracts" in prompt
    assert "no shell, repository, or network access" not in prompt


def test_build_user_prompt_refuses_a_template_that_lost_its_markers():
    with pytest.raises(core.CorpusError):
        core.build_user_prompt("no markers", "c", "a", "")


def test_strip_frontmatter():
    assert core.strip_frontmatter("---\nrole: x\n---\n\nbody") == "body"
    assert core.strip_frontmatter("plain") == "plain"
    assert core.strip_frontmatter("---\nunterminated") == "---\nunterminated"


@pytest.mark.parametrize("role", core.ROLES)
def test_every_role_has_a_system_template(role):
    path = _REPO / "templates" / "agents" / f"{role}.shared.md"
    assert core.strip_frontmatter(path.read_text(encoding="utf-8")).strip()


# --- review parsing ----------------------------------------------------------

REVIEW = """\
### Strengths

- Clear problem statement about the sky.

### Weaknesses/Gaps

- The sky colour claim is wrong: it is blue.
  It continues on a second line.
- Unrelated style issue.

### Scope Concerns

- None.

### Questions

1. Who verified the sky?

### Blocking Concerns

| Issue | Priority | Description |
|-------|----------|-------------|
| Sky colour | P0 | The sky is blue, not green |
| Minor | P2 | Wording only |

### Claims Checked

| Claim | Kind | Source read | Result |
|-------|------|-------------|--------|
| Sky is green | count-or-path | none | REFUTED |
| Grass is green | count-or-path | none | UNVERIFIED |
| Water is wet | count-or-path | none | VERIFIED |
"""


def test_parse_review_collects_findings_from_every_flagging_section():
    review = core.parse_review(REVIEW)
    joined = " | ".join(review.flagged)
    assert "It continues on a second line" in joined
    assert "Who verified the sky" in joined
    assert "Wording only" in joined
    assert "Grass is green" not in joined
    assert "Sky is green" in joined
    assert "Clear problem statement" not in joined
    assert "Water is wet" not in joined


def test_unverified_claims_are_not_findings():
    """A no-access review marks nearly every claim UNVERIFIED, so those rows prove nothing."""
    review = core.parse_review(REVIEW)
    assert not any("Grass is green" in row for row in review.flagged + review.blocking)
    assert not any("Water is wet" in row for row in review.flagged + review.blocking)


def test_parse_review_blocking_is_p0_p1_rows_and_refuted_claims():
    review = core.parse_review(REVIEW)
    assert any("Sky colour" in row for row in review.blocking)
    assert any("Sky is green" in row for row in review.blocking)
    assert not any("Wording only" in row for row in review.blocking)
    assert not any("Grass is green" in row for row in review.blocking)


def test_parse_review_of_unstructured_text_is_empty():
    review = core.parse_review("I could not find any problems.")
    assert review.flagged == [] and review.blocking == []


def test_table_separator_rows_are_not_findings():
    review = core.parse_review("### Blocking Concerns\n\n|---|---|---|\n")
    assert review.flagged == []


# --- scoring -----------------------------------------------------------------


def test_score_review_blocked_implies_flagged():
    rule = core.MatchRule((("sky",), ("blue",)))
    outcome = core.score_review(core.parse_review(REVIEW), rule)
    assert outcome.flagged and outcome.blocked
    assert "blue" in outcome.matched.lower()


def test_score_review_flagged_only_when_the_hit_is_a_weakness():
    rule = core.MatchRule((("second line",),))
    outcome = core.score_review(core.parse_review(REVIEW), rule)
    assert outcome.flagged and not outcome.blocked


def test_mentions_topic_looks_at_the_whole_response():
    assert core.mentions_topic("Intro. THE SKY is mentioned only in prose.", ("the sky",))
    assert not core.mentions_topic("Nothing relevant.", ("the sky",))


def test_score_response_reports_match_strength_and_mention():
    rule = core.MatchRule((("sky",), ("blue",)))
    hit = core.score_response(REVIEW, rule, ("the sky",))
    assert hit.flagged and hit.blocked and hit.mentioned
    silent = core.score_response("### Weaknesses/Gaps\n\n- Style only.", rule, ("the sky",))
    assert not silent.flagged and not silent.mentioned


def test_score_review_miss():
    rule = core.MatchRule((("quantum",),))
    outcome = core.score_review(core.parse_review(REVIEW), rule)
    assert not outcome.flagged and not outcome.blocked and outcome.matched == ""


def test_a_hit_must_sit_inside_one_finding():
    rule = core.MatchRule((("wording",), ("sky colour",)))
    assert not core.score_review(core.parse_review(REVIEW), rule).flagged


# --- the shipped corpus ------------------------------------------------------


@pytest.fixture(scope="module")
def shipped():
    return core.load_corpus(CORPUS_PATH)


def test_shipped_corpus_has_a_stated_selection_rule(shipped):
    assert shipped.selection["rule"].startswith("Universe:")
    assert shipped.selection["fetch_hint"].startswith("git fetch origin refs/pull/5181/head")


def test_every_shipped_defect_statement_matches_its_own_rule(shipped):
    """A rule that cannot fire on a correct statement of its defect is broken."""
    broken = [e.id for e in shipped.entries if not e.match.matches(e.defect)]
    assert broken == []


def test_shipped_match_rules_have_no_one_character_alternatives(shipped):
    """One-character alternatives match almost any finding."""
    short = [e.id for e in shipped.entries for g in e.match.all_of for a in g if len(a) < 2]
    assert short == []


def test_shipped_candidates_account_for_every_entry(shipped):
    candidates = shipped.selection["candidates"]
    by_commit = {c["commit"]: c for c in candidates}
    for entry in shipped.entries:
        assert by_commit[entry.fix_commit]["status"] == "included"
        assert entry.id in by_commit[entry.fix_commit]["defects"]
    listed = {d for c in candidates for d in c["defects"]}
    assert listed == {e.id for e in shipped.entries}
    assert shipped.selection["universe_size"] == len(candidates)


def test_every_excluded_candidate_states_a_reason(shipped):
    for candidate in shipped.selection["candidates"]:
        if candidate["status"] == "excluded":
            assert candidate["note"].strip()


def test_shipped_entries_use_full_commit_ids(shipped):
    for entry in shipped.entries:
        assert len(entry.fix_commit) == 40 and len(entry.base_commit) == 40
        assert entry.fix_commit != entry.base_commit
