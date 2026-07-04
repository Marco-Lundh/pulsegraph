import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, Download, Mail, Webhook } from 'lucide-react';
import {
  settingsApi,
  type NotificationChannel,
  type NotificationFrequency,
  type NotificationSettingOut,
} from '../api/settings';
import { deleteMyAccount, exportMyData } from '../api/auth';
import { useAuth } from '../contexts/AuthContext';
import { ApiError } from '../api/client';
import { ConfirmDialog } from '../components/ConfirmDialog';

const FREQUENCIES: { value: NotificationFrequency; label: string }[] = [
  { value: 'instant', label: 'Instant' },
  { value: 'daily_digest', label: 'Daily digest' },
];

const CARD_STYLE = {
  backgroundColor: 'var(--color-bg-card)',
  border: '1px solid var(--color-border)',
};

const INPUT_STYLE = {
  backgroundColor: 'var(--color-bg-input)',
  border: '1px solid var(--color-border)',
  color: 'var(--color-text-primary)',
};

interface ChannelCardProps {
  channel: NotificationChannel;
  icon: typeof Mail;
  title: string;
  description: string;
  destinationLabel: string;
  destinationPlaceholder: string;
  destinationRequired: boolean;
  setting: NotificationSettingOut | undefined;
}

function ChannelCard({
  channel,
  icon: Icon,
  title,
  description,
  destinationLabel,
  destinationPlaceholder,
  destinationRequired,
  setting,
}: ChannelCardProps) {
  const queryClient = useQueryClient();
  const [isActive, setIsActive] = useState(setting?.is_active ?? false);
  const [frequency, setFrequency] = useState<NotificationFrequency>(
    setting?.frequency ?? 'instant',
  );
  const [destination, setDestination] = useState(setting?.destination ?? '');
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);

  // Deliberately no effect re-syncing state from `setting`: the parent
  // gates rendering on isLoading, so these initializers already see the
  // loaded value on mount, and resyncing on every refetch (e.g. the
  // sibling card's save invalidating this query) would wipe an in-progress
  // edit here.

  const mutation = useMutation({
    mutationFn: () =>
      settingsApi.update(channel, {
        frequency,
        destination: destination.trim() || null,
        is_active: isActive,
      }),
    onSuccess: () => {
      setError('');
      setSaved(true);
      queryClient.invalidateQueries({ queryKey: ['notification-settings'] });
      setTimeout(() => setSaved(false), 2000);
    },
    onError: (err) => {
      setSaved(false);
      setError(err instanceof ApiError ? err.message : 'Failed to save.');
    },
  });

  const handleSubmit = (e: React.SubmitEvent<HTMLFormElement>) => {
    e.preventDefault();
    mutation.mutate();
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-4 rounded-xl p-5"
      style={CARD_STYLE}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <div
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
            style={{ backgroundColor: 'var(--color-bg-input)' }}
          >
            <Icon size={16} style={{ color: 'var(--color-text-secondary)' }} />
          </div>
          <div>
            <p
              className="text-sm font-semibold"
              style={{ color: 'var(--color-text-primary)' }}
            >
              {title}
            </p>
            <p
              className="mt-0.5 text-xs"
              style={{ color: 'var(--color-text-muted)' }}
            >
              {description}
            </p>
          </div>
        </div>

        <label className="flex shrink-0 cursor-pointer items-center gap-2">
          <input
            type="checkbox"
            checked={isActive}
            onChange={(e) => setIsActive(e.target.checked)}
            className="h-4 w-4 accent-[var(--color-accent)]"
          />
          <span
            className="text-xs font-medium"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            Enabled
          </span>
        </label>
      </div>

      <label className="flex flex-col gap-1.5">
        <span
          className="text-xs font-medium"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          {destinationLabel}
        </span>
        <input
          type="text"
          value={destination}
          onChange={(e) => setDestination(e.target.value)}
          required={destinationRequired && isActive}
          placeholder={destinationPlaceholder}
          className="rounded-lg px-3 py-2 text-sm outline-none"
          style={INPUT_STYLE}
        />
      </label>

      <div>
        <p
          className="mb-2 text-xs font-medium"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          Frequency
        </p>
        <div className="flex gap-2">
          {FREQUENCIES.map((f) => (
            <button
              key={f.value}
              type="button"
              onClick={() => setFrequency(f.value)}
              className="rounded-lg px-3 py-1.5 text-xs font-medium transition-colors"
              style={{
                backgroundColor:
                  frequency === f.value
                    ? 'var(--color-accent)'
                    : 'var(--color-bg-input)',
                border:
                  frequency === f.value
                    ? '1px solid var(--color-accent)'
                    : '1px solid var(--color-border)',
                color: frequency === f.value ? 'white' : 'var(--color-text-secondary)',
              }}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <p className="text-xs" style={{ color: 'var(--color-danger)' }}>
          {error}
        </p>
      )}

      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={mutation.isPending}
          className="self-start rounded-lg px-4 py-2 text-xs font-semibold transition-colors disabled:opacity-60"
          style={{ backgroundColor: 'var(--color-accent)', color: 'white' }}
        >
          {mutation.isPending ? 'Saving…' : 'Save'}
        </button>
        {saved && (
          <span className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            Saved
          </span>
        )}
      </div>
    </form>
  );
}

