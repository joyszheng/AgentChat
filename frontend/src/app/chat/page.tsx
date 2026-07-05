'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Bubble, Sender, Conversations } from '@ant-design/x';
import { message, Collapse, Tooltip, Popconfirm, Drawer, Segmented, Tag } from 'antd';
import { PlusIcon, PanelLeftOpenIcon, PanelLeftCloseIcon, DeleteIcon } from 'lucide-animated';
import http from '@/lib/http/axios';
import ReactMarkdown from 'react-markdown';

type ChatMode = 'chat' | 'rag' | 'mcp';

interface ChatMessageItem {
  id: string;
  role: string;
  content: string;
  sources?: string[];
  toolsUsed?: string[];
  mode?: ChatMode;
  loading?: boolean;
}

interface ChatSessionItem {
  id: number;
  title?: string | null;
  updated_at?: string | null;
}

interface ApiChatMessage {
  id: number;
  role: string;
  content: string;
  message_metadata?: {
    model?: string;
    tools_used?: string[];
  };
}

interface RagResponse {
  answer: string;
  sources: string[];
}

interface MCPAssistantResponse {
  answer: string;
  session_id: number;
  tools_used?: string[];
}

const CHAT_MODE_OPTIONS: { label: string; value: ChatMode }[] = [
  { label: '大模型', value: 'chat' },
  { label: '知识库', value: 'rag' },
  { label: 'MCP 工具', value: 'mcp' },
];

const MODE_PLACEHOLDER: Record<ChatMode, string> = {
  chat: '请输入问题...',
  rag: '向知识库提问...',
  mcp: '问我需要调用 MCP 工具的问题...',
};

const getErrorDetail = (error: unknown, fallback: string) => {
  if (typeof error === 'object' && error !== null && 'response' in error) {
    const response = (error as { response?: { data?: { detail?: string } } }).response;
    return response?.data?.detail || fallback;
  }
  return error instanceof Error ? error.message : fallback;
};

