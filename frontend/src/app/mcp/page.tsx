'use client';

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Empty,
  Modal,
  Popconfirm,
  Skeleton,
  Switch,
  Tag,
  Tooltip,
  message,
} from 'antd';
import {
  CircleCheckIcon,
  DeleteIcon,
  KeyIcon,
  PlusIcon,
  RefreshCwIcon,
  RouterIcon,
  SearchIcon,
  SettingsIcon,
  ShieldCheckIcon,
  WorkflowIcon,
  XIcon,
} from 'lucide-animated';
import { useRouter } from 'next/navigation';
import { isAxiosError } from 'axios';

import http from '@/lib/http/axios';
import { isAdmin } from '@/lib/auth';
import PageHeader from '@/components/PageHeader';


type MCPTransport = 'streamable_http' | 'sse';


interface MCPServer {
  id: number;
  name: string;
  description: string | null;
  transport: MCPTransport;
  url: string;
  enabled: boolean;
  require_admin: boolean;
  allowed_tools: string[];
  discovered_tools: string[];
  header_names: string[];
  call_timeout_seconds: number;
  max_result_chars: number;
  last_health_status: 'unknown' | 'healthy' | 'unhealthy' | 'disabled' | string;
  last_error: string | null;
  last_checked_at: string | null;
  created_at: string;
  updated_at: string;
}

interface MCPToolInfo {
  server_id: number;
  server_name: string;
  name: string;
  qualified_name: string;
  description: string;
  enabled: boolean;
  require_admin: boolean;
}

interface HeaderRow {
  id: number;
  key: string;
  value: string;
}

interface ServerFormState {
  name: string;
  description: string;
  transport: MCPTransport;
  url: string;
  enabled: boolean;
  requireAdmin: boolean;
  allowedTools: string[];
  allowAllTools: boolean;
  callTimeoutSeconds: number;
  maxResultChars: number;
  headers: HeaderRow[];
  clearExistingHeaders: boolean;
}

const EMPTY_FORM: ServerFormState = {
  name: '',
  description: '',
  transport: 'streamable_http',
  url: '',
  enabled: false,
  requireAdmin: true,
  allowedTools: [],
  allowAllTools: false,
  callTimeoutSeconds: 20,
  maxResultChars: 20000,
  headers: [],
  clearExistingHeaders: false,
};

const STATUS_META: Record<string, { label: string; color: string; dot: string }> = {
  healthy: { label: '连接正常', color: 'green', dot: 'bg-emerald-500' },
  unhealthy: { label: '连接异常', color: 'red', dot: 'bg-red-500' },
  disabled: { label: '未启用', color: 'default', dot: 'bg-slate-400' },
  unknown: { label: '待检测', color: 'gold', dot: 'bg-amber-400' },
};

type ApiErrorDetail = string | {
  loc?: Array<string | number>;
  msg?: string;
  type?: string;
} | ApiErrorDetail[];

function formatApiErrorDetail(detail: ApiErrorDetail | undefined): string | undefined {
  if (!detail) return undefined;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => formatApiErrorDetail(item))
      .filter(Boolean)
      .join('；');
  }
  if (typeof detail === 'object') {
    const location = detail.loc?.filter((item) => item !== 'body').join('.');
    return [location, detail.msg || detail.type].filter(Boolean).join('：');
  }
  return undefined;
}

function errorMessage(error: unknown, fallback: string): string {
  if (isAxiosError<{ detail?: ApiErrorDetail }>(error)) {
    return formatApiErrorDetail(error.response?.data?.detail) || error.message || fallback;
  }
  return error instanceof Error ? error.message : fallback;
}

function formatDate(value: string | null): string {
  if (!value) return '尚未检测';
  return new Date(value).toLocaleString();
}

