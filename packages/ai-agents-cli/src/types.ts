export interface BundleEntry {
  relativePath: string;
  size: number;
}

export interface TargetContext {
  targetDir: string;
  force: boolean;
  dryRun: boolean;
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

export interface VersionPin {
  version: string;
  manifestHash: string;
  installedAt: string;
  source: string;
}

export interface InitResult {
  commands: number;
  agents: number;
  skills: number;
  filesWritten: string[];
}
