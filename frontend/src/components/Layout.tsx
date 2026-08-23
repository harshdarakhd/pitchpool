import { useState } from 'react';
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuthStore, useThemeStore } from '../lib/store';

const baseNav = [
  { to: '/', label: 'Matches' },
  { to: '/rules', label: 'Rules' },
  { to: '/score-big', label: 'Score BIG' },
  { to: '/season-bets', label: 'Season Bets' },
  { to: '/leaderboard', label: 'Leaderboard' },
  { to: '/profile', label: 'Profile' },
];

export default function Layout() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const { dark, toggle } = useThemeStore();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);

  const nav = user?.role === 'admin' ? [...baseNav, { to: '/admin', label: 'Admin' }] : baseNav;

  const handleLogout = async () => {
    setMenuOpen(false);
    await logout();
    navigate('/login');
  };

  const closeMenu = () => setMenuOpen(false);

  return (
    <div className="min-h-screen flex flex-col safe-area-x">
      <header className="sticky top-0 z-50 border-b border-border bg-card/90 backdrop-blur-md safe-area-top">
        <div className="max-w-[1400px] mx-auto px-4 sm:px-6 h-14 sm:h-16 flex items-center gap-3 sm:gap-8">
          <Link to="/" className="flex items-center gap-2 font-display font-bold text-base sm:text-lg text-primary shrink-0">
            <span className="text-xl sm:text-2xl">🏏</span> PitchPool
          </Link>

          <nav className="hidden lg:flex gap-1 flex-1">
            {nav.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  `px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive ? 'text-primary border-b-2 border-primary' : 'text-muted hover:text-ink'
                  }`
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>

          {user && (
            <div className="flex items-center gap-2 sm:gap-3 ml-auto">
              <span className="font-mono-num text-xs sm:text-sm bg-primary/10 text-primary px-2 sm:px-3 py-1 rounded-full">
                {user.points_balance.toLocaleString()} pts
              </span>
              <span className="hidden sm:inline text-sm font-medium">{user.display_name}</span>
              <button type="button" onClick={toggle} className="btn-ghost text-lg touch-target" aria-label="Toggle theme">
                {dark ? '🌙' : '☀️'}
              </button>
              <button type="button" onClick={handleLogout} className="hidden sm:inline btn-ghost text-sm">
                Logout
              </button>
              <button
                type="button"
                onClick={() => setMenuOpen((o) => !o)}
                className="lg:hidden btn-ghost touch-target"
                aria-label={menuOpen ? 'Close menu' : 'Open menu'}
                aria-expanded={menuOpen}
              >
                {menuOpen ? '✕' : '☰'}
              </button>
            </div>
          )}
        </div>

        {menuOpen && user && (
          <>
            <button
              type="button"
              className="fixed inset-0 z-40 bg-black/40 lg:hidden"
              aria-label="Close menu overlay"
              onClick={closeMenu}
            />
            <nav className="lg:hidden relative z-50 border-t border-border bg-card px-4 py-3 safe-area-bottom">
              <div className="flex flex-col gap-1">
                {nav.map(({ to, label }) => (
                  <NavLink
                    key={to}
                    to={to}
                    end={to === '/'}
                    onClick={closeMenu}
                    className={({ isActive }) =>
                      `touch-target px-4 py-3 rounded-xl text-base font-medium transition-colors ${
                        isActive ? 'bg-primary/10 text-primary' : 'text-muted hover:bg-black/5 hover:text-ink'
                      }`
                    }
                  >
                    {label}
                  </NavLink>
                ))}
                <div className="border-t border-border mt-2 pt-2 sm:hidden">
                  <p className="px-4 py-1 text-sm text-muted">{user.display_name}</p>
                  <button type="button" onClick={handleLogout} className="touch-target w-full text-left px-4 py-3 rounded-xl text-base text-muted hover:bg-black/5">
                    Logout
                  </button>
                </div>
              </div>
            </nav>
          </>
        )}
      </header>
      <main className="flex-1 max-w-[1400px] w-full mx-auto px-4 sm:px-6 py-4 sm:py-6 safe-area-bottom">
        <Outlet />
      </main>
    </div>
  );
}
