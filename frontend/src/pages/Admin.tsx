import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  api,
  ApiError,
  type OpenBidsConflict,
  type Tournament,
  type TournamentPreview,
} from '../lib/api';

function fmtDate(value: string | null | undefined) {
  if (!value) return '—';
  return new Date(value).toLocaleString();
}

function TournamentCard({ tournament }: { tournament: Tournament }) {
  return (
    <div className="space-y-2 text-sm">
      <div className="flex flex-wrap items-baseline gap-2">
        <h3 className="font-display font-semibold text-base sm:text-lg">
          {tournament.display_name || tournament.slug}
        </h3>
        <span className="text-xs uppercase tracking-wide px-2 py-0.5 rounded-full bg-primary/10 text-primary">
          {tournament.status}
        </span>
      </div>
      <p className="text-muted break-all">
        CricHeroes ID {tournament.cricheroes_id} ·{' '}
        <a
          href={tournament.base_url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary hover:underline"
        >
          {tournament.base_url}
        </a>
      </p>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-1">
        <div>
          <p className="text-xs text-muted uppercase">Teams</p>
          <p className="font-mono-num">{tournament.team_count}</p>
        </div>
        <div>
          <p className="text-xs text-muted uppercase">Matches</p>
          <p className="font-mono-num">{tournament.match_count}</p>
        </div>
        <div>
          <p className="text-xs text-muted uppercase">Activated</p>
          <p>{fmtDate(tournament.activated_at)}</p>
        </div>
        <div>
          <p className="text-xs text-muted uppercase">Last sync</p>
          <p>{fmtDate(tournament.last_sync_at)}</p>
        </div>
      </div>
    </div>
  );
}

function PreviewCard({ preview }: { preview: TournamentPreview }) {
  return (
    <div className="space-y-3 text-sm">
      <div>
        <h3 className="font-display font-semibold text-base">{preview.display_name}</h3>
        <p className="text-muted break-all">
          ID {preview.cricheroes_id} ·{' '}
          <a
            href={preview.base_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary hover:underline"
          >
            {preview.base_url}
          </a>
        </p>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div>
          <p className="text-xs text-muted uppercase">Teams</p>
          <p className="font-mono-num">{preview.teams.length}</p>
        </div>
        <div>
          <p className="text-xs text-muted uppercase">Matches</p>
          <p className="font-mono-num">{preview.match_count}</p>
        </div>
        <div>
          <p className="text-xs text-muted uppercase">Biddable</p>
          <p className="font-mono-num">{preview.biddable_count}</p>
        </div>
        <div>
          <p className="text-xs text-muted uppercase">Schedule</p>
          <p className="text-xs">
            {preview.earliest_start ? fmtDate(preview.earliest_start) : '—'}
            {preview.latest_start && preview.earliest_start !== preview.latest_start && (
              <> → {fmtDate(preview.latest_start)}</>
            )}
          </p>
        </div>
      </div>
      {Object.keys(preview.status_counts).length > 0 && (
        <div>
          <p className="text-xs text-muted uppercase mb-1">Match status</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(preview.status_counts).map(([status, count]) => (
              <span key={status} className="text-xs px-2 py-1 rounded-lg bg-black/5">
                {status}: <span className="font-mono-num">{count}</span>
              </span>
            ))}
          </div>
        </div>
      )}
      {preview.teams.length > 0 && (
        <div>
          <p className="text-xs text-muted uppercase mb-1">Teams</p>
          <p className="text-muted">{preview.teams.join(', ')}</p>
        </div>
      )}
    </div>
  );
}

function SyncStatusBadge({ status }: { status: string }) {
  const color =
    status === 'success'
      ? 'bg-positive/15 text-positive'
      : status === 'running'
        ? 'bg-accent/15 text-accent'
        : 'bg-negative/15 text-negative';
  return (
    <span className={`text-xs uppercase tracking-wide px-2 py-0.5 rounded-full ${color}`}>
      {status}
    </span>
  );
}

function isOpenBidsConflict(detail: unknown): detail is OpenBidsConflict {
  return (
    !!detail &&
    typeof detail === 'object' &&
    'requires_confirmation' in detail &&
    (detail as OpenBidsConflict).requires_confirmation === true
  );
}

export default function Admin() {
  const qc = useQueryClient();
  const [ref, setRef] = useState('');
  const [preview, setPreview] = useState<TournamentPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [activateError, setActivateError] = useState<string | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [openBidCount, setOpenBidCount] = useState<number | null>(null);

  const [requestMessage, setRequestMessage] = useState<string | null>(null);

  const currentQuery = useQuery({
    queryKey: ['admin', 'current-tournament'],
    queryFn: api.adminCurrentTournament,
  });

  const archivesQuery = useQuery({
    queryKey: ['admin', 'archives'],
    queryFn: api.adminArchivedTournaments,
  });

  const syncRunsQuery = useQuery({
    queryKey: ['admin', 'sync-runs'],
    queryFn: api.adminSyncRuns,
    refetchInterval: (query) => {
      if (requestMessage) return 5000;
      const runs = query.state.data;
      return runs?.some((r) => r.status === 'running') ? 3000 : false;
    },
  });

  const previewMutation = useMutation({
    mutationFn: (tournamentRef: string) => api.adminPreviewTournament(tournamentRef),
    onMutate: () => {
      setPreviewError(null);
      setPreview(null);
    },
    onSuccess: (data) => setPreview(data),
    onError: (err: ApiError) => setPreviewError(err.message),
  });

  const activateMutation = useMutation({
    mutationFn: ({ tournamentRef, confirm_reset }: { tournamentRef: string; confirm_reset: boolean }) =>
      api.adminActivateTournament(tournamentRef, confirm_reset),
    onMutate: () => setActivateError(null),
    onSuccess: () => {
      setConfirmOpen(false);
      setOpenBidCount(null);
      setPreview(null);
      setRef('');
      qc.invalidateQueries({ queryKey: ['admin'] });
    },
    onError: (err: ApiError) => {
      if (err.status === 409 && isOpenBidsConflict(err.detail)) {
        setOpenBidCount(err.detail.open_bid_count);
        setConfirmOpen(true);
        return;
      }
      setActivateError(err.message);
      if (err.status !== 409 || !isOpenBidsConflict(err.detail)) {
        setConfirmOpen(false);
      }
    },
  });

  const syncMutation = useMutation({
    mutationFn: api.adminTriggerSync,
    onMutate: () => setSyncError(null),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin'] }),
    onError: (err: ApiError) => setSyncError(err.message),
  });

  const requestSyncMutation = useMutation({
    mutationFn: api.adminRequestSync,
    onMutate: () => {
      setSyncError(null);
      setRequestMessage(null);
    },
    onSuccess: (data) => {
      setRequestMessage(data.message);
      qc.invalidateQueries({ queryKey: ['admin'] });
    },
    onError: (err: ApiError) => setSyncError(err.message),
  });

  const handlePreview = () => {
    const trimmed = ref.trim();
    if (!trimmed) {
      setPreviewError('Enter a CricHeroes tournament ID or URL');
      return;
    }
    previewMutation.mutate(trimmed);
  };

  const handleActivateClick = () => {
    const trimmed = ref.trim();
    if (!trimmed) {
      setActivateError('Enter a tournament ID or URL and preview first');
      return;
    }
    if (!preview) {
      setActivateError('Preview the tournament before activating');
      return;
    }
    setOpenBidCount(null);
    setActivateError(null);
    setConfirmOpen(true);
  };

  const handleConfirmActivate = () => {
    const trimmed = ref.trim();
    if (!trimmed) return;
    activateMutation.mutate({
      tournamentRef: trimmed,
      confirm_reset: openBidCount !== null,
    });
  };

  const current = currentQuery.data;

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div>
        <h1 className="font-display text-2xl sm:text-3xl font-bold">Admin</h1>
        <p className="text-muted text-sm mt-1">
          Manage the active CricHeroes tournament, sync fixtures, and review history.
        </p>
      </div>

      <section className="card p-4 sm:p-6 space-y-4">
        <h2 className="font-display font-semibold">Current tournament</h2>
        {currentQuery.isLoading && <p className="text-muted text-sm">Loading current tournament…</p>}
        {currentQuery.isError && (
          <p className="text-negative text-sm">Failed to load current tournament. Refresh to retry.</p>
        )}
        {!currentQuery.isLoading && !currentQuery.isError && !current && (
          <p className="text-muted text-sm">
            No active tournament configured. Preview and activate one below.
          </p>
        )}
        {current && <TournamentCard tournament={current} />}
      </section>

      <section className="card p-4 sm:p-6 space-y-4">
        <h2 className="font-display font-semibold">Switch tournament</h2>
        <p className="text-muted text-sm">
          Paste a CricHeroes tournament ID (e.g. <span className="font-mono-num">1691351</span>) or
          full tournament URL.
        </p>
        <div className="flex flex-col sm:flex-row gap-3">
          <input
            type="text"
            className="input flex-1"
            placeholder="Tournament ID or URL"
            value={ref}
            onChange={(e) => setRef(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handlePreview()}
          />
          <button
            type="button"
            className="btn-primary touch-target shrink-0"
            onClick={handlePreview}
            disabled={previewMutation.isPending}
          >
            {previewMutation.isPending ? 'Previewing…' : 'Preview'}
          </button>
        </div>
        {previewError && (
          <p className="text-negative text-sm" role="alert">
            {previewError}
          </p>
        )}
        {preview && (
          <div className="border border-border rounded-xl p-4 bg-black/[0.02] space-y-4">
            <PreviewCard preview={preview} />
            <button
              type="button"
              className="btn-primary touch-target"
              onClick={handleActivateClick}
              disabled={activateMutation.isPending}
            >
              Activate tournament
            </button>
          </div>
        )}
        {activateError && (
          <p className="text-negative text-sm" role="alert">
            {activateError}
          </p>
        )}
      </section>

      <section className="card p-4 sm:p-6 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
          <div>
            <h2 className="font-display font-semibold">Sync fixtures</h2>
            <p className="text-muted text-sm mt-1">
              CricHeroes blocks the cloud server. Leave the home-PC agent running (see
              scripts/install_sync_agent.ps1). Tap the button below from your phone and the PC
              scrapes, then upcoming matches and quizzes appear for everyone.
            </p>
          </div>
          <div className="flex flex-col sm:flex-row gap-2 shrink-0">
            <button
              type="button"
              className="btn-primary touch-target"
              onClick={() => requestSyncMutation.mutate()}
              disabled={requestSyncMutation.isPending || !current}
            >
              {requestSyncMutation.isPending ? 'Requesting…' : 'Sync from my PC'}
            </button>
            <button
              type="button"
              className="btn-ghost touch-target"
              onClick={() => syncMutation.mutate()}
              disabled={syncMutation.isPending || !current}
            >
              {syncMutation.isPending ? 'Scraping…' : 'Try server scrape'}
            </button>
          </div>
        </div>
        {!current && <p className="text-muted text-sm">Activate a tournament before syncing.</p>}
        {requestMessage && (
          <p className="text-sm text-positive" role="status">
            {requestMessage}
          </p>
        )}
        {syncError && (
          <p
            className={`text-sm ${syncMutation.error instanceof ApiError && syncMutation.error.status === 409 ? 'text-accent' : 'text-negative'}`}
            role="alert"
          >
            {syncError}
            {syncMutation.error instanceof ApiError && syncMutation.error.status === 409 && (
              <> — wait for the current operation to finish, then retry.</>
            )}
          </p>
        )}
      </section>

      <section className="card p-4 sm:p-6 space-y-4">
        <h2 className="font-display font-semibold">Recent sync runs</h2>
        {syncRunsQuery.isLoading && <p className="text-muted text-sm">Loading sync history…</p>}
        {syncRunsQuery.isError && (
          <p className="text-negative text-sm">Failed to load sync runs.</p>
        )}
        {!syncRunsQuery.isLoading && !syncRunsQuery.isError && syncRunsQuery.data?.length === 0 && (
          <p className="text-muted text-sm">No sync runs yet.</p>
        )}
        {!!syncRunsQuery.data?.length && (
          <>
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-muted border-b border-border">
                    <th className="pb-2 pr-4 font-medium">Started</th>
                    <th className="pb-2 pr-4 font-medium">Status</th>
                    <th className="pb-2 pr-4 font-medium">Seen</th>
                    <th className="pb-2 pr-4 font-medium">Updated</th>
                    <th className="pb-2 font-medium">Error</th>
                  </tr>
                </thead>
                <tbody>
                  {syncRunsQuery.data.map((run) => (
                    <tr key={run.id} className="border-b border-border/60 last:border-0">
                      <td className="py-2 pr-4 whitespace-nowrap">{fmtDate(run.started_at)}</td>
                      <td className="py-2 pr-4">
                        <SyncStatusBadge status={run.status} />
                      </td>
                      <td className="py-2 pr-4 font-mono-num">{run.matches_seen}</td>
                      <td className="py-2 pr-4 font-mono-num">{run.matches_updated}</td>
                      <td className="py-2 text-muted truncate max-w-[200px]">{run.error || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="md:hidden space-y-3">
              {syncRunsQuery.data.map((run) => (
                <div key={run.id} className="border border-border rounded-xl p-3 space-y-2 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-muted">{fmtDate(run.started_at)}</span>
                    <SyncStatusBadge status={run.status} />
                  </div>
                  <p>
                    Seen <span className="font-mono-num">{run.matches_seen}</span> · Updated{' '}
                    <span className="font-mono-num">{run.matches_updated}</span>
                  </p>
                  {run.error && <p className="text-negative text-xs">{run.error}</p>}
                </div>
              ))}
            </div>
          </>
        )}
      </section>

      <section className="card p-4 sm:p-6 space-y-4">
        <h2 className="font-display font-semibold">Archived tournaments</h2>
        {archivesQuery.isLoading && <p className="text-muted text-sm">Loading archives…</p>}
        {archivesQuery.isError && (
          <p className="text-negative text-sm">Failed to load archived tournaments.</p>
        )}
        {!archivesQuery.isLoading && !archivesQuery.isError && archivesQuery.data?.length === 0 && (
          <p className="text-muted text-sm">No archived tournaments yet.</p>
        )}
        <div className="space-y-4">
          {archivesQuery.data?.map((t) => (
            <div key={t.id} className="border border-border rounded-xl p-4">
              <TournamentCard tournament={t} />
              <p className="text-xs text-muted mt-2">Archived {fmtDate(t.archived_at)}</p>
            </div>
          ))}
        </div>
      </section>

      {confirmOpen && (
        <>
          <button
            type="button"
            className="fixed inset-0 z-40 bg-black/50"
            aria-label="Close confirmation"
            onClick={() => !activateMutation.isPending && setConfirmOpen(false)}
          />
          <div
            className="fixed inset-x-4 top-1/2 -translate-y-1/2 sm:inset-x-auto sm:left-1/2 sm:-translate-x-1/2 z-50 max-w-md w-full card p-5 sm:p-6 space-y-4 shadow-xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby="activate-confirm-title"
          >
            <h3 id="activate-confirm-title" className="font-display font-semibold text-lg">
              Confirm tournament activation
            </h3>
            {current && (
              <div className="text-sm space-y-2">
                <p>
                  The current tournament{' '}
                  <strong>{current.display_name || current.slug}</strong> will be archived.
                </p>
                <p className="text-muted">
                  All player points will reset to starting balances and streaks will be cleared for
                  the new season.
                </p>
              </div>
            )}
            {openBidCount !== null && (
              <p className="text-sm text-accent bg-accent/10 rounded-xl px-3 py-2">
                <strong>{openBidCount}</strong> open bid{openBidCount === 1 ? '' : 's'} exist on
                unsettled matches. Confirming will proceed anyway.
              </p>
            )}
            {!current && preview && (
              <p className="text-sm text-muted">
                Activate <strong>{preview.display_name}</strong> as the live tournament?
              </p>
            )}
            <div className="flex flex-col-reverse sm:flex-row gap-3 pt-1">
              <button
                type="button"
                className="btn-ghost touch-target flex-1"
                onClick={() => setConfirmOpen(false)}
                disabled={activateMutation.isPending}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn-primary touch-target flex-1 bg-negative hover:bg-negative/90"
                onClick={handleConfirmActivate}
                disabled={activateMutation.isPending}
              >
                {activateMutation.isPending
                  ? 'Activating…'
                  : openBidCount !== null
                    ? 'Confirm despite open bids'
                    : current
                      ? 'Archive & activate'
                      : 'Activate'}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
