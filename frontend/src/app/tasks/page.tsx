'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Button,
  DatePicker,
  Drawer,
  Input,
  Modal,
  Popconfirm,
  Select,
  message,
} from 'antd';
import zhCN from 'antd/es/date-picker/locale/zh_CN';
import dayjs, { Dayjs } from 'dayjs';
import 'dayjs/locale/zh-cn';
import {
  BadgeAlertIcon,
  BanIcon,
  BotIcon,
  CircleCheckIcon,
  CircleDashedIcon,
  ClockIcon,
  DeleteIcon,
  HistoryIcon,
  PlayIcon,
  PlusIcon,
  RefreshCwIcon,
  SearchIcon,
  SquarePenIcon,
} from 'lucide-animated';
import http from '@/lib/http/axios';
import PageHeader from '@/components/PageHeader';

type TaskStatus = 'todo' | 'in_progress' | 'blocked' | 'done' | 'canceled';
type TaskPriority = 'low' | 'normal' | 'high' | 'urgent';
type TaskExecutionMode = 'manual' | 'ai_auto';
type TaskRecurrenceRule = 'none' | 'daily';
type AutoRefreshIntervalMs = 0 | 10000 | 30000 | 60000 | 300000 | 600000;

interface TaskItem {
  id: number;
  title: string;
  description?: string | null;
  completed: boolean;
  status: TaskStatus;
  priority: TaskPriority;
  due_at?: string | null;
  source: 'manual' | 'ai';
  execution_mode: TaskExecutionMode;
  schedule_at?: string | null;
  recurrence_rule: TaskRecurrenceRule;
  ai_prompt?: string | null;
  notify_email?: string | null;
  last_run_at?: string | null;
  next_run_at?: string | null;
  run_status: string;
  run_error?: string | null;
  run_count: number;
  created_at: string;
  updated_at: string;
}

interface TaskRunItem {
  id: number;
  task_id: number;
  status: string;
  output?: string | null;
  error_message?: string | null;
  tools_used: string[];
  email_sent: boolean;
  started_at: string;
  finished_at?: string | null;
}

interface TaskFormState {
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  dueAt: string;
  executionMode: TaskExecutionMode;
  scheduleAt: string;
  recurrenceRule: TaskRecurrenceRule;
  aiPrompt: string;
  notifyEmail: string;
}

type AnimatedIconComponent = React.ComponentType<{
  size?: number;
  className?: string;
  animateOnHover?: boolean;
}>;

const statusOptions: { label: string; value: TaskStatus | 'all' }[] = [
  { label: '全部状态', value: 'all' },
  { label: '待处理', value: 'todo' },
  { label: '进行中', value: 'in_progress' },
  { label: '阻塞', value: 'blocked' },
  { label: '已完成', value: 'done' },
  { label: '已取消', value: 'canceled' },
];

const priorityOptions: { label: string; value: TaskPriority | 'all' }[] = [
  { label: '全部优先级', value: 'all' },
  { label: '低', value: 'low' },
  { label: '普通', value: 'normal' },
  { label: '高', value: 'high' },
  { label: '紧急', value: 'urgent' },
];

const executionModeOptions: { label: string; value: TaskExecutionMode }[] = [
  { label: '手动处理', value: 'manual' },
  { label: 'AI 自动执行', value: 'ai_auto' },
];

const recurrenceOptions: { label: string; value: TaskRecurrenceRule }[] = [
  { label: '只执行一次', value: 'none' },
  { label: '每天重复', value: 'daily' },
];

const autoRefreshOptions: { label: string; shortLabel: string; value: AutoRefreshIntervalMs }[] = [
  { label: '关闭自动刷新', shortLabel: '手动', value: 0 },
  { label: '每 10 秒', shortLabel: '10 秒', value: 10000 },
  { label: '每 30 秒', shortLabel: '30 秒', value: 30000 },
  { label: '每 1 分钟', shortLabel: '1 分钟', value: 60000 },
  { label: '每 5 分钟', shortLabel: '5 分钟', value: 300000 },
  { label: '每 10 分钟', shortLabel: '10 分钟', value: 600000 },
];

