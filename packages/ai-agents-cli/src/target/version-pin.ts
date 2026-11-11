import { readFile, writeFile, mkdir } from "node:fs/promises";
import { join } from "node:path";
import { createHash } from "node:crypto";
import type { VersionPin } from "../types.js";

const PIN_FILE = ".ai-agents-version.json";

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

export function hashContent(content: Buffer): string {
  return createHash("sha256").update(content).digest("hex");
}

// Read the per-file content hashes recorded by the last install. A missing
// pin, a pin that is not valid JSON, or a pin written before hashes existed
// all mean "no record", so every existing file is judged against the incoming
// content. Any other read error is rethrown.
export async function readRecordedHashes(
  targetDir: string,
): Promise<Record<string, string>> {
  let raw: string;
  try {
    raw = await readFile(join(targetDir, ".claude", PIN_FILE), "utf-8");
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return {};
    throw err;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return {};
  }
  const files = (parsed as { files?: unknown } | null)?.files;
  if (typeof files !== "object" || files === null || Array.isArray(files)) {
    return {};
  }
  const recorded: Record<string, string> = {};
  for (const [path, hash] of Object.entries(files)) {
    if (typeof hash === "string") recorded[path] = hash;
  }
  return recorded;
}

export async function writeVersionPin(
  targetDir: string,
  version: string,
  manifestEntries: string[],
  dryRun: boolean,
  fileHashes?: Readonly<Record<string, string>>,
): Promise<void> {
  if (dryRun) return;

  const pin: VersionPin = {
    version,
    manifestHash: computeManifestHash(manifestEntries),
    installedAt: new Date().toISOString(),
    source: "@rjmurillo/ai-agents",
    ...(fileHashes ? { files: fileHashes } : {}),
  };

  const pinDir = join(targetDir, ".claude");
  await mkdir(pinDir, { recursive: true });

  const pinPath = join(pinDir, PIN_FILE);
  await writeFile(pinPath, JSON.stringify(pin, null, 2) + "\n", "utf-8");
}
