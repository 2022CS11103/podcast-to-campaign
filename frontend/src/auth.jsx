import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { createClient } from "@supabase/supabase-js";
import { setAccessTokenProvider } from "./api";

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
const cloudAuth = Boolean(supabaseUrl && supabaseAnonKey);
export const supabase = cloudAuth
  ? createClient(supabaseUrl, supabaseAnonKey)
  : null;

const SESSION_KEY = "creatoros.session";
const USERS_KEY = "creatoros.users";
const AuthContext = createContext(null);

function readJson(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function localUser(session) {
  if (!session) return null;
  return session.user || session;
}

export function AuthProvider({ children }) {
  const [session, setSession] = useState(() => (cloudAuth ? null : readJson(SESSION_KEY, null)));
  const [loading, setLoading] = useState(cloudAuth);

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
      enabled: true,
      cloud: cloudAuth,
      loading,
      session,
      user: cloudAuth ? session?.user || null : localUser(session),
      signIn: async (email, password) => {
        if (supabase) return supabase.auth.signInWithPassword({ email, password });
        const users = readJson(USERS_KEY, []);
        const match = users.find(
          (row) => row.email.toLowerCase() === email.trim().toLowerCase() && row.secret === btoa(password),
        );
        if (!match) return { error: { message: "Email or password is not right." } };
        const next = {
          user: { email: match.email, user_metadata: { full_name: match.name } },
        };
        localStorage.setItem(SESSION_KEY, JSON.stringify(next));
        setSession(next);
        return { error: null };
      },
      signUp: async (email, password, name) => {
        if (supabase) {
          return supabase.auth.signUp({
            email,
            password,
            options: { data: { full_name: name } },
          });
        }
        const users = readJson(USERS_KEY, []);
        if (users.some((row) => row.email.toLowerCase() === email.trim().toLowerCase())) {
          return { error: { message: "An account with this email already exists." } };
        }
        users.push({
          email: email.trim().toLowerCase(),
          name: name || "Creator",
          secret: btoa(password),
        });
        localStorage.setItem(USERS_KEY, JSON.stringify(users));
        const next = {
          user: { email: email.trim().toLowerCase(), user_metadata: { full_name: name || "Creator" } },
        };
        localStorage.setItem(SESSION_KEY, JSON.stringify(next));
        setSession(next);
        return { error: null };
      },
      signInWithGoogle: async () => {
        if (!supabase) {
          return { error: { message: "Google sign-in is available once cloud login is connected." } };
        }
        return supabase.auth.signInWithOAuth({
          provider: "google",
          options: { redirectTo: `${window.location.origin}/app/accounts` },
        });
      },
      resetPassword: async (email) => {
        if (supabase) {
          return supabase.auth.resetPasswordForEmail(email, {
            redirectTo: `${window.location.origin}/app/`,
          });
        }
        return { error: { message: "Password reset is available after cloud login is connected." } };
      },
      signOut: async () => {
        if (supabase) return supabase.auth.signOut();
        localStorage.removeItem(SESSION_KEY);
        setSession(null);
        return { error: null };
      },
    }),
    [loading, session],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
