import { writeFile, mkdir } from "node:fs/promises";
import { join, dirname } from "node:path";
import type { BundleEntry, TargetContext, TargetEmitter } from "./types.js";

const PATH_MAP: Record<string, (relativePath: string) => string> = {
  agent: (p) => {
    const name = p.replace(/^\.claude\/agents\//, "").replace(/\.md$/, "");
    return `.github/copilot/agents/${name}.agent.md`;
  },
  command: (p) => {
    const name = p.replace(/^\.claude\/commands\//, "").replace(/\.md$/, "");
    return `.github/prompts/${name}.md`;
  },
  config: (p) => {
    if (p === "CLAUDE.md" || p.endsWith("/CLAUDE.md")) {
      return ".github/copilot-instructions.md";
    }
    return p;
  },
};

export class CopilotTargetEmitter implements TargetEmitter {
  canEmit(target: TargetContext): boolean {
    return target.target === "copilot" || target.target === "both";
  }

  async emit(
    entry: BundleEntry,
    content: Buffer,
    target: TargetContext,
  ): Promise<void> {
    const mapper = PATH_MAP[entry.category];
    if (!mapper) return;

    const destPath = mapper(entry.relativePath);
    const fullPath = join(target.destDir, destPath);

    await mkdir(dirname(fullPath), { recursive: true });
    await writeFile(fullPath, content);
  }

  mapPath(entry: BundleEntry): string | null {
    const mapper = PATH_MAP[entry.category];
    return mapper ? mapper(entry.relativePath) : null;
  }
}
