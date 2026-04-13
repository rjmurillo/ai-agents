export interface BundleEntry {
  relativePath: string;
  mode: number;
}

export interface TargetContext {
  root: string;
  force: boolean;
  dryRun: boolean;
}

export interface BundleSource {
  list(): AsyncIterable<BundleEntry>;
  read(entry: BundleEntry): Promise<Buffer>;
}

export interface TargetEmitter {
  canEmit(target: TargetContext): boolean;
  emit(entry: BundleEntry, target: TargetContext): Promise<void>;
}

export type Transform = (
  entry: BundleEntry,
  target: TargetContext
) => BundleEntry | null;
