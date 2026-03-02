import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router';
import api from '../api/client';

export type Notification = {
  id: number;
  title: string;
  body: string;
  created_at: string;
  read_at: string | null;
};

export function useNotifications() {
  const { projectId } = useParams<{ projectId: string }>();
  const queryClient = useQueryClient();

  const query = useQuery<Notification[]>({
    queryKey: ['notifications', projectId],
    queryFn: async () => {
      if (!projectId) return [];
      const { data, error } = await api.GET(
        '/p/{project_id}/notifications',
        { params: { path: { project_id: projectId } } },
      );
      if (error) throw new Error('Failed to fetch notifications');
      return data.notifications;
    },
    enabled: !!projectId,
  });

  const unreadCountQuery = useQuery<{ count: number }>({
    queryKey: ['notifications-unread-count', projectId],
    queryFn: async () => {
      if (!projectId) return { count: 0 };
      const { data, error } = await api.GET(
        '/p/{project_id}/notifications/unread-count',
        { params: { path: { project_id: projectId } } },
      );
      if (error) return { count: 0 };
      return { count: data.count };
    },
    enabled: !!projectId,
    refetchInterval: 30000, // Poll every 30s for sync
  });

  const markReadMutation = useMutation({
    mutationFn: async (notificationId: number) => {
      if (!projectId) return;
      await api.POST(
        '/p/{project_id}/notifications/{notification_id}/read',
        {
          params: {
            path: { project_id: projectId, notification_id: notificationId },
          },
        },
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications', projectId] });
      queryClient.invalidateQueries({ queryKey: ['notifications-unread-count', projectId] });
    },
  });

  return {
    notifications: query.data || [],
    isLoading: query.isLoading,
    unreadCount: unreadCountQuery.data?.count || 0,
    markRead: markReadMutation.mutate,
  };
}
