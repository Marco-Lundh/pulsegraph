import { api } from './client';

export type NotificationChannel = 'dashboard' | 'email' | 'webhook';
export type NotificationStatus = 'pending' | 'sent' | 'failed';

export interface Delivery {
  channel: NotificationChannel;
  status: NotificationStatus;
  delivered_at: string | null;
  attempts: number;
}

export interface NotificationOut {
  id: string;
  user_id: string;
  analysis_id: string;
  channel: NotificationChannel;
  dedup_key: string;
  status: NotificationStatus;
  delivered_at: string | null;
  // Per-channel delivery status of the email/webhook sends for this item
  // (ADR 0016). The feed row itself is the dashboard channel.
  deliveries: Delivery[];
}

export const notificationsApi = {
  list: (): Promise<NotificationOut[]> =>
    api.get<NotificationOut[]>('/notifications'),
};
