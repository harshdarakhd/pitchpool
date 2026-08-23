const earnings = [
  { source: 'Match bid (parimutuel)', how: 'Pick the winning team — get wager back + slice of losing pool', ceiling: 'Unlimited' },
  { source: 'Quiz answer', how: 'Answer correctly before match deadline', ceiling: '+100 pts' },
  { source: 'Streak milestone', how: 'Hit 3/5/7/10/15/20/25 consecutive correct picks', ceiling: 'Up to +5,000' },
  { source: 'Season bet', how: 'IPL Winner / Orange Cap / Purple Cap — free entry', ceiling: 'Up to 5,000 each' },
  { source: 'Badges', how: 'Recognition on your profile', ceiling: 'Pride' },
];

export default function ScoreBig() {
  return (
    <div className="max-w-3xl mx-auto space-y-6 sm:space-y-8">
      <header className="text-center px-2">
        <span className="text-xs uppercase tracking-widest text-accent border border-accent/30 px-3 py-1 rounded-full">
          Player Strategy Guide
        </span>
        <h1 className="font-display text-2xl sm:text-3xl font-bold mt-4">How to Score BIG</h1>
        <p className="text-muted mt-2 text-sm sm:text-base">
          Every legal way to grow your point pile — from match bids to streak bonuses, quizzes, season picks, and badges.
        </p>
      </header>

      <div className="md:hidden space-y-3">
        <h2 className="font-display font-semibold px-1">Earnings at a Glance</h2>
        {earnings.map((e) => (
          <div key={e.source} className="card p-4 space-y-2">
            <p className="font-medium">{e.source}</p>
            <p className="text-sm text-muted">{e.how}</p>
            <p className="font-mono-num text-sm text-positive">Ceiling: {e.ceiling}</p>
          </div>
        ))}
      </div>

      <div className="card overflow-hidden hidden md:block">
        <div className="p-4 border-b border-border font-display font-semibold">Earnings at a Glance</div>
        <table className="w-full text-sm">
          <thead className="bg-black/5 text-left">
            <tr>
              <th className="p-3">Source</th>
              <th className="p-3">How it pays</th>
              <th className="p-3">Ceiling</th>
            </tr>
          </thead>
          <tbody>
            {earnings.map((e) => (
              <tr key={e.source} className="border-t border-border">
                <td className="p-3 font-medium">{e.source}</td>
                <td className="p-3 text-muted">{e.how}</td>
                <td className="p-3 font-mono-num text-positive">{e.ceiling}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card p-4 sm:p-6 space-y-3">
        <h2 className="font-display text-lg sm:text-xl font-semibold">Starting Capital</h2>
        <ul className="text-sm text-muted space-y-2 list-disc list-inside">
          <li>Every player begins with <strong className="text-ink">5,000 points</strong>.</li>
          <li>Late joiners: −100 pts per match already completed (floor 500).</li>
          <li>Balance never drops below 0 — earn back via quizzes and streaks.</li>
        </ul>
      </div>

      <div className="card p-4 sm:p-6">
        <h2 className="font-display text-lg sm:text-xl font-semibold mb-4">Streak Milestones</h2>
        <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-7 gap-2 sm:gap-3">
          {[3, 5, 7, 10, 15, 20, 25].map((w, i) => (
            <div key={w} className="text-center p-2 sm:p-3 bg-primary/5 rounded-xl">
              <div className="font-display font-bold text-base sm:text-lg">{w}W</div>
              <div className="font-mono-num text-positive text-xs sm:text-sm">
                +{[100, 300, 500, 1000, 2000, 3500, 5000][i]}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
