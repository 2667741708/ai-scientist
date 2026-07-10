import type { PropsWithChildren } from "react";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { AccountRole, AccountUser } from "../../types/workbench";
import {
  clearStoredAuthToken,
  fetchCurrentAccount,
  getStoredAuthToken,
  loginAccount,
  logoutAccount,
  registerResearcher,
  storeAuthToken,
} from "../../lib/api/auth";

type AuthContextValue = {
  user: AccountUser | null;
  token: string;
  loading: boolean;
  isAuthenticated: boolean;
  hasRole: (role: AccountRole) => boolean;
  signIn: (payload: { email: string; password: string }) => Promise<AccountUser>;
  register: (payload: {
    email: string;
    password: string;
    display_name: string;
    recovery_question?: string;
    recovery_answer?: string;
  }) => Promise<AccountUser>;
  signOut: () => Promise<void>;
  refreshUser: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const [token, setToken] = useState(() => getStoredAuthToken());
  const [user, setUser] = useState<AccountUser | null>(null);
  const [loading, setLoading] = useState(Boolean(token));

  const refreshUser = useCallback(async () => {
    const currentToken = getStoredAuthToken();
    setToken(currentToken);
    if (!currentToken) {
      setUser(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const response = await fetchCurrentAccount();
      setUser(response.user);
    } catch {
      clearStoredAuthToken();
      setToken("");
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshUser();
  }, [refreshUser]);

  const signIn = useCallback(async (payload: { email: string; password: string }) => {
    const session = await loginAccount(payload);
    storeAuthToken(session.access_token);
    setToken(session.access_token);
    setUser(session.user);
    return session.user;
  }, []);

  const register = useCallback(async (payload: {
    email: string;
    password: string;
    display_name: string;
    recovery_question?: string;
    recovery_answer?: string;
  }) => {
    const session = await registerResearcher(payload);
    storeAuthToken(session.access_token);
    setToken(session.access_token);
    setUser(session.user);
    return session.user;
  }, []);

  const signOut = useCallback(async () => {
    try {
      if (getStoredAuthToken()) await logoutAccount();
    } catch {
      // Stateless token logout should still clear the local session if the API is unavailable.
    }
    clearStoredAuthToken();
    setToken("");
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      token,
      loading,
      isAuthenticated: Boolean(token && user),
      hasRole: (role) => user?.role === role,
      signIn,
      register,
      signOut,
      refreshUser,
    }),
    [loading, refreshUser, register, signIn, signOut, token, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
