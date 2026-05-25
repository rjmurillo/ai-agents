import { readdir, readFile, stat } from "node:fs/promises";
import { join, relative, sep } from "node:path";
import type { BundleEntry, BundleSource } from "../types.js";

export class FsBundleSource implements BundleSource {
  private readonly assetsDir: string;

  constructor(assetsDir: string) {
    this.assetsDir = assetsDir;
  }

  async *list(): AsyncIterable<BundleEntry> {
    yield* this.walk(this.assetsDir);
  }

  async read(entry: BundleEntry): Promise<Buffer> {
    return readFile(join(this.assetsDir, entry.relativePath));
  }

  private async *walk(dir: string): AsyncIterable<BundleEntry> {
    const entries = await readdir(dir, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = join(dir, entry.name);
      if (entry.isDirectory()) {
        yield* this.walk(fullPath);
      } else if (entry.isFile()) {
        const info = await stat(fullPath);
        // Normalize to forward slashes so downstream prefix checks
        // (e.g., startsWith("skills/")) behave identically on Windows.
        const rel = relative(this.assetsDir, fullPath);
        yield {
          relativePath: sep === "/" ? rel : rel.split(sep).join("/"),
          size: info.size,
        };
      }
    }
  }
}
