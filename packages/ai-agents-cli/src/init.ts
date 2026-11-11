import type {
  BundleEntry,
  BundleSource,
  TargetContext,
  TargetEmitter,
  Transform,
} from "./types.js";

// Yield each bundle entry that survives the transforms, with its content.
async function* selectedEntries(
  source: BundleSource,
  target: TargetContext,
  transforms: Transform[],
): AsyncGenerator<{ entry: BundleEntry; content: Buffer }> {
  for await (const listed of source.list()) {
    let current: BundleEntry | null = listed;
    for (const transform of transforms) {
      current = transform(current, target);
      if (current === null) break;
    }
    if (current === null) continue;
    yield { entry: current, content: await source.read(current) };
  }
}

// Check every destination before the first write, so a refused run changes
// nothing. Returns the relative paths of files holding local modifications.
async function findDivergent(
  source: BundleSource,
  emitter: TargetEmitter,
  target: TargetContext,
  transforms: Transform[],
): Promise<string[]> {
  const divergent: string[] = [];
  for await (const { entry, content } of selectedEntries(
    source,
    target,
    transforms,
  )) {
    if (await emitter.diverges(entry, content, target)) {
      divergent.push(entry.relativePath);
    }
  }
  return divergent;
}

export async function init(
  source: BundleSource,
  emitter: TargetEmitter,
  target: TargetContext,
  transforms: Transform[] = [],
): Promise<number> {
  if (!target.force) {
    try {
      const divergent = await findDivergent(source, emitter, target, transforms);
      if (divergent.length > 0) {
        process.stderr.write(
          `Refusing to overwrite ${divergent.length} locally modified files under ${target.targetDir}/.claude:\n` +
            divergent.map((path) => `  ${path}\n`).join("") +
            "Nothing was written. Use --force to overwrite them.\n",
        );
        return 2;
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      process.stderr.write(`init failed before writing: ${message}\n`);
      return 1;
    }
  }

  let vendored = 0;
  try {
    for await (const { entry, content } of selectedEntries(
      source,
      target,
      transforms,
    )) {
      await emitter.emit(entry, content, target);
      vendored++;
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    process.stderr.write(`init failed after ${vendored} files: ${message}\n`);
    return 1;
  }

  if (target.dryRun) {
    process.stdout.write(`Would vendor ${vendored} files.\n`);
    return 0;
  }
  process.stdout.write(`Vendored ${vendored} files.\n`);
  process.stdout.write(
    "Open this folder in Claude Code and run /spec to start.\n",
  );
  return 0;
}