const statusMeta: Record<TaskStatus, { label: string; color: string; Icon: AnimatedIconComponent }> = {
  todo: { label: '待处理', color: 'default', Icon: CircleDashedIcon },
  in_progress: { label: '进行中', color: 'processing', Icon: PlayIcon },
  blocked: { label: '阻塞', color: 'warning', Icon: BadgeAlertIcon },
  done: { label: '已完成', color: 'success', Icon: CircleCheckIcon },
  canceled: { label: '已取消', color: 'error', Icon: BanIcon },
};

const priorityMeta: Record<TaskPriority, { label: string; color: string }> = {
  low: { label: '低', color: 'blue' },
  normal: { label: '普通', color: 'default' },
  high: { label: '高', color: 'orange' },
  urgent: { label: '紧急', color: 'red' },
};

const runStatusMeta: Record<string, string> = {
  idle: '未启用',
  pending: '等待执行',
  queued: '已入队列',
  running: '执行中',
  success: '执行成功',
  failed: '执行失败',
};

const runRecordMeta: Record<string, { label: string; className: string }> = {
  running: { label: '执行中', className: 'border-blue-100 bg-blue-50 text-blue-700' },
  success: { label: '执行成功', className: 'border-emerald-100 bg-emerald-50 text-emerald-700' },
  failed: { label: '执行失败', className: 'border-red-100 bg-red-50 text-red-700' },
};

const taskTagBaseClassName =
  'inline-flex h-6 shrink-0 items-center gap-1 rounded-md border px-2 text-xs font-medium leading-none whitespace-nowrap';

const statusTagClassName: Record<TaskStatus, string> = {
  todo: 'border-gray-200 bg-gray-50 text-gray-700',
  in_progress: 'border-blue-100 bg-blue-50 text-blue-700',
  blocked: 'border-amber-100 bg-amber-50 text-amber-700',
  done: 'border-emerald-100 bg-emerald-50 text-emerald-700',
  canceled: 'border-red-100 bg-red-50 text-red-700',
};

const priorityTagClassName: Record<TaskPriority, string> = {
  low: 'border-sky-100 bg-sky-50 text-sky-700',
  normal: 'border-gray-200 bg-gray-50 text-gray-700',
  high: 'border-orange-100 bg-orange-50 text-orange-700',
  urgent: 'border-red-100 bg-red-50 text-red-700',
};

