import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, ClipboardList, XCircle } from 'lucide-react';
import { adminApi, type ReviewDecisionKind } from '../api/admin';
import { ApiError } from '../api/client';

function EvalHealthBanner() {
  const { data } = useQuery({
    queryKey: ['admin', 'eval-health'],
    queryFn: () => adminApi.evalHealth(),
  });

  if (!data) return null;

  const text =
    data.total === 0
      ? 'No evaluations in the last 24h.'
      : `${((data.pct_approved ?? 0) * 100).toFixed(0)}% approved in the last 24h (${data.total} total).`;

  return (
    <p className="mb-4 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
      {text}
    </p>
  );
}

function CorrectForm({
  onSubmit,
  onCancel,
  isPending,
}: {
  onSubmit: (label: string, note: string) => void;
  onCancel: () => void;
  isPending: boolean;
}) {
  const [label, setLabel] = useState('');
  const [note, setNote] = useState('');

  return (
    <div
      className="mt-2 flex flex-col gap-2 rounded-lg p-3"
      style={{ backgroundColor: 'var(--color-bg-input)' }}
    >
      <input
        type="text"
        placeholder="Corrected label"
        value={label}
        onChange={(e) => setLabel(e.target.value)}
        className="rounded-lg px-3 py-2 text-sm outline-none"
        style={{
          backgroundColor: 'var(--color-bg-card)',
          border: '1px solid var(--color-border)',
          color: 'var(--color-text-primary)',
        }}
      />
      <textarea
        placeholder="Note (optional)"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        rows={2}
        className="rounded-lg px-3 py-2 text-sm outline-none"
        style={{
          backgroundColor: 'var(--color-bg-card)',
          border: '1px solid var(--color-border)',
          color: 'var(--color-text-primary)',
        }}
      />
      <div className="flex justify-end gap-2">
        <button
          onClick={onCancel}
          className="rounded-lg px-3 py-1.5 text-xs font-medium"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          Cancel
        </button>
        <button
          onClick={() => onSubmit(label, note)}
          disabled={!label || isPending}
          className="rounded-lg px-3 py-1.5 text-xs font-medium text-white disabled:opacity-40"
          style={{ backgroundColor: 'var(--color-accent)' }}
        >
          Submit
        </button>
      </div>
    </div>
  );
}

export function AdminReviewQueuePage() {
  const queryClient = useQueryClient();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [error, setError] = useState('');

  const { data: queue, isLoading } = useQuery({
    queryKey: ['admin', 'review-queue'],
    queryFn: () => adminApi.reviewQueue(),
  });

  const decideMutation = useMutation({
    mutationFn: ({
      id,
      decision,
      correctedLabel,
      note,
    }: {
      id: string;
      decision: ReviewDecisionKind;
      correctedLabel?: string;
      note?: string;
    }) =>
      adminApi.decide(id, {
        decision,
        corrected_label: correctedLabel,
        note,
      }),
    onSuccess: () => {
      setError('');
      setExpandedId(null);
      queryClient.invalidateQueries({ queryKey: ['admin', 'review-queue'] });
      queryClient.invalidateQueries({ queryKey: ['admin', 'eval-health'] });
    },
    onError: (err) => {
      setError(err instanceof ApiError ? err.message : 'Failed to record decision.');
    },
  });

  if (isLoading) {
    return (
      <div className="flex justify-center py-16">
        <div className="h-7 w-7 animate-spin rounded-full border-2 border-[var(--color-accent)] border-t-transparent" />
      </div>
    );
  }

  return (
    <div>
      <EvalHealthBanner />

      {error && (
        <div
          className="mb-4 rounded-lg p-3 text-sm"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--color-danger) 12%, transparent)',
            color: 'var(--color-danger)',
          }}
        >
          {error}
        </div>
      )}

      {(!queue || queue.length === 0) && (
        <div
          className="flex flex-col items-center gap-3 rounded-xl py-16 text-center"
          style={{
            backgroundColor: 'var(--color-bg-card)',
            border: '1px solid var(--color-border)',
          }}
        >
          <ClipboardList size={32} color="var(--color-text-muted)" />
          <p className="font-medium" style={{ color: 'var(--color-text-primary)' }}>
            Review queue is empty
          </p>
        </div>
      )}

      {queue && queue.length > 0 && (
        <div className="flex flex-col gap-2">
          {queue.map((item) => (
            <div
              key={item.id}
              className="rounded-xl p-4"
              style={{
                backgroundColor: 'var(--color-bg-card)',
                border: '1px solid var(--color-border)',
              }}
            >
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <p
                    className="truncate font-mono text-xs"
                    style={{ color: 'var(--color-text-muted)' }}
                  >
                    analysis {item.analysis_id.slice(0, 8)}
                  </p>
                  <p className="mt-1 text-sm" style={{ color: 'var(--color-text-primary)' }}>
                    relevance {item.relevance_score.toFixed(2)} · confidence{' '}
                    {item.confidence.toFixed(2)}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <button
                    onClick={() =>
                      decideMutation.mutate({ id: item.id, decision: 'approved' })
                    }
                    disabled={decideMutation.isPending}
                    className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium transition-colors disabled:opacity-60"
                    style={{
                      backgroundColor: 'color-mix(in srgb, var(--color-success) 12%, transparent)',
                      color: 'var(--color-success)',
                    }}
                  >
                    <CheckCircle2 size={13} />
                    Approve
                  </button>
                  <button
                    onClick={() =>
                      decideMutation.mutate({ id: item.id, decision: 'rejected' })
                    }
                    disabled={decideMutation.isPending}
                    className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium transition-colors disabled:opacity-60"
                    style={{
                      backgroundColor: 'color-mix(in srgb, var(--color-danger) 12%, transparent)',
                      color: 'var(--color-danger)',
                    }}
                  >
                    <XCircle size={13} />
                    Reject
                  </button>
                  <button
                    onClick={() =>
                      setExpandedId(expandedId === item.id ? null : item.id)
                    }
                    className="rounded-lg px-3 py-2 text-xs font-medium"
                    style={{
                      backgroundColor: 'var(--color-bg-input)',
                      color: 'var(--color-text-primary)',
                    }}
                  >
                    Correct
                  </button>
                </div>
              </div>

              {expandedId === item.id && (
                <CorrectForm
                  isPending={decideMutation.isPending}
                  onCancel={() => setExpandedId(null)}
                  onSubmit={(label, note) =>
                    decideMutation.mutate({
                      id: item.id,
                      decision: 'corrected',
                      correctedLabel: label,
                      note: note || undefined,
                    })
                  }
                />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
