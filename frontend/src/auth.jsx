import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { createClient } from "@supabase/supabase-js";
import { setAccessTokenProvider } from "./api";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
export const authEnabled = Boolean(supabaseUrl && supabaseAnonKey);
export const supabase = authEnabled
  ? createClient(supabaseUrl, supabaseAnonKey)
  : null;

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(authEnabled);

  useEffect(() => {
    if (!supabase) {
      setAccessTokenProvider(async () => null);
      return undefined;
    }

    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });
    const { data } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
      setLoading(false);
    });
    return () => data.subscription.unsubscribe();
  }, []);

  useEffect(() => {
    setAccessTokenProvider(async () => session?.access_token || null);
  }, [session]);

  const value = useMemo(
    () => ({
      enabled: authEnabled,
      loading,
      session,
      user: session?.user || null,
      signIn: (email, password) =>
        supabase.auth.signInWithPassword({ email, password }),
      signUp: (email, password, name) =>
        supabase.auth.signUp({
          email,
          password,
          options: { data: { full_name: name } },
        }),
      resetPassword: (email) =>
        supabase.auth.resetPasswordForEmail(email, {
          redirectTo: `${window.location.origin}/`,
        }),
      signOut: () => supabase.auth.signOut(),
    }),
    [loading, session],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
