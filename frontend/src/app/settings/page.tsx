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
}

function SettingField({ setting, onChange }: SettingFieldProps) {
  const fieldId = `setting-${setting.key}`;
  const isEmbeddingDimensions = setting.key === 'agentchat_embedding_dimensions';

  return (
    <div className="space-y-2">
      <label htmlFor={fieldId} className="block text-sm font-medium text-gray-700">
        {setting.description || setting.key}
        {setting.is_encrypted && (
          <span className="ml-2 text-xs font-normal text-gray-500">(加密存储)</span>
        )}
      </label>

      {setting.key === 'smtp_enabled' ? (
        <select
          id={fieldId}
          value={setting.value}
          onChange={(event) => onChange(setting.key, event.target.value)}
          className="min-h-11 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-base focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
        >
          <option value="true">启用</option>
          <option value="false">禁用</option>
        </select>
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
          className="min-h-11 w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-base text-gray-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
        />
      )}

      <p className="text-xs text-gray-500">配置键：{setting.key}</p>
    </div>
  );
}

export default function SettingsPage() {
  const router = useRouter();
  const [settings, setSettings] = useState<Record<string, SettingFormData>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

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
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <SettingsIcon size={24} className="text-gray-700" />
          <h1 className="text-xl font-semibold text-gray-900">系统设置</h1>
        </div>

        <button
          onClick={handleSave}
          disabled={saving}
          className="flex min-h-11 cursor-pointer items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-white transition-colors hover:bg-blue-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {saving ? (
            <>
              <RefreshCwIcon size={16} className="animate-spin" />
              <span>保存中...</span>
            </>
          ) : (
            <>
              <CheckIcon size={16} />
              <span>保存配置</span>
            </>
          )}
        </button>
      </div>

      {/* Message */}
      {message && (
        <div role="status" className={`mx-6 mt-4 p-3 rounded-lg flex items-center gap-2 ${
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
        <div className="max-w-4xl mx-auto space-y-6">
          {Object.entries(SETTING_CATEGORIES).map(([category, categoryInfo]) => {
            const categorySettings = groupedSettings[category] || [];
            const CategoryIcon = categoryInfo.icon;

            if (categorySettings.length === 0) return null;

            return (
              <div key={category} className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                <div className="px-6 py-4 bg-gray-50 border-b border-gray-200">
                  <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                    <CategoryIcon size={20} className="text-gray-600" />
                    <span>{categoryInfo.label}</span>
                  </h2>
                </div>

                {category === 'ai' ? (
                  <div className="p-4 sm:p-6">
                    <p className="text-sm leading-6 text-gray-600">
                      两类模型使用完全独立的接口地址、模型名称和 API 密钥，可分别接入不同厂商。
                    </p>
                    <div className="mt-5 grid gap-5 lg:grid-cols-2">
                      {AI_SETTING_GROUPS.map((group) => {
                        const GroupIcon = group.icon;
                        const groupSettings = group.settingKeys
                          .map((key) => settings[key])
                          .filter((setting): setting is SettingFormData => Boolean(setting));

                        return (
                          <fieldset key={group.key} className="rounded-xl border border-gray-200 bg-gray-50/60 p-4 sm:p-5">
                            <legend className="sr-only">{group.title}</legend>
                            <div className="mb-5 flex items-start gap-3">
                              <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border ${group.accentClassName}`}>
                                <GroupIcon size={20} />
                              </span>
                              <div>
                                <h3 className="font-semibold text-gray-900">{group.title}</h3>
                                <p className="mt-1 text-sm leading-5 text-gray-600">{group.description}</p>
                              </div>
                            </div>
                            <div className="space-y-4">
                              {groupSettings.map((setting) => (
                                <SettingField key={setting.key} setting={setting} onChange={handleChange} />
                              ))}
                            </div>
                          </fieldset>
                        );
                      })}
                    </div>
                  </div>
                ) : (
                  <div className="space-y-4 p-6">
                    {categorySettings.map((setting) => (
                      <SettingField key={setting.key} setting={setting} onChange={handleChange} />
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
