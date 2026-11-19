# Body-file scripts refuse a world-writable file and any open directory under a temp root

## What happens

`edit_pr_body.py --body-file` and `new_issue.py --body-file` read through `read_body_file_text` (`scripts/github_core/body_file.py`). It refuses a file that is a symlink, a FIFO, owned by another user, hard-linked, or world-writable. A `pr-body-*.md` file must be mode 600.

Under a shared temp root, every directory down to the file must also belong to the caller and refuse other writers. A fine file in an open directory is still refused.

## Measured 2026-11-11

Scratchpad directory under `/tmp`, `new_issue.py --dry-run`:

| File mode | Directory mode | Result |
|---|---|---|
| 600 | 700 | accepted |
| 664 | 700 | accepted |
| 666 | 700 | refused: `body file must not be world-writable` |
| 664 | 775 | refused: `body file directory is not private to the caller` |

So `chmod 600` on the file is not the whole fix. The child report said a group-writable file is refused. That held only because the directory was open. Make the directory mode 700 and the file not world-writable.

## Practice

Create one private directory per caller, `chmod 700`, and keep body files in it. `new_pr.py --prepare-body-file` does this and picks a unique name. A fixed shared name such as `body.md` lets concurrent sessions publish each other's text.

## Evidence

- `scripts/github_core/body_file.py` lines 215 to 255 (mode checks and the private-directory walk), read 2026-11-11.
- `edit_pr_body.py` module docstring, lines 10 to 20.
- The four-row table above is a local run; the probe used a scratch directory and no network write.

## Relations

- **related_to**: [github/github-pr-body-files-collide-in-a-shared-scratch-directory](../github/github-pr-body-files-collide-in-a-shared-scratch-directory.md)
- **related_to**: [pr-review/pr-validator-needs-prepare-body-file-and-diff-backed-paths](../pr-review/pr-validator-needs-prepare-body-file-and-diff-backed-paths.md)
