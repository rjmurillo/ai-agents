"""Tests for scripts/metrics/sg_prompt_audit_parse.py (#5856, REQ-3).

Prompt classification (classify_prompt), diff/checkout extraction, block and
cap-marker parsing, message-text/usage/structured-output helpers, and
timestamp arithmetic. Split out of the original monolithic
``test_sg_prompt_audit.py`` under the taste-lints file-size gate; fixture
prompt builders live in ``tests/metrics/sg_prompt_audit_helpers.py``.
"""

from __future__ import annotations

import hashlib

import pytest

from scripts.metrics import sg_prompt_audit_parse as parse_mod
from scripts.metrics.sg_prompt_audit_models import UsageTotals
from tests.metrics.sg_prompt_audit_helpers import (
    CHANGED_FILES,
    USAGE_1,
    USAGE_2,
    assistant_entry,
    diff_text,
    investigate_prompt,
    iter2_prompt,
    refute_prompt,
)

# --- classify_prompt ----------------------------------------------------------


def test_classify_prompt_detects_investigate() -> None:
    text = investigate_prompt(diff_text([("a.py", "+x\n")]))
    assert parse_mod.classify_prompt(text) == "investigate"


def test_classify_prompt_detects_iter2() -> None:
    text = iter2_prompt(diff_text([("a.py", "+x\n")]))
    assert parse_mod.classify_prompt(text) == "iter2"


def test_classify_prompt_detects_refute() -> None:
    text = refute_prompt(diff_text([("a.py", "+x\n")]))
    assert parse_mod.classify_prompt(text) == "refute"


def test_classify_prompt_returns_none_for_unrelated_text() -> None:
    assert parse_mod.classify_prompt("Please summarize this repository.") is None


# --- diff/checkout extraction --------------------------------------------------


def test_extract_diff_recovers_exact_content_for_investigate() -> None:
    diff = diff_text([("a.py", "+line one\n+line two\n")])
    text = investigate_prompt(diff)
    body, checkout_note = parse_mod.extract_diff_and_checkout(text, "investigate")
    assert body == diff
    assert checkout_note is False


def test_extract_diff_stops_before_iter2_suffix_not_at_prior_reviewer_marker() -> None:
    """Regression: the iter2 diff body ends at the SAME terminator as
    investigate ("\\n\\nInvestigate per the method"), not at
    "\\n\\n---\\n\\nA prior reviewer" (verified against llm.py and a real
    transcript; see sg_prompt_audit_parse.py's module docstring).
    """
    diff = diff_text([("a.py", "+line one\n")])
    text = iter2_prompt(diff)
    body, _ = parse_mod.extract_diff_and_checkout(text, "iter2")
    assert body == diff
    assert "Investigate per the method" not in body
    assert "A prior reviewer" not in body


def test_extract_diff_flags_checkout_note_when_present() -> None:
    diff = diff_text([("a.py", "+x\n")])
    text = investigate_prompt(diff, checkout_note=True)
    _, checkout_note = parse_mod.extract_diff_and_checkout(text, "investigate")
    assert checkout_note is True


def test_extract_diff_returns_empty_body_when_diff_header_missing() -> None:
    text = "Review this change for security vulnerabilities.\n\nno diff header here"
    body, checkout_note = parse_mod.extract_diff_and_checkout(text, "investigate")
    assert body == ""
    assert checkout_note is False


def test_extract_diff_falls_back_to_end_of_text_when_terminator_missing() -> None:
    text = (
        "Review this change for security vulnerabilities.\n\n"
        + CHANGED_FILES
        + "\n\nUnified diff (only + lines are new):\n\n"
        + "+trailing content with no terminator"
    )
    body, _ = parse_mod.extract_diff_and_checkout(text, "investigate")
    assert body == "+trailing content with no terminator"


def test_extract_diff_refute_recovers_exact_content() -> None:
    diff = diff_text([("a.py", "+x\n")])[:8000]
    text = refute_prompt(diff)
    body, checkout_note = parse_mod.extract_diff_and_checkout(text, "refute")
    assert body == diff
    assert checkout_note is False


def test_extract_diff_refute_returns_empty_when_header_missing() -> None:
    text = "You previously flagged these candidate vulnerabilities:\n\nno diff header"
    body, _ = parse_mod.extract_diff_and_checkout(text, "refute")
    assert body == ""


def test_extract_diff_refute_falls_back_to_end_of_text_when_terminator_missing() -> None:
    text = "You previously flagged these candidate vulnerabilities:\n\n[]\n\nDIFF:\n+no terminator"
    body, _ = parse_mod.extract_diff_and_checkout(text, "refute")
    assert body == "+no terminator"


# --- blocks and caps ------------------------------------------------------------


def test_extract_blocks_returns_empty_list_when_no_markers() -> None:
    assert parse_mod.extract_blocks("plain diff text, no markers") == []


def test_extract_blocks_recovers_each_files_exact_content_in_order() -> None:
    files = [("a.py", "+A one\n+A two\n"), ("b.py", "+B one\n")]
    diff = diff_text(files)
    blocks = parse_mod.extract_blocks(diff)
    assert [b.path for b in blocks] == ["a.py", "b.py"]
    for (_path, content), block in zip(files, blocks, strict=True):
        payload = content.encode("utf-8")
        assert block.bytes == len(payload)
        assert block.sha256 == hashlib.sha256(payload).hexdigest()


def test_count_caps_counts_zero_when_absent() -> None:
    caps = parse_mod.count_caps("plain diff, nothing capped")
    assert caps.per_file_truncated == 0
    assert caps.total_truncated == 0
    assert caps.omitted == 0