export function SettingsPage() {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const [exportError, setExportError] = useState('');
  const [deleteError, setDeleteError] = useState('');
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const { data: settings, isLoading } = useQuery({
    queryKey: ['notification-settings'],
    queryFn: () => settingsApi.list(),
  });

  const emailSetting = settings?.find((s) => s.channel === 'email');
  const webhookSetting = settings?.find((s) => s.channel === 'webhook');

  const exportMutation = useMutation({
    mutationFn: () => exportMyData(),
    onSuccess: (data) => {
      setExportError('');
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: 'application/json',
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'pulsegraph-data-export.json';
      link.click();
      URL.revokeObjectURL(url);
    },
    onError: (err) => {
      setExportError(err instanceof ApiError ? err.message : 'Export failed.');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteMyAccount(),
    onSuccess: () => {
      signOut();
      navigate('/login', { replace: true });
    },
    onError: (err) => {
      setConfirmingDelete(false);
      setDeleteError(
        err instanceof ApiError ? err.message : 'Failed to delete account.',
      );
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
    <div className="mx-auto flex max-w-2xl flex-col gap-8">
      <h1
        className="text-2xl font-semibold"
        style={{ color: 'var(--color-text-primary)' }}
      >
        Settings
      </h1>

      <section className="flex flex-col gap-4">
        <h2
          className="text-sm font-semibold uppercase tracking-wide"
          style={{ color: 'var(--color-text-muted)' }}
        >
          Notification channels
        </h2>
        <ChannelCard
          channel="email"
          icon={Mail}
          title="Email"
          description="Delivered to your account email unless overridden below."
          destinationLabel="Email address (optional)"
          destinationPlaceholder={user?.email ?? 'you@example.com'}
          destinationRequired={false}
          setting={emailSetting}
        />
        <ChannelCard
          channel="webhook"
          icon={Webhook}
          title="Webhook"
          description="Delivered as a signed JSON POST to the URL below."
          destinationLabel="Webhook URL"
          destinationPlaceholder="https://example.com/hooks/pulsegraph"
          destinationRequired
          setting={webhookSetting}
        />
      </section>

      <section className="flex flex-col gap-4">
        <h2
          className="text-sm font-semibold uppercase tracking-wide"
          style={{ color: 'var(--color-text-muted)' }}
        >
          Your data
        </h2>
        <div
          className="flex items-center justify-between gap-4 rounded-xl p-5"
          style={CARD_STYLE}
        >
          <div>
            <p
              className="text-sm font-semibold"
              style={{ color: 'var(--color-text-primary)' }}
            >
              Export my data
            </p>
            <p
              className="mt-0.5 text-xs"
              style={{ color: 'var(--color-text-muted)' }}
            >
              Download everything PulseGraph stores about you as JSON (GDPR
              portability).
            </p>
            {exportError && (
              <p className="mt-2 text-xs" style={{ color: 'var(--color-danger)' }}>
                {exportError}
              </p>
            )}
          </div>
          <button
            onClick={() => exportMutation.mutate()}
            disabled={exportMutation.isPending}
            className="flex shrink-0 items-center gap-2 rounded-lg px-4 py-2 text-xs font-semibold transition-colors disabled:opacity-60"
            style={{
              backgroundColor: 'var(--color-bg-input)',
              border: '1px solid var(--color-border)',
              color: 'var(--color-text-primary)',
            }}
          >
            <Download size={14} />
            {exportMutation.isPending ? 'Exporting…' : 'Export'}
          </button>
        </div>
      </section>

      <section className="flex flex-col gap-4">
        <h2
          className="text-sm font-semibold uppercase tracking-wide"
          style={{ color: 'var(--color-danger)' }}
        >
          Danger zone
        </h2>
        <div
          className="flex items-center justify-between gap-4 rounded-xl p-5"
          style={{
            backgroundColor: 'var(--color-bg-card)',
            border: '1px solid color-mix(in srgb, var(--color-danger) 30%, transparent)',
          }}
        >
          <div>
            <p
              className="text-sm font-semibold"
              style={{ color: 'var(--color-text-primary)' }}
            >
              Delete account
            </p>
            <p
              className="mt-0.5 text-xs"
              style={{ color: 'var(--color-text-muted)' }}
            >
              Permanently erases your account and all associated data (GDPR
              right to erasure). This cannot be undone.
            </p>
            {deleteError && (
              <p className="mt-2 text-xs" style={{ color: 'var(--color-danger)' }}>
                {deleteError}
              </p>
            )}
          </div>
          <button
            onClick={() => setConfirmingDelete(true)}
            className="flex shrink-0 items-center gap-2 rounded-lg px-4 py-2 text-xs font-semibold text-white transition-colors"
            style={{ backgroundColor: 'var(--color-danger)' }}
          >
            <AlertTriangle size={14} />
            Delete
          </button>
        </div>
      </section>

      {confirmingDelete && user && (
        <ConfirmDialog
          title="Delete account"
          message={`This permanently erases ${user.email} and all of your data (GDPR right to erasure). This cannot be undone.`}
          confirmText={user.email}
          isLoading={deleteMutation.isPending}
          onCancel={() => setConfirmingDelete(false)}
          onConfirm={() => deleteMutation.mutate()}
        />
      )}
    </div>
  );
}
