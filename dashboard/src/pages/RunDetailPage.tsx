import { useNavigate, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Check } from 'lucide-react';
import { runsApi, type ModelKind } from '../api/runs';
import { StatusBadge } from '../components/StatusBadge';

function formatDatetime(iso: string | null): string {
  if (!iso) {
    return '—';
  }
  return new Date(iso).toLocaleString('sv-SE', {
    dateStyle: 'short',
    timeStyle: 'short',
  });
}

function formatDuration(start: string, end: string | null): string {
  if (!end) {
    return '—';
  }
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (ms < 1000) {
    return `${ms}ms`;
  }
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatScore(value: number | null): string {
  if (value === null) {
    return '—';
  }
  return `${Math.round(value * 100)}%`;
}

const modelLabels: Record<ModelKind, string> = {
  ollama: 'Ollama',
  claude: 'Claude',
};

// Local model tint is muted (free/on-prem); the cloud model is accented
// so the cost-bearing calls (ADR 0002/0008) stand out at a glance.
function ModelBadge({ model, version }: { model: ModelKind; version: string }) {
  const isCloud = model === 'claude';
  return (
    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
      title={version}
      style={{
        backgroundColor: isCloud
          ? 'color-mix(in srgb, var(--color-accent) 15%, transparent)'
          : 'color-mix(in srgb, var(--color-text-muted) 15%, transparent)',
        color: isCloud ? 'var(--color-accent)' : 'var(--color-text-secondary)',
      }}
    >
      {modelLabels[model]}
    </span>
  );
}

export function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();

  const { data: run, isLoading } = useQuery({
    queryKey: ['runs', 'detail', runId],
    queryFn: () => runsApi.get(runId!),
    enabled: !!runId,
  });

  const { data: items } = useQuery({
    queryKey: ['runs', runId, 'items'],
    queryFn: () => runsApi.itemsForRun(runId!),
    enabled: !!runId,
  });

  if (isLoading || !run) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-7 w-7 animate-spin rounded-full border-2 border-[var(--color-accent)] border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl">
      <button
        onClick={() => navigate(-1)}
        className="mb-6 flex items-center gap-2 text-sm transition-colors"
        style={{ color: 'var(--color-text-secondary)' }}
      >
        <ArrowLeft size={14} />
        Back
      </button>

      <div
        className="mb-6 rounded-xl p-6"
        style={{
          backgroundColor: 'var(--color-bg-card)',
          border: '1px solid var(--color-border)',
        }}
      >
        <div className="flex items-center gap-3">
          <StatusBadge status={run.status} />
          <h1
            className="text-lg font-semibold"
            style={{ color: 'var(--color-text-primary)' }}
          >
            Run detail
          </h1>
        </div>

        <dl
          className="mt-5 grid grid-cols-2 gap-4 border-t pt-5 text-sm sm:grid-cols-4"
          style={{ borderColor: 'var(--color-border)' }}
        >
          {[
            ['Started', formatDatetime(run.started_at)],
            ['Finished', formatDatetime(run.finished_at)],
            ['Duration', formatDuration(run.started_at, run.finished_at)],
            ['Items', String(items?.length ?? 0)],
          ].map(([label, value]) => (
            <div key={label}>
              <dt style={{ color: 'var(--color-text-muted)' }} className="text-xs">
                {label}
              </dt>
              <dd
                style={{ color: 'var(--color-text-primary)' }}
                className="mt-0.5 font-medium"
              >
                {value}
              </dd>
            </div>
          ))}
        </dl>

        {/* LangSmith trace link (ADR 0007): connects a run — especially a
            failed one — back to its underlying execution trace. */}
        <div
          className="mt-4 border-t pt-4"
          style={{ borderColor: 'var(--color-border)' }}
        >
          <dt style={{ color: 'var(--color-text-muted)' }} className="text-xs">
            LangSmith trace
          </dt>
          <dd
            className="mt-0.5 truncate font-mono text-xs"
            style={{ color: 'var(--color-text-secondary)' }}
            title={run.langsmith_trace_id ?? undefined}
          >
            {run.langsmith_trace_id ?? 'Not traced (tracing disabled)'}
          </dd>
        </div>

        {run.error && (
          <div
            className="mt-4 rounded-lg p-3 text-sm"
            style={{
              backgroundColor: 'color-mix(in srgb, var(--color-danger) 10%, transparent)',
              color: 'var(--color-danger)',
            }}
          >
            {run.error}
          </div>
        )}
      </div>

      <h2
        className="mb-3 text-sm font-medium"
        style={{ color: 'var(--color-text-secondary)' }}
      >
        Analyzed items
      </h2>

      {!items || items.length === 0 ? (
        <p className="text-sm" style={{ color: 'var(--color-text-muted)' }}>
          No items were analyzed in this run.
        </p>
      ) : (
        <div
          className="overflow-x-auto rounded-xl"
          style={{
            backgroundColor: 'var(--color-bg-card)',
            border: '1px solid var(--color-border)',
          }}
        >
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                {['Item', 'Model', 'Relevance', 'Confidence', 'Eval', 'Notified'].map(
                  (h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left text-xs font-medium"
                      style={{ color: 'var(--color-text-muted)' }}
                    >
                      {h}
                    </th>
                  )
                )}
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr
                  key={item.item_id}
                  style={{ borderBottom: '1px solid var(--color-border)' }}
                  className="last:border-0"
                >
                  <td className="px-4 py-3">
                    <div
                      className="max-w-md truncate"
                      style={{ color: 'var(--color-text-primary)' }}
                      title={item.summary}
                    >
                      {item.summary}
                    </div>
                    {item.external_id && (
                      <div
                        className="mt-0.5 font-mono text-xs"
                        style={{ color: 'var(--color-text-muted)' }}
                      >
                        {item.external_id}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <ModelBadge
                      model={item.model_used}
                      version={item.model_version}
                    />
                  </td>
                  <td
                    className="px-4 py-3"
                    style={{ color: 'var(--color-text-secondary)' }}
                  >
                    {formatScore(item.relevance_score)}
                  </td>
                  <td
                    className="px-4 py-3"
                    style={{ color: 'var(--color-text-secondary)' }}
                  >
                    {formatScore(item.analysis_confidence)}
                  </td>
                  <td className="px-4 py-3">
                    {item.eval_status ? (
                      <StatusBadge status={item.eval_status} />
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {item.notified ? (
                      <Check size={16} color="var(--color-success)" />
                    ) : (
                      <span style={{ color: 'var(--color-text-muted)' }}>—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
