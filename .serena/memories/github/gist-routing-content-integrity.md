# Gist routing content integrity

[2026-08-14] [ext:GitHub Gist API and live gh probes]: Gist IDs exist in numeric legacy form and 20-character and 32-character hexadecimal forms. `gh api gists/1`, `gh api gists/6f1ba788bf70fb501439`, and `gh api gists/057481db4dbd999bb7077f211f53f212` each resolved.

[2026-08-14] [ext:GitHub raw gist endpoints]: The 40-character hash in `gist.githubusercontent.com/.../raw/{hash}/{file}` is a raw-content hash, not the gist history revision accepted by `GET /gists/{id}/{revision}`. Route raw URLs directly with `gh api <raw-url>` and normalize HTTP to HTTPS.

[2026-08-14] [agent:Copilot]: Raw gist paths must reject decoded dot segments, encoded slashes, control characters, and gh placeholders before command construction. Page `?file=` selection applies to `.js` embed URLs. File fragments need filename-slug matching with ambiguity failure. Preserve uppercase `-L<n>` line-anchor semantics.

[2026-08-14] [doc:.claude/skills/github-url-intercept/scripts/gist_routing.py]: The implemented parser preserves pinned revisions, emits only selected file objects, rejects duplicate or empty selectors, and uses shell-safe quoting.

[2026-08-14] [issue:#5001]: Decode the complete gist fragment before testing the `file-` prefix. Validate every percent escape as `%HH`, then reject controls, separators, leading or trailing hyphens, and slugs outside GitHub's generated filename grammar. Otherwise an encoded or malformed selector can fall through to whole-gist retrieval and widen agent context.

## Relations

- **related_to**: [skills-github-cli-index]
- **related_to**: [github/pr-context-authoritative-metadata]
