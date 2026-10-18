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
const assetsDir = join(packageRoot, "bundle", "assets");

async function shouldExclude(relativePath: string, name: string): Promise<boolean> {
  if (EXCLUDED_DIRS.has(name) || EXCLUDED_FILES.has(name)) return true;
  for (const pattern of EXCLUDED_PATTERNS) {
    if (pattern.test(name)) return true;
  }
  return false;
}

// .claude/agents/<name>.md and each shipped .claude/skills/<name> are relative
// symlinks into src/claude/ (ADR-119). A Dirent reports a link as neither a
// file nor a directory, so classify by following it, and copy the target's
// bytes rather than the link.
async function isDirectoryEntry(
  path: string,
  entry: { isDirectory(): boolean; isSymbolicLink(): boolean },
): Promise<boolean> {
  if (entry.isDirectory()) return true;
  if (!entry.isSymbolicLink()) return false;
  await assertInsideRepo(path);
  return (await stat(path)).isDirectory();
}

// A followed link must stay inside the repository, or the npm package would
// carry whatever file the link names (CWE-59).
async function assertInsideRepo(path: string): Promise<void> {
  const target = await realpath(path);
  const root = await realpath(repoRoot);
  if (target !== root && !target.startsWith(root + sep)) {
    throw new Error(`Refusing to bundle ${path}: it links outside the repository (${target})`);
  }
}

async function copyTree(src: string, dest: string, depth: number): Promise<number> {
  let count = 0;
  const entries = await readdir(src, { withFileTypes: true });

  for (const entry of entries) {
    if (await shouldExclude(entry.name, entry.name)) continue;

    if (depth === 0 && entry.name === "skills" && (await isDirectoryEntry(join(src, entry.name), entry))) {
      const skillsSrc = join(src, "skills");
      const skillsDest = join(dest, "skills");
      const skills = await readdir(skillsSrc, { withFileTypes: true });
      for (const skill of skills) {
        const skillSrc = join(skillsSrc, skill.name);
        if (!(await isDirectoryEntry(skillSrc, skill))) continue;
        if (EXCLUDED_SKILLS.has(skill.name)) continue;
        const skillDest = join(skillsDest, skill.name);
        // Recurse into each kept skill so EXCLUDED_FILES / EXCLUDED_PATTERNS
        // are enforced inside skill subtrees (lockfiles, caches, local overrides).
        count += await copyTree(skillSrc, skillDest, depth + 1);
      }
      continue;
    }

    const srcPath = join(src, entry.name);
    const destPath = join(dest, entry.name);

    if (await isDirectoryEntry(srcPath, entry)) {
      count += await copyTree(srcPath, destPath, depth + 1);
    } else {
      const dir = dirname(destPath);
      await mkdir(dir, { recursive: true });
      if (entry.isSymbolicLink()) await assertInsideRepo(srcPath);
      await cp(srcPath, destPath, { dereference: true });
      count++;
    }
  }

  return count;
}

async function main(): Promise<void> {
  await rm(assetsDir, { recursive: true, force: true });

  const count = await copyTree(sourceDir, assetsDir, 0);
  console.log(`Bundled ${count} files into ${assetsDir}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
