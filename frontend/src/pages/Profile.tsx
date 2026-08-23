import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';

const txFilters = ['all', 'bid', 'payout', 'penalty', 'quiz', 'streak_bonus', 'season'];

export default function Profile() {
  const [filter, setFilter] = useState('all');
  const { data: stats } = useQuery({ queryKey: ['profile-stats'], queryFn: api.profileStats });
  const { data: txs = [] } = useQuery({
    queryKey: ['transactions', filter],
    queryFn: () => api.transactions(filter),
  });

  const s = stats as {
    user: { display_name: string; email: string; points_balance: number };
    win_rate: number;
    wins: number;
    net_profit: number;
    current_streak: number;
    best_streak: number;
    badges: { icon: string; name: string }[];
    streak_milestones: { wins: number; bonus: number }[];
  } | undefined;

  if (!s) return <p className="text-muted text-center py-12">Loading profile…</p>;

  const transactions = txs as { created_at: string; description: string; delta: number; balance_after: number }[];

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div className="card p-4 sm:p-6 flex flex-col sm:flex-row sm:items-center gap-4">
        <div className="flex items-center gap-4 min-w-0">
          <div className="w-14 h-14 sm:w-16 sm:h-16 rounded-full bg-primary/20 flex items-center justify-center font-display text-xl sm:text-2xl font-bold text-primary shrink-0">
            {s.user.display_name[0]?.toUpperCase()}
          </div>
          <div className="min-w-0">
            <h1 className="font-display text-xl sm:text-2xl font-bold truncate">{s.user.display_name}</h1>
            <p className="text-muted text-sm truncate">{s.user.email}</p>
          </div>
        </div>
        <div className="sm:ml-auto font-mono-num text-xl sm:text-2xl text-primary">
          {s.user.points_balance.toLocaleString()} pts
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        {[
          { label: 'Win Rate', value: `${s.win_rate}%`, color: 'text-positive' },
          { label: 'Wins', value: s.wins, color: 'text-positive' },
          { label: 'Net Profit', value: `${s.net_profit >= 0 ? '+' : ''}${s.net_profit}`, color: s.net_profit >= 0 ? 'text-positive' : 'text-negative' },
          { label: 'Streak', value: `${s.current_streak} (best ${s.best_streak})`, color: 'text-primary' },
        ].map((k) => (
          <div key={k.label} className="card p-3 sm:p-4 text-center">
            <p className="text-xs text-muted uppercase">{k.label}</p>
            <p className={`font-mono-num text-lg sm:text-xl font-semibold mt-1 ${k.color}`}>{k.value}</p>
          </div>
        ))}
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <div className="card p-4 sm:p-5">
          <h2 className="font-display font-semibold mb-3">Streak Bonuses</h2>
          <div className="flex flex-wrap gap-2">
            {s.streak_milestones.map((m) => (
              <span
                key={m.wins}
                className={`text-xs px-2 py-1 rounded ${
                  s.current_streak >= m.wins ? 'bg-positive/20 text-positive' : 'bg-black/5 text-muted'
                }`}
              >
                {m.wins}W +{m.bonus}
              </span>
            ))}
          </div>
        </div>
        <div className="card p-4 sm:p-5">
          <h2 className="font-display font-semibold mb-3">Badges</h2>
          <div className="flex flex-wrap gap-3">
            {s.badges.length === 0 && <p className="text-muted text-sm">No badges yet</p>}
            {s.badges.map((b) => (
              <div key={b.name} className="text-center">
                <span className="text-2xl">{b.icon}</span>
                <p className="text-xs mt-1">{b.name}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card overflow-hidden">
        <div className="p-3 sm:p-4 border-b border-border flex flex-wrap gap-2 items-center">
          <h2 className="font-display font-semibold w-full sm:w-auto sm:flex-1">Points History</h2>
          <div className="flex flex-wrap gap-2">
            {txFilters.map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setFilter(f)}
                className={`text-xs px-2 py-1.5 rounded capitalize touch-target ${
                  filter === f ? 'bg-primary text-white' : 'bg-black/5 text-muted'
                }`}
              >
                {f.replace('_', ' ')}
              </button>
            ))}
          </div>
        </div>

        <div className="md:hidden divide-y divide-border">
          {transactions.map((tx, i) => (
            <div key={i} className="p-4 space-y-1">
              <div className="flex items-start justify-between gap-2">
                <p className="text-sm font-medium">{tx.description ?? '—'}</p>
                <span className={`font-mono-num text-sm shrink-0 ${tx.delta >= 0 ? 'text-positive' : 'text-negative'}`}>
                  {tx.delta >= 0 ? '+' : ''}{tx.delta}
                </span>
              </div>
              <div className="flex justify-between text-xs text-muted">
                <span>{new Date(tx.created_at).toLocaleString()}</span>
                <span className="font-mono-num">Bal {tx.balance_after.toLocaleString()}</span>
              </div>
            </div>
          ))}
          {transactions.length === 0 && (
            <p className="p-8 text-center text-muted text-sm">No transactions</p>
          )}
        </div>

        <table className="w-full text-sm hidden md:table">
          <thead className="bg-black/5 text-left">
            <tr>
              <th className="p-3">When</th>
              <th className="p-3">Event</th>
              <th className="p-3">Change</th>
              <th className="p-3">After</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((tx, i) => (
              <tr key={i} className="border-t border-border">
                <td className="p-3 text-muted">{new Date(tx.created_at).toLocaleString()}</td>
                <td className="p-3">{tx.description ?? '—'}</td>
                <td className={`p-3 font-mono-num ${tx.delta >= 0 ? 'text-positive' : 'text-negative'}`}>
                  {tx.delta >= 0 ? '+' : ''}{tx.delta}
                </td>
                <td className="p-3 font-mono-num">{tx.balance_after.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
