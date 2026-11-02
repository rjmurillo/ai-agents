#!/usr/bin/env bash
# Install the Muse port of project-toolkit as Muse custom skills.
#
# Copies every skill in both packs into the Muse custom skills directory
# (default ~/workspace/custom-skills, override with MUSE_SKILLS_DIR).
# Existing skill directories are left untouched unless --force is given.
set -euo pipefail

TARGET="${MUSE_SKILLS_DIR:-$HOME/workspace/custom-skills}"
FORCE=0
if [[ "${1:-}" == "--force" ]]; then
  FORCE=1
fi

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$TARGET"

installed=0
skipped=0
for pack in project-toolkit-knowledge project-toolkit-delivery; do
  for skill in "$SRC_DIR/$pack/skills"/*/; do
    name="$(basename "$skill")"
    if [[ -e "$TARGET/$name" && $FORCE -eq 0 ]]; then
      echo "skip (exists): $name"
      skipped=$((skipped + 1))
      continue
    fi
    rm -rf "${TARGET:?}/$name"
    cp -R "$skill" "$TARGET/$name"
    installed=$((installed + 1))
  done
done

echo "installed $installed skills, skipped $skipped, target $TARGET"
