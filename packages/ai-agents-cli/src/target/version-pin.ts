import { writeFile, mkdir } from "node:fs/promises";
import { join } from "node:path";
import { createHash } from "node:crypto";
import type { VersionPin } from "../types.js";

export function computeManifestHash(entries: string[]): string {
  const hash = createHash("sha256");
  // Copy before sort so we do not mutate caller-owned arrays.
  // Length-prefix + NUL terminator so distinct splits like
  // ["ab","c"] and ["a","bc"] hash to different values.
  for (const entry of [...entries].sort()) {
    hash.update(String(entry.length));
    hash.update(":");
    hash.update(entry);
    hash.update("\0");
  }
  return hash.digest("hex").slice(0, 16);
}

export async function writeVersionPin(
  targetDir: string,
  version: string,
  manifestEntries: string[],
  dryRun: boolean,
): Promise<void> {
  if (dryRun) return;

  const pin: VersionPin = {
    version,
    manifestHash: computeManifestHash(manifestEntries),
    installedAt: new Date().toISOString(),
    source: "@rjmurillo/ai-agents",
  };

  const pinDir = join(targetDir, ".claude");
  await mkdir(pinDir, { recursive: true });

  const pinPath = join(pinDir, ".ai-agents-version.json");
  await writeFile(pinPath, JSON.stringify(pin, null, 2) + "\n", "utf-8");
}
