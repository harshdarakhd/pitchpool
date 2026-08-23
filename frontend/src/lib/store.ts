import { create } from 'zustand';
import type { User } from './api';
import { api, clearToken } from './api';

interface AuthState {
  user: User | null;
  loading: boolean;
  setUser: (user: User | null) => void;
  fetchUser: () => Promise<void>;
  logout: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  loading: true,
  setUser: (user) => set({ user, loading: false }),
  fetchUser: async () => {
    try {
      const user = await api.me();
      set({ user, loading: false });
    } catch {
      clearToken();
      set({ user: null, loading: false });
    }
  },
  logout: async () => {
    try {
      await api.logout();
    } finally {
      set({ user: null });
    }
  },
}));

interface ThemeState {
  dark: boolean;
  toggle: () => void;
}

export const useThemeStore = create<ThemeState>((set) => ({
  dark: localStorage.getItem('theme') === 'dark',
  toggle: () =>
    set((s) => {
      const dark = !s.dark;
      localStorage.setItem('theme', dark ? 'dark' : 'light');
      document.body.classList.toggle('dark', dark);
      return { dark };
    }),
}));
