/**
 * Pipeline interfaces for ai-agents init (REQ-1.7).
 *
 * Pipeline: BundleSource -> Transform[] -> TargetEmitter
 */

export type Target = "claude" | "copilot" | "both";

export interface BundleEntry {
  readonly relativePath: string;
  readonly category: "agent" | "command" | "skill" | "config" | "other";
}

export interface TargetContext {
  readonly target: Target;
  readonly destDir: string;
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
  content: Buffer,
  target: TargetContext,
) => { entry: BundleEntry; content: Buffer } | null;
