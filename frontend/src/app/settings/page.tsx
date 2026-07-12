'use client';

import React, { useCallback, useEffect, useState } from 'react';
import {
  BellIcon,
  BotIcon,
  BrainIcon,
  CheckIcon,
  CircleCheckIcon,
  DatabaseIcon,
  MailboxIcon,
  RefreshCwIcon,
  SettingsIcon,
  XIcon,
} from 'lucide-animated';
import { useRouter } from 'next/navigation';
import { isAxiosError } from 'axios';
import http from '@/lib/http/axios';
import { isAdmin } from '@/lib/auth';
import PageHeader from '@/components/PageHeader';

interface SystemSetting {
  id: number;
  key: string;
  value: string;
  category: string;
  is_encrypted: boolean;
  description: string | null;
  created_at: string;
  updated_at: string;
}

interface SettingFormData {
  key: string;
  value: string;
  category: string;
  is_encrypted: boolean;
  description: string;
}

interface ModelOption {
  id: string;
  owned_by: string | null;
}

interface ModelOptionsResponse {
  models: ModelOption[];
  count: number;
}

const SETTING_CATEGORIES = {
  ai: { label: 'AI 模型配置', icon: BotIcon },
  email: { label: '邮件通知', icon: MailboxIcon },
  vector_db: { label: '向量数据库', icon: DatabaseIcon },
  notification: { label: '通知设置', icon: BellIcon },
};

const LEGACY_SETTING_ALIASES: Record<string, string> = {
  ai_base_url: 'llm_base_url',
  ai_model: 'llm_model',
};

const AI_SETTING_GROUPS = [
  {
    key: 'llm',
    title: 'LLM 大模型',
    description: '负责对话、任务执行和内容生成。',
    icon: BotIcon,
    settingKeys: ['llm_base_url', 'llm_model', 'llm_api_key'],
    accentClassName: 'border-blue-200 bg-blue-50 text-blue-700',
  },
  {
    key: 'embedding',
    title: 'Embedding 模型',
    description: '负责文档向量化与语义检索，可使用另一家厂商。',
    icon: BrainIcon,
    settingKeys: [
      'embedding_base_url',
      'embedding_model',
      'embedding_api_key',
      'agentchat_embedding_dimensions',
    ],
    accentClassName: 'border-violet-200 bg-violet-50 text-violet-700',
  },
] as const;

const DEFAULT_SETTINGS: SettingFormData[] = [
  {
    key: 'llm_base_url',
    value: 'https://ai.hybgzs.com/v1',
    category: 'ai',
    is_encrypted: false,
    description: 'LLM API 基础地址',
  },
  {
    key: 'llm_model',
    value: 'moonshotai/kimi-k2.6',
    category: 'ai',
    is_encrypted: false,
    description: 'LLM 模型名称',
  },
  {
    key: 'llm_api_key',
    value: '',
    category: 'ai',
    is_encrypted: true,
    description: 'LLM API 密钥',
  },
  {
    key: 'embedding_base_url',
    value: 'https://ai.hybgzs.com/v1',
    category: 'ai',
    is_encrypted: false,
    description: 'Embedding API 基础地址',
  },
  {
    key: 'embedding_model',
    value: 'Qwen/Qwen3-Embedding-8B',
    category: 'ai',
    is_encrypted: false,
    description: 'Embedding 模型名称',
  },
  {
    key: 'embedding_api_key',
    value: '',
    category: 'ai',
    is_encrypted: true,
    description: 'Embedding API 密钥',
  },
  {
    key: 'agentchat_embedding_dimensions',
    value: '1024',
    category: 'ai',
    is_encrypted: false,
    description: 'Embedding 向量维度',
  },
  {
    key: 'smtp_host',
    value: 'smtp.qq.com',
    category: 'email',
    is_encrypted: false,
    description: 'SMTP 服务器地址',
  },
  {
    key: 'smtp_port',
    value: '465',
    category: 'email',
    is_encrypted: false,
    description: 'SMTP 服务器端口',
  },
  {
    key: 'smtp_user',
    value: '',
    category: 'email',
    is_encrypted: false,
    description: 'SMTP 用户名（邮箱地址）',
  },
  {
    key: 'smtp_password',
    value: '',
    category: 'email',
    is_encrypted: true,
    description: 'SMTP 密码（QQ 邮箱授权码）',
  },
  {
    key: 'smtp_from_email',
    value: '',
    category: 'email',
    is_encrypted: false,
    description: '发件人邮箱地址',
  },
  {
    key: 'smtp_from_name',
    value: 'AgentChat通知系统',
    category: 'email',
    is_encrypted: false,
    description: '发件人名称',
  },
  {
    key: 'smtp_enabled',
    value: 'true',
    category: 'email',
    is_encrypted: false,
    description: '是否启用邮件通知',
  },
  {
    key: 'document_notification_email',
    value: '2810363752@qq.com',
    category: 'notification',
    is_encrypted: false,
    description: '文档处理通知接收邮箱',
  },
  {
    key: 'agentchat_milvus_uri',
    value: 'http://localhost:19530',
    category: 'vector_db',
    is_encrypted: false,
    description: 'Milvus 服务地址',
  },
  {
    key: 'agentchat_milvus_collection',
    value: 'agentchat_documents',
    category: 'vector_db',
    is_encrypted: false,
    description: 'Milvus 集合名称',
  },
];

