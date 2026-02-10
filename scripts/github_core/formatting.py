"""Formatting utilities for GitHub output (emoji mappings)."""

from __future__ import annotations

PRIORITY_EMOJI: dict[str, str] = {
    "P0": "\U0001f525",  # fire
    "P1": "\u2757",  # exclamation
    "P2": "\u2796",  # dash
    "P3": "\u2b07\ufe0f",  # down arrow
}

REACTION_EMOJI: dict[str, str] = {
    "+1": "\U0001f44d",
    "-1": "\U0001f44e",
    "laugh": "\U0001f604",
    "confused": "\U0001f615",
    "heart": "\u2764\ufe0f",
    "hooray": "\U0001f389",
    "rocket": "\U0001f680",
    "eyes": "\U0001f440",
}


def get_priority_emoji(priority: str) -> str:
    """Return the emoji for a priority level (P0-P3)."""
    return PRIORITY_EMOJI.get(priority, "\u2754")  # question mark default


def get_reaction_emoji(reaction: str) -> str:
    """Return the emoji for a GitHub reaction type."""
    return REACTION_EMOJI.get(reaction, reaction)
