import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft } from 'lucide-react';
import { watchesApi, type SourceKind } from '../api/watches';
import { ApiError } from '../api/client';

const SOURCES: { value: SourceKind; label: string; description: string }[] = [
  {
    value: 'jobtech',
    label: 'JobTech',
    description: 'Swedish job listings from Arbetsförmedlingen',
  },
  {
    value: 'riksdagen',
    label: 'Riksdagen',
    description: 'Swedish parliamentary documents and motions',
  },
  {
    value: 'entsoe',
    label: 'ENTSO-E',
    description: 'European electricity market and grid data',
  },
];

const INTERVALS = [
  { label: '15 min', seconds: 900 },
  { label: '1 hour', seconds: 3600 },
  { label: '6 hours', seconds: 21600 },
  { label: '24 hours', seconds: 86400 },
];

export function CreateWatchPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [source, setSource] = useState<SourceKind>('jobtech');
  const [prompt, setPrompt] = useState('');
  const [interval, setInterval] = useState(3600);
  const [error, setError] = useState('');

  const mutation = useMutation({
    mutationFn: () =>
      watchesApi.create({ source, prompt, schedule_interval_seconds: interval }),
    onSuccess: (watch) => {
      queryClient.invalidateQueries({ queryKey: ['watches'] });
      navigate(`/watches/${watch.id}`, { replace: true });
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError('An unexpected error occurred.');
      }
    },
  });

  const handleSubmit = (e: React.SubmitEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError('');
    mutation.mutate();
  };

  return (
    <div className="mx-auto max-w-2xl">
      <button
        onClick={() => navigate(-1)}
        className="mb-6 flex items-center gap-2 text-sm transition-colors"
        style={{ color: 'var(--color-text-secondary)' }}
      >
        <ArrowLeft size={14} />
        Back
      </button>

      <div className="mb-6">
        <h1
          className="text-2xl font-semibold"
          style={{ color: 'var(--color-text-primary)' }}
        >
          New watch
        </h1>
        <p className="mt-1 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
          PulseGraph will poll the source and alert you when your prompt matches.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-6">
        {error && (
          <div
            className="rounded-lg p-3 text-sm"
            style={{
              backgroundColor: 'color-mix(in srgb, var(--color-danger) 12%, transparent)',
              color: 'var(--color-danger)',
              border: '1px solid color-mix(in srgb, var(--color-danger) 30%, transparent)',
            }}
          >
            {error}
          </div>
        )}

        <div>
          <p
            className="mb-3 text-xs font-medium"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            Data source
          </p>
          <div className="grid grid-cols-3 gap-3">
            {SOURCES.map((s) => (
              <button
                key={s.value}
                type="button"
                onClick={() => setSource(s.value)}
                className="flex flex-col items-start rounded-xl p-4 text-left transition-colors"
                style={{
                  backgroundColor:
                    source === s.value
                      ? 'color-mix(in srgb, var(--color-accent) 12%, transparent)'
                      : 'var(--color-bg-card)',
                  border:
                    source === s.value
                      ? '1px solid color-mix(in srgb, var(--color-accent) 50%, transparent)'
                      : '1px solid var(--color-border)',
                }}
              >
                <span
                  className="text-sm font-semibold"
                  style={{
                    color:
                      source === s.value
                        ? 'var(--color-accent)'
                        : 'var(--color-text-primary)',
                  }}
                >
                  {s.label}
                </span>
                <span
                  className="mt-1 text-xs leading-snug"
                  style={{ color: 'var(--color-text-muted)' }}
                >
                  {s.description}
                </span>
              </button>
            ))}
          </div>
        </div>

        <label className="flex flex-col gap-1.5">
          <span
            className="text-xs font-medium"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            Monitoring prompt
          </span>
          <textarea
            value={prompt}
            onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) =>
              setPrompt(e.target.value)
            }
            required
            rows={3}
            className="resize-none rounded-lg px-3 py-2.5 text-sm outline-none"
            style={{
              backgroundColor: 'var(--color-bg-input)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-text-primary)',
            }}
            placeholder="e.g. Notify me when there are new senior Python engineering roles in Stockholm"
          />
          <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            Describe what to look for. The AI will match results to your criteria.
          </span>
        </label>

        <div>
          <p
            className="mb-3 text-xs font-medium"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            Check frequency
          </p>
          <div className="flex gap-2">
            {INTERVALS.map((i) => (
              <button
                key={i.seconds}
                type="button"
                onClick={() => setInterval(i.seconds)}
                className="rounded-lg px-4 py-2 text-sm font-medium transition-colors"
                style={{
                  backgroundColor:
                    interval === i.seconds
                      ? 'var(--color-accent)'
                      : 'var(--color-bg-card)',
                  border:
                    interval === i.seconds
                      ? '1px solid var(--color-accent)'
                      : '1px solid var(--color-border)',
                  color:
                    interval === i.seconds
                      ? 'white'
                      : 'var(--color-text-secondary)',
                }}
              >
                {i.label}
              </button>
            ))}
          </div>
        </div>

        <button
          type="submit"
          disabled={mutation.isPending || !prompt.trim()}
          className="self-start rounded-lg px-6 py-2.5 text-sm font-semibold transition-colors disabled:opacity-60"
          style={{ backgroundColor: 'var(--color-accent)', color: 'white' }}
        >
          {mutation.isPending ? 'Creating…' : 'Create watch'}
        </button>
      </form>
    </div>
  );
}