const emptyForm: TaskFormState = {
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

dayjs.locale('zh-cn');

const roundToNextFiveMinutes = () => {
  const now = dayjs().add(1, 'hour');
  const minute = Math.ceil(now.minute() / 5) * 5;
  return now.minute(minute).second(0).millisecond(0);
};

const toPayloadDateTime = (value: string) => {
  return value || null;
};

const toPickerValue = (value: string) => {
  if (!value) return null;
  const date = dayjs(value);
  return date.isValid() ? date : null;
};

const isPastDateTime = (value: string) => {
  const date = toPickerValue(value);
  return Boolean(date && date.isBefore(dayjs()));
};

const disabledPastDate = (current: Dayjs) => {
  return current.endOf('day').isBefore(dayjs());
};

const disabledPastTime = (current: Dayjs | null) => {
  if (!current || !current.isSame(dayjs(), 'day')) {
    return {};
  }

  const now = dayjs();
  return {
    disabledHours: () => Array.from({ length: now.hour() }, (_, hour) => hour),
    disabledMinutes: (selectedHour: number) => (
      selectedHour === now.hour()
        ? Array.from({ length: now.minute() + 1 }, (_, minute) => minute)
        : []
    ),
  };
};

const formatDateTime = (value?: string | null) => {
  if (!value) return '未设置';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '未设置';
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
};

const formatCountdownSeconds = (seconds: number) => {
  const safeSeconds = Math.max(0, seconds);
  const minutes = Math.floor(safeSeconds / 60);
  const remainingSeconds = safeSeconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`;
};

export default function TasksPage() {
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [statusFilter, setStatusFilter] = useState<TaskStatus | 'all'>('all');
  const [priorityFilter, setPriorityFilter] = useState<TaskPriority | 'all'>('all');
  const [search, setSearch] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<TaskItem | null>(null);
  const [form, setForm] = useState<TaskFormState>(emptyForm);
  const [historyTask, setHistoryTask] = useState<TaskItem | null>(null);
  const [runs, setRuns] = useState<TaskRunItem[]>([]);
  const [runsLoading, setRunsLoading] = useState(false);
  const [autoRefreshMs, setAutoRefreshMs] = useState<AutoRefreshIntervalMs>(0);
  const [autoRefreshRemainingSeconds, setAutoRefreshRemainingSeconds] = useState(0);

  const openTasks = useMemo(
    () => tasks.filter((task) => task.status !== 'done' && task.status !== 'canceled').length,
    [tasks],
  );
  const doneTasks = tasks.filter((task) => task.status === 'done').length;
  const dueAtPresets = useMemo(
    () => [
      { label: '1 小时后', value: roundToNextFiveMinutes() },
      { label: '明天 09:00', value: dayjs().add(1, 'day').hour(9).minute(0).second(0) },
      { label: '三天后 18:00', value: dayjs().add(3, 'day').hour(18).minute(0).second(0) },
      { label: '一周后 09:00', value: dayjs().add(1, 'week').hour(9).minute(0).second(0) },
    ],
    [modalOpen],
  );

  const fetchTasks = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: '100' });
      if (statusFilter !== 'all') params.set('status', statusFilter);
      if (priorityFilter !== 'all') params.set('priority', priorityFilter);
      if (search.trim()) params.set('search', search.trim());
      const data = await http.get<TaskItem[], TaskItem[]>(`/tasks?${params.toString()}`);
      setTasks(data);
    } catch {
      message.error('任务加载失败');
    } finally {
      setLoading(false);
    }
  }, [priorityFilter, search, statusFilter]);

  const autoRefreshSelectOptions = useMemo(
    () =>
      autoRefreshOptions.map((option) => ({
        value: option.value,
        label:
          option.value === autoRefreshMs && option.value > 0
            ? `${option.shortLabel} · ${formatCountdownSeconds(autoRefreshRemainingSeconds)}`
            : option.label,
      })),
    [autoRefreshMs, autoRefreshRemainingSeconds],
  );

  const handleAutoRefreshSelect = useCallback(
    (nextInterval: AutoRefreshIntervalMs) => {
      setAutoRefreshMs(nextInterval);
      setAutoRefreshRemainingSeconds(Math.ceil(nextInterval / 1000));
      void fetchTasks();
    },
    [fetchTasks],
  );

  useEffect(() => {
    const timer = window.setTimeout(() => void fetchTasks(), 120);
    return () => window.clearTimeout(timer);
  }, [fetchTasks]);

  useEffect(() => {
    if (autoRefreshMs === 0) {
      return undefined;
    }

    const intervalSeconds = Math.ceil(autoRefreshMs / 1000);
    let nextRefreshAt = Date.now() + autoRefreshMs;

    const countdownTimer = window.setInterval(() => {
      setAutoRefreshRemainingSeconds(
        Math.max(0, Math.ceil((nextRefreshAt - Date.now()) / 1000)),
      );
    }, 1000);

    const refreshTimer = window.setInterval(() => {
      nextRefreshAt = Date.now() + autoRefreshMs;
      setAutoRefreshRemainingSeconds(intervalSeconds);
      void fetchTasks();
    }, autoRefreshMs);

    return () => {
      window.clearInterval(countdownTimer);
      window.clearInterval(refreshTimer);
    };
  }, [autoRefreshMs, fetchTasks]);

  const openCreateModal = () => {
    setEditingTask(null);
    setForm(emptyForm);
    setModalOpen(true);
  };

  const openEditModal = (task: TaskItem) => {
    setEditingTask(task);
    setForm({
      title: task.title,
      description: task.description || '',
      status: task.status,
      priority: task.priority,
      dueAt: task.due_at || '',
      executionMode: task.execution_mode,
      scheduleAt: task.schedule_at || task.next_run_at || '',
      recurrenceRule: task.recurrence_rule || 'none',
      aiPrompt: task.ai_prompt || '',
      notifyEmail: task.notify_email || '',
    });
    setModalOpen(true);
  };

  const saveTask = async () => {
    if (!form.title.trim()) {
      message.warning('请输入任务标题');
      return;
    }
    if (form.executionMode === 'ai_auto') {
      if (!form.scheduleAt) {
        message.warning('请选择 AI 自动执行时间');
        return;
      }
      if (isPastDateTime(form.scheduleAt)) {
        message.warning('AI 执行时间不能早于当前时间');
        return;
      }
      if (!form.aiPrompt.trim()) {
        message.warning('请填写 AI 执行说明');
        return;
      }
    }

    setSaving(true);
    const payload = {
      title: form.title.trim(),
      description: form.description.trim() || null,
      status: form.status,
      completed: form.status === 'done',
      priority: form.priority,
      due_at: toPayloadDateTime(form.dueAt),
      execution_mode: form.executionMode,
      schedule_at: form.executionMode === 'ai_auto' ? toPayloadDateTime(form.scheduleAt) : null,
      recurrence_rule: form.executionMode === 'ai_auto' ? form.recurrenceRule : 'none',
      ai_prompt: form.executionMode === 'ai_auto' ? form.aiPrompt.trim() : null,
      notify_email: form.executionMode === 'ai_auto' ? form.notifyEmail.trim() || null : null,
    };

    try {
      if (editingTask) {
        await http.patch(`/tasks/${editingTask.id}`, payload);
        message.success('任务已更新');
      } else {
        await http.post('/tasks', payload);
        message.success('任务已创建');
      }
      setModalOpen(false);
      await fetchTasks();
    } catch {
      message.error('任务保存失败');
    } finally {
      setSaving(false);
    }
  };

  const updateStatus = async (task: TaskItem, status: TaskStatus) => {
    try {
      await http.patch(`/tasks/${task.id}`, {
        status,
        completed: status === 'done',
      });
      setTasks((current) =>
        current.map((item) =>
          item.id === task.id ? { ...item, status, completed: status === 'done' } : item,
        ),
      );
    } catch {
      message.error('状态更新失败');
    }
  };

  const deleteTask = async (task: TaskItem) => {
    try {
      await http.delete(`/tasks/${task.id}`);
      setTasks((current) => current.filter((item) => item.id !== task.id));
      message.success('任务已删除');
    } catch {
      message.error('任务删除失败');
    }
  };

  const openHistory = async (task: TaskItem) => {
    setHistoryTask(task);
    setRuns([]);
    setRunsLoading(true);
    try {
      const data = await http.get<TaskRunItem[], TaskRunItem[]>(
        `/tasks/${task.id}/runs?limit=20`,
      );
      setRuns(data);
    } catch {
      message.error('执行记录加载失败');
    } finally {
      setRunsLoading(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col bg-white">
      <PageHeader
        title="任务管理"
        description="管理手动任务与 AI 定时自动执行。"
        icon={<CircleDashedIcon size={16} />}
        meta={(
          <>
            <span>未完成 {openTasks}</span>
            <span className="text-gray-300">/</span>
            <span>已完成 {doneTasks}</span>
            <span className="text-gray-300">/</span>
            <span>当前列表 {tasks.length}</span>
          </>
        )}
        actions={(
          <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
            <Input
              allowClear
              size="small"
              prefix={<SearchIcon size={14} className="text-gray-400" />}
              placeholder="搜索标题或描述"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="sm:w-60"
            />
            <Select
              size="small"
              value={statusFilter}
              options={statusOptions}
              onChange={setStatusFilter}
              className="sm:w-32"
            />
            <Select
              size="small"
              value={priorityFilter}
              options={priorityOptions}
              onChange={setPriorityFilter}
              className="sm:w-32"
            />
            <Select<AutoRefreshIntervalMs>
              size="small"
              aria-label="选择自动刷新间隔"
              value={autoRefreshMs}
              options={autoRefreshSelectOptions}
              prefix={(
                <RefreshCwIcon
                  size={14}
                  className={loading ? 'animate-spin text-gray-400' : 'text-gray-400'}
                />
              )}
              onSelect={handleAutoRefreshSelect}
              className="sm:w-44"
            />
            <Button size="small" type="primary" icon={<PlusIcon size={14} />} onClick={openCreateModal}>
              新建任务
            </Button>
          </div>
        )}
      />

      <div className="min-h-0 flex-1 overflow-y-auto bg-gray-50/60 p-3 md:p-6">
        <div className="mx-auto flex max-w-6xl flex-col gap-3">
          {!loading && tasks.length === 0 && (
            <div className="rounded-lg border border-dashed border-gray-200 bg-white px-6 py-12 text-center">
              <p className="text-sm font-medium text-gray-700">暂无任务</p>
            </div>
          )}

          {tasks.map((task) => {
            const StatusIcon = statusMeta[task.status].Icon;
            return (
              <div
                key={task.id}
                className="group rounded-lg border border-gray-200 bg-white transition-colors hover:border-gray-300 hover:bg-gray-50/40"
              >
                <div className="flex flex-col gap-4 px-4 py-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="flex min-w-0 flex-1 gap-3">
                    <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-gray-200 bg-gray-50 text-gray-500 transition-colors group-hover:border-gray-300 group-hover:bg-white">
                      <StatusIcon size={17} />
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                        <div className="min-w-0">
                          <h2 className="break-words text-[15px] font-semibold leading-6 text-gray-950">
                            {task.title}
                          </h2>
                          {task.description && (
                            <p className="mt-1 max-w-3xl whitespace-pre-wrap break-words text-sm leading-6 text-gray-600">
                              {task.description}
                            </p>
                          )}
                        </div>
                      </div>

                      <div className="mt-3 flex flex-wrap items-center gap-1.5">
                        <span className={`${taskTagBaseClassName} ${statusTagClassName[task.status]}`}>
                          {statusMeta[task.status].label}
                        </span>
                        <span className={`${taskTagBaseClassName} ${priorityTagClassName[task.priority]}`}>
                          {priorityMeta[task.priority].label}
                        </span>
                        {task.source === 'ai' && (
                          <span className={`${taskTagBaseClassName} border-indigo-100 bg-indigo-50 text-indigo-700`}>
                            AI 创建
                          </span>
                        )}
                        {task.execution_mode === 'ai_auto' && (
                          <span className={`${taskTagBaseClassName} border-violet-100 bg-violet-50 text-violet-700`}>
                            <BotIcon size={12} className="shrink-0" />
                            自动执行
                          </span>
                        )}
                      </div>

                      <div className="mt-3 grid gap-2 text-xs text-gray-500 sm:grid-cols-2 xl:grid-cols-4">
                        <span className="inline-flex min-h-8 items-center gap-1.5 rounded-md border border-gray-100 bg-gray-50 px-2.5">
                          <ClockIcon size={14} className="text-gray-400" />
                          <span className="text-gray-400">截止</span>
                          <span className="font-medium text-gray-700">{formatDateTime(task.due_at)}</span>
                        </span>
                        <span className="inline-flex min-h-8 items-center gap-1.5 rounded-md border border-gray-100 bg-gray-50 px-2.5">
                          <span className="text-gray-400">更新</span>
                          <span className="font-medium text-gray-700">{formatDateTime(task.updated_at)}</span>
                        </span>
                        {task.execution_mode === 'ai_auto' && (
                          <span className="inline-flex min-h-8 items-center gap-1.5 rounded-md border border-violet-100 bg-violet-50 px-2.5">
                            <span className="text-violet-500">下次执行</span>
                            <span className="font-medium text-violet-800">
                              {formatDateTime(task.next_run_at || task.schedule_at)}
                            </span>
                          </span>
                        )}
                        {task.execution_mode === 'ai_auto' && task.run_status !== 'idle' && (
                          <span className="inline-flex min-h-8 items-center gap-1.5 rounded-md border border-blue-100 bg-blue-50 px-2.5">
                            <span className="text-blue-500">执行状态</span>
                            <span className="font-medium text-blue-800">
                              {runStatusMeta[task.run_status] || task.run_status}
                            </span>
                          </span>
                        )}
                      </div>

                      {task.execution_mode === 'ai_auto' && (
                        <div className="mt-3 flex items-start gap-2 rounded-md border border-violet-100 bg-violet-50/70 px-3 py-2 text-xs leading-5 text-violet-700">
                          <BotIcon size={14} className="mt-0.5 shrink-0" />
                          <span className="break-words">
                            {task.notify_email ? `结果将发送至 ${task.notify_email}` : '未填写结果收件邮箱，可在执行说明中写入邮箱地址'}
                          </span>
                        </div>
                      )}

                      {task.execution_mode === 'ai_auto' && task.run_status === 'failed' && task.run_error && (
                        <div className="mt-2 flex items-start gap-2 rounded-md border border-red-100 bg-red-50/70 px-3 py-2 text-xs leading-5 text-red-700">
                          <BadgeAlertIcon size={14} className="mt-0.5 shrink-0" />
                          <span className="break-words">{task.run_error}</span>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="flex shrink-0 flex-wrap items-center gap-2 border-t border-gray-100 pt-3 lg:border-t-0 lg:pt-0">
                    <Select<TaskStatus>
                      aria-label="更新任务状态"
                      value={task.status}
                      options={statusOptions.filter((item) => item.value !== 'all') as { label: string; value: TaskStatus }[]}
                      onChange={(value) => updateStatus(task, value)}
                      className="w-32"
                    />
                    {task.execution_mode === 'ai_auto' && (
                      <Button
                        icon={<HistoryIcon size={16} />}
                        onClick={() => openHistory(task)}
                        className="min-w-20"
                      >
                        历史
                      </Button>
                    )}
                    <Button
                      icon={<SquarePenIcon size={16} />}
                      onClick={() => openEditModal(task)}
                      className="min-w-20"
                    >
                      编辑
                    </Button>
                    <Popconfirm
                      title="确认删除该任务？"
                      okText="删除"
                      cancelText="取消"
                      onConfirm={() => deleteTask(task)}
                    >
                      <Button danger icon={<DeleteIcon size={16} />} className="min-w-20">
                        删除
                      </Button>
                    </Popconfirm>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <Modal
        title={
          <span className="text-base font-semibold text-gray-900">
            {editingTask ? '编辑任务' : '新建任务'}
          </span>
        }
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={saveTask}
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
        destroyOnHidden
      >
        <div className="space-y-3 pt-1">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-gray-600">标题</span>
            <Input
              value={form.title}
              maxLength={100}
              showCount
              onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-gray-600">描述</span>
            <Input.TextArea
              value={form.description}
              maxLength={500}
              showCount
              autoSize={{ minRows: 3, maxRows: 6 }}
              onChange={(event) =>
                setForm((current) => ({ ...current, description: event.target.value }))
              }
            />
          </label>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-gray-600">状态</span>
              <Select<TaskStatus>
                value={form.status}
                options={statusOptions.filter((item) => item.value !== 'all') as { label: string; value: TaskStatus }[]}
                onChange={(value) => setForm((current) => ({ ...current, status: value }))}
                className="w-full"
              />
            </label>

            <label className="block">
              <span className="mb-1 block text-xs font-medium text-gray-600">优先级</span>
              <Select<TaskPriority>
                value={form.priority}
                options={priorityOptions.filter((item) => item.value !== 'all') as { label: string; value: TaskPriority }[]}
                onChange={(value) => setForm((current) => ({ ...current, priority: value }))}
                className="w-full"
              />
            </label>

            <label className="block">
              <span className="mb-1 block text-xs font-medium text-gray-600">截止时间</span>
              <DatePicker
                allowClear
                showNow
                showTime={{ format: 'HH:mm', minuteStep: 5 }}
                format="YYYY-MM-DD HH:mm"
                locale={zhCN}
                presets={dueAtPresets}
                placeholder="选择日期和时间"
                suffixIcon={<ClockIcon size={16} />}
                value={toPickerValue(form.dueAt)}
                onChange={(value) =>
                  setForm((current) => ({
                    ...current,
                    dueAt: value ? value.toISOString() : '',
                  }))
                }
                className="w-full"
              />
            </label>
          </div>

          <div className="border-t border-gray-100 pt-3">
            <div className="mb-3 flex items-center gap-2 text-xs font-medium text-gray-600">
              <BotIcon size={14} />
              AI 执行
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <label className="block">
                <span className="mb-1 block text-xs font-medium text-gray-600">执行方式</span>
                <Select<TaskExecutionMode>
                  value={form.executionMode}
                  options={executionModeOptions}
                  onChange={(value) =>
                    setForm((current) => ({ ...current, executionMode: value }))
                  }
                  className="w-full"
                />
              </label>

              <label className="block">
                <span className="mb-1 block text-xs font-medium text-gray-600">执行时间</span>
                <DatePicker
                  allowClear
                  disabled={form.executionMode !== 'ai_auto'}
                  showNow
                  showTime={{ format: 'HH:mm', minuteStep: 5 }}
                  format="YYYY-MM-DD HH:mm"
                  locale={zhCN}
                  disabledDate={disabledPastDate}
                  disabledTime={disabledPastTime}
                  presets={dueAtPresets}
                  placeholder="选择执行时间"
                  suffixIcon={<ClockIcon size={16} />}
                  value={toPickerValue(form.scheduleAt)}
                  onChange={(value) =>
                    setForm((current) => ({
                      ...current,
                      scheduleAt: value ? value.toISOString() : '',
                    }))
                  }
                  className="w-full"
                />
              </label>

              <label className="block">
                <span className="mb-1 block text-xs font-medium text-gray-600">重复规则</span>
                <Select<TaskRecurrenceRule>
                  disabled={form.executionMode !== 'ai_auto'}
                  value={form.recurrenceRule}
                  options={recurrenceOptions}
                  onChange={(value) =>
                    setForm((current) => ({ ...current, recurrenceRule: value }))
                  }
                  className="w-full"
                />
              </label>
            </div>

            {form.executionMode === 'ai_auto' && (
              <div className="mt-3 grid grid-cols-1 gap-3">
                <label className="block">
                  <span className="mb-1 block text-xs font-medium text-gray-600">
                    AI 执行说明
                  </span>
                  <Input.TextArea
                    value={form.aiPrompt}
                    maxLength={4000}
                    showCount
                    autoSize={{ minRows: 3, maxRows: 6 }}
                    placeholder="例如：总结今天未完成的任务，按优先级给出明天建议。"
                    onChange={(event) =>
                      setForm((current) => ({ ...current, aiPrompt: event.target.value }))
                    }
                  />
                </label>

                <label className="block">
                  <span className="mb-1 block text-xs font-medium text-gray-600">
                    结果收件邮箱
                  </span>
                  <Input
                    value={form.notifyEmail}
                    type="email"
                    placeholder="可选；也可以直接写在 AI 执行说明里"
                    onChange={(event) =>
                      setForm((current) => ({ ...current, notifyEmail: event.target.value }))
                    }
                  />
                </label>
              </div>
            )}
          </div>
        </div>
      </Modal>

      <Drawer
        title={(
          <span className="text-base font-semibold text-gray-900">
            执行历史{historyTask ? ` · ${historyTask.title}` : ''}
          </span>
        )}
        placement="right"
        size={520}
        onClose={() => setHistoryTask(null)}
        open={historyTask !== null}
        destroyOnHidden
      >
        {runsLoading && <p className="text-sm text-gray-500">加载中…</p>}

        {!runsLoading && runs.length === 0 && (
          <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50 px-6 py-12 text-center text-sm text-gray-500">
            暂无执行记录
          </div>
        )}

        <div className="flex flex-col gap-3">
          {runs.map((run) => {
            const meta = runRecordMeta[run.status] || {
              label: run.status,
              className: 'border-gray-200 bg-gray-50 text-gray-700',
            };
            return (
              <div key={run.id} className="rounded-lg border border-gray-200 bg-white p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`${taskTagBaseClassName} ${meta.className}`}>{meta.label}</span>
                  <span className="text-xs text-gray-500">{formatDateTime(run.started_at)}</span>
                  {run.email_sent && (
                    <span className={`${taskTagBaseClassName} border-emerald-100 bg-emerald-50 text-emerald-700`}>
                      已发邮件
                    </span>
                  )}
                </div>

                {run.error_message && (
                  <p className="mt-2 whitespace-pre-wrap break-words rounded-md border border-red-100 bg-red-50/70 px-3 py-2 text-xs leading-5 text-red-700">
                    {run.error_message}
                  </p>
                )}

                {run.output && (
                  <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md border border-gray-100 bg-gray-50 px-3 py-2 text-xs leading-5 text-gray-700">
                    {run.output}
                  </pre>
                )}
              </div>
            );
          })}
        </div>
      </Drawer>
    </div>
  );
}
