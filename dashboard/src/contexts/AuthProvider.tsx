import { useState, useEffect, type ReactNode } from 'react';
import { getMe, login, logout, register } from '../api/auth';
import { clearToken } from '../api/client';
import { AuthContext, type AuthState } from './AuthContext';

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
