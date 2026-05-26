import { mkdir, rename, writeFile, unlink } from "node:fs/promises";
import { dirname, resolve, sep } from "node:path";
import type { BundleEntry, TargetContext, TargetEmitter } from "../types.js";
import { PathTraversalError, TargetWriteError } from "../io/errfmt.js";

export class FsTargetEmitter implements TargetEmitter {
  canEmit(_target: TargetContext): boolean {
    return true;
  }

  async emit(
    entry: BundleEntry,
    content: Buffer,
    target: TargetContext,
  ): Promise<void> {
    // CWE-22 path traversal guard: resolve under the canonical .claude root
    // and reject any entry whose path escapes the root.
    const claudeRoot = resolve(target.targetDir, ".claude");
    const destPath = resolve(claudeRoot, entry.relativePath);
    if (destPath !== claudeRoot && !destPath.startsWith(claudeRoot + sep)) {
      throw new PathTraversalError(entry.relativePath, destPath);
    }
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
