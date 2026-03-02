import type {
  HealthResult,
  RedactOptions,
  RedactResult,
  RedaktOptions,
} from "./types";

export type { HealthResult, RedactOptions, RedactResult, RedaktEntity, RedaktOptions } from "./types";

/** Redakt API client for medical document de-identification. */
export class Redakt {
  private readonly host: string;
  private readonly timeout: number;

  constructor(options: RedaktOptions = {}) {
    this.host = (options.host ?? "http://localhost:8080").replace(/\/$/, "");
    this.timeout = options.timeout ?? 300_000;
  }

  /** Check if the Redakt API server is healthy and ready. */
  async isHealthy(): Promise<boolean> {
    try {
      const result = await this.health();
      return result.status === "ok";
    } catch {
      return false;
    }
  }

  /** Get detailed health status from the server. */
  async health(): Promise<HealthResult> {
    const resp = await this._fetch("/api/health", { method: "GET" });
    return resp as HealthResult;
  }

  /**
   * Redact PII from text.
   *
   * @example
   * ```ts
   * const client = new Redakt();
   * const result = await client.redact("Ahmet Yilmaz, TC: 12345678901");
   * console.log(result.entities);       // [{original: "Ahmet Yilmaz", category: "name", ...}]
   * console.log(result.redacted_text);  // "████████████, TC: ███████████"
   * console.log(result.placeholder_text); // "[NAME_1], TC: [ID_1]"
   * ```
   */
  async redact(text: string, options?: RedactOptions): Promise<RedactResult> {
    const body: Record<string, string> = { text };
    if (options?.language) {
      body.language = options.language;
    }
    return (await this._fetch("/api/redact", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })) as RedactResult;
  }

  /**
   * Redact PII from a file (Buffer or Blob).
   *
   * @example
   * ```ts
   * import { readFileSync } from "fs";
   * const client = new Redakt();
   * const buf = readFileSync("report.pdf");
   * const result = await client.redactFile(buf, "report.pdf");
   * ```
   */
  async redactFile(
    file: Buffer | Blob | ArrayBuffer,
    filename: string,
    options?: RedactOptions
  ): Promise<RedactResult> {
    const formData = new FormData();

    if (typeof Buffer !== "undefined" && Buffer.isBuffer(file)) {
      formData.append("file", new Blob([file]), filename);
    } else if (file instanceof ArrayBuffer) {
      formData.append("file", new Blob([file]), filename);
    } else {
      formData.append("file", file, filename);
    }

    if (options?.language) {
      formData.append("language", options.language);
    }

    return (await this._fetch("/api/redact/file", {
      method: "POST",
      body: formData,
    })) as RedactResult;
  }

  private async _fetch(path: string, init: RequestInit): Promise<unknown> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeout);

    try {
      const resp = await fetch(`${this.host}${path}`, {
        ...init,
        signal: controller.signal,
      });

      if (!resp.ok) {
        const body = await resp.text();
        let message: string;
        try {
          message = JSON.parse(body).error ?? body;
        } catch {
          message = body;
        }
        throw new RedaktError(message, resp.status);
      }

      return await resp.json();
    } finally {
      clearTimeout(timer);
    }
  }
}

/** Error thrown by the Redakt client. */
export class RedaktError extends Error {
  readonly statusCode: number;

  constructor(message: string, statusCode: number) {
    super(message);
    this.name = "RedaktError";
    this.statusCode = statusCode;
  }
}
