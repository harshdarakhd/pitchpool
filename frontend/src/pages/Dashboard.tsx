import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, type Match, type MatchDetail } from '../lib/api';
import { CountdownTimer } from '../components/CountdownTimer';
import { PoolBar } from '../components/PoolBar';
import { useRealtime } from '../hooks/useRealtime';

const tabs = [
  { key: '', label: 'All' },
  { key: 'upcoming', label: 'Upcoming' },
  { key: 'awaiting', label: 'Awaiting Result' },
  { key: 'completed', label: 'Completed' },
];

export default function Dashboard() {
  useRealtime();
  const [tab, setTab] = useState('');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [bidAmount, setBidAmount] = useState('100');
  const [bidTeam, setBidTeam] = useState<number | null>(null);
  const [bidError, setBidError] = useState('');
  const qc = useQueryClient();

  const { data: matches = [], isLoading } = useQuery({
    queryKey: ['matches', tab],
    queryFn: () => api.matches(tab || undefined),
  });

  const { data: detail } = useQuery({
    queryKey: ['match', selectedId],
    queryFn: () => api.match(selectedId!),
    enabled: !!selectedId,
  });

  const { data: quiz = [] } = useQuery({
    queryKey: ['quiz', selectedId],
    queryFn: () => api.quiz(selectedId!),
    enabled: !!selectedId,
  });

  const handleBid = async () => {
    if (!selectedId || !bidTeam) return;
    setBidError('');
    try {
      await api.placeBid(selectedId, bidTeam, parseInt(bidAmount, 10));
      qc.invalidateQueries({ queryKey: ['match', selectedId] });
      qc.invalidateQueries({ queryKey: ['matches'] });
      setBidAmount('100');
    } catch (e) {
      setBidError(e instanceof Error ? e.message : 'Bid failed');
    }
  };

  const handleQuiz = async (questionId: number, option: string) => {
    await api.answerQuiz(questionId, option);
    qc.invalidateQueries({ queryKey: ['quiz', selectedId] });
  };

  const showList = !selectedId;
  const showDetail = !!selectedId;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[340px_1fr] gap-4 lg:gap-6 min-h-[calc(100dvh-5.5rem)] lg:h-[calc(100vh-120px)]">
      <aside
        className={`card flex flex-col overflow-hidden min-h-0 ${
          showDetail ? 'hidden lg:flex' : 'flex'
        }`}
      >
        <div className="flex gap-1 p-2 sm:p-3 border-b border-border overflow-x-auto scrollbar-none">
          {tabs.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={`shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium touch-target ${
                tab === t.key ? 'bg-primary text-white' : 'text-muted hover:bg-black/5'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-2">
          {isLoading && <p className="text-muted text-center py-8">Loading…</p>}
          {!isLoading && matches.length === 0 && (
            <div className="text-center py-8 px-3 space-y-2">
              <p className="text-muted text-sm">
                {tab === 'upcoming'
                  ? 'No scheduled fixtures right now. New matches appear here as soon as the organiser publishes them on CricHeroes.'
                  : 'No matches found'}
              </p>
              {tab !== '' && (
                <button
                  type="button"
                  onClick={() => setTab('')}
                  className="text-xs font-medium text-primary hover:underline touch-target"
                >
                  View all matches
                </button>
              )}
            </div>
          )}
          {matches.map((m: Match) => (
            <button
              key={m.id}
              type="button"
              onClick={() => setSelectedId(m.id)}
              className={`w-full text-left p-3 rounded-xl border transition-colors touch-target ${
                selectedId === m.id ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/40'
              }`}
            >
              <div className="font-display font-semibold">
                {m.team_a.short_name} vs {m.team_b.short_name}
              </div>
              <div className="text-xs text-muted mt-1">
                {m.stage_label ? `${m.stage_label} · ` : ''}
                {new Date(m.start_time).toLocaleDateString()}
              </div>
              {m.winner_team && (
                <div className="text-xs text-positive mt-1">{m.winner_team.short_name} won</div>
              )}
              {m.multiplier > 1 && (
                <span className="text-xs bg-accent/20 text-accent px-2 py-0.5 rounded mt-1 inline-block">
                  {m.multiplier}x
                </span>
              )}
            </button>
          ))}
        </div>
      </aside>

      <section
        className={`card p-4 sm:p-6 overflow-y-auto min-h-0 ${
          showList ? 'hidden lg:block' : 'block'
        }`}
      >
        {!detail ? (
          <div className="h-full min-h-[40vh] lg:min-h-0 flex flex-col items-center justify-center text-muted">
            <span className="text-4xl mb-4">⚡</span>
            <p className="font-display text-lg">Select a match</p>
          </div>
        ) : (
          <MatchDetailPanel
            detail={detail}
            quiz={quiz as { id: number; text: string; options: Record<string, string>; user_answer?: string }[]}
            bidAmount={bidAmount}
            setBidAmount={setBidAmount}
            bidTeam={bidTeam}
            setBidTeam={setBidTeam}
            bidError={bidError}
            onBid={handleBid}
            onQuiz={handleQuiz}
            onBack={() => setSelectedId(null)}
          />
        )}
      </section>
    </div>
  );
}

function MatchDetailPanel({
  detail,
  quiz,
  bidAmount,
  setBidAmount,
  bidTeam,
  setBidTeam,
  bidError,
  onBid,
  onQuiz,
  onBack,
}: {
  detail: MatchDetail;
  quiz: { id: number; text: string; options: Record<string, string>; user_answer?: string }[];
  bidAmount: string;
  setBidAmount: (v: string) => void;
  bidTeam: number | null;
  setBidTeam: (v: number) => void;
  bidError: string;
  onBid: () => void;
  onQuiz: (qid: number, opt: string) => void;
  onBack: () => void;
}) {
  const poolA = detail.pools.find((p) => p.team_id === detail.team_a.id);
  const poolB = detail.pools.find((p) => p.team_id === detail.team_b.id);

  return (
    <div className="space-y-6">
      <header>
        <button
          type="button"
          onClick={onBack}
          className="lg:hidden flex items-center gap-1 text-sm text-primary font-medium mb-3 touch-target -ml-1"
        >
          ← Back to matches
        </button>
        <h2 className="font-display text-xl sm:text-2xl font-bold">
          {detail.team_a.short_name} vs {detail.team_b.short_name}
        </h2>
        <p className="text-muted text-sm mt-1">
          {detail.venue} · {new Date(detail.start_time).toLocaleString()}
        </p>
        <div className="flex flex-wrap gap-3 mt-2 items-center">
          <span className="text-xs uppercase tracking-wide bg-black/5 px-2 py-1 rounded">{detail.status}</span>
          {detail.status === 'upcoming' && (
            <>Bid closes in <CountdownTimer deadline={detail.bid_deadline} /></>
          )}
        </div>
      </header>

      {detail.winner_team && (
        <div className="text-center py-4 bg-positive/10 rounded-xl">
          <p className="text-xs uppercase text-muted">Winner</p>
          <p className="font-display text-2xl font-bold text-positive">{detail.winner_team.short_name}</p>
        </div>
      )}

      <PoolBar
        teamA={{ name: detail.team_a.short_name, total: poolA?.total_wager ?? 0 }}
        teamB={{ name: detail.team_b.short_name, total: poolB?.total_wager ?? 0 }}
      />

      {detail.status === 'upcoming' && (
        <div className="border border-border rounded-xl p-4 space-y-3">
          <h3 className="font-display font-semibold">Place a bid</h3>
          <p className="text-xs text-muted">Up to 3 bids · Min 100 pts · 30% gap rule applies</p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setBidTeam(detail.team_a.id)}
              className={`flex-1 py-3 sm:py-2 rounded-lg border touch-target ${
                bidTeam === detail.team_a.id ? 'border-primary bg-primary/10' : 'border-border'
              }`}
            >
              {detail.team_a.short_name}
            </button>
            <button
              type="button"
              onClick={() => setBidTeam(detail.team_b.id)}
              className={`flex-1 py-3 sm:py-2 rounded-lg border touch-target ${
                bidTeam === detail.team_b.id ? 'border-primary bg-primary/10' : 'border-border'
              }`}
            >
              {detail.team_b.short_name}
            </button>
          </div>
          <input
            className="input font-mono-num"
            type="number"
            min={100}
            inputMode="numeric"
            value={bidAmount}
            onChange={(e) => setBidAmount(e.target.value)}
          />
          {bidError && <p className="text-negative text-sm">{bidError}</p>}
          <button type="button" className="btn-primary w-full sm:w-auto touch-target" onClick={onBid} disabled={!bidTeam}>
            Place bid
          </button>
        </div>
      )}

      {detail.user_bids.length > 0 && (
        <div className="space-y-2">
          <h3 className="font-display font-semibold">Your bids ({detail.user_bids.length})</h3>
          {detail.user_bids.map((b) => (
            <div key={b.id} className="flex justify-between text-sm font-mono-num bg-black/5 px-3 py-2 rounded-lg">
              <span>{b.team_id === detail.team_a.id ? detail.team_a.short_name : detail.team_b.short_name}</span>
              <span>{b.amount} pts</span>
            </div>
          ))}
        </div>
      )}

      {quiz.length > 0 && (
        <div className="space-y-3">
          <h3 className="font-display font-semibold">Quiz (+100 pts each)</h3>
          {quiz.map((q) => (
            <div key={q.id} className="border border-border rounded-xl p-4">
              <p className="text-sm mb-3">{q.text}</p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(q.options).map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => onQuiz(q.id, key)}
                    className={`px-3 py-2 rounded-lg text-sm border touch-target ${
                      q.user_answer === key ? 'border-positive bg-positive/10 text-positive' : 'border-border hover:border-primary'
                    }`}
                  >
                    {key}: {label}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
