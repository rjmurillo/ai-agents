import { mkdir, readFile, rename, writeFile, unlink } from "node:fs/promises";
import { dirname, resolve, sep } from "node:path";
import type { BundleEntry, TargetContext, TargetEmitter } from "../types.js";
import { PathTraversalError, TargetWriteError } from "../io/errfmt.js";
import { hashContent } from "./version-pin.js";

// CWE-22 path traversal guard: resolve under the canonical .claude root
// and reject any entry whose path escapes the root.
function resolveDestination(entry: BundleEntry, target: TargetContext): string {
  const claudeRoot = resolve(target.targetDir, ".claude");
  const destPath = resolve(claudeRoot, entry.relativePath);
  if (destPath !== claudeRoot && !destPath.startsWith(claudeRoot + sep)) {
    throw new PathTraversalError(entry.relativePath, destPath);
  }
  return destPath;
}

export class FsTargetEmitter implements TargetEmitter {
  private readonly emitted: Record<string, string> = {};

  // recordedHashes holds the content hashes written by the last install, keyed
  // by path relative to .claude/. Empty means no record (first install, or a
  // pin written before hashes existed).
  constructor(
    private readonly recordedHashes: Readonly<Record<string, string>> = {},
  ) {}

  // Content hashes of every entry emitted so far, for the next version pin.
  installedHashes(): Record<string, string> {
    return { ...this.emitted };
  }

  async diverges(
    entry: BundleEntry,
    content: Buffer,
    target: TargetContext,
  ): Promise<boolean> {
    const destPath = resolveDestination(entry, target);
    let current: Buffer;
    try {
      current = await readFile(destPath);
    } catch (err) {
      if ((err as NodeJS.ErrnoException).code === "ENOENT") return false;
      throw err;
    }
    const currentHash = hashContent(current);
    if (currentHash === hashContent(content)) return false;
    return currentHash !== this.recordedHashes[entry.relativePath];
  }

  async emit(
    entry: BundleEntry,
    content: Buffer,
    target: TargetContext,
  ): Promise<void> {
    const destPath = resolveDestination(entry, target);
    this.emitted[entry.relativePath] = hashContent(content);
    if (target.dryRun) {
      return;
    }
    const dir = dirname(destPath);
    const tmpPath = destPath + ".tmp";
    try {
      await mkdir(dir, { recursive: true });
      await writeFile(tmpPath, content);
      await rename(tmpPath, destPath);
    } catch (err) {
      try {
        await unlink(tmpPath);
      } catch {
        // tmp cleanup is best-effort
      }
      const message = err instanceof Error ? err.message : String(err);
      throw new TargetWriteError(destPath, message);
    }
  }
}
