// Which harness instruction file(s) the inline block is appended to.
// "claude" writes CLAUDE.md, "copilot" writes .github/copilot-instructions.md,
// "both" writes both.
export type Target = "claude" | "copilot" | "both";

export const TARGETS: readonly Target[] = ["claude", "copilot", "both"];

export interface BundleEntry {
  readonly relativePath: string;
  readonly size: number;
}

export interface TargetContext {
  readonly targetDir: string;
  readonly force: boolean;
  readonly dryRun: boolean;
}

export interface VersionPin {
  readonly version: string;
  readonly manifestHash: string;
  readonly installedAt: string;
  readonly source: string;
  // SHA-256 hex of each vendored file's content at install time, keyed by
  // path relative to .claude/. Absent in pins written before issue #7218.
  readonly files?: Readonly<Record<string, string>>;
}

export interface BundleSource {
  list(): AsyncIterable<BundleEntry>;
  read(entry: BundleEntry): Promise<Buffer>;
}

export interface TargetEmitter {
  // True when the destination file exists with content that differs from both
  // the incoming content and the content recorded at the last install.
  diverges(
    entry: BundleEntry,
    content: Buffer,
    target: TargetContext,
  ): Promise<boolean>;
  emit(entry: BundleEntry, content: Buffer, target: TargetContext): Promise<void>;
}

export type Transform = (
  entry: BundleEntry,
  target: TargetContext,
) => BundleEntry | null;
