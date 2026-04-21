import type {
  BundleSource,
  TargetContext,
  TargetEmitter,
  Transform,
} from "./types.js";

export async function init(
  source: BundleSource,
  emitter: TargetEmitter,
  target: TargetContext,
  transforms: Transform[] = [],
): Promise<number> {
  if (!emitter.canEmit(target)) {
    process.stderr.write(
      `Target ${target.targetDir} exists and diverges from vendor snapshot. Use --force to overwrite.\n`,
    );
    return 2;
  }

  let vendored = 0;
  for await (const entry of source.list()) {
    let current: typeof entry | null = entry;
    for (const transform of transforms) {
      current = transform(current, target);
      if (current === null) break;
    }
    if (current === null) continue;

    const content = await source.read(current);
    await emitter.emit(current, content, target);
    vendored++;
  }

  process.stdout.write(`Vendored ${vendored} files.\n`);
  process.stdout.write(
    "Open this folder in Claude Code and run /spec to start.\n",
  );
  return 0;
}
