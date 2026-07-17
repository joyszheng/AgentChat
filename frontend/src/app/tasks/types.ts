import React from 'react';

export type TaskStatus = 'todo' | 'in_progress' | 'blocked' | 'done' | 'canceled';
export type TaskPriority = 'low' | 'normal' | 'high' | 'urgent';
export type TaskExecutionMode = 'manual' | 'ai_auto';
export type TaskRecurrenceRule = 'none' | 'daily';
export type AutoRefreshIntervalMs = 0 | 10000 | 30000 | 60000 | 300000 | 600000;

export interface TaskItem {
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

export interface TaskRunItem {
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

export interface TaskFormState {
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

export type AnimatedIconComponent = React.ComponentType<{
  size?: number;
  className?: string;
  animateOnHover?: boolean;
}>;
