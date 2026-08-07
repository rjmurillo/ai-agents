"""Stable exception identities shared by script-style eval modules."""

from __future__ import annotations


class MalformedProviderMetadataError(RuntimeError):
    """A provider returned metadata that cannot be recorded truthfully."""
