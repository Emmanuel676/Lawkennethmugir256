// Typed client for the read-only FairLend Watch API (../api). Every number on screen comes from here.
// The API address is a setting: NEXT_PUBLIC_API_URL (default http://127.0.0.1:8000).

export const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

export type BandKey = "high" | "medium" | "low";
export interface Band { key: BandKey; label: string }
export interface Money { amount: number | null; exact: string; compact: string }

export interface DatasetInfo {
  name: string; slug: string; kind: string; synthetic: boolean; as_of_date: string; notice: string;
  classifier: string; currency: string;
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
  statuses: StatusShare[]; owed_unpaid: Money; owed_follow_up: Money; grace_days: number;
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

export async function getJson<T>(path: string, params?: Params, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiUrl(path, params), { signal, headers: { Accept: "application/json" } });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError(
      `The data service is not reachable at ${API_BASE}. Is the API running? (see docs/UI_V2.md)`, 0);
  }
  if (!response.ok) {
    let detail = `The data service answered ${response.status}.`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* keep the generic message */
    }
    throw new ApiError(detail, response.status);
  }
  return (await response.json()) as T;
}
