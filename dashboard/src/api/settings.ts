import { api } from './client';

export type NotificationChannel = 'email' | 'webhook';
export type NotificationFrequency = 'instant' | 'daily_digest';

export interface NotificationSettingOut {
  user_id: string;
  channel: NotificationChannel;
  frequency: NotificationFrequency;
  destination: string | null;
  is_active: boolean;
}

export interface NotificationSettingUpdate {
  frequency: NotificationFrequency;
  destination?: string | null;
  is_active: boolean;
}

export const settingsApi = {
  list: (): Promise<NotificationSettingOut[]> =>
    api.get<NotificationSettingOut[]>('/notifications/settings'),
  update: (
    channel: NotificationChannel,
    body: NotificationSettingUpdate,
  ): Promise<NotificationSettingOut> =>
    api.put<NotificationSettingOut>(`/notifications/settings/${channel}`, body),
};
