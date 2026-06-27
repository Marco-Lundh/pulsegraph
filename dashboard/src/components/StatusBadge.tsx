interface StatusBadgeProps {
  status: string;
  size?: 'sm' | 'md';
}

const statusConfig: Record<
  string,
  { label: string; color: string; dot: string }
> = {
  success: {
    label: 'Success',
    color: 'color-mix(in srgb, var(--color-success) 15%, transparent)',
    dot: 'var(--color-success)',
  },
  failed: {
    label: 'Failed',
    color: 'color-mix(in srgb, var(--color-danger) 15%, transparent)',
    dot: 'var(--color-danger)',
  },
  running: {
    label: 'Running',
    color: 'color-mix(in srgb, var(--color-accent) 15%, transparent)',
    dot: 'var(--color-accent)',
  },
  pending: {
    label: 'Pending',
    color: 'color-mix(in srgb, var(--color-warning) 15%, transparent)',
    dot: 'var(--color-warning)',
  },
  delivered: {
    label: 'Delivered',
    color: 'color-mix(in srgb, var(--color-success) 15%, transparent)',
    dot: 'var(--color-success)',
  },
  active: {
    label: 'Active',
    color: 'color-mix(in srgb, var(--color-success) 15%, transparent)',
    dot: 'var(--color-success)',
  },
  paused: {
    label: 'Paused',
    color: 'color-mix(in srgb, var(--color-text-muted) 15%, transparent)',
    dot: 'var(--color-text-muted)',
  },
};

export function StatusBadge({ status, size = 'sm' }: StatusBadgeProps) {
  const cfg = statusConfig[status] ?? {
    label: status,
    color: 'color-mix(in srgb, var(--color-text-muted) 15%, transparent)',
    dot: 'var(--color-text-muted)',
  };

  const padding = size === 'sm' ? '2px 8px' : '4px 10px';
  const fontSize = size === 'sm' ? '11px' : '12px';

  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full font-medium"
      style={{
        backgroundColor: cfg.color,
        color: cfg.dot,
        padding,
        fontSize,
      }}
    >
      <span
        className="h-1.5 w-1.5 rounded-full"
        style={{ backgroundColor: cfg.dot }}
      />
      {cfg.label}
    </span>
  );
}
