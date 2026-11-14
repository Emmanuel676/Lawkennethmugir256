// Typed client for the FairLend Watch API (../api). Every number on screen comes from here.
// By default the browser calls /api/* on this web app's own origin and Next.js forwards it to the API
// (next.config.ts), so the session cookie stays first-party. NEXT_PUBLIC_API_URL overrides it (read-only demo use).

export const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

export type BandKey = "high" | "medium" | "low";
export interface Band { key: BandKey; label: string }
export interface Money { amount: number | null; exact: string; compact: string }

export interface DatasetInfo {
  name: string; slug: string; kind: "demo" | "imported"; label: string; demonstration: boolean; as_of_date: string;
  notice: string; trust_line: string; classifier: string; currency: string;
}

export interface Meta {
  product: { name: string; tagline: string };
  dataset: DatasetInfo;
  trust_line: string;
  review_line: string;
  presentation_mode: boolean;
  read_only: boolean;
  bands: (Band & { min_score: number })[];
  message_classes: { key: string; label: string; description: string; abusive: boolean }[];
  glossary: Record<string, string>;
}

export interface TopBorrower {
  borrower_id: string; score: number; band: Band; open_lenders: number; total_owed: Money; abusive_messages: number;
}

export interface Overview {
  dataset: DatasetInfo;
  trust_line: string;
  kpis: {
    borrowers_scored: number;
    band_counts: Record<BandKey, number>;
    band_shares: Record<BandKey, number>;
    owed_by_high_band: Money;
    messages_classified: number;
    abusive_message_share: number;
    lenders_ranked: number;
    lenders_unranked: number;
    flagged_and_harassed: number;
    concern_min_abusive_messages: number;
  };
  bands: (Band & { borrowers: number; share: number })[];
  top_n: number;
  top_borrowers: TopBorrower[];
  coverage: string;
}

export interface BorrowerRow {
  borrower_id: string; score: number; band: Band; placed_in_medium_by_cycling: boolean; region: string;
  open_lenders: number; total_owed: Money; debt_to_income: number; abusive_messages: number;
  late_night_messages: number; third_party_messages: number;
}

export interface BorrowerList {
  total: number; matching: number; page: number; pages: number; page_size: number; sort: string;
  order: "asc" | "desc"; sortable: string[]; regions: string[]; items: BorrowerRow[];
}

export interface BorrowerDetail {
  borrower_id: string; score: number; band: Band; placed_in_medium_by_cycling: boolean; region: string;
  open_lenders: number; total_owed: Money; monthly_income: Money; debt_to_income: number; arrears_share: number;
  cycling_events: number; recent_loans: number; abusive_messages: number; explanation: string[];
  points: { key: string; signal: string; points: number; max_points: number; description: string }[];
  lenders_involved: number;
  loans: { loan_id: string; lender: string; principal: Money; owed: Money; issue_date: string; due_date: string;
           status: string }[];
  messages: { message_id: string; sent_at: string; lender: string;
              label: { key: string; label: string; abusive: boolean }; label_from: string; late_night: boolean;
              third_party: boolean; recipient_type: string; text: string }[];
  classifier: string;
}

export interface LenderRow {
  rank: number | null; lender_id: string; name: string; size: string; messages: number; too_small: boolean;
  reason: string | null; abusive_share: number; interval_low: number; interval_high: number; threat_share: number;
  shaming_share: number; third_party_share: number; late_night_share: number; messages_per_borrower: number;
}

export interface Lenders {
  confidence: number; min_messages: number; coverage: string; ranked: LenderRow[]; unranked: LenderRow[];
}

export interface LenderDetail extends LenderRow {
  sentence: string;
  examples: { class: { key: string; label: string };
              messages: { message_id: string; sent_at: string; recipient_type: string; text: string }[] }[];
}

export interface StatusShare { key: string; label: string; loans: number; share: number; follow_up: boolean }

export interface Repayments {
  dataset: DatasetInfo; trust_line: string; owed_note: string; prompt: string; lump: boolean; loans: number;
  statuses: StatusShare[]; owed_unpaid: Money; owed_follow_up: Money; owed_not_yet_due: Money;
  owed_past_due: Money; owed_in_grace: Money; grace_days: number;
  not_paying_after_days: number; min_loans_to_compare: number;
  ageing: { bucket: string; loans: number; owed: Money }[];
  lender_mix: { lender_id: string; name: string; loans: number; comparable: boolean;
                shares: Record<string, number> }[];
  worst_status: { key: string; label: string; borrowers: number }[];
  follow_up_borrowers: number;
  limits: string[];
}

export interface FollowUpRow {
  borrower_id: string; lenders_overdue: string; status: { key: string; label: string }; days_past_due: number;
  owed_overdue: Money; owed_all_loans: Money; loans_overdue: number; band: Band | null; open_lenders: number | null;
}

export interface FollowUp {
  matching: number; page: number; pages: number; page_size: number; sort: string; order: "asc" | "desc";
  sortable: string[];
  options: { lenders: string[]; statuses: { key: string; label: string }[]; bands: Band[] };
  items: FollowUpRow[];
}

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

export type Params = Record<string, string | number | undefined | null>;

export function apiUrl(path: string, params?: Params): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params ?? {})) {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  }
  const text = query.toString();
  return `${API_BASE}${path}${text ? `?${text}` : ""}`;
}

