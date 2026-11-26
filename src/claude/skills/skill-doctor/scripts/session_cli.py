"""Harness choices and corpus-export arguments for the skill-doctor collector.

Copyright (c) 2026 Denver Technologies, Inc. MIT license, see ../LICENSE.
"""

from __future__ import annotations

import argparse

# t3 and gemini are corpus-only sources: they carry no tool calls, so they read only
# with --export-corpus and never reach scoring.
HARNESS_CHOICES = (
    "auto",
    "all",
    "claude",
    "codex",
    "copilot",
    "warp",
    "pi",
    "grok",
    "zcode",
    "hermes",
    "droid",
    "muse",
    "t3",
    "gemini",
)


def add_corpus_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--export-corpus",
        metavar="PATH",
        default=None,
        help="also write every collected user and assistant message as full-text JSONL "
        "(redacted, no truncation). Also reads T3 and Gemini antigravity sources, which "
        "carry no repository path, so they export only with --all-conversations",
    )
    parser.add_argument(
        "--t3-home",
        default="~/.t3",
        help="T3 Code home containing userdata/statev2.sqlite (default: ~/.t3)",
    )
    parser.add_argument(
        "--gemini-home",
        default="~/.gemini/antigravity-cli",
        help="Gemini antigravity home containing brain/ (default: ~/.gemini/antigravity-cli)",
    )
