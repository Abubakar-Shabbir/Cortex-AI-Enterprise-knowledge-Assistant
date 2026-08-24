import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { api, setCsrfToken } from '../api/client';

const SessionContext = createContext(null);

export function SessionProvider({ children }) {
  const [session, setSession] = useState({ loading: true, authenticated: false, user: null, permissions: [], canViewAdminArea: false });

  const refresh = useCallback(async () => {
    const data = await api.get('/auth/session/');
    setCsrfToken(data.csrf_token);
    if (data.authenticated) {
      setSession({
        loading: false,
        authenticated: true,
        user: data.user,
        role: data.role,
        permissions: data.permissions || [],
        canViewAdminArea: data.can_view_admin_area,
      });
    } else {
      setSession({ loading: false, authenticated: false, user: null, permissions: [], canViewAdminArea: false });
    }
    return data;
  }, []);

  useEffect(() => {
    refresh().catch(() => setSession((s) => ({ ...s, loading: false })));
  }, [refresh]);

  const login = useCallback(async (username, password, rememberMe) => {
    let data;
    try {
      data = await api.post('/auth/login/', { username, password, remember_me: rememberMe });
    } catch (err) {
      return { error: err.message };
    }

    if (data.csrf_token) setCsrfToken(data.csrf_token);

    if (data.pending_verification) {
      return { pendingVerification: true, redirect: data.redirect };
    }

    setSession({
      loading: false,
      authenticated: true,
      user: data.user,
      role: data.role,
      permissions: data.permissions || [],
      canViewAdminArea: data.can_view_admin_area,
    });
    return { ok: true };
  }, []);

  const logout = useCallback(async () => {
    const data = await api.post('/auth/logout/');
    setCsrfToken(data.csrf_token);
    setSession({ loading: false, authenticated: false, user: null, permissions: [], canViewAdminArea: false });
  }, []);

  const hasPermission = useCallback(
    (codename) => session.permissions.includes(codename),
    [session.permissions],
  );

  return (
    <SessionContext.Provider value={{ ...session, login, logout, hasPermission, refresh }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error('useSession must be used inside SessionProvider');
  return ctx;
}
