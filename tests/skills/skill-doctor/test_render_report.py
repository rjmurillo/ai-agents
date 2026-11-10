#!/usr/bin/env python3
"""Tests for skill-doctor report rendering."""

import base64
import html
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
from functools import partial
from pathlib import Path
from unittest.mock import patch

SKILL_ROOT = Path(__file__).resolve().parents[3] / "src" / "claude" / "skills" / "skill-doctor"

from render_report import (
    embedded_diffs_script,
    format_generated_at,
    main,
    open_report,
    parse_args,
    render_page,
)


def _run_with_browser_stub(command, *, expression, run=subprocess.run, **kwargs):
    command = list(command)
    command[-2] = (
        f"import webbrowser; webbrowser.open = lambda url, new: {expression}; " + command[-2]
    )
    kwargs.pop("errors", None)
    return run(command, errors="replace", **kwargs)


class ReportRendererTests(unittest.TestCase):
    def test_cli_renders_utf8_from_an_unrelated_directory(self):
        for platform in ("claude", "copilot-cli"):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp) / "report \u65e5\u672c\u8a9e #1"
                work.mkdir()
                report_path = work / "report.json"
                report_path.write_text(
                    json.dumps(
                        {
                            "handle": "\u65e5\u672c\u8a9e",
                            "scores": {"overall": 0.9},
                            "top_findings": ["\u65e5\u672c\u8a9e: Escape <not-a-tag>."],
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                script = (
                    SKILL_ROOT.parents[2]
                    / platform
                    / "skills"
                    / "skill-doctor"
                    / "scripts"
                    / "render_report.py"
                )
                result = subprocess.run(
                    [sys.executable, str(script), str(report_path)],
                    cwd=work,
                    env={**os.environ, "PYTHONIOENCODING": "cp1252"},
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn((work / "report.html").as_uri(), result.stdout)
                html = (work / "report.html").read_text(encoding="utf-8")
                self.assertTrue("\u65e5\u672c\u8a9e" in html, "Unicode finding missing.")
                self.assertTrue("&lt;not-a-tag&gt;" in html, "Finding was not escaped.")
                self.assertTrue('class="grade">A-' in html, "Computed grade missing.")
                self.assertTrue("<script src=" not in html, "External script dependency.")

    def test_skill_startup_contract_is_centralized(self):
        skill_root = SKILL_ROOT
        skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        harness_text = (skill_root / "references" / "supported-harnesses.md").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "$SKILL_ROOT/references/supported-harnesses.md",
            skill_text,
        )
        self.assertIn("Conversations in this repository", skill_text)
        self.assertIn("All conversations", skill_text)
        self.assertIn("Choose projects to analyze", skill_text)
        self.assertIn(
            "Project skills + global skills",
            skill_text,
        )
        self.assertIn("Project skills only", skill_text)
        self.assertIn(
            "Process datasets of 50 transcripts or fewer in a single batch",
            skill_text,
        )
        self.assertIn(
            "For datasets with more than 50 transcripts, use parallel batches "
            "(20 transcripts per batch recommended)",
            skill_text,
        )
        self.assertNotIn("--harness claude|codex|warp", skill_text)
        self.assertNotIn("--claude-home PATH", skill_text)
        self.assertIn("| Warp | `warp` |", harness_text)
        self.assertIn("| Claude Code | `claude` |", harness_text)
        self.assertIn("| Codex | `codex` |", harness_text)
        self.assertIn("stop before creating a report directory", harness_text)

    def test_skill_scores_verbosity_and_procedure_compliance(self):
        skill_root = SKILL_ROOT
        skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        procedure_text = (skill_root / "scorers" / "procedure-compliance.md").read_text(
            encoding="utf-8"
        )
        verbosity_text = (skill_root / "scorers" / "verbosity.md").read_text(encoding="utf-8")

        self.assertIn(
            "$SKILL_ROOT/scorers/procedure-compliance.md",
            skill_text,
        )
        self.assertIn("$SKILL_ROOT/scorers/verbosity.md", skill_text)
        self.assertIn("raw_procedure_compliance", skill_text)
        self.assertIn("raw_verbosity", skill_text)
        self.assertIn(
            "A conversation fails when at least one applicable efficiency, "
            "code-quality, procedure-compliance, or verbosity score is below "
            "`0.5`",
            skill_text,
        )
        self.assertIn("name: Procedure Compliance", procedure_text)
        self.assertIn("name: Verbosity", verbosity_text)

        page = render_page(
            {
                "scores": {
                    "efficiency": 1.0,
                    "code_quality": 0.9,
                    "procedure_compliance": 0.8,
                    "verbosity": 0.7,
                    "skill_coverage": 0.6,
                    "overall": 0.83,
                },
            }
        )
        self.assertIn("Procedure Compliance", page)
        self.assertIn("Verbosity", page)

    def test_code_diffs_follow_os_theme(self):
        bundle = embedded_diffs_script()

        self.assertIn('themeType:"system"', bundle)
        self.assertIn(
            'theme:{dark:"pierre-dark",light:"pierre-light"}',
            bundle,
        )

    def test_report_follows_os_theme(self):
        page = render_page(
            {
                "scores": {
                    "efficiency": 1.0,
                    "code_quality": 1.0,
                    "skill_coverage": 1.0,
                    "overall": 1.0,
                },
            }
        )

        self.assertIn('<meta name="color-scheme" content="light dark">', page)
        self.assertIn("@media (prefers-color-scheme: dark)", page)
        self.assertIn("--page-bg: #0f0d14", page)
        self.assertIn("background: var(--surface)", page)
        self.assertIn(
            "--mono-font: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
            page,
        )
        self.assertIn("--diffs-font-family: var(--mono-font)", page)
        self.assertIn("--diffs-header-font-family: var(--mono-font)", page)

    def test_factories_footer_is_sticky_and_contains_inline_cta(self):
        report = {
            "title": "Agent Skill Report",
            "generated_at": "2026-08-25T00:00:00Z",
            "harness": "codex",
            "handle": "example",
            "stats": {
                "sessions_analyzed": 1,
                "sessions_scanned": 1,
                "skills_found": 1,
                "skills_used": 1,
                "window_days": 45,
            },
            "scores": {
                "efficiency": 1.0,
                "code_quality": 1.0,
                "skill_coverage": 1.0,
                "overall": 1.0,
            },
            "top_findings": ["No material waste detected."],
            "suggestions": [],
            "cta_url": "https://warp.dev/factories/request-access",
        }

        page = render_page(report)

        self.assertNotIn("Do this automatically with Warp Factories", page)
        self.assertIn('<div class="stamp-row row factories-footer">', page)
        self.assertIn(
            '<div class="stamp-name">Automatically improve your skills with Warp Factories</div>',
            page,
        )
        self.assertIn(">Request access</a>", page)
        self.assertIn(".factories-footer { position: sticky; bottom: 16px;", page)
        self.assertNotIn("all analysis ran locally", page)
        self.assertIn(
            "Generated August 25, 2026 at 12:00 AM UTC &middot; harness: codex",
            page,
        )

    def test_generated_timestamp_formatting(self):
        self.assertEqual(
            format_generated_at("2026-08-27T22:06:10.421941+00"),
            "August 27, 2026 at 10:06 PM UTC",
        )
        self.assertEqual(format_generated_at("not-a-date"), "not-a-date")

    def test_open_report_uses_default_browser_with_file_uri(self):
        report_path = Path("/tmp/skill 日本語 #1/report.html")
        args = parse_args([str(report_path), "--open"])

        self.assertEqual(args.report_path, str(report_path))
        self.assertTrue(args.open_browser)

        with patch("render_report.subprocess.run") as launch:
            launch.return_value.returncode = 0
            self.assertTrue(open_report(report_path))

        command = launch.call_args.args[0]
        self.assertEqual(command[:5], [sys.executable, "-I", "-X", "utf8", "-c"])
        self.assertEqual(command[-1], report_path.absolute().as_uri())
        self.assertIn("new=2", command[-2])
        options = launch.call_args.kwargs
        self.assertGreater(options["timeout"], 0)
        self.assertLessEqual(options["timeout"], 5)
        self.assertEqual(options["stdin"], subprocess.DEVNULL)
        self.assertIs(options["stdout"], options["stderr"])
        self.assertNotEqual(options["stdout"], subprocess.PIPE)
        self.assertEqual(options["stdout"].encoding, "utf-8")
        self.assertTrue(options["stdout"].closed)
        self.assertEqual(options["errors"], "replace")
        self.assertFalse(options.get("shell", False))

    def test_open_report_returns_false_for_launch_failures(self):
        failures = [
            OSError("launch failed"),
            subprocess.TimeoutExpired("browser", 5),
        ]
        for failure in failures:
            with (
                self.subTest(failure=failure),
                patch("render_report.subprocess.run", side_effect=failure),
            ):
                self.assertFalse(open_report(Path("report.html")))
        with patch("render_report.subprocess.run") as launch:
            launch.return_value.returncode = 1
            self.assertFalse(open_report(Path("report.html")))

    def test_real_browser_child_is_bounded_and_output_is_isolated(self):
        report_path = Path("日本語 #1/report.html")
        expressions = [
            (f"url == {report_path.absolute().as_uri()!r} and new == 2", True),
            ("(print('日本語 🧪'), print('café', file=__import__('sys').stderr), True)[2]", True),
            ("False", False),
            ("(_ for _ in ()).throw(__import__('webbrowser').Error('failed'))", False),
            ("__import__('time').sleep(30)", False),
        ]
        for expression, expected in expressions:
            stdout, stderr = io.StringIO(), io.StringIO()
            started = time.monotonic()
            with (
                self.subTest(expression=expression),
                patch("render_report.BROWSER_TIMEOUT_SECONDS", 0.5),
                patch(
                    "render_report.subprocess.run",
                    side_effect=partial(_run_with_browser_stub, expression=expression),
                ),
                patch("sys.stdout", stdout),
                patch("sys.stderr", stderr),
            ):
                self.assertEqual(open_report(report_path), expected)
            self.assertLess(time.monotonic() - started, 3)
            self.assertEqual((stdout.getvalue(), stderr.getvalue()), ("", ""))

    def test_cli_warns_only_for_requested_failed_launch(self):
        cases = [
            (False, 1),
            (True, 1),
            (True, 0),
            (True, OSError("launch failed")),
            (True, subprocess.TimeoutExpired("browser", 5)),
        ]
        for requested, code in cases:
            with self.subTest(requested=requested, code=code), tempfile.TemporaryDirectory() as tmp:
                report_path = Path(tmp) / "report.json"
                report_path.write_text('{"scores": {"overall": 0.9}}', encoding="utf-8")
                stdout, stderr = io.StringIO(), io.StringIO()
                argv = [str(report_path)] + (["--open"] if requested else [])
                with (
                    patch("render_report.subprocess.run") as launch,
                    patch("sys.stdout", stdout),
                    patch("sys.stderr", stderr),
                ):
                    launch.return_value.returncode = code
                    launch.side_effect = code if isinstance(code, Exception) else None
                    self.assertIsNone(main(argv))
                self.assertEqual(launch.call_count, int(requested))
                self.assertTrue((Path(tmp) / "report.html").is_file())
                self.assertIn("report:", stdout.getvalue())
                self.assertEqual("warning:" in stderr.getvalue(), requested and code != 0)
                self.assertEqual("opened in" in stdout.getvalue(), requested and code == 0)

    def test_cta_destination_cannot_be_overridden_by_report_data(self):
        destinations = [
            "javascript:alert(1)",
            "JaVaScRiPt:alert(1)",
            "\tjavascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "//evil.example",
            "https://warp.dev.evil.example/factories/request-access",
            "https://warp.dev@evil.example/",
            "https://warp.dev/factories/request-access",
            None,
        ]
        for destination in destinations:
            with self.subTest(destination=destination):
                page = render_page({"scores": {"overall": 0.9}, "cta_url": destination})
                links = re.findall(r'<a class="cta-button" href="([^"]+)">', page)
                self.assertEqual(links, ["https://warp.dev/factories/request-access"])

    def test_nonempty_unicode_proposal_diff_round_trips_and_escapes(self):
        diff = (
            "--- a/SKILL.md\n+++ b/SKILL.md\n@@ -1 +1 @@\n"
            "-古い手順\n+新しい手順 🧪 <script>alert('x')</script> & café\n"
        )
        page = render_page(
            {
                "scores": {"overall": 0.9},
                "suggestions": [
                    {
                        "skill": "日本語",
                        "change": "更新",
                        "diff": diff,
                        "proposed_path": 'proposals/日本語 "test".md',
                    }
                ],
            }
        )
        encoded = re.search(r'data-diff="([^"]+)"', page).group(1)
        self.assertEqual(base64.b64decode(encoded).decode("utf-8"), diff)
        fallback = re.search(r'<pre class="diff-fallback">(.*?)</pre>', page, re.S).group(1)
        self.assertEqual(html.unescape(fallback), diff)
        self.assertNotIn("<script>", fallback)
        self.assertIn('data-filename="日本語 &quot;test&quot;.md"', page)

    def test_share_card_uses_skill_doctor_attribution(self):
        page = render_page(
            {
                "scores": {
                    "efficiency": 1.0,
                    "code_quality": 1.0,
                    "skill_coverage": 1.0,
                    "overall": 1.0,
                },
            }
        )

        self.assertIn(
            '"stamp": ["Get your report with /skill-doctor", "warp.dev/skill-doctor"]',
            page,
        )
        self.assertIn('"eyebrow": "skill-doctor"', page)
        self.assertIn("text('# ' + CARD.eyebrow", page)

    def test_report_metric_lines_animate_like_skill_doctor_landing_page(self):
        page = render_page(
            {
                "scores": {
                    "efficiency": 0.75,
                    "code_quality": 0.93,
                    "procedure_compliance": 0.88,
                    "verbosity": 0.81,
                    "skill_coverage": 0.74,
                    "overall": 0.82,
                },
            }
        )

        self.assertIn(
            "animation: skill-doctor-fill 700ms "
            "cubic-bezier(0.22, 1, 0.36, 1) var(--metric-delay) both",
            page,
        )
        self.assertIn("@keyframes skill-doctor-fill", page)
        self.assertIn("from { transform: scaleX(0); }", page)
        self.assertIn("to { transform: scaleX(1); }", page)
        self.assertIn("width:75%;--metric-delay:180ms", page)
        self.assertIn("width:93%;--metric-delay:290ms", page)
        self.assertIn("width:88%;--metric-delay:400ms", page)
        self.assertIn("width:81%;--metric-delay:510ms", page)
        self.assertIn("width:74%;--metric-delay:620ms", page)
        self.assertIn("@media (prefers-reduced-motion: reduce)", page)
        self.assertIn(".bar-fill { animation: none; }", page)
        self.assertIn(
            "gap = CARD.bars.length > 3 ? 12 : 28",
            page,
        )
        self.assertIn(
            "CARD.bars.length * rowH + (CARD.bars.length - 1) * gap",
            page,
        )

    def test_skill_output_links_report_without_automatic_edit_prompt(self):
        skill_path = SKILL_ROOT / "SKILL.md"
        skill_text = skill_path.read_text(encoding="utf-8")

        self.assertIn(
            'render_report.py" "$REPORT_DIR/report.json" --open',
            skill_text,
        )
        self.assertIn(
            "Finish with the absolute path to `REPORT_DIR/report.html`.",
            skill_text,
        )
        self.assertIn(
            "Do not apply suggested edits without the user's explicit instruction.", skill_text
        )
        self.assertNotIn("[View in browser]", skill_text)

    def test_skill_edits_only_use_failed_conversations(self):
        skill_path = SKILL_ROOT / "SKILL.md"
        skill_text = skill_path.read_text(encoding="utf-8")

        self.assertIn(
            "`raw_efficiency` = mean of efficiency scores across all scored sessions",
            skill_text,
        )
        self.assertIn(
            "`curve(score) = 0.5 + 0.5 * score`",
            skill_text,
        )
        self.assertIn(
            "`overall = 0.25 * efficiency + 0.25 * code_quality + "
            "0.2 * procedure_compliance + 0.15 * verbosity + "
            "0.15 * skill_coverage.`",
            skill_text,
        )
        self.assertIn(
            "from each conversation's raw, uncurved scorer results",
            skill_text,
        )
        self.assertIn(
            "Use only `failed_conversations` as evidence for "
            "skill-improvement suggestions and draft skill edits",
            skill_text,
        )

    def test_report_renders_letter_grade(self):
        page = render_page(
            {
                "scores": {
                    "efficiency": 0.7,
                    "code_quality": 0.7,
                    "skill_coverage": 0.8,
                    "overall": 0.7,
                },
            }
        )

        self.assertIn('<div class="grade">C-</div>', page)
        self.assertIn('<div class="grade-label">overall 70</div>', page)


if __name__ == "__main__":
    unittest.main()