export default function MCPPage() {
  const router = useRouter();
  const [servers, setServers] = useState<MCPServer[]>([]);
  const [tools, setTools] = useState<MCPToolInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [reloading, setReloading] = useState(false);
  const [actionKey, setActionKey] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingServer, setEditingServer] = useState<MCPServer | null>(null);
  const [form, setForm] = useState<ServerFormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [headerSequence, setHeaderSequence] = useState(1);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const [serverData, toolData] = await Promise.all([
        http.get<MCPServer[], MCPServer[]>('/mcp/servers'),
        http.get<MCPToolInfo[], MCPToolInfo[]>('/mcp/tools?include_disabled=true'),
      ]);
      setServers(serverData);
      setTools(toolData);
    } catch (error) {
      message.error(errorMessage(error, 'MCP 配置加载失败'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isAdmin()) {
      router.replace('/login');
      return;
    }
    const timer = window.setTimeout(() => void fetchData(), 0);
    return () => window.clearTimeout(timer);
  }, [fetchData, router]);

  const summary = useMemo(() => ({
    total: servers.length,
    healthy: servers.filter((server) => server.last_health_status === 'healthy').length,
    enabled: servers.filter((server) => server.enabled).length,
    tools: tools.filter((tool) => tool.enabled).length,
  }), [servers, tools]);

  const openCreateModal = () => {
    setEditingServer(null);
    setForm(EMPTY_FORM);
    setFormError(null);
    setModalOpen(true);
  };

  const openEditModal = (server: MCPServer) => {
    setEditingServer(server);
    setForm({
      name: server.name,
      description: server.description || '',
      transport: server.transport,
      url: server.url,
      enabled: server.enabled,
      requireAdmin: server.require_admin,
      allowedTools: server.allowed_tools.includes('*') ? [] : server.allowed_tools,
      allowAllTools: server.allowed_tools.includes('*'),
      callTimeoutSeconds: server.call_timeout_seconds,
      maxResultChars: server.max_result_chars,
      headers: [],
      clearExistingHeaders: false,
    });
    setFormError(null);
    setModalOpen(true);
  };

  const closeModal = () => {
    if (saving) return;
    setModalOpen(false);
    setEditingServer(null);
    setForm(EMPTY_FORM);
    setFormError(null);
  };

  const addHeaderRow = () => {
    setForm((current) => ({
      ...current,
      headers: [...current.headers, { id: headerSequence, key: '', value: '' }],
    }));
    setHeaderSequence((current) => current + 1);
  };

  const updateHeaderRow = (id: number, field: 'key' | 'value', value: string) => {
    setForm((current) => ({
      ...current,
      headers: current.headers.map((header) => (
        header.id === id ? { ...header, [field]: value } : header
      )),
    }));
  };

  const removeHeaderRow = (id: number) => {
    setForm((current) => ({
      ...current,
      headers: current.headers.filter((header) => header.id !== id),
    }));
  };

  const toggleTool = (toolName: string) => {
    setForm((current) => ({
      ...current,
      allowedTools: current.allowedTools.includes(toolName)
        ? current.allowedTools.filter((name) => name !== toolName)
        : [...current.allowedTools, toolName],
    }));
  };

  const saveServer = async () => {
    const name = form.name.trim();
    const url = form.url.trim();
    const description = form.description.trim();
    if (!name || !url) {
      setFormError('请填写服务器名称和 MCP 地址。');
      return;
    }
    if (name.length > 100) {
      setFormError(`服务器名称不能超过 100 个字符（当前 ${name.length} 个）。`);
      return;
    }
    if (!/^[a-zA-Z0-9_-]+$/.test(name)) {
      setFormError('服务器名称只能包含字母、数字、下划线和短横线。');
      return;
    }
    if (description.length > 500) {
      setFormError(`服务说明不能超过 500 个字符（当前 ${description.length} 个）。`);
      return;
    }

    const incompleteHeader = form.headers.some((header) => (
      Boolean(header.key.trim()) !== Boolean(header.value.trim())
    ));
    if (incompleteHeader) {
      setFormError('认证 Header 的名称和值需要成对填写。');
      return;
    }

    const headers = Object.fromEntries(
      form.headers
        .filter((header) => header.key.trim() && header.value.trim())
        .map((header) => [header.key.trim(), header.value.trim()]),
    );
    const allowedTools = form.allowAllTools ? ['*'] : form.allowedTools;

    try {
      setSaving(true);
      setFormError(null);
      if (editingServer) {
        const payload: Record<string, unknown> = {
          description: description || null,
          transport: form.transport,
          url,
          enabled: form.enabled,
          require_admin: form.requireAdmin,
          allowed_tools: allowedTools,
          call_timeout_seconds: form.callTimeoutSeconds,
          max_result_chars: form.maxResultChars,
        };
        if (form.clearExistingHeaders) {
          payload.headers = {};
        } else if (Object.keys(headers).length > 0) {
          payload.headers = headers;
        }
        await http.put(`/mcp/servers/${editingServer.id}`, payload);
        message.success('MCP Server 配置已更新');
      } else {
        await http.post('/mcp/servers', {
          name,
          description: description || null,
          transport: form.transport,
          url,
          headers,
          enabled: form.enabled,
          require_admin: form.requireAdmin,
          allowed_tools: allowedTools,
          call_timeout_seconds: form.callTimeoutSeconds,
          max_result_chars: form.maxResultChars,
        });
        message.success('MCP Server 已添加');
      }
      closeModal();
      await fetchData();
    } catch (error) {
      setFormError(errorMessage(error, '保存 MCP Server 失败'));
    } finally {
      setSaving(false);
    }
  };

  const testServer = async (server: MCPServer) => {
    const key = `test-${server.id}`;
    try {
      setActionKey(key);
      const discovered = await http.post<MCPToolInfo[], MCPToolInfo[]>(
        `/mcp/servers/${server.id}/test`,
      );
      message.success(`连接成功，发现 ${discovered.length} 个工具`);
      await fetchData();
    } catch (error) {
      message.error(errorMessage(error, '连接测试失败'));
      await fetchData();
    } finally {
      setActionKey(null);
    }
  };

  const toggleServer = async (server: MCPServer, enabled: boolean) => {
    const key = `toggle-${server.id}`;
    try {
      setActionKey(key);
      await http.put(`/mcp/servers/${server.id}`, { enabled });
      message.success(enabled ? 'MCP Server 已启用' : 'MCP Server 已停用');
      await fetchData();
    } catch (error) {
      message.error(errorMessage(error, '状态更新失败'));
    } finally {
      setActionKey(null);
    }
  };

  const deleteServer = async (server: MCPServer) => {
    const key = `delete-${server.id}`;
    try {
      setActionKey(key);
      await http.delete(`/mcp/servers/${server.id}`);
      message.success('MCP Server 已删除');
      await fetchData();
    } catch (error) {
      message.error(errorMessage(error, '删除失败'));
    } finally {
      setActionKey(null);
    }
  };

  const reloadRegistry = async () => {
    try {
      setReloading(true);
      await http.post('/mcp/reload');
      message.success('运行时工具注册表已重新加载');
      await fetchData();
    } catch (error) {
      message.error(errorMessage(error, '重新加载失败'));
    } finally {
      setReloading(false);
    }
  };

  const editingDiscoveredTools = editingServer?.discovered_tools || [];

  return (
    <div className="flex h-full flex-col bg-slate-50/70">
      <PageHeader
        title="MCP 工具接入"
        description="管理远程 Streamable HTTP 服务，发现工具并控制模型可用范围。"
        icon={<WorkflowIcon size={16} />}
        actions={(
          <div className="flex w-full gap-2 sm:w-auto">
            <button
              type="button"
              onClick={() => void reloadRegistry()}
              disabled={reloading}
              className="inline-flex h-8 flex-1 cursor-pointer items-center justify-center gap-1.5 rounded-md border border-gray-200 bg-white px-3 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 disabled:cursor-not-allowed disabled:opacity-50 sm:flex-none"
            >
              <RefreshCwIcon size={14} className={reloading ? 'animate-spin' : ''} />
              重新加载
            </button>
            <button
              type="button"
              onClick={openCreateModal}
              className="inline-flex h-8 flex-1 cursor-pointer items-center justify-center gap-1.5 rounded-md bg-blue-600 px-3 text-xs font-medium text-white shadow-sm transition-colors hover:bg-blue-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 sm:flex-none"
            >
              <PlusIcon size={14} />
              添加服务
            </button>
          </div>
        )}
      />

      <main className="flex-1 overflow-y-auto px-4 py-5 md:px-6 md:py-6">
        <div className="mx-auto max-w-7xl space-y-5">
          <section aria-label="MCP 状态概览" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[
              { label: '已注册服务', value: summary.total, icon: RouterIcon, color: 'text-blue-600', bg: 'bg-blue-50' },
              { label: '健康服务', value: summary.healthy, icon: CircleCheckIcon, color: 'text-emerald-600', bg: 'bg-emerald-50' },
              { label: '已启用服务', value: summary.enabled, icon: ShieldCheckIcon, color: 'text-violet-600', bg: 'bg-violet-50' },
              { label: '模型可用工具', value: summary.tools, icon: WorkflowIcon, color: 'text-amber-600', bg: 'bg-amber-50' },
            ].map((item) => (
              <div key={item.label} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-medium text-slate-500 sm:text-sm">{item.label}</span>
                  <span className={`flex h-8 w-8 items-center justify-center rounded-lg ${item.bg} ${item.color}`}>
                    <item.icon size={17} />
                  </span>
                </div>
                <p className="mt-3 text-2xl font-semibold tabular-nums text-slate-900">{item.value}</p>
              </div>
            ))}
          </section>

          {loading ? (
            <div className="grid gap-4 lg:grid-cols-2">
              {[0, 1].map((item) => (
                <div key={item} className="rounded-xl border border-slate-200 bg-white p-5">
                  <Skeleton active paragraph={{ rows: 4 }} />
                </div>
              ))}
            </div>
          ) : servers.length === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-14 text-center">
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={(
                  <div>
                    <p className="font-medium text-slate-700">还没有 MCP Server</p>
                    <p className="mt-1 text-sm text-slate-500">添加一个远程服务，测试连接后选择允许模型调用的工具。</p>
                  </div>
                )}
              >
                <button
                  type="button"
                  onClick={openCreateModal}
                  className="mt-2 inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-lg bg-blue-600 px-4 text-sm font-medium text-white hover:bg-blue-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
                >
                  <PlusIcon size={17} />
                  添加第一个服务
                </button>
              </Empty>
            </div>
          ) : (
            <section aria-label="MCP Server 列表" className="grid gap-4 lg:grid-cols-2">
              {servers.map((server) => {
                const statusMeta = STATUS_META[server.last_health_status] || STATUS_META.unknown;
                const allowAll = server.allowed_tools.includes('*');
                const exposedCount = allowAll
                  ? server.discovered_tools.length
                  : server.allowed_tools.filter((name) => server.discovered_tools.includes(name)).length;
                return (
                  <article key={server.id} className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm transition-shadow hover:shadow-md">
                    <div className="p-5">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex min-w-0 items-start gap-3">
                          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-700">
                            <RouterIcon size={20} />
                          </div>
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <h2 className="truncate text-base font-semibold text-slate-900">{server.name}</h2>
                              <Tag color={statusMeta.color} className="m-0">
                                <span className="inline-flex items-center gap-1.5">
                                  <span className={`h-1.5 w-1.5 rounded-full ${statusMeta.dot}`} />
                                  {statusMeta.label}
                                </span>
                              </Tag>
                            </div>
                            <p className="mt-1 line-clamp-2 text-sm leading-5 text-slate-500">
                              {server.description || '未填写服务说明'}
                            </p>
                          </div>
                        </div>
                        <Switch
                          checked={server.enabled}
                          loading={actionKey === `toggle-${server.id}`}
                          onChange={(checked) => void toggleServer(server, checked)}
                          aria-label={`${server.enabled ? '停用' : '启用'} ${server.name}`}
                        />
                      </div>

                      <div className="mt-4 rounded-lg bg-slate-50 p-3">
                        <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-500">
                          <WorkflowIcon size={14} />
                          {server.transport === 'sse' ? 'SSE' : 'Streamable HTTP'}
                        </div>
                        <Tooltip title={server.url} placement="bottomLeft">
                          <p className="mt-1 truncate font-mono text-xs text-slate-700">{server.url}</p>
                        </Tooltip>
                      </div>

                      <div className="mt-4 grid grid-cols-3 divide-x divide-slate-200 rounded-lg border border-slate-200 py-3 text-center">
                        <div>
                          <p className="text-lg font-semibold tabular-nums text-slate-900">{server.discovered_tools.length}</p>
                          <p className="text-xs text-slate-500">已发现</p>
                        </div>
                        <div>
                          <p className="text-lg font-semibold tabular-nums text-slate-900">{exposedCount}</p>
                          <p className="text-xs text-slate-500">已允许</p>
                        </div>
                        <div>
                          <p className="text-lg font-semibold tabular-nums text-slate-900">{server.header_names.length}</p>
                          <p className="text-xs text-slate-500">认证头</p>
                        </div>
                      </div>

                      {server.discovered_tools.length > 0 && (
                        <div className="mt-4 flex flex-wrap gap-1.5">
                          {server.discovered_tools.slice(0, 6).map((toolName) => {
                            const allowed = allowAll || server.allowed_tools.includes(toolName);
                            return (
                              <Tag key={toolName} color={allowed ? 'blue' : 'default'} className="m-0 max-w-full truncate font-mono text-xs">
                                {toolName}
                              </Tag>
                            );
                          })}
                          {server.discovered_tools.length > 6 && (
                            <Tag className="m-0">+{server.discovered_tools.length - 6}</Tag>
                          )}
                        </div>
                      )}

                      {server.last_error && (
                        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                          <div className="flex items-start gap-2">
                            <XIcon size={16} className="mt-0.5 shrink-0" />
                            <p className="line-clamp-3 break-all">{server.last_error}</p>
                          </div>
                        </div>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 bg-slate-50/80 px-5 py-3">
                      <span className="text-xs text-slate-500">检测时间：{formatDate(server.last_checked_at)}</span>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => void testServer(server)}
                          disabled={actionKey === `test-${server.id}`}
                          className="inline-flex min-h-10 cursor-pointer items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <SearchIcon size={15} className={actionKey === `test-${server.id}` ? 'animate-pulse' : ''} />
                          测试连接
                        </button>
                        <button
                          type="button"
                          onClick={() => openEditModal(server)}
                          className="inline-flex min-h-10 cursor-pointer items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-3 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
                        >
                          <SettingsIcon size={15} />
                          配置
                        </button>
                        <Popconfirm
                          title={`删除 ${server.name}？`}
                          description="删除后模型将无法再使用该服务的工具。"
                          okText="删除"
                          cancelText="取消"
                          okButtonProps={{ danger: true }}
                          onConfirm={() => void deleteServer(server)}
                        >
                          <button
                            type="button"
                            aria-label={`删除 ${server.name}`}
                            disabled={actionKey === `delete-${server.id}`}
                            className="flex h-10 w-10 cursor-pointer items-center justify-center rounded-lg border border-red-200 bg-white text-red-600 transition-colors hover:bg-red-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-600 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            <DeleteIcon size={16} />
                          </button>
                        </Popconfirm>
                      </div>
                    </div>
                  </article>
                );
              })}
            </section>
          )}
        </div>
      </main>

      <Modal
        open={modalOpen}
        onCancel={closeModal}
        title={editingServer ? `配置 ${editingServer.name}` : '添加 MCP Server'}
        width={720}
        footer={null}
        destroyOnHidden
        styles={{ body: { maxHeight: '72vh', overflowY: 'auto', paddingRight: 4 } }}
      >
        <form
          className="mt-5 space-y-6"
          onSubmit={(event) => {
            event.preventDefault();
            void saveServer();
          }}
        >
          {formError && <Alert type="error" showIcon title={formError} role="alert" />}

          <fieldset className="space-y-4">
            <legend className="text-sm font-semibold text-slate-900">连接信息</legend>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="space-y-1.5 text-sm font-medium text-slate-700" htmlFor="mcp-name">
                服务名称 <span className="text-red-500">*</span>
                <input
                  id="mcp-name"
                  value={form.name}
                  disabled={Boolean(editingServer)}
                  onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                  placeholder="例如 amap"
                  autoComplete="off"
                  className="min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 font-mono text-sm font-normal text-slate-900 transition-colors focus:border-blue-500 focus:outline-none disabled:bg-slate-100 disabled:text-slate-500"
                />
                <span className="block text-xs font-normal text-slate-500">用于生成 `server__tool` 工具名称，保存后不可修改。</span>
              </label>
              <label className="space-y-1.5 text-sm font-medium text-slate-700" htmlFor="mcp-transport">
                传输协议
                <select
                  id="mcp-transport"
                  value={form.transport}
                  onChange={(event) => setForm((current) => ({
                    ...current,
                    transport: event.target.value as MCPTransport,
                  }))}
                  className="min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm font-normal text-slate-900 transition-colors focus:border-blue-500 focus:outline-none"
                >
                  <option value="streamable_http">Streamable HTTP（推荐）</option>
                  <option value="sse">SSE（兼容旧服务）</option>
                </select>
                <span className="block text-xs font-normal text-slate-500">新服务优先使用 Streamable HTTP，旧服务可选择 SSE。</span>
              </label>
            </div>
            <label className="space-y-1.5 text-sm font-medium text-slate-700" htmlFor="mcp-url">
              MCP 地址 <span className="text-red-500">*</span>
              <input
                id="mcp-url"
                type="url"
                value={form.url}
                onChange={(event) => setForm((current) => ({ ...current, url: event.target.value }))}
                placeholder="https://example.com/mcp"
                autoComplete="url"
                className="min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 font-mono text-sm font-normal text-slate-900 transition-colors focus:border-blue-500 focus:outline-none"
              />
            </label>
            <label className="space-y-1.5 text-sm font-medium text-slate-700" htmlFor="mcp-description">
              服务说明
              <textarea
                id="mcp-description"
                value={form.description}
                onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
                placeholder="说明这个 MCP 提供什么能力，方便后续维护。"
                rows={3}
                maxLength={500}
                aria-describedby="mcp-description-count"
                className="w-full resize-y rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm font-normal text-slate-900 transition-colors focus:border-blue-500 focus:outline-none"
              />
              <span
                id="mcp-description-count"
                className={`block text-right text-xs font-normal ${form.description.length > 450 ? 'text-amber-600' : 'text-slate-500'}`}
              >
                {form.description.length}/500
              </span>
            </label>
          </fieldset>

          <fieldset className="space-y-4 border-t border-slate-200 pt-5">
            <div className="flex items-center justify-between gap-3">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                <KeyIcon size={17} className="text-slate-500" />
                认证 Headers
              </h3>
              <button
                type="button"
                onClick={addHeaderRow}
                className="inline-flex min-h-10 cursor-pointer items-center gap-1.5 rounded-lg px-3 text-sm font-medium text-blue-600 transition-colors hover:bg-blue-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
              >
                <PlusIcon size={15} />
                添加 Header
              </button>
            </div>

            {editingServer && editingServer.header_names.length > 0 && (
              <div className="rounded-lg border border-blue-100 bg-blue-50 p-3">
                <p className="text-xs font-medium text-blue-900">已保存且不会回显</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {editingServer.header_names.map((name) => <Tag key={name} className="m-0 font-mono">{name}</Tag>)}
                </div>
                <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm text-blue-900">
                  <input
                    type="checkbox"
                    checked={form.clearExistingHeaders}
                    onChange={(event) => setForm((current) => ({
                      ...current,
                      clearExistingHeaders: event.target.checked,
                      headers: event.target.checked ? [] : current.headers,
                    }))}
                    className="h-4 w-4 rounded border-blue-300 text-blue-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
                  />
                  清除全部已保存的认证 Header
                </label>
              </div>
            )}

            {!form.clearExistingHeaders && form.headers.map((header) => (
              <div key={header.id} className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_44px]">
                <label className="sr-only" htmlFor={`header-key-${header.id}`}>Header 名称</label>
                <input
                  id={`header-key-${header.id}`}
                  value={header.key}
                  onChange={(event) => updateHeaderRow(header.id, 'key', event.target.value)}
                  placeholder="Authorization"
                  autoComplete="off"
                  className="min-h-11 rounded-lg border border-slate-300 px-3 font-mono text-sm focus:border-blue-500 focus:outline-none"
                />
                <label className="sr-only" htmlFor={`header-value-${header.id}`}>Header 值</label>
                <input
                  id={`header-value-${header.id}`}
                  type="password"
                  value={header.value}
                  onChange={(event) => updateHeaderRow(header.id, 'value', event.target.value)}
                  placeholder="Bearer ..."
                  autoComplete="new-password"
                  className="min-h-11 rounded-lg border border-slate-300 px-3 font-mono text-sm focus:border-blue-500 focus:outline-none"
                />
                <button
                  type="button"
                  aria-label="删除这个 Header"
                  onClick={() => removeHeaderRow(header.id)}
                  className="flex h-11 w-11 cursor-pointer items-center justify-center rounded-lg border border-red-200 text-red-600 hover:bg-red-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-600"
                >
                  <DeleteIcon size={16} />
                </button>
              </div>
            ))}
            <p className="text-xs leading-5 text-slate-500">
              新认证信息会在后端加密保存。编辑时留空表示保留原值；若服务将密钥放在 URL 中，则无需添加 Header。
            </p>
          </fieldset>

          <fieldset className="space-y-4 border-t border-slate-200 pt-5">
            <div className="flex items-center justify-between gap-3">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                <WorkflowIcon size={17} className="text-slate-500" />
                工具白名单
              </h3>
              <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-700">
                允许全部工具
                <Switch
                  size="small"
                  checked={form.allowAllTools}
                  onChange={(checked) => setForm((current) => ({
                    ...current,
                    allowAllTools: checked,
                    allowedTools: checked ? [] : current.allowedTools,
                  }))}
                />
              </label>
            </div>

            {!editingServer ? (
              <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-5 text-center text-sm text-slate-500">
                保存后点击“测试连接”发现工具，再回来配置白名单。
              </div>
            ) : editingDiscoveredTools.length === 0 ? (
              <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-5 text-center text-sm text-slate-500">
                尚未发现工具，请先保存并在服务卡片上点击“测试连接”。
              </div>
            ) : form.allowAllTools ? (
              <Alert
                type="warning"
                showIcon
                title={`将向模型开放当前及未来发现的全部工具（当前 ${editingDiscoveredTools.length} 个）`}
              />
            ) : (
              <div className="grid max-h-56 gap-2 overflow-y-auto rounded-lg border border-slate-200 p-2 sm:grid-cols-2">
                {editingDiscoveredTools.map((toolName) => {
                  const checked = form.allowedTools.includes(toolName);
                  return (
                    <label
                      key={toolName}
                      className={`flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 transition-colors ${checked ? 'border-blue-300 bg-blue-50 text-blue-900' : 'border-transparent bg-slate-50 text-slate-700 hover:border-slate-300'}`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleTool(toolName)}
                        className="h-4 w-4 rounded border-slate-300 text-blue-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
                      />
                      <span className="min-w-0 truncate font-mono text-xs" title={toolName}>{toolName}</span>
                    </label>
                  );
                })}
              </div>
            )}
          </fieldset>

          <fieldset className="space-y-4 border-t border-slate-200 pt-5">
            <legend className="text-sm font-semibold text-slate-900">运行策略</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="flex cursor-pointer items-start justify-between gap-3 rounded-lg border border-slate-200 p-4">
                <span>
                  <span className="block text-sm font-medium text-slate-800">启用服务</span>
                  <span className="mt-1 block text-xs leading-5 text-slate-500">启用后后端会连接并加载白名单工具。</span>
                </span>
                <Switch
                  checked={form.enabled}
                  onChange={(checked) => setForm((current) => ({ ...current, enabled: checked }))}
                />
              </label>
              <label className="flex cursor-pointer items-start justify-between gap-3 rounded-lg border border-slate-200 p-4">
                <span>
                  <span className="block text-sm font-medium text-slate-800">仅管理员可用</span>
                  <span className="mt-1 block text-xs leading-5 text-slate-500">建议保持开启，确认工具安全后再放宽。</span>
                </span>
                <Switch
                  checked={form.requireAdmin}
                  onChange={(checked) => setForm((current) => ({ ...current, requireAdmin: checked }))}
                />
              </label>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="space-y-1.5 text-sm font-medium text-slate-700" htmlFor="mcp-timeout">
                调用超时（秒）
                <input
                  id="mcp-timeout"
                  type="number"
                  inputMode="numeric"
                  min={1}
                  max={300}
                  value={form.callTimeoutSeconds}
                  onChange={(event) => setForm((current) => ({
                    ...current,
                    callTimeoutSeconds: Number(event.target.value),
                  }))}
                  className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm font-normal focus:border-blue-500 focus:outline-none"
                />
              </label>
              <label className="space-y-1.5 text-sm font-medium text-slate-700" htmlFor="mcp-max-result">
                最大文本结果字符数
                <input
                  id="mcp-max-result"
                  type="number"
                  inputMode="numeric"
                  min={1000}
                  max={200000}
                  step={1000}
                  value={form.maxResultChars}
                  onChange={(event) => setForm((current) => ({
                    ...current,
                    maxResultChars: Number(event.target.value),
                  }))}
                  className="min-h-11 w-full rounded-lg border border-slate-300 px-3 text-sm font-normal focus:border-blue-500 focus:outline-none"
                />
              </label>
            </div>
          </fieldset>

          <div className="sticky bottom-0 -mx-1 flex flex-col-reverse gap-2 border-t border-slate-200 bg-white px-1 pt-4 sm:flex-row sm:justify-end">
            <button
              type="button"
              onClick={closeModal}
              disabled={saving}
              className="min-h-11 cursor-pointer rounded-lg border border-slate-300 bg-white px-5 text-sm font-medium text-slate-700 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={saving}
              className="inline-flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-lg bg-blue-600 px-5 text-sm font-medium text-white hover:bg-blue-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {saving ? <RefreshCwIcon size={16} className="animate-spin" /> : <CircleCheckIcon size={16} />}
              {saving ? '保存中…' : '保存配置'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