interface SettingFieldProps {
  setting: SettingFormData;
  onChange: (key: string, value: string) => void;
  modelOptions?: ModelOption[];
  modelsLoading?: boolean;
  modelError?: string;
  onRefreshModels?: (key: string) => void;
}

function SettingField({
  setting,
  onChange,
  modelOptions = [],
  modelsLoading = false,
  modelError,
  onRefreshModels,
}: SettingFieldProps) {
  const fieldId = `setting-${setting.key}`;
  const isEmbeddingDimensions = setting.key === 'agentchat_embedding_dimensions';
  const isModelField = setting.key === 'llm_model' || setting.key === 'embedding_model';
  const modelListId = `${fieldId}-options`;

  return (
    <div className="space-y-1.5">
      <label htmlFor={fieldId} className="block text-xs font-medium text-gray-600">
        {setting.description || setting.key}
        {setting.is_encrypted && (
          <span className="ml-2 text-[11px] font-normal text-gray-400">(加密存储)</span>
        )}
      </label>

      {setting.key === 'smtp_enabled' ? (
        <div className="flex items-center gap-3 pt-1">
          <button
            type="button"
            id={fieldId}
            role="switch"
            aria-checked={setting.value === 'true'}
            onClick={() => onChange(setting.key, setting.value === 'true' ? 'false' : 'true')}
            className={`relative inline-flex h-7 w-12 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors duration-300 ease-in-out focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 ${
              setting.value === 'true' ? 'bg-blue-500' : 'bg-gray-200'
            }`}
          >
            <span
              aria-hidden="true"
              className={`pointer-events-none inline-block h-6 w-6 transform rounded-full bg-white shadow-sm ring-0 transition duration-300 ease-in-out ${
                setting.value === 'true' ? 'translate-x-5' : 'translate-x-0'
              }`}
            />
          </button>
          <span className={`text-xs font-medium transition-colors ${setting.value === 'true' ? 'text-blue-600' : 'text-gray-400'}`}>
            {setting.value === 'true' ? '已启用' : '已禁用'}
          </span>
        </div>
      ) : isModelField ? (
        <div className="space-y-2">
          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              id={fieldId}
              type="text"
              list={modelListId}
              value={setting.value}
              onChange={(event) => onChange(setting.key, event.target.value)}
              placeholder={`请输入${setting.description || setting.key}`}
              autoComplete="off"
              className="min-h-11 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            />
            <button
              type="button"
              onClick={() => onRefreshModels?.(setting.key)}
              disabled={modelsLoading}
              aria-label="获取可用模型"
              title="获取可用模型"
              className="inline-flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-lg border border-gray-300 bg-white px-3 py-2 text-xs font-medium text-gray-700 transition-colors hover:bg-gray-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <RefreshCwIcon size={16} className={modelsLoading ? 'animate-spin' : ''} />
              <span className="whitespace-nowrap">获取</span>
            </button>
          </div>
          <datalist id={modelListId}>
            {modelOptions.map((option) => (
              <option key={option.id} value={option.id} label={option.owned_by || option.id} />
            ))}
          </datalist>
          {modelError && (
            <p role="alert" className="text-[11px] leading-5 text-red-600">
              {modelError}
            </p>
          )}
          {!modelError && modelOptions.length > 0 && (
            <p className="text-[11px] leading-5 text-gray-500">
              已获取 {modelOptions.length} 个模型，可选择或继续手动输入。
            </p>
          )}
        </div>
      ) : (
        <input
          id={fieldId}
          type={setting.is_encrypted ? 'password' : isEmbeddingDimensions ? 'number' : 'text'}
          inputMode={isEmbeddingDimensions ? 'numeric' : undefined}
          min={isEmbeddingDimensions ? 1 : undefined}
          value={setting.value}
          onChange={(event) => onChange(setting.key, event.target.value)}
          placeholder={`请输入${setting.description || setting.key}`}
          autoComplete={setting.is_encrypted ? 'new-password' : 'off'}
          className="min-h-11 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
        />
      )}

    </div>
  );
}

