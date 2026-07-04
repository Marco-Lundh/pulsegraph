import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Trash2, Users } from 'lucide-react';
import { adminApi } from '../api/admin';
import { ApiError } from '../api/client';
import { ConfirmDialog } from '../components/ConfirmDialog';
import type { UserOut } from '../api/auth';

export function AdminUsersPage() {
  const queryClient = useQueryClient();
  const [target, setTarget] = useState<UserOut | null>(null);
  const [error, setError] = useState('');

  const { data: users, isLoading } = useQuery({
    queryKey: ['admin', 'users'],
    queryFn: () => adminApi.users(),
  });

  const deleteMutation = useMutation({
    mutationFn: (userId: string) => adminApi.deleteUser(userId),
    onSuccess: () => {
      setError('');
      setTarget(null);
      queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
    },
    onError: (err) => {
      setTarget(null);
      setError(
        err instanceof ApiError ? err.message : 'Failed to delete user.',
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
    <div>
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

      {(!users || users.length === 0) && (
        <div
          className="flex flex-col items-center gap-3 rounded-xl py-16 text-center"
          style={{
            backgroundColor: 'var(--color-bg-card)',
            border: '1px solid var(--color-border)',
          }}
        >
          <Users size={32} color="var(--color-text-muted)" />
          <p className="font-medium" style={{ color: 'var(--color-text-primary)' }}>
            No users found
          </p>
        </div>
      )}

      {users && users.length > 0 && (
        <div
          className="overflow-hidden rounded-xl"
          style={{
            backgroundColor: 'var(--color-bg-card)',
            border: '1px solid var(--color-border)',
          }}
        >
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                {['Email', 'Role', 'Created', ''].map((h) => (
                  <th
                    key={h}
                    className="px-4 py-3 text-left text-xs font-medium"
                    style={{ color: 'var(--color-text-muted)' }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr
                  key={u.id}
                  style={{ borderBottom: '1px solid var(--color-border)' }}
                  className="last:border-0"
                >
                  <td className="px-4 py-3" style={{ color: 'var(--color-text-primary)' }}>
                    {u.email}
                  </td>
                  <td
                    className="px-4 py-3 capitalize"
                    style={{ color: 'var(--color-text-secondary)' }}
                  >
                    {u.role}
                  </td>
                  <td className="px-4 py-3" style={{ color: 'var(--color-text-secondary)' }}>
                    {new Date(u.created_at).toLocaleDateString('sv-SE')}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => setTarget(u)}
                      className="rounded-md p-1.5 transition-colors"
                      style={{ color: 'var(--color-danger)' }}
                      title="Delete user"
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {target && (
        <ConfirmDialog
          title="Delete user"
          message={`This permanently erases ${target.email} and all of their data (GDPR right to erasure). This cannot be undone.`}
          confirmText={target.email}
          isLoading={deleteMutation.isPending}
          onCancel={() => setTarget(null)}
          onConfirm={() => deleteMutation.mutate(target.id)}
        />
      )}
    </div>
  );
}
