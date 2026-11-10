"""Structure, accessibility, theme and branding checks for the HTML report."""

import json
import re
from pathlib import Path
from typing import Any

import pytest
import report_evaluation
import report_style
from render_report import render_page

REPO = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "audit"
TEMPLATE = REPO / "templates" / "skills" / "skill-doctor.SKILL.md.tmpl"
VENDOR_STRINGS = ("warp.dev", "Warp Factories", "Request access", "factories", "request-access")


def _candidate(**overrides: Any) -> dict[str, Any]:
    candidate: dict[str, Any] = {
        "skill": "deploy",
        "status": "unevaluated",
        "owner": "skill",
        "target": "/repo/.claude/skills/deploy/SKILL.md",
        "change": "Add a preflight check for the staging token.",
        "evidence": "session abc123: agent retried deploy 4 times without a token",
        "mechanism": "A preflight step makes the missing token visible.",
        "expected_improvement": "One deploy attempt instead of four.",
        "acceptance_checks": ["agent reports the missing token"],
    }
    candidate.update(overrides)
    return candidate


def _report(n_candidates: int = 2, **extra: Any) -> dict[str, Any]:
    report: dict[str, Any] = {
        "title": "Agent Skill Report",
        "generated_at": "2026-11-10T14:05:00Z",
        "harness": "claude",
        "handle": "example",
        "stats": {
            "sessions_analyzed": 3,
            "sessions_scanned": 9,
            "skills_found": 4,
            "skills_used": 2,
        },
        "scores": {
            "efficiency": 0.7,
            "code_quality": 0.8,
            "procedure_compliance": 0.6,
            "verbosity": 0.7,
            "skill_coverage": 0.5,
            "overall": 0.68,
        },
        "top_findings": ["Retried deploy four times."],
        "suggestions": [_candidate(skill=f"skill-{i}") for i in range(n_candidates)],
    }
    report.update(extra)
    return report


def _card_json(page: str) -> str:
    match = re.search(r"var CARD = (\{.*?\});\n", page, re.S)
    assert match is not None
    return match.group(1)


def _audit_report() -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / "report.json").read_text(encoding="utf-8"))
    return data


# Branding


@pytest.mark.parametrize("extra", [{}, {"cta_url": "https://example.invalid/request-access"}])
def test_page_and_share_card_carry_no_vendor_branding(extra: dict[str, Any]) -> None:
    page = render_page(_report(**extra))

    for text in VENDOR_STRINGS:
        assert text.lower() not in page.lower(), text
    assert "example.invalid" not in page
    card = json.loads(_card_json(page).replace("<\\/", "</"))
    assert card["eyebrow"] == "skill-doctor"
    assert "stamp" not in card and "paths" not in card and "viewbox" not in card


def test_page_has_no_remote_references() -> None:
    page = render_page(_report())

    assert not re.search(r'(?:src|href)="https?:', page)
    assert "<link" not in page


def test_skill_template_drops_the_cta_field_and_branding_line() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")

    assert "cta_url" not in text
    assert "request-access" not in text
    assert "retains Warp" not in text
    assert "no vendor branding" in text


def test_pixel_mark_asset_is_gone() -> None:
    assert not (REPO / "src/claude/skills/skill-doctor/assets/warp-pixel-icon.svg").exists()


# Handoff prompts


def test_every_handoff_prompt_has_copy_and_select_all_controls() -> None:
    page = render_page(_report(n_candidates=3))

    assert page.count('class="button-quiet copy-btn"') == 6
    assert page.count('class="button-quiet select-btn"') == 6
    assert page.count('role="status" aria-live="polite"') == 6
    ids = re.findall(r'<pre class="prompt" id="([^"]+)"', page)
    assert len(ids) == 6 and len(set(ids)) == 6
    assert "navigator.clipboard.writeText" in page
    assert "document.execCommand('copy')" in page


def test_prompt_text_is_escaped_inside_the_pre() -> None:
    page = render_page(_report(1, suggestions=[_candidate(skill="<img src=x onerror=1>")]))

    assert "<img src=x" not in page
    assert "&lt;img src=x onerror=1&gt;" in page


# Structure


def _headings(page: str) -> list[tuple[int, str]]:
    return [
        (int(level), re.sub(r"<[^>]+>", "", text).strip())
        for level, text in re.findall(r"<h([1-6])[^>]*>(.*?)</h\1>", page, re.S)
    ]


def test_headings_start_at_h1_then_h2_sections_in_reading_order() -> None:
    page = render_page(_report(sampling={"per_harness": {"claude": {"scoreable": 1}}}))

    headings = _headings(page)
    levels = [level for level, _ in headings]
    assert levels[0] == 1 and levels.count(1) == 1
    assert [t for level, t in headings if level == 2] == [
        "Summary",
        "Findings",
        "Suggested skill changes",
        "Evidence",
    ]
    assert all(b - a <= 1 for a, b in zip(levels, levels[1:], strict=False))


def test_landmarks_and_labelled_sections() -> None:
    page = render_page(_report())

    assert '<html lang="en">' in page
    assert page.count("<header") == 1 and page.count("<main") == 1
    assert "<footer" not in page
    assert '<a class="skip" href="#main">' in page
    for target in re.findall(r'aria-labelledby="([^"]+)"', page):
        assert f'id="{target}"' in page


