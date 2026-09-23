Fixed in commit 4548d25d (rebased to b87bce81). Removed the duplicate `.factory/**` at line 122; the entry at line 113 covers it.

Verified: `grep -c '.factory' .markdownlint-cli2.yaml` returns 1.
