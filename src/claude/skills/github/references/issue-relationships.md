# Issue Relationships

GitHub links issues natively. A `#123` mention in an issue body is only text: it
creates no parent, no dependency, and no relation. Agents that write
"Blocked by #123" or "Parent tracker: #456" in a body without the native link
leave the sub-issue progress bar, the dependency graph, and the sidebar empty.

Write the text if it helps a human reader. Always add the native link too.

## The five relationships

Read each row from the point of view of `--issue`.

| Relation | Meaning | Limit |
|----------|---------|-------|
| `parent` | `--target` is the parent of `--issue` | One parent per issue |
| `sub-issue` | Each `--target` becomes a child of `--issue` | A child has one parent |
| `blocked-by` | `--issue` cannot finish until each `--target` finishes | None |
| `blocking` | `--issue` must finish before each `--target` | None |
| `relates-to` | The issues share context, with no order between them | None |

`blocked-by` and `blocking` are one link seen from its two ends. Adding
"#5 blocking #7" and "#7 blocked-by #5" creates the same link once.

Only issues take part. A pull request is rejected. Link a pull request to its
issue with a closing keyword (`Closes #123`) in the pull request body.

A target in another repository is passed as `owner/repo#123`. GitHub decides
whether that repository can take part; a refusal comes back as an API error.

## Choosing the relation

Decide from what the text says, not from where the number appears.

| The text says | Relation to add on the issue that says it |
|---------------|-------------------------------------------|
| "Parent", "Parent tracker", "child of #N", "part of epic #N", "umbrella #N", "Tracking issue: #N" | `parent` N |
| An epic or tracker lists its children, or a checklist of child issues | `sub-issue` for each child |
| "Blocked by #N", "Depends on #N", "Requires #N first", "after #N lands" | `blocked-by` N |
| "Blocks #N", "Unblocks #N", "#N is blocked by this", "prerequisite of #N" | `blocking` N |
| An epic's execution steps, release candidates, or release gates name #N as work that must finish first | `blocked-by` N |
| A problem statement, context, or background section names #N | `relates-to` N |
| "Split out of #N", "follow-up to #N", "sibling of #N", "#N owns X", "coordinates with #N", "supersedes #N", evidence taken from #N | `relates-to` N |
| The text calls #N a wrong citation or unrelated, or `#N` is a placeholder such as `Fixes #123` in a sample | No link |

Rules that settle the common doubts:

- An epic with an execution plan is **blocked by** the issues in that plan.
  It is not their parent unless the child issues call it their parent.
- Issues named in an epic's problem statement get **relates-to**. The same
  issue can also be in the execution plan; then it gets both links.
- "Available from #N", "uses #N if present", or "consumes #N once available" is
  **relates-to**. It does not wait on #N.
- A blocker that says "stays blocked on #N" but also says the blocked scope was
  dropped is **relates-to**.
- A closed target is still a valid link. It records history and shows as done.
- Do not make an open issue the child of a closed parent. Use **relates-to**
  and name the conflict in your report.

## Commands

Read what is linked today:

```bash
# CLAUDE_PLUGIN_ROOT is set in a vendored install; falls back to .claude in-repo.
S="${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/github/scripts/issue"
python3 "$S/get_issue_relationships.py" --issue 5456
```

Add links. Several targets in one call share one relation:

```bash
python3 "$S/set_issue_relationship.py" --issue 5456 --relation blocked-by --target 5394 5395 5396
python3 "$S/set_issue_relationship.py" --issue 5456 --relation relates-to --target 5404 5436
python3 "$S/set_issue_relationship.py" --issue 5820 --relation parent --target 5817
python3 "$S/set_issue_relationship.py" --issue 5390 --relation sub-issue --target 5384 other/repo#12
```

Remove a link with `--remove`. Preview any change with `--dry-run`.

Move a child to a new parent with `--replace-parent`. Without that flag the
script refuses, because the move silently detaches the child from its old
parent.

The script reads current links first. A link that exists already is reported
as `already_linked` and costs no mutation, so a rerun is safe.

## After creating an issue

`new_issue.py` creates the issue only. Its output carries the new number. Add
the links in the next step, from the body you just wrote:

```bash
python3 "$S/set_issue_relationship.py" --issue <new> --relation parent --target <epic>
python3 "$S/set_issue_relationship.py" --issue <new> --relation blocked-by --target <prereq>
```

When you file several children of one epic, link each child as it is created.
Do not leave the linking for the end of the run.

## Auditing existing issues

To find references that have no native link:

1. List the open issues and their bodies with `list_issues.py`.
2. For each issue, collect every `#N` outside code fences, then drop pull
   request numbers and the issue's own number.
3. Read the current links with `get_issue_relationships.py`. Drop any pair that
   is linked already, in any relation.
4. Classify each remaining pair with the table above. Read the full sentence,
   not the line around the number.
5. Apply with `set_issue_relationship.py`, then repeat step 3. Only the pairs
   you chose not to link should remain.

## MCP fallback

When `check_github_transport.py` reports `gh_unusable`, use the GitHub MCP
operations. Coverage is partial:

| Script call | MCP operation | Gap |
|-------------|---------------|-----|
| `--relation sub-issue` or `parent` | `sub_issue_write` method `add` or `remove`, with `replace_parent` for a move | None |
| Read sub-issues | `issue_read` method `get_sub_issues` | Does not return the parent |
| `--relation blocked-by` or `blocking` | `issue_dependency_write` method `add` or `remove`, `type` `blocked_by` or `blocking` | Behind the `issue-dependencies` feature flag; check that your toolset exposes it |
| Read dependencies | `issue_dependency_read` method `get_blocked_by` or `get_blocking` | Same feature flag |
| `--relation relates-to` | None | Report the link as not added, and name the pair |
