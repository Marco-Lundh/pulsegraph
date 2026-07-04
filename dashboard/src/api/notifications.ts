import { api } from './client';

export type NotificationChannel = 'email' | 'webhook' | 'in_app';
export type NotificationStatus = 'pending' | 'sent' | 'failed';

export interface NotificationOut {
  id: string;
  user_id: string;
  analysis_id: string;
  channel: NotificationChannel;
  dedup_key: string;
  status: NotificationStatus;
  delivered_at: string | null;
}

export const notificationsApi = {
  list: (): Promise<NotificationOut[]> =>
    api.get<NotificationOut[]>('/notifications'),
};
