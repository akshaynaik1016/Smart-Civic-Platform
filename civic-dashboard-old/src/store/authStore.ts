import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { jwtDecode } from 'jwt-decode';
import type { AuthState, AuthTokens, User } from '../types';
import { apiClient } from '../services/api';

interface AuthStore extends AuthState {
  login:      (email: string, password: string) => Promise<void>;
  logout:     () => void;
  refreshAuth:() => Promise<boolean>;
  setUser:    (user: User) => void;
  clearError: () => void;
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set, get) => ({
      user:      null,
      tokens:    null,
      isLoading: false,
      error:     null,

      login: async (email, password) => {
        set({ isLoading: true, error: null });
        try {
          const { data } = await apiClient.post<{ tokens: AuthTokens; user: User }>(
            '/auth/login', { email, password }
          );
          apiClient.defaults.headers.common.Authorization =
            `Bearer ${data.tokens.accessToken}`;
          set({ tokens: data.tokens, user: data.user, isLoading: false });
        } catch (err: any) {
          const msg = err?.response?.data?.detail ?? 'Login failed. Check credentials.';
          set({ isLoading: false, error: msg });
          throw new Error(msg);
        }
      },

      logout: () => {
        delete apiClient.defaults.headers.common.Authorization;
        set({ user: null, tokens: null, error: null });
      },

      refreshAuth: async () => {
        const { tokens } = get();
        if (!tokens?.refreshToken) return false;
        try {
          const { data } = await apiClient.post<{ tokens: AuthTokens }>(
            '/auth/refresh', { refreshToken: tokens.refreshToken }
          );
          apiClient.defaults.headers.common.Authorization =
            `Bearer ${data.tokens.accessToken}`;
          set({ tokens: data.tokens });
          return true;
        } catch {
          get().logout();
          return false;
        }
      },

      setUser:    (user)  => set({ user }),
      clearError: ()      => set({ error: null }),
    }),
    {
      name:    'civic-auth',
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({ tokens: s.tokens, user: s.user }),
      onRehydrateStorage: () => (state) => {
        if (state?.tokens?.accessToken) {
          try {
            const decoded: any = jwtDecode(state.tokens.accessToken);
            if (decoded.exp * 1000 < Date.now()) {
              // Token expired — trigger refresh on first API call
              state.tokens = null;
            } else {
              apiClient.defaults.headers.common.Authorization =
                `Bearer ${state.tokens.accessToken}`;
            }
          } catch {
            state.tokens = null;
          }
        }
      },
    }
  )
);

// ─── Axios interceptor for 401 auto-refresh ──────────────────────────────────
apiClient.interceptors.response.use(
  (res) => res,
  async (error) => {
    const original = error.config;
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true;
      const refreshed = await useAuthStore.getState().refreshAuth();
      if (refreshed) {
        original.headers.Authorization =
          apiClient.defaults.headers.common.Authorization;
        return apiClient(original);
      }
    }
    return Promise.reject(error);
  }
);
