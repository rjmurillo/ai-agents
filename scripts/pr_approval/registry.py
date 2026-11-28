"""Operator-owned identity registry, keyed by stable GitHub account IDs.

Logins are informational. Classification never reads login suffixes,
commit author strings, PR bodies, labels, or model output.
"""

from __future__ import annotations

from dataclasses import dataclass

import tomllib

SCHEMA_VERSION = 1
_LIST_KEYS = ("independent_authors", "agent_accounts", "bot_accounts", "approver_principals")
_TOP_KEYS = frozenset({"schema_version", "aliases", *_LIST_KEYS})
_ACCOUNT_KEYS = frozenset({"id", "login"})
_ALIAS_KEYS = frozenset({"ids", "note"})


class RegistryError(ValueError):
    """Raised when the registry file is invalid."""


@dataclass(frozen=True)
class Registry:
    independent_authors: frozenset[int]
    agent_accounts: frozenset[int]
    bot_accounts: frozenset[int]
    approver_principals: frozenset[int]
    alias_groups: tuple[frozenset[int], ...]

    def principal(self, account_id: int) -> frozenset[int]:
        """Return every ID registered as the same principal as ``account_id``."""
        group = {account_id}
        for aliases in self.alias_groups:
            if account_id in aliases:
                group |= aliases
        return frozenset(group)

    def is_bot(self, account_id: int) -> bool:
        return account_id in self.bot_accounts or account_id in self.agent_accounts


def _id(value: object, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RegistryError(f"{where} must be a positive integer account ID")
    return value


def _accounts(raw: object, key: str) -> frozenset[int]:
    if not isinstance(raw, list):
        raise RegistryError(f"{key} must be an array of tables")
    ids: set[int] = set()
    for index, entry in enumerate(raw):
        where = f"{key}[{index}]"
        if not isinstance(entry, dict):
            raise RegistryError(f"{where} must be a table")
        unknown = sorted(set(entry) - _ACCOUNT_KEYS)
        if unknown:
            raise RegistryError(f"{where} has unknown keys: {', '.join(unknown)}")
        ids.add(_id(entry.get("id"), f"{where}.id"))
    return frozenset(ids)


def parse_registry(data: bytes) -> Registry:
    """Parse and validate registry bytes. Raises ``RegistryError``."""
    try:
        raw = tomllib.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise RegistryError(f"registry is not valid UTF-8 TOML: {exc}") from exc
    unknown = sorted(set(raw) - _TOP_KEYS)
    if unknown:
        raise RegistryError(f"registry has unknown keys: {', '.join(unknown)}")
    if raw.get("schema_version") != SCHEMA_VERSION or isinstance(raw.get("schema_version"), bool):
        raise RegistryError(f"schema_version must be {SCHEMA_VERSION}")
    lists = {key: _accounts(raw.get(key, []), key) for key in _LIST_KEYS}
    aliases_raw = raw.get("aliases", [])
    if not isinstance(aliases_raw, list):
        raise RegistryError("aliases must be an array of tables")
    groups: list[frozenset[int]] = []
    for index, entry in enumerate(aliases_raw):
        where = f"aliases[{index}]"
        if not isinstance(entry, dict) or set(entry) - _ALIAS_KEYS:
            raise RegistryError(f"{where} must be a table with 'ids' and optional 'note'")
        ids = entry.get("ids")
        if not isinstance(ids, list) or len(ids) < 2:
            raise RegistryError(f"{where}.ids must list at least two account IDs")
        groups.append(frozenset(_id(item, f"{where}.ids") for item in ids))
    return Registry(
        independent_authors=lists["independent_authors"],
        agent_accounts=lists["agent_accounts"],
        bot_accounts=lists["bot_accounts"],
        approver_principals=lists["approver_principals"],
        alias_groups=tuple(groups),
    )
