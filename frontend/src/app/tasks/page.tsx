'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Button,
  Input,
  Popconfirm,
  Select,
  message,
} from 'antd';
import {
  BadgeAlertIcon,
  BotIcon,
  CircleDashedIcon,
  ClockIcon,
  DeleteIcon,
  HistoryIcon,
  PlusIcon,
  RefreshCwIcon,
  SearchIcon,
  SquarePenIcon,
} from 'lucide-animated';
import http from '@/lib/http/axios';
import PageHeader from '@/components/PageHeader';

import {
  TaskStatus,
  TaskPriority,
  AutoRefreshIntervalMs,
  TaskItem,
  TaskRunItem,
  TaskFormState,
} from './types';
import {
  statusOptions,
  priorityOptions,
  autoRefreshOptions,
  statusMeta,
  priorityMeta,
  runStatusMeta,
  taskTagBaseClassName,
  statusTagClassName,
  priorityTagClassName,
  emptyForm,
} from './constants';
import {
  toPayloadDateTime,
  formatDateTime,
  formatCountdownSeconds,
} from './utils';
import TaskFormModal from './components/TaskFormModal';
import TaskHistoryDrawer from './components/TaskHistoryDrawer';

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

      <TaskFormModal
        open={modalOpen}
        editingTask={editingTask}
        form={form}
        setForm={setForm}
        onSave={saveTask}
        onCancel={() => setModalOpen(false)}
        saving={saving}
      />

      <TaskHistoryDrawer
        historyTask={historyTask}
        onClose={() => setHistoryTask(null)}
        runs={runs}
        runsLoading={runsLoading}
      />
    </div>
  );
}
