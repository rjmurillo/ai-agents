export interface BundleEntry {
  readonly relativePath: string;
  readonly size: number;
}

export interface TargetContext {
  readonly targetDir: string;
  readonly force: boolean;
}

export interface BundleSource {
  list(): AsyncIterable<BundleEntry>;
  read(entry: BundleEntry): Promise<Buffer>;
}

export interface TargetEmitter {
  canEmit(target: TargetContext): boolean;
  emit(entry: BundleEntry, content: Buffer, target: TargetContext): Promise<void>;
}

export type Transform = (
  entry: BundleEntry,
  target: TargetContext,
) => BundleEntry | null;
