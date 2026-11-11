"""Optional offline smoke test. Install Playwright and its Chromium to run."""

import struct
from pathlib import Path
from typing import Any

import pytest
from render_report import DIFF_CLAMP_PX, render_page


def _write_report(directory: Path) -> Path:
    additions = "".join(f"+新しい手順 {index} 🧪 café <safe>\n" for index in range(80))
    diff = "--- a/SKILL.md\n+++ b/SKILL.md\n@@ -1 +1,80 @@\n-古い手順\n" + additions
    report_path = directory / "report 日本語.html"
    report_path.write_text(
        render_page(
            {
                "handle": "offline-smoke",
                "title": "日本語 🧪 report",
                "scores": {"overall": 0.9},
                "suggestions": [
                    {
                        "skill": "日本語",
                        "change": "更新",
                        "diff": diff,
                        "proposed_path": "proposals/SKILL.md",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return report_path


def _check_diff_expansion(page: Any, expect: Any) -> None:
    view = page.locator("[data-pierre-diff]")
    expect(view).to_have_attribute("data-rendered", "true")
    expect(view.locator(".diff-fallback")).to_have_count(0)
    expect(view.locator("diffs-container")).to_have_count(1)
    expect(view.locator("diffs-container")).to_contain_text("新しい手順 79 🧪 café <safe>")
    expect(view.locator("[data-error-wrapper]")).to_have_count(0)
    wrap = page.locator(".diff-wrap")
    expect(wrap).to_have_attribute("data-overflowing", "true")
    toggle = page.get_by_role("button", name="Show more", exact=True)
    expect(toggle).to_be_visible()
    collapsed_height = view.evaluate("(node) => node.getBoundingClientRect().height")
    assert collapsed_height <= DIFF_CLAMP_PX
    toggle.click()
    expect(wrap).to_have_attribute("data-collapsed", "false")
    expanded_height = view.evaluate("(node) => node.getBoundingClientRect().height")
    assert expanded_height > collapsed_height
    page.get_by_role("button", name="Show less", exact=True).click()
    expect(wrap).to_have_attribute("data-collapsed", "true")
    assert view.evaluate("(node) => node.getBoundingClientRect().height") == collapsed_height
    print(f"diff: Unicode rendered, expanded {collapsed_height}px -> {expanded_height}px")


def test_offline_report_diff_expands_and_share_downloads_png(tmp_path: Path) -> None:
    api = pytest.importorskip("playwright.sync_api", reason="optional browser smoke dependency")
    report_path = _write_report(tmp_path)
    errors, requests = [], []
    with api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            with browser.new_context(offline=True, accept_downloads=True) as context:
                context.route("https://**/*", lambda route: route.abort())
                context.route("http://**/*", lambda route: route.abort())
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("request", lambda outgoing: requests.append(outgoing.url))
                page.on(
                    "console",
                    lambda message: (
                        errors.append(message.text) if message.type == "error" else None
                    ),
                )
                page.goto(report_path.as_uri())
                api.expect(page.get_by_role("link", name="Request access")).to_have_count(0)
                _check_diff_expansion(page, api.expect)
                with page.expect_download() as downloaded:
                    page.get_by_role("button", name="Share", exact=True).click()
                download = downloaded.value
                assert download.failure() is None
                assert download.suggested_filename == "offline-smoke-skill-report.png"
                image = Path(download.path()).read_bytes()
                assert image[:8] == b"\x89PNG\r\n\x1a\n"
                assert image[12:16] == b"IHDR"
                # report_script.py: drawCard(2) exports a 2x 1200x675 canvas.
                assert struct.unpack(">II", image[16:24]) == (2400, 1350)
                assert len(image) > 10_000
                assert requests == [report_path.as_uri()]
                assert errors == []
                print(f"PNG: {download.suggested_filename}, 2400x1350, {len(image)} bytes")
                print("network: only local report requested; page/console errors: 0")
        finally:
            browser.close()
