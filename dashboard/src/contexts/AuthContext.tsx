import {
  createContext,
  useContext,
  useState,
  useEffect,
  type ReactNode,
} from 'react';
import { getMe, login, logout, register, type UserOut } from '../api/auth';
import { clearToken } from '../api/client';

interface AuthState {
  user: UserOut | null;
  isLoading: boolean;
}

interface AuthContextValue extends AuthState {
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string) => Promise<void>;
  signOut: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    user: null,
    isLoading: true,
  });

  useEffect(() => {
    getMe()
      .then((user) => setState({ user, isLoading: false }))
      .catch(() => {
        clearToken();
        setState({ user: null, isLoading: false });
      });
  }, []);

  const signIn = async (email: string, password: string) => {
    await login(email, password);
    const user = await getMe();
    setState({ user, isLoading: false });
  };

  const signUp = async (email: string, password: string) => {
    await register(email, password);
    await signIn(email, password);
  };

  const signOut = () => {
    logout();
    setState({ user: null, isLoading: false });
  };

  return (
    <AuthContext.Provider value={{ ...state, signIn, signUp, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return ctx;
}
