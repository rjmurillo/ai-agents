import { cp, rm, readdir, stat } from "node:fs/promises";
import { join, resolve, dirname } from "node:path";
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

async function copyTree(src: string, dest: string, depth: number): Promise<number> {
  let count = 0;
  const entries = await readdir(src, { withFileTypes: true });

  for (const entry of entries) {
    if (await shouldExclude(entry.name, entry.name)) continue;

    if (depth === 0 && entry.name === "skills" && entry.isDirectory()) {
      const skillsSrc = join(src, "skills");
      const skillsDest = join(dest, "skills");
      const skills = await readdir(skillsSrc, { withFileTypes: true });
      for (const skill of skills) {
        if (EXCLUDED_SKILLS.has(skill.name)) continue;
        const skillSrc = join(skillsSrc, skill.name);
        const skillDest = join(skillsDest, skill.name);
        await cp(skillSrc, skillDest, { recursive: true });
        count++;
      }
      continue;
    }

    const srcPath = join(src, entry.name);
    const destPath = join(dest, entry.name);

    if (entry.isDirectory()) {
      count += await copyTree(srcPath, destPath, depth + 1);
    } else {
      const dir = dirname(destPath);
      await cp(srcPath, destPath, { recursive: true });
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
