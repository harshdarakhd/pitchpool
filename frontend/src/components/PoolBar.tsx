interface PoolBarProps {
  teamA: { name: string; total: number };
  teamB: { name: string; total: number };
}

export function PoolBar({ teamA, teamB }: PoolBarProps) {
  const total = teamA.total + teamB.total || 1;
  const pctA = (teamA.total / total) * 100;

  return (
    <div className="space-y-2">
      <div className="flex justify-between text-sm font-mono-num">
        <span>{teamA.name}: {teamA.total.toLocaleString()}</span>
        <span>{teamB.name}: {teamB.total.toLocaleString()}</span>
      </div>
      <div className="h-3 rounded-full bg-border overflow-hidden flex">
        <div className="bg-primary transition-all duration-500" style={{ width: `${pctA}%` }} />
        <div className="bg-accent flex-1 transition-all duration-500" />
      </div>
    </div>
  );
}