def test_evaluation_status_sits_in_the_summary_band() -> None:
    report = _report()
    page = render_page(report)

    summary = page.split('<section class="summary"', 1)[1].split("</section>", 1)[0]
    line = report_evaluation.evaluation_summary(report)
    assert 'id="evaluation-status"' in summary
    assert line in summary
    assert "conversations scored" in summary and "skills installed" in summary


def test_candidate_labels_facts_apart_from_hypotheses() -> None:
    page = render_page(_report(1))

    assert page.index("What was observed") < page.index("What is hypothesized, not yet tested")
    assert page.index("Observed (fact)") < page.index("Hypothesis")
    assert 'data-status="unevaluated">unevaluated</span>' in page


def test_empty_states_say_what_happened() -> None:
    page = render_page(_report(0, top_findings=[]))

    assert "No findings were recorded" in page
    assert report_evaluation.EMPTY_STATIC_STATEMENT in page


# Audit reachability and escaping


def test_every_audit_section_is_reachable_in_collapsible_evidence() -> None:
    report = _audit_report()
    page = render_page(report)

    evidence = page.split('id="evidence-h"', 1)[1]
    for name in ("Audit evidence", "Score artifact", "Skill catalog", "Per-conversation evidence"):
        assert f"<summary>{name}</summary>" in evidence, name
    for record in report["audit"]["records"]:
        assert record["session_id"] in evidence


def test_tables_have_captions_scoped_headers_and_scroll_regions() -> None:
    page = render_page(_audit_report())

    tables = page.count("<table>")
    assert tables >= 3
    assert page.count("<caption>") == tables
    assert page.count('<th scope="col">') >= tables * 2
    assert page.count('class="table-scroll" role="region"') == tables


def test_audit_injection_stays_escaped() -> None:
    data = json.loads((FIXTURES / "report_injection.json").read_text(encoding="utf-8"))
    page = render_page(data)

    assert "<img src=x onerror" not in page
    assert page.count("<script>") == 2


# Theme


def _tokens(block: str) -> dict[str, str]:
    return dict(re.findall(r"--([a-z-]+):\s*(#[0-9a-fA-F]{6})", block))


def _theme_blocks() -> tuple[dict[str, str], dict[str, str]]:
    css = report_style.PAGE_CSS
    light = css.split(":root {", 1)[1].split("}", 1)[0]
    dark = css.split("prefers-color-scheme: dark", 1)[1].split("}", 1)[0]
    return _tokens(light), _tokens(dark)


def _luminance(color: str) -> float:
    channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_light_and_dark_token_blocks_define_the_same_tokens() -> None:
    light, dark = _theme_blocks()

    assert set(light) == set(dark)
    assert "color-scheme: light" in report_style.PAGE_CSS
    assert "color-scheme: dark" in report_style.PAGE_CSS
    assert "@media (prefers-color-scheme: dark)" in render_page(_report())


@pytest.mark.parametrize("scheme", [0, 1])
def test_text_tokens_meet_wcag_aa_on_every_surface(scheme: int) -> None:
    tokens = _theme_blocks()[scheme]
    grounds = [tokens[name] for name in ("page-bg", "surface", "panel")]
    for name in ("fg", "muted", "accent"):
        for ground in grounds:
            assert _contrast(tokens[name], ground) >= 4.5, (name, ground)
    pairs = [
        ("accent-fg", "accent"),
        ("notice-fg", "notice-bg"),
        ("ok-fg", "ok-bg"),
        ("bad-fg", "bad-bg"),
    ]
    for fg, bg in pairs:
        assert _contrast(tokens[fg], tokens[bg]) >= 4.5, (fg, bg)


def test_proportional_font_for_prose_and_monospace_for_code() -> None:
    css = report_style.PAGE_CSS

    assert re.search(r"body \{[^}]*var\(--sans-font\)", css)
    assert "code, pre { font-family: var(--mono-font)" in css
    assert "max-width: 70ch" in css


def test_motion_focus_print_and_narrow_screen_rules_exist() -> None:
    page = render_page(_report())

    assert "@media (prefers-reduced-motion: reduce)" in page
    assert ".bar-fill { animation: none; }" in page
    assert ":focus-visible { outline: 2px solid var(--accent)" in page
    assert "@media print" in page
    assert "details::details-content" in page
    assert "beforeprint" in page and "afterprint" in page
    assert 'name="viewport"' in page
    assert "flex-wrap: wrap" in page


def test_field_labels_stay_muted_outside_missing_evidence() -> None:
    import report_style

    css = report_style.PAGE_CSS

    assert ".missing .field-label { color: inherit; }" in css
    assert "\n.field-label { color: inherit; }" not in css


def test_side_by_side_fields_share_a_top_edge() -> None:
    import report_style

    assert ".fields > .field + .field { margin-top: 0; }" in report_style.PAGE_CSS


def test_print_restore_only_reclamps_diffs_it_expanded() -> None:
    import report_script

    script = report_script.page_script("{}", 320)

    assert "unclamped.push(w)" in script
    assert "forEach(function (w) { w.dataset.collapsed = 'true'; })" not in script.replace(
        "unclamped.forEach(function (w) { w.dataset.collapsed = 'true'; })", ""
    )
