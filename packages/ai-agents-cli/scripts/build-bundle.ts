import { cp, rm, mkdir, readdir, realpath, stat } from "node:fs/promises";
import { join, resolve, dirname, sep } from "node:path";
import { fileURLToPath } from "node:url";

const EXCLUDED_DIRS = new Set(["hooks", "lib", "worktrees"]);
const EXCLUDED_FILES = new Set(["settings.json", "settings.local.json", "scheduled_tasks.lock"]);
const EXCLUDED_SKILLS = new Set(["github"]);
const EXCLUDED_PATTERNS = [/__pycache__/, /\.pyc$/, /\.lock$/, /\.local\.json$/, /\.skill_pattern_cache\.json$/];

const currentFile = fileURLToPath(import.meta.url);
const packageRoot = resolve(dirname(currentFile), "..");
const repoRoot = resolve(packageRoot, "../..");
const sourceDir = join(repoRoot, ".claude");
// Followed links must land in the plugin tree being bundled, not anywhere in the repo.
const pluginRoot = join(repoRoot, "src", "claude");
const assetsDir = join(packageRoot, "bundle", "assets");

async function shouldExclude(relativePath: string, name: string): Promise<boolean> {
  if (EXCLUDED_DIRS.has(name) || EXCLUDED_FILES.has(name)) return true;
  for (const pattern of EXCLUDED_PATTERNS) {
    if (pattern.test(name)) return true;
  }
  return false;
}

// Context for one bundle run. `allowedRoot` bounds every followed link;
// `ancestors` holds the realpaths of the directories on the current path, so a
// link back to one of them is refused instead of recursing until ELOOP (CWE-835).
export interface CopyContext {
  allowedRoot: string;
  ancestors: string[];
}

// .claude/agents/<name>.md and each shipped .claude/skills/<name> are relative
// symlinks into src/claude/ (ADR-119). A Dirent reports a link as neither a
// file nor a directory, so classify by following it, and copy the target's
// bytes rather than the link.
async function isDirectoryEntry(
  path: string,
  entry: { isDirectory(): boolean; isSymbolicLink(): boolean },
  ctx: CopyContext,
): Promise<boolean> {
  if (entry.isDirectory()) return true;
  if (!entry.isSymbolicLink()) return false;
  await assertInsideRoot(path, ctx);
  return (await stat(path)).isDirectory();
}

// A followed link must stay inside the plugin tree, or the npm package would
// carry whatever file the link names (CWE-59).
async function assertInsideRoot(path: string, ctx: CopyContext): Promise<void> {
  const target = await realpath(path);
  const root = await realpath(ctx.allowedRoot);
  if (target !== root && !target.startsWith(root + sep)) {
    throw new Error(`Refusing to bundle ${path}: it links outside the plugin tree (${target})`);
  }
}

export async function copyTree(src: string, dest: string, depth: number, ctx: CopyContext): Promise<number> {
  const here = await realpath(src);
  if (ctx.ancestors.includes(here)) {
    throw new Error(`Refusing to bundle ${src}: link cycle, it resolves to ${here} which is already being copied`);
  }
  const inner: CopyContext = { ...ctx, ancestors: [...ctx.ancestors, here] };
  let count = 0;
  const entries = await readdir(src, { withFileTypes: true });

  for (const entry of entries) {
    if (await shouldExclude(entry.name, entry.name)) continue;

    if (depth === 0 && entry.name === "skills" && (await isDirectoryEntry(join(src, entry.name), entry, ctx))) {
      const skillsSrc = join(src, "skills");
      const skillsDest = join(dest, "skills");
      const skills = await readdir(skillsSrc, { withFileTypes: true });
      for (const skill of skills) {
        const skillSrc = join(skillsSrc, skill.name);
        if (!(await isDirectoryEntry(skillSrc, skill, ctx))) continue;
        if (EXCLUDED_SKILLS.has(skill.name)) continue;
        const skillDest = join(skillsDest, skill.name);
        // Recurse into each kept skill so EXCLUDED_FILES / EXCLUDED_PATTERNS
        // are enforced inside skill subtrees (lockfiles, caches, local overrides).
        count += await copyTree(skillSrc, skillDest, depth + 1, inner);
      }
      continue;
    }

    const srcPath = join(src, entry.name);
    const destPath = join(dest, entry.name);

    if (await isDirectoryEntry(srcPath, entry, ctx)) {
      count += await copyTree(srcPath, destPath, depth + 1, inner);
    } else {
      const dir = dirname(destPath);
      await mkdir(dir, { recursive: true });
      if (entry.isSymbolicLink()) await assertInsideRoot(srcPath, ctx);
      await cp(srcPath, destPath, { dereference: true });
      count++;
    }
  }

  return count;
}

async function main(): Promise<void> {
  await rm(assetsDir, { recursive: true, force: true });

  const count = await copyTree(sourceDir, assetsDir, 0, { allowedRoot: pluginRoot, ancestors: [] });
  console.log(`Bundled ${count} files into ${assetsDir}`);
}

if (import.meta.main) {
  main().catch((err) => {
    console.error(err);
    process.exit(1);
  });
}
