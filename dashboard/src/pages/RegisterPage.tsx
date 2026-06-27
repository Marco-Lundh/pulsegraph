import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Zap } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { ApiError } from '../api/client';

export function RegisterPage() {
  const { signUp } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.SubmitEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);
    try {
      await signUp(email, password);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('An unexpected error occurred.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div
      className="flex min-h-screen items-center justify-center p-4"
      style={{ backgroundColor: 'var(--color-bg-base)' }}
    >
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-3">
          <div
            className="flex h-11 w-11 items-center justify-center rounded-xl"
            style={{ backgroundColor: 'var(--color-accent)' }}
          >
            <Zap size={22} color="white" />
          </div>
          <div className="text-center">
            <h1
              className="text-xl font-semibold"
              style={{ color: 'var(--color-text-primary)' }}
            >
              Create your account
            </h1>
            <p className="mt-1 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
              Start monitoring open data in minutes.
            </p>
          </div>
        </div>

        <form
          onSubmit={handleSubmit}
          className="rounded-xl p-6"
          style={{
            backgroundColor: 'var(--color-bg-card)',
            border: '1px solid var(--color-border)',
          }}
        >
          {error && (
            <div
              className="mb-4 rounded-lg p-3 text-sm"
              style={{
                backgroundColor: 'color-mix(in srgb, var(--color-danger) 12%, transparent)',
                color: 'var(--color-danger)',
                border: '1px solid color-mix(in srgb, var(--color-danger) 30%, transparent)',
              }}
            >
              {error}
            </div>
          )}

          <div className="flex flex-col gap-4">
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
                Email
              </span>
              <input
                type="email"
                value={email}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  setEmail(e.target.value)
                }
                required
                autoComplete="email"
                className="rounded-lg px-3 py-2 text-sm outline-none transition-colors"
                style={{
                  backgroundColor: 'var(--color-bg-input)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text-primary)',
                }}
                placeholder="you@example.com"
              />
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
                Password
              </span>
              <input
                type="password"
                value={password}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  setPassword(e.target.value)
                }
                required
                minLength={8}
                autoComplete="new-password"
                className="rounded-lg px-3 py-2 text-sm outline-none transition-colors"
                style={{
                  backgroundColor: 'var(--color-bg-input)',
                  border: '1px solid var(--color-border)',
                  color: 'var(--color-text-primary)',
                }}
                placeholder="Min. 8 characters"
              />
            </label>
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="mt-5 w-full rounded-lg py-2.5 text-sm font-semibold transition-colors disabled:opacity-60"
            style={{
              backgroundColor: 'var(--color-accent)',
              color: 'white',
            }}
          >
            {isLoading ? 'Creating account…' : 'Create account'}
          </button>
        </form>

        <p
          className="mt-4 text-center text-sm"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          Already have an account?{' '}
          <Link
            to="/login"
            className="font-medium underline"
            style={{ color: 'var(--color-accent)' }}
          >
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