export default function SettingsPage() {
  const router = useRouter();
  const [settings, setSettings] = useState<Record<string, SettingFormData>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [modelOptions, setModelOptions] = useState<Record<string, ModelOption[]>>({});
  const [modelLoading, setModelLoading] = useState<Record<string, boolean>>({});
  const [modelErrors, setModelErrors] = useState<Record<string, string>>({});

  const fetchSettings = useCallback(async () => {
    try {
      setLoading(true);
      const response = await http.get<SystemSetting[], SystemSetting[]>('/settings');

      const settingsMap: Record<string, SettingFormData> = {};

      // 先填充默认配置
      DEFAULT_SETTINGS.forEach(setting => {
        settingsMap[setting.key] = { ...setting };
      });

      // 用数据库中的配置覆盖默认值
      const responseKeys = new Set(response.map((setting) => setting.key));
      response.forEach((setting: SystemSetting) => {
        const canonicalKey = LEGACY_SETTING_ALIASES[setting.key] || setting.key;
        if (canonicalKey !== setting.key && responseKeys.has(canonicalKey)) {
          return;
        }

        settingsMap[canonicalKey] = {
          key: canonicalKey,
          value: setting.value,
          category: setting.category,
          is_encrypted: setting.is_encrypted,
          description: setting.description || settingsMap[canonicalKey]?.description || '',
        };
      });

      setSettings(settingsMap);
    } catch (error) {
      console.error('Failed to fetch settings:', error);
      // 加载失败时使用默认配置
      const settingsMap: Record<string, SettingFormData> = {};
      DEFAULT_SETTINGS.forEach(setting => {
        settingsMap[setting.key] = { ...setting };
      });
      setSettings(settingsMap);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // 检查管理员权限
    if (!isAdmin()) {
      router.push('/login');
      return;
    }

    const timer = window.setTimeout(() => {
      void fetchSettings();
    }, 0);

    return () => window.clearTimeout(timer);
  }, [fetchSettings, router]);

  const handleSave = async () => {
    try {
      setSaving(true);
      setMessage(null);

      const settingsArray = Object.values(settings);

      await http.post('/settings/batch', {
        settings: settingsArray,
      });

      setMessage({ type: 'success', text: '配置保存成功！' });

      // 3 秒后清除提示
      setTimeout(() => setMessage(null), 3000);

      // 重新加载配置
      await fetchSettings();
    } catch (error: unknown) {
      console.error('Failed to save settings:', error);
      const detail = isAxiosError<{ detail?: string }>(error)
        ? error.response?.data?.detail
        : undefined;
      setMessage({
        type: 'error',
        text: `保存失败：${detail || (error instanceof Error ? error.message : '未知错误')}`
      });
    } finally {
      setSaving(false);
    }
  };

  const handleChange = (key: string, value: string) => {
    setSettings(prev => ({
      ...prev,
      [key]: {
        ...prev[key],
        value,
      },
    }));
  };

  const handleRefreshModels = async (key: string) => {
    const kind = key === 'embedding_model' ? 'embedding' : key === 'llm_model' ? 'llm' : null;
    if (!kind) {
      return;
    }

    const baseUrlKey = kind === 'llm' ? 'llm_base_url' : 'embedding_base_url';
    const apiKeyKey = kind === 'llm' ? 'llm_api_key' : 'embedding_api_key';
    const baseUrl = settings[baseUrlKey]?.value?.trim() || '';
    const apiKey = settings[apiKeyKey]?.value || '';

    if (!baseUrl) {
      setModelErrors(prev => ({
        ...prev,
        [key]: '请先填写接口地址',
      }));
      return;
    }

    try {
      setModelLoading(prev => ({ ...prev, [key]: true }));
      setModelErrors(prev => ({ ...prev, [key]: '' }));

      const response = await http.post<ModelOptionsResponse, ModelOptionsResponse>(
        '/settings/model-options',
        {
          kind,
          base_url: baseUrl,
          api_key: apiKey,
        }
      );

      setModelOptions(prev => ({
        ...prev,
        [key]: response.models,
      }));

      if (response.count === 0) {
        setModelErrors(prev => ({
          ...prev,
          [key]: '模型服务未返回可用模型',
        }));
      }
    } catch (error: unknown) {
      console.error('Failed to fetch model options:', error);
      const detail = isAxiosError<{ detail?: string }>(error)
        ? error.response?.data?.detail
        : undefined;
      setModelErrors(prev => ({
        ...prev,
        [key]: detail || (error instanceof Error ? error.message : '获取模型列表失败'),
      }));
    } finally {
      setModelLoading(prev => ({ ...prev, [key]: false }));
    }
  };

  const groupedSettings = Object.values(settings).reduce((acc, setting) => {
    if (!acc[setting.category]) {
      acc[setting.category] = [];
    }
    acc[setting.category].push(setting);
    return acc;
  }, {} as Record<string, SettingFormData[]>);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <RefreshCwIcon className="animate-spin" size={32} />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <PageHeader
        title="系统设置"
        description="配置模型、邮箱、向量库与通知参数。"
        icon={<SettingsIcon size={16} />}
        actions={(
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="inline-flex h-8 cursor-pointer items-center gap-1.5 rounded-md bg-blue-600 px-3 text-xs font-medium text-white transition-colors hover:bg-blue-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? (
              <>
                <RefreshCwIcon size={14} className="animate-spin" />
                <span>保存中...</span>
              </>
            ) : (
              <>
                <CheckIcon size={14} />
                <span>保存配置</span>
              </>
            )}
          </button>
        )}
      />

      {/* Message */}
      {message && (
        <div role="status" className={`mx-6 mt-4 p-3 rounded-lg flex items-center gap-2 text-sm ${
          message.type === 'success' ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-800'
        }`}>
          {message.type === 'success' ? (
            <CircleCheckIcon size={20} />
          ) : (
            <XIcon size={20} />
          )}
          <span>{message.text}</span>
        </div>
      )}

      {/* Settings Content */}
      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-4xl mx-auto space-y-5">
          {Object.entries(SETTING_CATEGORIES).map(([category, categoryInfo]) => {
            const categorySettings = groupedSettings[category] || [];
            const CategoryIcon = categoryInfo.icon;

            if (categorySettings.length === 0) return null;

            return (
              <div key={category} className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                <div className="px-6 py-3.5 bg-gray-50 border-b border-gray-200">
                  <h2 className="text-base font-semibold text-gray-900 flex items-center gap-2">
                    <CategoryIcon size={18} className="text-gray-600" />
                    <span>{categoryInfo.label}</span>
                  </h2>
                </div>

                {category === 'ai' ? (
                  <div className="p-4 sm:p-6">
                    <p className="text-xs leading-5 text-gray-500">
                      两类模型使用完全独立的接口地址、模型名称和 API 密钥，可分别接入不同厂商。
                    </p>
                    <div className="mt-4 grid gap-4 lg:grid-cols-2">
                      {AI_SETTING_GROUPS.map((group) => {
                        const GroupIcon = group.icon;
                        const groupSettings = group.settingKeys
                          .map((key) => settings[key])
                          .filter((setting): setting is SettingFormData => Boolean(setting));

                        return (
                          <fieldset key={group.key} className="rounded-xl border border-gray-200 bg-gray-50/60 p-4">
                            <legend className="sr-only">{group.title}</legend>
                            <div className="mb-4 flex items-start gap-3">
                              <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border ${group.accentClassName}`}>
                                <GroupIcon size={18} />
                              </span>
                              <div>
                                <h3 className="text-sm font-semibold text-gray-900">{group.title}</h3>
                                <p className="mt-1 text-xs leading-5 text-gray-500">{group.description}</p>
                              </div>
                            </div>
                            <div className="space-y-3.5">
                              {groupSettings.map((setting) => (
                                <SettingField
                                  key={setting.key}
                                  setting={setting}
                                  onChange={handleChange}
                                  modelOptions={modelOptions[setting.key] || []}
                                  modelsLoading={Boolean(modelLoading[setting.key])}
                                  modelError={modelErrors[setting.key]}
                                  onRefreshModels={handleRefreshModels}
                                />
                              ))}
                            </div>
                          </fieldset>
                        );
                      })}
                    </div>
                  </div>
                ) : (
                  <div className="space-y-3.5 p-6">
                    {categorySettings.map((setting) => (
                      <SettingField
                        key={setting.key}
                        setting={setting}
                        onChange={handleChange}
                        modelOptions={modelOptions[setting.key] || []}
                        modelsLoading={Boolean(modelLoading[setting.key])}
                        modelError={modelErrors[setting.key]}
                        onRefreshModels={handleRefreshModels}
                      />
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
