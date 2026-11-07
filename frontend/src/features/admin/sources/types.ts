export type SourceKind = "sgk" | "de";
export type SourceStatus = "loaded" | "loading" | "pending" | "failed";

export interface Source {
  id: string;
  name: string;
  kind: SourceKind;
  subject: string;
  grade: number;
  official: boolean;
  status: SourceStatus;
}

export interface NewSource {
  name: string;
  kind: SourceKind;
  subject: string;
  grade: number;
  official: boolean;
  filename: string;
}

export interface Coverage {
  covered: number; // lessons that have at least one chunk
  total: number; // lessons in the textbook outline
}

export interface CoverageCheck {
  ok: boolean;
  missing: number;
  ref: string; // test-case id the check mirrors
}