def test_count_caps_counts_each_marker_including_repeats() -> None:
    body = (
        "a [truncated by security-guidance: file exceeds per-file byte cap] "
        "b [truncated by security-guidance: file exceeds per-file byte cap] "
        "c [truncated by security-guidance: total diff byte cap reached] "
        "d [omitted by security-guidance: total diff byte cap reached]"
    )
    caps = parse_mod.count_caps(body)
    assert caps.per_file_truncated == 2
    assert caps.total_truncated == 1
    assert caps.omitted == 1


# --- message text / usage / structured output -----------------------------------


def test_extract_message_text_handles_plain_string() -> None:
    assert parse_mod.extract_message_text("hello") == "hello"


def test_extract_message_text_handles_list_of_text_items() -> None:
    content = [{"type": "text", "text": "hello "}, {"type": "text", "text": "world"}]
    assert parse_mod.extract_message_text(content) == "hello world"


def test_extract_message_text_ignores_non_text_items() -> None:
    content = [{"type": "tool_use", "name": "Read"}]
    assert parse_mod.extract_message_text(content) == ""


def test_extract_message_text_ignores_text_item_with_non_string_text_field() -> None:
    content = [{"type": "text", "text": None}, {"type": "text", "text": "kept"}]
    assert parse_mod.extract_message_text(content) == "kept"


def test_extract_message_text_returns_empty_for_unexpected_shape() -> None:
    assert parse_mod.extract_message_text(None) == ""
    assert parse_mod.extract_message_text(42) == ""


def test_has_structured_output_true_when_tool_use_present() -> None:
    entry = assistant_entry("2026-09-20T00:00:00Z", tool_names=("Read", "StructuredOutput"))
    assert parse_mod.has_structured_output(entry) is True


def test_has_structured_output_false_when_absent() -> None:
    entry = assistant_entry("2026-09-20T00:00:00Z", tool_names=("Read",))
    assert parse_mod.has_structured_output(entry) is False


def test_has_structured_output_false_when_content_not_a_list() -> None:
    entry = {"type": "assistant", "message": {"content": "not a list"}}
    assert parse_mod.has_structured_output(entry) is False


def test_has_structured_output_false_when_message_missing() -> None:
    assert parse_mod.has_structured_output({"type": "assistant"}) is False


def test_usage_from_entry_reads_all_four_fields() -> None:
    entry = assistant_entry("2026-09-20T00:00:00Z", usage=USAGE_1)
    usage = parse_mod.usage_from_entry(entry)
    assert usage == UsageTotals(**USAGE_1)


def test_usage_from_entry_treats_missing_or_null_fields_as_zero() -> None:
    entry = {
        "type": "assistant",
        "message": {"content": [], "usage": {"input_tokens": None}},
    }
    usage = parse_mod.usage_from_entry(entry)
    assert usage == UsageTotals(0, 0, 0, 0)


def test_usage_from_entry_handles_missing_usage_object() -> None:
    entry = {"type": "assistant", "message": {"content": []}}
    assert parse_mod.usage_from_entry(entry) == UsageTotals(0, 0, 0, 0)


def test_add_usage_sums_field_by_field() -> None:
    total = parse_mod.add_usage(UsageTotals(**USAGE_1), UsageTotals(**USAGE_2))
    assert total == UsageTotals(300, 11, 55, 60)


# --- timestamps -----------------------------------------------------------------


def test_latency_seconds_computes_delta() -> None:
    delta = parse_mod.latency_seconds(
        "2026-09-20T00:00:00.000Z", "2026-09-20T00:00:05.500Z"
    )
    assert delta == pytest.approx(5.5)


def test_latency_seconds_zero_when_either_timestamp_missing() -> None:
    assert parse_mod.latency_seconds("", "2026-09-20T00:00:00Z") == 0.0
    assert parse_mod.latency_seconds("2026-09-20T00:00:00Z", "") == 0.0


def test_latency_seconds_zero_when_timestamp_unparsable() -> None:
    assert parse_mod.latency_seconds("not-a-timestamp", "2026-09-20T00:00:00Z") == 0.0




# --- diff bodies that quote the prompt's own markers --------------------------

_QUOTED_TAIL = (
    "+    \"\\n\\nInvestigate per the method in your instructions, then return \"\n"
    "\n\nInvestigate per the method in your instructions, then return the findings list.\n"
    "+tail = 1\n"
)


def test_extract_diff_keeps_body_that_quotes_investigate_terminator() -> None:
    diff = diff_text([("a.py", _QUOTED_TAIL)])
    body, _ = parse_mod.extract_diff_and_checkout(investigate_prompt(diff), "investigate")
    assert body == diff


def test_extract_diff_keeps_iter2_body_that_quotes_investigate_terminator() -> None:
    diff = diff_text([("a.py", _QUOTED_TAIL)])
    body, _ = parse_mod.extract_diff_and_checkout(iter2_prompt(diff), "iter2")
    assert body == diff


def test_extract_diff_keeps_refute_body_that_quotes_refute_terminator() -> None:
    diff = diff_text([("a.py", "+x\n\n\nNow adversarially try it\n+y\n")])
    body, _ = parse_mod.extract_diff_and_checkout(refute_prompt(diff), "refute")
    assert body == diff


def test_classify_prompt_ignores_iter2_markers_quoted_inside_the_diff() -> None:
    quoted = (
        "+\"\\n\\n---\\n\\nA prior reviewer already flagged\"\n"
        "\n\n---\n\nA prior reviewer already flagged <excluded_findings>\n"
    )
    text = investigate_prompt(diff_text([("a.py", quoted)]))
    assert parse_mod.classify_prompt(text) == "investigate"


def test_classify_prompt_treats_missing_terminator_as_investigate() -> None:
    text = "Review this change for security vulnerabilities.\n\n<excluded_findings>"
    assert parse_mod.classify_prompt(text) == "investigate"