async function send(path: string, init: RequestInit, params?: Params): Promise<Response> {
  try {
    return await fetch(apiUrl(path, params), { credentials: "same-origin", ...init });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError("The data service is not reachable. Is the API running? (see docs/UI_V2.md)", 0);
  }
}

async function readError(response: Response): Promise<ApiError> {
  let detail = `The data service answered ${response.status}.`;
  if (response.status === 401) detail = "Sign in to see this.";
  if (response.status === 403) detail = "Your role does not allow this. Ask an Admin if you need it.";
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") detail = body.detail;
  } catch {
    /* keep the generic message */
  }
  return new ApiError(detail, response.status);
}

/** POST/PATCH/DELETE with a JSON body. The browser adds the Origin header the API checks. */
export async function sendJson<T>(method: "POST" | "PATCH" | "DELETE", path: string, body?: unknown): Promise<T> {
  const response = await send(path, {
    method, headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw await readError(response);
  return (await response.json()) as T;
}

/** POST a multipart form (file uploads). */
export async function sendForm<T>(path: string, form: FormData): Promise<T> {
  const response = await send(path, { method: "POST", headers: { Accept: "application/json" }, body: form });
  if (!response.ok) throw await readError(response);
  return (await response.json()) as T;
}

export async function getJson<T>(path: string, params?: Params, signal?: AbortSignal): Promise<T> {
  const response = await send(path, { signal, headers: { Accept: "application/json" } }, params);
  if (!response.ok) throw await readError(response);
  return (await response.json()) as T;
}

// --- Phase 12B: sign-in, datasets, import, users, audit ---------------------------------------------------------

export type Role = "viewer" | "importer" | "admin";
export const ROLE_RANK: Record<Role, number> = { viewer: 0, importer: 1, admin: 2 };
export const ROLE_LABEL: Record<Role, string> = { viewer: "Viewer", importer: "Importer", admin: "Admin" };

export interface User {
  id: number; email: string; role: Role; disabled: boolean; created_at: number; created_by: string; locked: boolean;
}
export interface Me { user: User | null; roles: Role[] }

export interface DatasetEntry {
  slug: string; name: string; kind: "demo" | "imported"; label: string; notes: string; source: string;
  added_by: string; added_at: number | null; updated_at: number | null; as_of_date: string;
  counts: Record<string, number>; imports: number; deletable: boolean;
}
export interface DatasetList { datasets: DatasetEntry[]; can_import: boolean; can_delete: boolean }
export interface DatasetDetail extends DatasetEntry {
  health: { borrowers: number; shared_borrowers: number; min_messages: number;
            per_lender: Record<string, string | number>[] };
}

export interface Issue { location: string; message: string; text: string }
export interface ImportOutcome {
  stage: "refused" | "invalid" | "valid" | "imported" | "failed";
  reasons: string[]; message: string; dataset: string; already_known: number; suggested_as_of: string;
  report: null | {
    ok: boolean; counts: Record<string, number>; as_of_date: string; errors_total: number; warnings_total: number;
    errors: Issue[]; warnings: Issue[]; notes: Issue[]; found: Record<string, number>; already_known: number;
  };
  record?: DatasetEntry | null;
}
export interface ImportInfo {
  permission_text: string; limits: { max_upload_mb: number; max_rows_per_file: number };
  day_first_default: boolean; targets: { slug: string; name: string }[]; label: string;
}

export interface UserList { users: User[]; roles: Role[]; password_min_length: number }
export interface AuditEntry {
  id: number; at: number; actor: string; action: string; action_label: string; target: string;
  detail: Record<string, unknown>;
}
export interface AuditPage { total: number; page: number; page_size: number; pages: number; entries: AuditEntry[] }


// --- Phase 12C: Guided Demo, About, Export, Review labels -------------------------------------------------------

export interface GuidedCase {
  step: number; key: string; title: string; kind: "borrower" | "lender"; id: string; say: string;
  counts?: { messages: number; abusive: number; abusive_late_night: number; abusive_third_party: number };
}
export interface GuidedDemo { available: boolean; reason: string; opening: string[]; cases: GuidedCase[]; missing: string[] }

export interface About {
  product: { name: string; tagline: string }; dataset: DatasetInfo;
  signals: { key: string; signal: string; measures: string; full_at: number; weight: number }[];
  bands: { medium: number; high: number }; cycling_rule: { min_events: number } | null;
  classes: { key: string; label: string; description: string; abusive: boolean }[];
  label_note: string; classifier: string; human_share: number; min_lender_messages: number; confidence: number;
  review_line: string;
}

export interface ExportSummary {
  dataset: DatasetInfo; notice: string; flagged_borrowers: number; lenders: number; follow_up_borrowers: number;
  classifier: string;
}

export interface ReviewSummary {
  available: boolean; reason?: string;
  messages: number; reviewed: number; share_reviewed: number;
  per_batch: Record<string, number>; per_class: Record<string, number>;
  accuracy: { ok: boolean; sentence: string; n: number; accuracy: number | null; low: number | null; high: number | null;
              per_class: { class: string; checked: number; model_right: number; recall: number | null;
                           low: number | null; high: number | null }[] };
  classes: string[]; kinds: Record<string, string>; default_size: number; show_model_label: boolean;
}
export interface ReviewMessage {
  message_id: string; text: string; sent_at: string; recipient_type: string; lender: string;
  model_label: string | null; model_confidence: number | null;
}
