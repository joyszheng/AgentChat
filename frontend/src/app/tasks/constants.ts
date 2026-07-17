import {
  BadgeAlertIcon,
  BanIcon,
  CircleCheckIcon,
  CircleDashedIcon,
  PlayIcon,
} from 'lucide-animated';
import {
  TaskStatus,
  TaskPriority,
  TaskExecutionMode,
  TaskRecurrenceRule,
  AutoRefreshIntervalMs,
  AnimatedIconComponent,
  TaskFormState,
} from './types';

export const statusOptions: { label: string; value: TaskStatus | 'all' }[] = [
  { label: '全部状态', value: 'all' },
  { label: '待处理', value: 'todo' },
  { label: '进行中', value: 'in_progress' },
  { label: '阻塞', value: 'blocked' },
  { label: '已完成', value: 'done' },
  { label: '已取消', value: 'canceled' },
];

export const priorityOptions: { label: string; value: TaskPriority | 'all' }[] = [
  { label: '全部优先级', value: 'all' },
  { label: '低', value: 'low' },
  { label: '普通', value: 'normal' },
  { label: '高', value: 'high' },
  { label: '紧急', value: 'urgent' },
];

export const executionModeOptions: { label: string; value: TaskExecutionMode }[] = [
  { label: '手动处理', value: 'manual' },
  { label: 'AI 自动执行', value: 'ai_auto' },
];

export const recurrenceOptions: { label: string; value: TaskRecurrenceRule }[] = [
  { label: '只执行一次', value: 'none' },
  { label: '每天重复', value: 'daily' },
];

export const autoRefreshOptions: { label: string; shortLabel: string; value: AutoRefreshIntervalMs }[] = [
  { label: '关闭自动刷新', shortLabel: '手动', value: 0 },
  { label: '每 10 秒', shortLabel: '10 秒', value: 10000 },
  { label: '每 30 秒', shortLabel: '30 秒', value: 30000 },
  { label: '每 1 分钟', shortLabel: '1 分钟', value: 60000 },
  { label: '每 5 分钟', shortLabel: '5 分钟', value: 300000 },
  { label: '每 10 分钟', shortLabel: '10 分钟', value: 600000 },
];

export const statusMeta: Record<TaskStatus, { label: string; color: string; Icon: AnimatedIconComponent }> = {
  todo: { label: '待处理', color: 'default', Icon: CircleDashedIcon },
  in_progress: { label: '进行中', color: 'processing', Icon: PlayIcon },
  blocked: { label: '阻塞', color: 'warning', Icon: BadgeAlertIcon },
  done: { label: '已完成', color: 'success', Icon: CircleCheckIcon },
  canceled: { label: '已取消', color: 'error', Icon: BanIcon },
};

export const priorityMeta: Record<TaskPriority, { label: string; color: string }> = {
  low: { label: '低', color: 'blue' },
  normal: { label: '普通', color: 'default' },
  high: { label: '高', color: 'orange' },
  urgent: { label: '紧急', color: 'red' },
};

export const runStatusMeta: Record<string, string> = {
  idle: '未启用',
  pending: '等待执行',
  queued: '已入队列',
  running: '执行中',
  success: '执行成功',
  failed: '执行失败',
};

export const runRecordMeta: Record<string, { label: string; className: string }> = {
  running: { label: '执行中', className: 'border-blue-100 bg-blue-50 text-blue-700' },
  success: { label: '执行成功', className: 'border-emerald-100 bg-emerald-50 text-emerald-700' },
  failed: { label: '执行失败', className: 'border-red-100 bg-red-50 text-red-700' },
};

export const taskTagBaseClassName =
  'inline-flex h-6 shrink-0 items-center gap-1 rounded-md border px-2 text-xs font-medium leading-none whitespace-nowrap';

export const statusTagClassName: Record<TaskStatus, string> = {
  todo: 'border-gray-200 bg-gray-50 text-gray-700',
  in_progress: 'border-blue-100 bg-blue-50 text-blue-700',
  blocked: 'border-amber-100 bg-amber-50 text-amber-700',
  done: 'border-emerald-100 bg-emerald-50 text-emerald-700',
  canceled: 'border-red-100 bg-red-50 text-red-700',
};

export const priorityTagClassName: Record<TaskPriority, string> = {
  low: 'border-sky-100 bg-sky-50 text-sky-700',
  normal: 'border-gray-200 bg-gray-50 text-gray-700',
  high: 'border-orange-100 bg-orange-50 text-orange-700',
  urgent: 'border-red-100 bg-red-50 text-red-700',
};

export const emptyForm: TaskFormState = {
  title: '',
  description: '',
  status: 'todo',
  priority: 'normal',
  dueAt: '',
  executionMode: 'manual',
  scheduleAt: '',
  recurrenceRule: 'none',
  aiPrompt: '',
  notifyEmail: '',
};
