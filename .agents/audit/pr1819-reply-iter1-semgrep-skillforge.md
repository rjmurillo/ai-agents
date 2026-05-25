Self-resolved. The Semgrep finding was on commit `97f0cbcd`, which
already struck through the matched text (`<strike>...</strike>`)
inside an audit reply file and added the "Fixed in commit" annotation.

The finding location was content inside `.agents/audit/pr1819-reply-
semgrep-skillforge.md`, which is a quoted reply explaining a
previous Semgrep autonomy alert. No production code or skill
content was affected.
