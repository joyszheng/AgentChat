import { ToolCallState, ToolCallStatus } from './types';

export const getErrorDetail = (error: unknown, fallback: string) => {
  if (typeof error === 'object' && error !== null && 'response' in error) {
    const response = (error as { response?: { data?: { detail?: string } } }).response;
    return response?.data?.detail || fallback;
  }
  return error instanceof Error ? error.message : fallback;
};

export const getStreamHeaders = () => {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
};

export const mergeToolCalls = (
  current: ToolCallState[] | undefined,
  toolNames: string[],
  status: ToolCallStatus,
) => {
  const byName = new Map((current || []).map((item) => [item.name, item]));
  for (const name of toolNames) {
    byName.set(name, { name, status });
  }
  return Array.from(byName.values());
};

export const getGroupName = (timeStr: string | null | undefined) => {
  if (!timeStr) return '早期会话';
  const date = new Date(timeStr);
  const now = new Date();

  const dateStr = date.toDateString();
  const nowStr = now.toDateString();
  if (dateStr === nowStr) return '今天';

  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (dateStr === yesterday.toDateString()) return '昨天';

  const diffTime = Math.abs(now.getTime() - date.getTime());
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
  if (diffDays <= 7) return '一周内';

  return `${date.getFullYear()}-${(date.getMonth() + 1).toString().padStart(2, '0')}`;
};
