import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check } from 'lucide-react';
import { adminApi, type PromptOut } from '../api/admin';
import { StatusBadge } from '../components/StatusBadge';

function formatDatetime(iso: string): string {
  return new Date(iso).toLocaleString('sv-SE', {
    dateStyle: 'short',
    timeStyle: 'short',
  });
}

const roleLabels: Record<string, string> = {
  analyzer: 'Analyzer',
  evaluator: 'Evaluator',
};

/**
 * Editor for one prompt family (all versions sharing a name). Keyed on the
 * active version's id by the parent, so activating or saving a new version
 * remounts it and the textarea re-seeds from the new active template.
 */
function PromptEditor({
  name,
  versions,
}: {
  name: string;
  versions: PromptOut[];
}) {
  const queryClient = useQueryClient();
  const active = versions.find((v) => v.is_active) ?? versions[0];
  const [template, setTemplate] = useState(active?.template ?? '');

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ['admin', 'prompts'] });

  const saveMutation = useMutation({
    mutationFn: () => adminApi.createPrompt({ name, template }),
    onSuccess: invalidate,
  });

  const activateMutation = useMutation({
    mutationFn: (id: string) => adminApi.activatePrompt(id),
    onSuccess: invalidate,
  });

  const dirty = template !== (active?.template ?? '');

  return (
    <div
      className="mb-6 rounded-xl p-5"
      style={{
        backgroundColor: 'var(--color-bg-card)',
        border: '1px solid var(--color-border)',
      }}
    >
      <div className="mb-3 flex items-center gap-2">
        <h2
          className="text-sm font-semibold"
          style={{ color: 'var(--color-text-primary)' }}
        >
          {roleLabels[active?.role] ?? name}
        </h2>
        <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
          v{active?.version} active
        </span>
      </div>

      <textarea
        value={template}
        onChange={(e) => setTemplate(e.target.value)}
        rows={7}
        className="w-full resize-y rounded-lg p-3 font-mono text-xs leading-relaxed"
        style={{
          backgroundColor: 'var(--color-bg-input)',
          border: '1px solid var(--color-border)',
          color: 'var(--color-text-primary)',
        }}
      />

      <div className="mt-3 flex items-center gap-3">
        <button
          onClick={() => saveMutation.mutate()}
          disabled={!dirty || template.trim().length === 0 || saveMutation.isPending}
          className="rounded-lg px-3 py-2 text-xs font-medium transition-colors disabled:opacity-50"
          style={{
            backgroundColor: 'var(--color-accent)',
            color: 'var(--color-accent-contrast, #fff)',
          }}
        >
          {saveMutation.isPending ? 'Saving…' : 'Save as new version'}
        </button>
        {dirty && (
          <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            Unsaved edit — saving creates v{(active?.version ?? 0) + 1} and
            activates it.
          </span>
        )}
      </div>

      <div
        className="mt-5 border-t pt-4"
        style={{ borderColor: 'var(--color-border)' }}
      >
        <p className="mb-2 text-xs font-medium" style={{ color: 'var(--color-text-muted)' }}>
          Version history
        </p>
        <div className="flex flex-col gap-1.5">
          {versions.map((v) => (
            <div key={v.id} className="flex items-center gap-3 text-xs">
              <span
                className="w-8 font-mono"
                style={{ color: 'var(--color-text-secondary)' }}
              >
                v{v.version}
              </span>
              {v.is_active ? (
                <StatusBadge status="active" />
              ) : (
                <button
                  onClick={() => activateMutation.mutate(v.id)}
                  disabled={activateMutation.isPending}
                  className="rounded px-2 py-0.5 text-xs font-medium transition-colors disabled:opacity-50"
                  style={{
                    backgroundColor: 'var(--color-bg-input)',
                    border: '1px solid var(--color-border)',
                    color: 'var(--color-text-primary)',
                  }}
                >
                  Activate
                </button>
              )}
              <span style={{ color: 'var(--color-text-muted)' }}>
                {formatDatetime(v.created_at)}
              </span>
              {v.is_active && (
                <Check size={13} color="var(--color-success)" />
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function AdminPromptsPage() {
  const { data: prompts, isLoading } = useQuery({
    queryKey: ['admin', 'prompts'],
    queryFn: () => adminApi.prompts(),
  });

  if (isLoading || !prompts) {
    return (
      <div className="flex justify-center py-16">
        <div className="h-7 w-7 animate-spin rounded-full border-2 border-[var(--color-accent)] border-t-transparent" />
      </div>
    );
  }

  // Group versions by prompt name (analyzer / evaluator).
  const byName = new Map<string, PromptOut[]>();
  for (const p of prompts) {
    const list = byName.get(p.name) ?? [];
    list.push(p);
    byName.set(p.name, list);
  }

  return (
    <div>
      <p className="mb-5 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
        The active version of each prompt is what the pipeline loads at
        runtime. Saving an edit creates a new version and activates it.
      </p>
      {[...byName.entries()].map(([name, versions]) => {
        const active = versions.find((v) => v.is_active) ?? versions[0];
        return (
          <PromptEditor key={active?.id ?? name} name={name} versions={versions} />
        );
      })}
    </div>
  );
}
