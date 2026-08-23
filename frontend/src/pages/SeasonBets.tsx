import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';

const categories = [
  { key: 'winner', title: 'Tournament Winner', icon: '🏆', color: 'text-positive' },
  { key: 'orange_cap', title: 'Orange Cap (Runs)', icon: '🧡', color: 'text-negative' },
  { key: 'purple_cap', title: 'Purple Cap (Wickets)', icon: '💜', color: 'text-purple-600' },
];

export default function SeasonBets() {
  const qc = useQueryClient();
  const { data: bets = [] } = useQuery({ queryKey: ['season'], queryFn: api.seasonBets });
  const [picks, setPicks] = useState<Record<string, string>>({});

  const handleSubmit = async (category: string) => {
    const pick = picks[category];
    if (!pick) return;
    await api.placeSeasonBet(category, pick);
    qc.invalidateQueries({ queryKey: ['season'] });
  };

  return (
    <div className="space-y-8">
      <header className="text-center">
        <h1 className="font-display text-3xl font-bold">Season Bets</h1>
        <p className="text-muted">Long-term predictions · The clock is ticking</p>
        <p className="text-sm text-negative mt-2">Cap decays ~90 pts/day — bet early for max upside</p>
      </header>

      <div className="grid md:grid-cols-3 gap-6">
        {categories.map((cat) => {
          const existing = (bets as { category: string; pick: string; locked_cap: number; result: string }[]).find(
            (b) => b.category === cat.key,
          );
          return (
            <SeasonCard
              key={cat.key}
              cat={cat}
              existing={existing}
              pick={picks[cat.key] ?? ''}
              onPickChange={(v) => setPicks((p) => ({ ...p, [cat.key]: v }))}
              onSubmit={() => handleSubmit(cat.key)}
            />
          );
        })}
      </div>
    </div>
  );
}

function SeasonCard({
  cat,
  existing,
  pick,
  onPickChange,
  onSubmit,
}: {
  cat: (typeof categories)[0];
  existing?: { pick: string; locked_cap: number; result: string };
  pick: string;
  onPickChange: (v: string) => void;
  onSubmit: () => void;
}) {
  const { data: community = [] } = useQuery({
    queryKey: ['season-community', cat.key],
    queryFn: () => api.seasonCommunity(cat.key),
  });

  return (
    <div className="card p-5 space-y-4">
      <div className="flex items-center gap-2">
        <span className="text-2xl">{cat.icon}</span>
        <h2 className={`font-display font-semibold ${cat.color}`}>{cat.title}</h2>
        <span className="text-xs bg-positive/10 text-positive px-2 py-0.5 rounded ml-auto">Free entry</span>
      </div>

      {existing ? (
        <div className="bg-black/5 rounded-xl p-4">
          <p className="text-xs text-muted">Your pick (locked)</p>
          <p className="font-medium">{existing.pick}</p>
          <p className="font-mono-num text-positive text-sm mt-1">Cap: {existing.locked_cap.toLocaleString()} pts</p>
          {existing.result !== 'pending' && (
            <p className={existing.result === 'won' ? 'text-positive' : 'text-negative'}>{existing.result}</p>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          <input
            className="input"
            placeholder="Enter your pick…"
            value={pick}
            onChange={(e) => onPickChange(e.target.value)}
          />
          <button type="button" className="btn-primary w-full" onClick={onSubmit}>
            Lock pick
          </button>
        </div>
      )}

      {community.length > 0 && (
        <div>
          <p className="text-xs uppercase text-muted mb-2">Community picks</p>
          <div className="space-y-2">
            {community.slice(0, 5).map((c) => (
              <div key={c.pick}>
                <div className="flex justify-between text-xs mb-1">
                  <span className="truncate">{c.pick}</span>
                  <span className="font-mono-num">{c.pct}%</span>
                </div>
                <div className="h-1.5 bg-border rounded-full overflow-hidden">
                  <div className="h-full bg-primary" style={{ width: `${c.pct}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
