import React, { useMemo } from 'react';
import { Modal, Input, Select, DatePicker } from 'antd';
import { BotIcon, ClockIcon } from 'lucide-animated';
import zhCN from 'antd/es/date-picker/locale/zh_CN';
import dayjs from 'dayjs';
import {
  TaskFormState,
  TaskStatus,
  TaskPriority,
  TaskExecutionMode,
  TaskRecurrenceRule,
  TaskItem,
} from '../types';
import {
  statusOptions,
  priorityOptions,
  executionModeOptions,
  recurrenceOptions,
} from '../constants';
import {
  toPickerValue,
  disabledPastDate,
  disabledPastTime,
  roundToNextFiveMinutes,
} from '../utils';

interface TaskFormModalProps {
  open: boolean;
  editingTask: TaskItem | null;
  form: TaskFormState;
  setForm: React.Dispatch<React.SetStateAction<TaskFormState>>;
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
}

export default function TaskFormModal({
  open,
  editingTask,
  form,
  setForm,
  onSave,
  onCancel,
  saving,
}: TaskFormModalProps) {
  const dueAtPresets = useMemo(
    () => [
      { label: '1 小时后', value: roundToNextFiveMinutes() },
      { label: '明天 09:00', value: dayjs().add(1, 'day').hour(9).minute(0).second(0) },
      { label: '三天后 18:00', value: dayjs().add(3, 'day').hour(18).minute(0).second(0) },
      { label: '一周后 09:00', value: dayjs().add(1, 'week').hour(9).minute(0).second(0) },
    ],
    []
  );

  return (
    <Modal
      title={
        <span className="text-base font-semibold text-gray-900">
          {editingTask ? '编辑任务' : '新建任务'}
        </span>
      }
      open={open}
      onCancel={onCancel}
      onOk={onSave}
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
  );
}
