/** Configuration options for the Redakt client. */
export interface RedaktOptions {
  /** Base URL of the Redakt API server. Default: "http://localhost:8080" */
  host?: string;
  /** Request timeout in milliseconds. Default: 300000 (5 minutes) */
  timeout?: number;
}

/** A detected PII entity. */
export interface RedaktEntity {
  /** The original text that was identified as PII. */
  original: string;
  /** Category of PII: name, date, id, address, phone, email, institution, age. */
  category: string;
  /** Replacement placeholder, e.g. "[NAME_1]", "[TARIH_2]". */
  placeholder: string;
  /** Confidence score (0-1). */
  confidence: number;
  /** Raw subcategory from the LLM. */
  subcategory: string;
}

/** Response from the /api/redact endpoint. */
export interface RedactResult {
  /** List of detected PII entities. */
  entities: RedaktEntity[];
  /** Text with PII replaced by unicode block characters. */
  redacted_text: string;
  /** Text with PII replaced by [PLACEHOLDER] tags. */
  placeholder_text: string;
  /** Number of entities detected. */
  entity_count: number;
  /** Original filename (only present for file uploads). */
  filename?: string;
}

/** Response from the /api/health endpoint. */
export interface HealthResult {
  status: "ok" | "starting";
  service: string;
  version: string;
}

/** Options for the redact method. */
export interface RedactOptions {
  /** Override the default language for this request. */
  language?: "tr" | "en";
}
