import { useEffect, useState } from 'react';

export function CountdownTimer({ deadline }: { deadline: string }) {
  const [left, setLeft] = useState('');

  useEffect(() => {
    const tick = () => {
      const diff = new Date(deadline).getTime() - Date.now();
      if (diff <= 0) {
        setLeft('Closed');
        return;
      }
      const h = Math.floor(diff / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      const s = Math.floor((diff % 60000) / 1000);
      setLeft(`${h}h ${m}m ${s}s`);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [deadline]);

  return (
    <span className={`font-mono-num text-sm ${left === 'Closed' ? 'text-negative' : 'text-primary'}`}>
      {left}
    </span>
  );
}
