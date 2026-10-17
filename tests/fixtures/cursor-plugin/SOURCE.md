# Cursor plugin schemas

These two files are byte copies of Cursor's published JSON schemas.

- `plugin.schema.json` from <https://raw.githubusercontent.com/cursor/plugins/main/schemas/plugin.schema.json>
- `marketplace.schema.json` from <https://raw.githubusercontent.com/cursor/plugins/main/schemas/marketplace.schema.json>

Both match the upstream `main` branch as fetched on 2026-10-13. Both are
draft-07 schemas with `additionalProperties: false`.

`tests/test_cursor_plugin_artifacts.py` validates the committed Cursor manifest
and marketplace against them. Refresh a copy by fetching the URL above, then
rerun that test.
