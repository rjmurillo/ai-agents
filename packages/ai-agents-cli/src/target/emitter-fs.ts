import { mkdir, rename, writeFile, unlink } from "node:fs/promises";
import { join, dirname } from "node:path";
import type { BundleEntry, TargetContext, TargetEmitter } from "../types.js";
import { TargetWriteError } from "../io/errfmt.js";

export class FsTargetEmitter implements TargetEmitter {
  canEmit(_target: TargetContext): boolean {
    return true;
  }

  async emit(
    entry: BundleEntry,
    content: Buffer,
    target: TargetContext,
  ): Promise<void> {
    const destPath = join(target.targetDir, ".claude", entry.relativePath);
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
