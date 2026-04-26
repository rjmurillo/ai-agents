export class CliError extends Error {
  readonly cause_: string;
  readonly fix: string;
  readonly docs: string;

  constructor(opts: {
    error: string;
    cause: string;
    fix: string;
    docs?: string;
  }) {
    super(opts.error);
    this.name = "CliError";
    this.cause_ = opts.cause;
    this.fix = opts.fix;
    this.docs = opts.docs ?? "";
  }

  format(): string {
    const lines = [`error: ${this.message}`, `cause: ${this.cause_}`, `fix: ${this.fix}`];
    if (this.docs) {
      lines.push(`docs: ${this.docs}`);
    }
    return lines.join("\n");
  }
}

export class TargetNotEmptyError extends CliError {
  constructor(targetDir: string) {
    super({
      error: `Target .claude/ directory already exists and differs from vendor snapshot`,
      cause: `${targetDir}/.claude/ contains local modifications`,
      fix: `Re-run with --force to overwrite, or remove the directory first`,
    });
  }
}

export class TargetWriteError extends CliError {
  constructor(path: string, reason: string) {
    super({
      error: `Failed to write ${path}`,
      cause: reason,
      fix: `Check file permissions and available disk space`,
    });
  }
}
