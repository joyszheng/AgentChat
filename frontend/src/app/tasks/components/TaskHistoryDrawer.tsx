import React from 'react';
import { Drawer } from 'antd';
import { TaskItem, TaskRunItem } from '../types';
import { runRecordMeta, taskTagBaseClassName } from '../constants';
import { formatDateTime } from '../utils';

interface TaskHistoryDrawerProps {
  historyTask: TaskItem | null;
  onClose: () => void;
  runs: TaskRunItem[];
  runsLoading: boolean;
}

export default function TaskHistoryDrawer({
  historyTask,
  onClose,
  runs,
  runsLoading
}: TaskHistoryDrawerProps) {
  return (
    <Drawer
      title={(
        <span className="text-base font-semibold text-gray-900">
          执行历史{historyTask ? ` · ${historyTask.title}` : ''}
        </span>
      )}
      placement="right"
      size={520}
      onClose={onClose}
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
  );
}
