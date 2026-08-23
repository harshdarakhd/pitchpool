import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../lib/api';
import { useAuthStore } from '../lib/store';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [isRegister, setIsRegister] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const fetchUser = useAuthStore((s) => s.fetchUser);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      if (isRegister) {
        await api.register(email, password, displayName);
      }
      await api.login(email, password);
      await fetchUser();
      navigate('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen min-h-[100dvh] grid lg:grid-cols-2 safe-area-x">
      <div className="bg-primary text-white p-6 sm:p-8 lg:p-12 flex flex-col justify-between safe-area-top gap-6">
        <div>
          <h1 className="font-display text-3xl sm:text-4xl font-bold mb-3 sm:mb-4">PitchPool</h1>
          <p className="text-white/80 text-base sm:text-lg max-w-md">
            Predict match winners, wager your points, climb the leaderboard. Every match matters.
          </p>
        </div>
        <div className="flex flex-col sm:flex-row sm:flex-wrap gap-3 sm:gap-8 text-sm text-white/70">
          <span><strong className="text-accent">5,000</strong> Starting Points</span>
          <span>Parimutuel Pool Bidding</span>
          <span>Real-time Updates</span>
        </div>
      </div>
      <div className="flex items-center justify-center p-6 sm:p-8 lg:p-12 bg-surface safe-area-bottom">
        <form onSubmit={handleSubmit} className="w-full max-w-md space-y-4 sm:space-y-5">
          <h2 className="font-display text-xl sm:text-2xl font-bold">{isRegister ? 'Create account' : 'Welcome back'}</h2>
          <p className="text-muted text-sm">
            {isRegister ? 'Join the bidding arena with email and password.' : 'Sign in to continue your predictions.'}
          </p>
          {isRegister && (
            <input
              className="input"
              placeholder="Display name"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              required
              autoComplete="name"
            />
          )}
          <input
            className="input"
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="email"
            inputMode="email"
          />
          <input
            className="input"
            type="password"
            placeholder="Password (min 8 chars)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            autoComplete={isRegister ? 'new-password' : 'current-password'}
          />
          {error && <p className="text-negative text-sm">{error}</p>}
          <button type="submit" className="btn-primary w-full touch-target" disabled={loading}>
            {loading ? 'Please wait…' : isRegister ? 'Register & Sign in' : 'Sign in'}
          </button>
          <button
            type="button"
            className="text-sm text-primary hover:underline touch-target py-2"
            onClick={() => setIsRegister(!isRegister)}
          >
            {isRegister ? 'Already have an account? Sign in' : 'New here? Create an account'}
          </button>
        </form>
      </div>
    </div>
  );
}