const getGroupName = (timeStr: string | null | undefined) => {
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

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessageItem[]>([{ id: 'welcome', role: 'assistant', content: '你好，我是 AgentChat，请问有什么可以帮你？' }]);
  const [inputValue, setInputValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessions, setSessions] = useState<ChatSessionItem[]>([]);
  const [sessionId, setSessionId] = useState<number | null>(null);
  
  const sessionIdRef = useRef<number | null>(null);

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [chatMode, setChatMode] = useState<ChatMode>('chat');
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const handleResize = () => {
      const mobile = window.innerWidth < 768;
      setIsMobile(mobile);
      if (mobile) setSidebarCollapsed(true);
    };
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const [skip, setSkip] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

  const fetchSessions = async (reset = false) => {
    try {
      const currentSkip = reset ? 0 : skip;
      const res = await http.get<ChatSessionItem[], ChatSessionItem[]>(`/ai/sessions?skip=${currentSkip}&limit=20`);
      if (reset) {
        setSessions(res);
      } else {
        setSessions(prev => {
          const newItems = res.filter((r) => !prev.find((p) => p.id === r.id));
          return [...prev, ...newItems];
        });
      }
      setSkip(currentSkip + res.length);
      setHasMore(res.length === 20);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    const timer = window.setTimeout(() => void fetchSessions(true), 0);
    return () => window.clearTimeout(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop, scrollHeight, clientHeight } = e.currentTarget;
    if (scrollHeight - scrollTop - clientHeight < 50 && hasMore && !loadingMore) {
      setLoadingMore(true);
      fetchSessions().finally(() => setLoadingMore(false));
    }
  };

  const loadSession = async (id: number) => {
    setSessionId(id);
    sessionIdRef.current = id;
    if (isMobile) {
      setSidebarCollapsed(true);
    }
    try {
      const msgs = await http.get<ApiChatMessage[], ApiChatMessage[]>(`/ai/sessions/${id}/messages`);
      const formatted: ChatMessageItem[] = msgs.map((m) => ({
        id: m.id.toString(),
        role: m.role,
        content: m.content,
        mode: m.message_metadata?.model === 'mcp-assistant' ? 'mcp' : 'chat',
        toolsUsed: m.message_metadata?.tools_used || [],
      }));
      setMessages(formatted.length ? formatted : [{ id: 'welcome', role: 'assistant', content: '你好，我是 AgentChat，请问有什么可以帮你？' }]);
    } catch {
      message.error('加载历史记录失败');
    }
  };

  const deleteSession = async (id: number) => {
    try {
      await http.delete(`/ai/sessions/${id}`);
      message.success('删除成功');
      if (sessionIdRef.current === id) {
        startNewSession();
      }
      fetchSessions(true);
    } catch {
      message.error('删除失败');
    }
  };

  const startNewSession = () => {
    setSessionId(null);
    sessionIdRef.current = null;
    setMessages([{ id: 'welcome', role: 'assistant', content: '你好，我是 AgentChat，请问有什么可以帮你？' }]);
    if (isMobile) {
      setSidebarCollapsed(true);
    }
  };

  const sendRequest = async (text: string) => {
    const userMsgId = Date.now().toString();
    const assistantMsgId = (Date.now() + 1).toString();
    
    setMessages((prev) => [
      ...prev,
      { id: userMsgId, role: 'user', content: text },
      {
        id: assistantMsgId,
        role: 'assistant',
        content: '',
        sources: [],
        toolsUsed: [],
        mode: chatMode,
        loading: true,
      }
    ]);
    setInputValue('');
    setLoading(true);

    if (chatMode === 'rag') {
      try {
        const res = await http.post<RagResponse, RagResponse>('/ai/rag', { question: text });
        setMessages((prev) => prev.map((msg) => 
          msg.id === assistantMsgId 
            ? { ...msg, content: res.answer, sources: res.sources, loading: false }
            : msg
        ));
      } catch {
        message.error('请求知识库失败');
        setMessages((prev) => prev.map((msg) => 
          msg.id === assistantMsgId 
            ? { ...msg, loading: false }
            : msg
        ));
      } finally {
        setLoading(false);
      }
      return;
    }

    if (chatMode === 'mcp') {
      let createdNewSession = false;
      try {
        const res = await http.post<MCPAssistantResponse, MCPAssistantResponse>('/ai/mcp-assistant', {
          message: text,
          session_id: sessionIdRef.current,
        });

        if (sessionIdRef.current !== res.session_id) {
          setSessionId(res.session_id);
          sessionIdRef.current = res.session_id;
          createdNewSession = true;
        }

        setMessages((prev) => prev.map((msg) =>
          msg.id === assistantMsgId
            ? {
                ...msg,
                content: res.answer,
                toolsUsed: res.tools_used || [],
                loading: false,
              }
            : msg
        ));
      } catch (e) {
        message.error(getErrorDetail(e, 'MCP 工具助手请求失败'));
        setMessages((prev) => prev.map((msg) =>
          msg.id === assistantMsgId
            ? {
                ...msg,
                content: 'MCP 工具助手暂时不可用，请确认已启用可用工具并稍后重试。',
                loading: false,
              }
            : msg
        ));
      } finally {
        setLoading(false);
        if (createdNewSession) {
          fetchSessions(true);
        }
      }
      return;
    }

    let createdNewSession = false;

    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'}/ai/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, session_id: sessionIdRef.current })
      });

      if (!res.body) throw new Error('No stream body');

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let currentEvent = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; 

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            const dataStr = line.slice(6).trim();
            if (dataStr) {
              try {
                const data = JSON.parse(dataStr);
                if (currentEvent === 'token' && data.delta) {
                  setMessages((prev) => prev.map((msg) => 
                    msg.id === assistantMsgId 
                      ? { ...msg, content: msg.content + data.delta, loading: false }
                      : msg
                  ));
                } else if (currentEvent === 'start' && data.session_id) {
                  if (sessionIdRef.current !== data.session_id) {
                    setSessionId(data.session_id);
                    sessionIdRef.current = data.session_id;
                    createdNewSession = true;
                  }
                } else if (currentEvent === 'error') {
                  message.error(data.message || 'AI 请求出错');
                }
              } catch (e) {
                console.error('Failed to parse SSE data', e);
              }
            }
          }
        }
      }
    } catch (e) {
      console.error(e);
      message.error('请求失败，请稍后重试');
    } finally {
      setLoading(false);
      setMessages((prev) => prev.map((msg) => 
        msg.id === assistantMsgId 
          ? { ...msg, loading: false }
          : msg
      ));
      if (createdNewSession) {
        fetchSessions(true);
      }
    }
  };

  const renderSidebar = () => (
    <>
      <div className="px-4 border-b border-gray-100 flex items-center justify-between bg-white hidden md:flex shrink-0 h-[56px]">
        <span className="font-medium text-gray-700">历史会话</span>
        <div className="flex items-center gap-1 -mr-2">
          <Tooltip title="新会话">
            <div className="flex items-center justify-center w-8 h-8 rounded-md hover:bg-black/5 cursor-pointer text-gray-600 transition-colors" onClick={startNewSession}>
              <PlusIcon size={16} />
            </div>
          </Tooltip>
          <Tooltip title="收起">
            <div className="flex items-center justify-center w-8 h-8 rounded-md hover:bg-black/5 cursor-pointer text-gray-600 transition-colors" onClick={() => setSidebarCollapsed(true)}>
              <PanelLeftCloseIcon size={16} />
            </div>
          </Tooltip>
        </div>
      </div>
      <div className="flex-1 overflow-y-auto overflow-x-hidden bg-white md:bg-gray-50/30" onScroll={handleScroll}>
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
                  onConfirm={(e) => { e?.stopPropagation(); deleteSession(s.id); }}
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
          onActiveChange={(key) => loadSession(Number(key))}
        />
        {loadingMore && <div className="text-center py-3 text-xs text-gray-400">加载中...</div>}
        {!hasMore && sessions.length > 0 && <div className="text-center py-3 text-xs text-gray-300">没有更多会话了</div>}
      </div>
    </>
  );

  return (
    <div className="flex h-full bg-white overflow-hidden relative">
      {/* Mobile Drawer */}
      {isMobile && (
        <Drawer
          title={<div className="flex justify-between items-center w-full"><span>历史会话</span><div className="flex items-center gap-1 bg-[#1677ff] hover:bg-[#4096ff] text-white px-2 py-1 rounded text-sm cursor-pointer transition-colors" onClick={startNewSession}><PlusIcon size={14} />新会话</div></div>}
          placement="left"
          onClose={() => setSidebarCollapsed(true)}
          open={!sidebarCollapsed}
          styles={{ body: { padding: 0, display: 'flex', flexDirection: 'column' } }}
          size="default"
        >
          {renderSidebar()}
        </Drawer>
      )}

      {/* Desktop Sidebar */}
      {!isMobile && !sidebarCollapsed && (
        <div className="hidden md:flex w-64 border-r border-gray-100 flex-col bg-gray-50/50">
          {renderSidebar()}
        </div>
      )}

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-w-0 bg-white">
        <div className="px-4 border-b border-gray-100 bg-white flex items-center justify-between shadow-sm z-10 shrink-0 h-[56px]">
          <div className="flex items-center gap-3">
            {(sidebarCollapsed || isMobile) && (
              <div 
                className="flex items-center justify-center w-8 h-8 rounded-md hover:bg-black/5 cursor-pointer text-gray-500 transition-colors -ml-2"
                onClick={() => setSidebarCollapsed(false)} 
              >
                <PanelLeftOpenIcon size={16} />
              </div>
            )}
            <span className="font-medium text-gray-700">
              当前会话
            </span>
          </div>
          <div>
            {isMobile && (
              <Segmented
                size="small"
                options={CHAT_MODE_OPTIONS}
                value={chatMode}
                onChange={(value) => setChatMode(value as ChatMode)}
              />
            )}
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6 bg-gray-50/30">
          {messages.map((msg) => (
            <Bubble
              key={msg.id}
              loading={msg.loading}
              loadingRender={() => (
                <div className="text-gray-400 text-sm animate-pulse flex items-center gap-2">
                  {msg.mode === 'mcp' ? 'MCP 工具助手处理中...' : 'AI 思考中...'}
                </div>
              )}
              placement={msg.role === 'user' ? 'end' : 'start'}
              styles={{
                content: msg.role === 'user'
                  ? { 
                      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)', 
                      color: '#ffffff', 
                      border: 'none', 
                      boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)'
                    }
                  : { 
                      background: 'linear-gradient(135deg, #ffffff 0%, #f9fafb 100%)', 
                      color: '#1f2937', 
                      border: '1px solid #e5e7eb', 
                      boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.05)'
                    }
              }}
              content={
                msg.role === 'user' ? (
                  msg.content
                ) : (
                  <>
                    <div className="prose prose-sm max-w-none text-gray-800 break-words [&>p]:mb-0 [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                    </div>
                    {msg.sources && msg.sources.length > 0 && (
                      <Collapse
                        size="small"
                        ghost
                        items={[
                          {
                            key: '1',
                            label: <span className="text-xs text-gray-500">查看引用来源 ({msg.sources.length})</span>,
                            children: (
                              <ul className="list-disc pl-4 text-xs text-gray-600 break-words">
                                {msg.sources.map((s: string, idx: number) => (
                                  <li key={idx}>{s}</li>
                                ))}
                              </ul>
                            ),
                          },
                        ]}
                      />
                    )}
                    {msg.toolsUsed && msg.toolsUsed.length > 0 && (
                      <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-gray-100 pt-2">
                        <span className="text-xs font-medium text-gray-500">调用工具</span>
                        {msg.toolsUsed.map((toolName: string) => (
                          <Tag key={toolName} color="blue" className="m-0 max-w-full truncate font-mono text-xs">
                            {toolName}
                          </Tag>
                        ))}
                      </div>
                    )}
                  </>
                )
              }
            />
          ))}
        </div>
        <div className="p-3 md:p-4 border-t border-gray-100 bg-white">
          <Sender
            prefix={
              !isMobile ? (
                <div className="flex items-center mr-2 mb-1 border-r border-gray-100 pr-3 relative -top-[1px]">
                  <Segmented
                    size="small"
                    options={CHAT_MODE_OPTIONS}
                    value={chatMode}
                    onChange={(value) => setChatMode(value as ChatMode)}
                  />
                </div>
              ) : null
            }
            value={inputValue}
            onChange={setInputValue}
            onSubmit={() => {
              if (inputValue.trim() && !loading) {
                sendRequest(inputValue.trim());
              }
            }}
            loading={loading}
            placeholder={MODE_PLACEHOLDER[chatMode]}
            className="shadow-sm border-gray-200"
          />
        </div>
      </div>
    </div>
  );
}
