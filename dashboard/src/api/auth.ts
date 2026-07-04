import { api, setToken, clearToken } from './client';

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface UserOut {
  id: string;
  email: string;
  role: string;
  created_at: string;
}

export async function login(
  email: string,
  password: string,
): Promise<TokenResponse> {
  const data = await api.post<TokenResponse>('/auth/login', {
    email,
    password,
  });
  setToken(data.access_token);
  return data;
}

export async function register(
  email: string,
  password: string,
): Promise<UserOut> {
  return api.post<UserOut>('/auth/register', { email, password });
}

export function logout(): void {
  clearToken();
}

export async function getMe(): Promise<UserOut> {
  return api.get<UserOut>('/auth/me');
}

export async function exportMyData(): Promise<Record<string, unknown>> {
  return api.get<Record<string, unknown>>('/auth/me/export');
}

export async function deleteMyAccount(): Promise<void> {
  return api.delete<void>('/auth/me');
}
