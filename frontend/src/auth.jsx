import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { createClient } from "@supabase/supabase-js";
import { creatorApi, setAccessTokenProvider, setUserEmailProvider } from "./api";

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

function loadGoogleScript() {
  if (window.google?.accounts?.oauth2) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const existing = document.querySelector("script[data-google-gsi]");
    if (existing) {
      if (window.google?.accounts?.oauth2) resolve();
      else existing.addEventListener("load", () => resolve(), { once: true });
      return;
    }
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.dataset.googleGsi = "1";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Could not load Google sign-in."));
    document.head.appendChild(script);
  });
}

function googleProfileFromToken(accessToken) {
  return fetch("https://www.googleapis.com/oauth2/v3/userinfo", {
    headers: { Authorization: `Bearer ${accessToken}` },
  }).then(async (response) => {
    if (!response.ok) throw new Error("Google did not return a profile.");
    return response.json();
  });
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
    const local = cloudAuth ? session?.user : localUser(session);
    setUserEmailProvider(async () => local?.email || null);
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
        if (supabase) {
          return supabase.auth.signInWithOAuth({
            provider: "google",
            options: { redirectTo: `${window.location.origin}/app/accounts` },
          });
        }
        try {
          const config = await creatorApi.authConfig();
          const clientId = config.google_client_id;
          if (!clientId) {
            return {
              error: {
                message: "Add GOOGLE_CLIENT_ID to the project .env, then restart the server.",
              },
            };
          }
          await loadGoogleScript();
          const profile = await new Promise((resolve, reject) => {
            const client = window.google.accounts.oauth2.initTokenClient({
              client_id: clientId,
              scope: "openid email profile",
              callback: (response) => {
                if (response.error) {
                  reject(new Error(response.error_description || response.error));
                  return;
                }
                googleProfileFromToken(response.access_token).then(resolve).catch(reject);
              },
              error_callback: (error) => {
                reject(new Error(error?.message || "Google sign-in was cancelled."));
              },
            });
            client.requestAccessToken();
          });
          const next = {
            user: {
              email: profile.email,
              user_metadata: { full_name: profile.name || profile.given_name || "Creator" },
              picture: profile.picture,
            },
          };
          localStorage.setItem(SESSION_KEY, JSON.stringify(next));
          setSession(next);
          return { error: null };
        } catch (error) {
          const text = String(error?.message || error);
          if (/origin is not allowed|redirect_uri|unauthorized/i.test(text)) {
            return {
              error: {
                message:
                  `Google blocked this origin (${window.location.origin}). In Google Cloud Console, add it under Authorized JavaScript origins for this OAuth client.`,
              },
            };
          }
          return { error: { message: text } };
        }
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
