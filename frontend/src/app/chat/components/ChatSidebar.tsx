import React from 'react';
import { Conversations } from '@ant-design/x';
import { Tooltip, Popconfirm } from 'antd';
import { PlusIcon, PanelLeftCloseIcon, DeleteIcon } from 'lucide-animated';
import { ChatSessionItem } from '../types';
import { getGroupName } from '../utils';

interface ChatSidebarProps {
  sessions: ChatSessionItem[];
  sessionId: number | null;
  loadingMore: boolean;
  hasMore: boolean;
  onScroll: (e: React.UIEvent<HTMLDivElement>) => void;
  onLoadSession: (id: number) => void;
  onDeleteSession: (id: number) => void;
  onStartNewSession: () => void;
  onCollapse: () => void;
}

export default function ChatSidebar({
  sessions,
  sessionId,
  loadingMore,
  hasMore,
  onScroll,
  onLoadSession,
  onDeleteSession,
  onStartNewSession,
  onCollapse,
}: ChatSidebarProps) {
  return (
    <>
      <div className="px-4 border-b border-gray-100 flex items-center justify-between bg-white hidden md:flex shrink-0 h-[56px]">
        <span className="font-medium text-gray-700">历史会话</span>
        <div className="flex items-center gap-1 -mr-2">
          <Tooltip title="新会话">
            <div className="flex items-center justify-center w-8 h-8 rounded-md hover:bg-black/5 cursor-pointer text-gray-600 transition-colors" onClick={onStartNewSession}>
              <PlusIcon size={16} />
            </div>
          </Tooltip>
          <Tooltip title="收起">
            <div className="flex items-center justify-center w-8 h-8 rounded-md hover:bg-black/5 cursor-pointer text-gray-600 transition-colors" onClick={onCollapse}>
              <PanelLeftCloseIcon size={16} />
            </div>
          </Tooltip>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto overflow-x-hidden bg-white md:bg-gray-50/30" onScroll={onScroll}>
        <Conversations
          groupable={{
            label: (group) => <span className="text-[11px] text-gray-400/90 font-medium tracking-wide">{group}</span>
          }}
          items={sessions.map(s => ({
            key: s.id.toString(),
            group: getGroupName(s.updated_at),
            label: (
              <div className="flex justify-between items-center w-full group overflow-hidden">
                <span className="truncate flex-1">{s.title || '新会话'}</span>
                <Popconfirm 
                  title="确认删除该会话？"
                  onConfirm={(e) => { e?.stopPropagation(); onDeleteSession(s.id); }}
                  onCancel={(e) => e?.stopPropagation()}
                  okText="确认"
                  cancelText="取消"
                >
                  <div 
                    className="flex items-center justify-center w-6 h-6 rounded-md hover:bg-red-50 cursor-pointer opacity-100 md:opacity-0 group-hover:opacity-100 transition-all text-gray-400 hover:text-red-500 ml-2"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <DeleteIcon size={14} />
                  </div>
                </Popconfirm>
              </div>
            ),
          }))}
          activeKey={sessionId ? sessionId.toString() : undefined}
          onActiveChange={(key) => onLoadSession(Number(key))}
        />
        {loadingMore && <div className="text-center py-3 text-xs text-gray-400">加载中...</div>}
        {!hasMore && sessions.length > 0 && <div className="text-center py-3 text-xs text-gray-300">没有更多会话了</div>}
      </div>
    </>
  );
}
