import {
  createContext,
  type PropsWithChildren,
  useContext,
  useMemo,
  useState
} from "react";
import { api } from "./api";
import type { LoginResponse, User } from "./types";

interface AuthValue {
  token: string | null;
  user: User | null;
  login: (email: string, password: string) => Promise<User>;
  logout: () => void;
}

const AuthContext = createContext<AuthValue | null>(null);
const STORAGE_KEY = "refund-agent-session";

function readSession(): { token: string; user: User } | null {
  const raw = sessionStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as { token: string; user: User };
  } catch {
    sessionStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export function AuthProvider({ children }: PropsWithChildren) {
  const initial = readSession();
  const [token, setToken] = useState<string | null>(initial?.token ?? null);
  const [user, setUser] = useState<User | null>(initial?.user ?? null);

  const value = useMemo<AuthValue>(
    () => ({
      token,
      user,
      async login(email, password) {
        const result = await api<LoginResponse>("/auth/login", {
          method: "POST",
          body: JSON.stringify({ email, password })
        });
        setToken(result.access_token);
        setUser(result.user);
        sessionStorage.setItem(
          STORAGE_KEY,
          JSON.stringify({ token: result.access_token, user: result.user })
        );
        return result.user;
      },
      logout() {
        setToken(null);
        setUser(null);
        sessionStorage.removeItem(STORAGE_KEY);
      }
    }),
    [token, user]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// AuthProvider and its consumer hook intentionally share the same module.
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
