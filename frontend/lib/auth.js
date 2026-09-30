'use client';
import { createContext, useContext, useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { clearSession, getStoredUser, getToken, HOME_BY_ROLE } from './api';

const AuthCtx = createContext({ user: null, ready: false });

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    setUser(getToken() ? getStoredUser() : null);
    setReady(true);
  }, []);
  const signOut = () => { clearSession(); setUser(null); window.location.href = '/'; };
  return <AuthCtx.Provider value={{ user, setUser, ready, signOut }}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);

// Redirects to sign-in (or to the user's own home) if the role does not match.
export function useRequireRole(...roles) {
  const { user, ready } = useAuth();
  const router = useRouter();
  const path = usePathname();
  useEffect(() => {
    if (!ready) return;
    if (!user) router.replace(`/?next=${encodeURIComponent(path)}`);
    else if (roles.length && !roles.includes(user.role)) router.replace(HOME_BY_ROLE[user.role] || '/');
  }, [ready, user, path]); // eslint-disable-line react-hooks/exhaustive-deps
  return { user, allowed: !!user && (!roles.length || roles.includes(user.role)) };
}
