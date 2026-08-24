const API_BASE = import.meta.env.VITE_API_URL || '';

export interface User {
  id: number;
  email: string;
  display_name: string;
  role: string;
  points_balance: number;
  starting_balance: number;
  created_at: string;
}

export interface Team {
  id: number;
  name: string;
  short_name: string;
  logo_url?: string;
}

export interface Match {
  id: number;
  stage: string;
  stage_label?: string;
  status: string;
  venue?: string;
  start_time: string;
  bid_deadline: string;
  multiplier: number;
  team_a: Team;
  team_b: Team;
  winner_team?: Team;
  result_raw?: string;
}

export interface MatchDetail extends Match {
  pools: { team_id: number; team: Team; total_wager: number; bidder_count: number }[];
  user_bid_count: number;
  user_bids: { id: number; team_id: number; amount: number; created_at: string }[];
}

export function clearToken() {
  // Remove tokens left by pre-cookie builds. Authentication now lives only in
  // HttpOnly same-origin cookies so JavaScript and URLs never expose the JWT.
  localStorage.removeItem('access_token');
}

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(message: string, status: number, detail?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

export interface OpenBidsConflict {
  message: string;
  open_bid_count: number;
  requires_confirmation: true;
}

export interface Tournament {
  id: number;
  cricheroes_id: number;
  slug: string;
  base_url: string;
  display_name: string | null;
  status: string;
  team_count: number;
  match_count: number;
  activated_at: string | null;
  activated_by_user_id: number | null;
  archived_at: string | null;
  archived_by_user_id: number | null;
  last_sync_at: string | null;
  created_at: string;
}

export interface TournamentPreview {
  cricheroes_id: number;
  slug: string;
  base_url: string;
  display_name: string;
  teams: string[];
  match_count: number;
  status_counts: Record<string, number>;
  biddable_count: number;
  earliest_start: string | null;
  latest_start: string | null;
}

export interface TournamentActivateResult {
  tournament: Tournament;
  sync_status: string;
  matches_seen: number;
  matches_updated: number;
}

export interface SyncRun {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: string;
  matches_seen: number;
  matches_updated: number;
  error: string | null;
}

function formatApiError(status: number, detail: unknown): ApiError {
  if (typeof detail === 'string') {
    return new ApiError(detail, status, detail);
  }
  if (detail && typeof detail === 'object' && 'message' in detail) {
    const message = String((detail as { message: string }).message);
    return new ApiError(message, status, detail);
  }
  return new ApiError('Request failed', status, detail);
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };

  let res = await fetch(`${API_BASE}${path}`, { ...options, headers, credentials: 'include' });

  if (res.status === 401 && !path.includes('/auth/')) {
    const refreshed = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
      method: 'POST',
      credentials: 'include',
    });
    if (refreshed.ok) {
      res = await fetch(`${API_BASE}${path}`, { ...options, headers, credentials: 'include' });
    }
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw formatApiError(res.status, err.detail);
  }
  return res.json();
}

export const api = {
  register: (email: string, password: string, display_name: string) =>
    request<User>('/api/v1/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, display_name }),
    }),
  login: async (email: string, password: string) => {
    const data = await request<{ access_token: string }>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    clearToken();
    return data;
  },
  logout: () => request('/api/v1/auth/logout', { method: 'POST' }).then(clearToken),
  me: () => request<User>('/api/v1/auth/me'),
  matches: (status?: string) =>
    request<Match[]>(`/api/v1/matches${status ? `?status=${status}` : ''}`),
  match: (id: number) => request<MatchDetail>(`/api/v1/matches/${id}`),
  bidHints: (matchId: number) => request<Record<string, unknown>>(`/api/v1/bids/hints/${matchId}`),
  placeBid: (match_id: number, team_id: number, amount: number) =>
    request('/api/v1/bids', { method: 'POST', body: JSON.stringify({ match_id, team_id, amount }) }),
  quiz: (matchId: number) => request<unknown[]>(`/api/v1/predictions/quiz/${matchId}`),
  answerQuiz: (question_id: number, chosen_option: string) =>
    request('/api/v1/predictions/quiz/answer', {
      method: 'POST',
      body: JSON.stringify({ question_id, chosen_option }),
    }),
  seasonBets: () => request<unknown[]>('/api/v1/predictions/season'),
  placeSeasonBet: (category: string, pick: string) =>
    request('/api/v1/predictions/season', {
      method: 'POST',
      body: JSON.stringify({ category, pick }),
    }),
  seasonCommunity: (category: string) =>
    request<{ pick: string; count: number; pct: number }[]>(
      `/api/v1/predictions/season/community/${category}`,
    ),
  leaderboard: () => request<unknown[]>('/api/v1/leaderboard'),
  profileStats: () => request<unknown>('/api/v1/profile/stats'),
  transactions: (type?: string) =>
    request<unknown[]>(`/api/v1/profile/transactions${type && type !== 'all' ? `?tx_type=${type}` : ''}`),
  bidders: (matchId: number) => request<unknown[]>(`/api/v1/matches/${matchId}/bidders`),

  adminCurrentTournament: () =>
    request<Tournament | null>('/api/v1/admin/tournaments/current'),
  adminPreviewTournament: (ref: string) =>
    request<TournamentPreview>('/api/v1/admin/tournaments/preview', {
      method: 'POST',
      body: JSON.stringify({ ref }),
    }),
  adminActivateTournament: (ref: string, confirm_reset = false) =>
    request<TournamentActivateResult>('/api/v1/admin/tournaments/activate', {
      method: 'POST',
      body: JSON.stringify({ ref, confirm_reset }),
    }),
  adminArchivedTournaments: () =>
    request<Tournament[]>('/api/v1/admin/tournaments/archives'),
  adminSyncRuns: () => request<SyncRun[]>('/api/v1/admin/sync/runs'),
  adminTriggerSync: () =>
    request<SyncRun>('/api/v1/admin/sync', { method: 'POST' }),
  adminRequestSync: () =>
    request<{ ok: boolean; message: string }>('/api/v1/admin/sync/request', { method: 'POST' }),
};
