'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Bubble, Sender, Conversations } from '@ant-design/x';
import { message, Collapse, Tooltip, Popconfirm, Drawer, Select, Tag } from 'antd';
import { PlusIcon, PanelLeftOpenIcon, PanelLeftCloseIcon } from 'lucide-animated';
import http from '@/lib/http/axios';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { ChatMode, ToolCallState, ChatMessageItem, ChatSessionItem, ApiChatMessage, MCPAssistantResponse } from './types';
import { CHAT_MODE_OPTIONS, MODE_PLACEHOLDER } from './constants';
import { getErrorDetail, getStreamHeaders, mergeToolCalls, getGroupName } from './utils';
import ChatSidebar from './components/ChatSidebar';

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessageItem[]>([{ id: 'welcome', role: 'assistant', content: '你好，我是 AgentChat，请问有什么可以帮你？' }]);
  const [inputValue, setInputValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessions, setSessions] = useState<ChatSessionItem[]>([]);
  const [sessionId, setSessionId] = useState<number | null>(null);
  
  const sessionIdRef = useRef<number | null>(null);

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [chatMode, setChatMode] = useState<ChatMode>('auto');
  const [isMobile, setIsMobile] = useState(false);

  const chatModeSelect = (width = 144) => (
    <Select<ChatMode>
      aria-label="选择聊天模式"
      size="middle"
      value={chatMode}
      options={CHAT_MODE_OPTIONS}
      popupMatchSelectWidth={false}
      style={{ width }}
      onChange={setChatMode}
    />
  );

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
        mode: m.message_metadata?.model === 'assistant' ? 'auto' : m.message_metadata?.model === 'mcp-assistant' ? 'mcp' : m.message_metadata?.model === 'rag' ? 'rag' : 'chat',
        route: m.message_metadata?.route,
        sources: m.message_metadata?.sources || [],
        toolsUsed: m.message_metadata?.tools_used || [],
        toolCalls: (m.message_metadata?.tools_used || []).map((name) => ({
          name,
          status: 'completed' as const,
        })),
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
        toolCalls: chatMode === 'mcp'
          ? [{ name: 'MCP 工具', status: 'running' }]
          : [],
        mode: chatMode,
        loading: true,
      }
    ]);
    setInputValue('');
    setLoading(true);

    if (chatMode === 'auto') {
      let createdNewSession = false;
      try {
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'}/ai/assistant/stream`, {
          method: 'POST',
          headers: getStreamHeaders(),
          body: JSON.stringify({ message: text, session_id: sessionIdRef.current }),
        });

        if (!res.ok) {
          throw new Error('智能助手请求失败');
        }
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
              if (!dataStr) continue;

              try {
                const data = JSON.parse(dataStr);
                if (currentEvent === 'token' && data.delta) {
                  setMessages((prev) => prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? {
                          ...msg,
                          content: msg.content + data.delta,
                          loading: false,
                          streamStatus: undefined,
                        }
                      : msg
                  ));
                } else if (currentEvent === 'metadata' || currentEvent === 'done') {
                  setMessages((prev) => prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? {
                          ...msg,
                          route: data.route ?? msg.route,
                          sources: data.sources || msg.sources || [],
                          toolsUsed: data.tools_used || msg.toolsUsed || [],
                          toolCalls: data.tools_used
                            ? mergeToolCalls(msg.toolCalls, data.tools_used, 'completed')
                            : msg.toolCalls,
                        }
                      : msg
                  ));
                } else if (currentEvent === 'progress' && data.message) {
                  setMessages((prev) => prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? {
                          ...msg,
                          streamStatus: data.message,
                          toolCalls: Array.isArray(data.tools)
                            ? mergeToolCalls(
                                msg.toolCalls,
                                data.tools,
                                data.status === 'completed' ? 'completed' : 'running',
                              )
                            : msg.toolCalls,
                        }
                      : msg
                  ));
                } else if (currentEvent === 'start' && data.session_id) {
                  if (sessionIdRef.current !== data.session_id) {
                    setSessionId(data.session_id);
                    sessionIdRef.current = data.session_id;
                    createdNewSession = true;
                  }
                } else if (currentEvent === 'error') {
                  message.error(data.message || '智能助手请求失败');
                  setMessages((prev) => prev.map((msg) =>
                    msg.id === assistantMsgId
                      ? {
                          ...msg,
                          content: data.message || '智能助手暂时不可用，请稍后重试。',
                          loading: false,
                        }
                      : msg
                  ));
                }
              } catch (e) {
                console.error('Failed to parse SSE data', e);
              }
            }
          }
        }
      } catch (e) {
        console.error(e);
        message.error(getErrorDetail(e, '智能助手请求失败'));
        setMessages((prev) => prev.map((msg) =>
          msg.id === assistantMsgId
            ? {
                ...msg,
                content: '智能助手暂时不可用，请稍后重试。',
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

    if (chatMode === 'rag') {
      let createdNewSession = false;
      try {
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'}/ai/rag/stream`, {
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
                  } else if (currentEvent === 'sources' && Array.isArray(data.sources)) {
                    setMessages((prev) => prev.map((msg) =>
                      msg.id === assistantMsgId
                        ? { ...msg, sources: data.sources }
                        : msg
                    ));
                  } else if (currentEvent === 'start' && data.session_id) {
                    if (sessionIdRef.current !== data.session_id) {
                      setSessionId(data.session_id);
                      sessionIdRef.current = data.session_id;
                      createdNewSession = true;
                    }
                  } else if (currentEvent === 'error') {
                    message.error(data.message || '知识库请求出错');
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
        message.error('请求知识库失败');
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
                toolCalls: (res.tools_used && res.tools_used.length > 0)
                  ? res.tools_used.map((name) => ({ name, status: 'completed' as const }))
                  : mergeToolCalls(msg.toolCalls, ['MCP 工具'], 'completed'),
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
                toolCalls: mergeToolCalls(msg.toolCalls, ['MCP 工具'], 'failed'),
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

  const renderToolCards = (toolCalls?: ToolCallState[]) => {
    if (!toolCalls || toolCalls.length === 0) return null;

    return (
      <div className="mb-3 flex flex-col gap-1.5">
        {toolCalls.map((tool) => {
          const completed = tool.status === 'completed';
          const failed = tool.status === 'failed';
          return (
            <div
              key={tool.name}
              className={`flex max-w-full items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs ${
                failed
                  ? 'border-red-100 bg-red-50/70 text-red-800'
                  : completed
                    ? 'border-emerald-100 bg-emerald-50/70 text-emerald-800'
                    : 'border-blue-100 bg-blue-50/70 text-blue-800'
              }`}
            >
              <span
                className={`h-2 w-2 shrink-0 rounded-full ${
                  failed ? 'bg-red-500' : completed ? 'bg-emerald-500' : 'animate-pulse bg-blue-500'
                }`}
              />
              <span className="shrink-0 font-medium">
                {failed ? '调用失败' : completed ? '调用完成' : '调用中'}
              </span>
              <span className="min-w-0 truncate font-mono text-[11px]">
                {tool.name}
              </span>
            </div>
          );
        })}
      </div>
    );
  };



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
          <ChatSidebar
            sessions={sessions}
            sessionId={sessionId}
            loadingMore={loadingMore}
            hasMore={hasMore}
            onScroll={handleScroll}
            onLoadSession={loadSession}
            onDeleteSession={deleteSession}
            onStartNewSession={startNewSession}
            onCollapse={() => setSidebarCollapsed(true)}
          />
        </Drawer>
      )}

      {/* Desktop Sidebar */}
      {!isMobile && !sidebarCollapsed && (
        <div className="hidden md:flex w-64 border-r border-gray-100 flex-col bg-gray-50/50">
          <ChatSidebar
            sessions={sessions}
            sessionId={sessionId}
            loadingMore={loadingMore}
            hasMore={hasMore}
            onScroll={handleScroll}
            onLoadSession={loadSession}
            onDeleteSession={deleteSession}
            onStartNewSession={startNewSession}
            onCollapse={() => setSidebarCollapsed(true)}
          />
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
              chatModeSelect(144)
            )}
          </div>
        </div>
        <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6 bg-gray-50/30">
          {messages.map((msg) => (
            <Bubble
              key={msg.id}
              loading={msg.loading}
              loadingRender={() => (
                <div>
                  {renderToolCards(msg.toolCalls)}
                  <div className="text-gray-400 text-sm animate-pulse flex items-center gap-2">
                    {msg.streamStatus || (msg.mode === 'auto' ? '智能助手处理中...' : msg.mode === 'mcp' ? 'MCP 工具助手处理中...' : 'AI 思考中...')}
                  </div>
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
                    {renderToolCards(msg.toolCalls)}
                    <div className="prose prose-sm max-w-none text-gray-800 break-words [&>p]:mb-0 [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
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
                    {msg.route && (
                      <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-gray-100 pt-2">
                        <Tag color="geekblue" className="m-0 max-w-full truncate font-mono text-xs">
                          {msg.route}
                        </Tag>
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
                <div className="flex items-center mr-3 border-r border-gray-100 pr-3">
                  {chatModeSelect()}
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
