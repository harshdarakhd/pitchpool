import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';
import { useRealtime } from '../hooks/useRealtime';

type Entry = {
  rank: number;
  display_name: string;
  points_balance: number;
  win_rate: number;
  current_streak: number;
  best_streak: number;
  badge_count: number;
};

export default function Leaderboard() {
  useRealtime();
  const [tab, setTab] = useState<'rankings' | 'streaks'>('rankings');
  const [search, setSearch] = useState('');
  const { data: entries = [], isLoading } = useQuery({
    queryKey: ['leaderboard'],
    queryFn: () => api.leaderboard() as Promise<Entry[]>,
  });

  const filtered = entries.filter((e) =>
    e.display_name.toLowerCase().includes(search.toLowerCase()),
  );

  const top3 = filtered.slice(0, 3);
  const sorted =
    tab === 'streaks'
      ? [...filtered].sort((a, b) => b.current_streak - a.current_streak)
      : filtered;

  return (
    <div className="space-y-6 sm:space-y-8">
      <header className="text-center">
        <h1 className="font-display text-2xl sm:text-3xl font-bold text-primary">Leaderboard</h1>
        <p className="text-muted text-sm sm:text-base">Top predictors this season</p>
      </header>

      {top3.length >= 3 && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4 max-w-2xl mx-auto sm:items-end">
          {[top3[1], top3[0], top3[2]].map((e, i) => (
            <div
              key={e.rank}
              className={`card p-4 text-center order-none ${
                i === 1 ? 'sm:scale-105 sm:border-primary sm:order-none' : ''
              } ${i === 0 ? 'sm:order-1' : i === 1 ? 'sm:order-2 order-first' : 'sm:order-3'}`}
            >
              <div className="text-2xl mb-2">{['🥈', '🥇', '🥉'][i]}</div>
              <p className="font-display font-semibold truncate">{e.display_name}</p>
              <p className="font-mono-num text-lg text-primary">{e.points_balance.toLocaleString()}</p>
              <p className="text-xs text-muted">{e.current_streak} streak</p>
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-2 justify-center flex-wrap">
        {(['rankings', 'streaks'] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-xl text-sm capitalize touch-target ${
              tab === t ? 'bg-primary text-white' : 'bg-black/5 text-muted'
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <input
        className="input max-w-sm mx-auto block"
        placeholder="Search by name…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      <div className="md:hidden space-y-2">
        {isLoading && <p className="text-muted text-center py-8">Loading…</p>}
        {sorted.map((e) => (
          <div key={e.rank} className="card p-4 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-3 min-w-0">
                <span className="font-mono-num text-lg text-muted shrink-0">#{e.rank}</span>
                <span className="font-medium truncate">{e.display_name}</span>
              </div>
              <span className="font-mono-num text-primary font-semibold shrink-0">
                {e.points_balance.toLocaleString()}
              </span>
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
              <span>Win {e.win_rate}%</span>
              <span>Streak {e.current_streak} (best {e.best_streak})</span>
              <span>{e.badge_count} badges</span>
            </div>
          </div>
        ))}
      </div>

      <div className="card overflow-hidden hidden md:block">
        <table className="w-full text-sm">
          <thead className="bg-black/5 text-left">
            <tr>
              <th className="p-3">#</th>
              <th className="p-3">Player</th>
              <th className="p-3">Points</th>
              <th className="p-3">Win %</th>
              <th className="p-3">Streak</th>
              <th className="p-3">Badges</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={6} className="p-8 text-center text-muted">Loading…</td></tr>
            )}
            {sorted.map((e) => (
              <tr key={e.rank} className="border-t border-border">
                <td className="p-3 font-mono-num">{e.rank}</td>
                <td className="p-3 font-medium">{e.display_name}</td>
                <td className="p-3 font-mono-num">{e.points_balance.toLocaleString()}</td>
                <td className="p-3">{e.win_rate}%</td>
                <td className="p-3">{e.current_streak} (best {e.best_streak})</td>
                <td className="p-3">{e.badge_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
