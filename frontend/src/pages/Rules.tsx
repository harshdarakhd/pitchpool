const sections = [
  {
    title: 'Getting Started',
    items: [
      'Every player starts with 5,000 points. No purchases or top-ups.',
      'Points are your currency for bidding on matches.',
      'Balance never drops below 0. At 0 you cannot bid but can still earn via quizzes and streaks.',
    ],
  },
  {
    title: 'Bid Deadlines',
    items: [
      'Bidding closes 15 minutes before scheduled match time.',
      'Once the deadline passes, no new bids can be placed.',
    ],
  },
  {
    title: 'League Match Rules',
    badge: '70 League Matches',
    items: [
      'Up to 3 bids per match.',
      'You may bid on both teams — totals must differ by at least 30%.',
      'Minimum wager: 100 points per bid.',
      'Non-bid penalty: −100 pts added to the winning pool.',
    ],
  },
  {
    title: 'Playoff Rules (Qualifier & Eliminator)',
    items: [
      'Only 1 bid, one team only.',
      'Minimum wager: 30% of current balance (or 100 pts, whichever is higher).',
      'Non-bid penalty: −30% of balance.',
    ],
  },
  {
    title: 'Final Rules',
    badge: 'THE FINAL',
    items: [
      'Only 1 bid, one team only.',
      'ALL-IN: your entire balance is wagered automatically.',
      'Non-bid penalty: lose 100% of your points.',
    ],
  },
  {
    title: 'How Payouts Work (Parimutuel)',
    items: [
      'Losing bids + non-bidder penalties form the profit pool.',
      'Winners get wager back + proportional share: (your wager / total winning wagers) × profit pool.',
      'Bigger wager on the winner = bigger share.',
    ],
  },
];

export default function Rules() {
  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <header className="text-center">
        <span className="text-xs uppercase tracking-widest text-primary border border-primary/30 px-3 py-1 rounded-full">
          Official Rule Book
        </span>
        <h1 className="font-display text-3xl font-bold mt-4">PitchPool Bidding Arena</h1>
        <p className="text-muted mt-2">
          Everything you need to know before placing your bids. The rules change as stakes get higher.
        </p>
      </header>
      {sections.map((s) => (
        <article key={s.title} className="card p-6">
          <div className="flex items-center gap-3 mb-4">
            <h2 className="font-display text-xl font-semibold">{s.title}</h2>
            {s.badge && (
              <span className="text-xs bg-primary/10 text-primary px-2 py-1 rounded">{s.badge}</span>
            )}
          </div>
          <ol className="list-decimal list-inside space-y-2 text-sm text-muted">
            {s.items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ol>
        </article>
      ))}
    </div>
  );
}
