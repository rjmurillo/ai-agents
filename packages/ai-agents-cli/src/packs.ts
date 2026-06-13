import type { BundleEntry, Transform } from "./types.js";

// Optional skill packs. A pack is excluded from `ai-agents init` by default and
// installed only when requested via `--pack <id>` (issue #2509, follow-up to
// #1784). Maps the pack id (the --pack value) to the skill directory it vendors.
export const PACKS: Record<string, string> = {
  business: "business-strategy",
};

const PACK_SKILL_DIRS = new Set<string>(Object.values(PACKS));

// Sorted list of known pack ids, for help text and error messages.
export function knownPacks(): string[] {
  return Object.keys(PACKS).sort();
}

// Parse and validate --pack values. Each value may be comma-separated
// (`--pack a,b`) or the flag may repeat (`--pack a --pack b`). Throws on an
// unknown pack id so the CLI can surface a clear, actionable error.
export function parsePacks(raw: string[] | undefined): Set<string> {
  const requested = new Set<string>();
  for (const item of raw ?? []) {
    for (const name of item.split(",").map((s) => s.trim()).filter(Boolean)) {
      if (!Object.prototype.hasOwnProperty.call(PACKS, name)) {
        throw new Error(
          `Unknown pack "${name}". Available packs: ${knownPacks().join(", ")}.`,
        );
      }
      requested.add(name);
    }
  }
  return requested;
}

// Transform that drops optional-pack skill entries unless their pack is
// requested. Pack skills live under `skills/<dir>/` in the bundle; a
// non-requested pack's files are skipped so they are neither vendored nor
// recorded in the version-pin manifest.
export function makePackFilter(requestedPacks: Set<string>): Transform {
  const requestedDirs = new Set<string>(
    [...requestedPacks].map((id) => PACKS[id]).filter(Boolean),
  );
  return (entry: BundleEntry): BundleEntry | null => {
    const normalized = entry.relativePath.replace(/\\/g, "/");
    const match = normalized.match(/^skills\/([^/]+)\//i);
    if (match) {
      const dir = match[1].toLowerCase();
      if (PACK_SKILL_DIRS.has(dir) && !requestedDirs.has(dir)) {
        return null;
      }
    }
    return entry;
  };
}
