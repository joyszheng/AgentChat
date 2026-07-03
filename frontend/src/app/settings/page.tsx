'use client';

import React, { useState, useEffect } from 'react';
import { CheckIcon, RefreshCwIcon, CircleCheckIcon, XIcon, SettingsIcon } from 'lucide-animated';
import { useRouter } from 'next/navigation';
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
  ai: { label: 'AI 模型配置', icon: '🤖' },
  email: { label: '邮件通知', icon: '📧' },
  vector_db: { label: '向量数据库', icon: '🗄️' },
  notification: { label: '通知设置', icon: '🔔' },
};

const DEFAULT_SETTINGS: SettingFormData[] = [
  {
    key: 'ai_base_url',
    value: 'https://ai.hybgzs.com/v1',
    category: 'ai',
    is_encrypted: false,
    description: 'AI API 基础地址',
  },
  {
    key: 'ai_model',
    value: 'moonshotai/kimi-k2.6',
    category: 'ai',
    is_encrypted: false,
    description: 'LLM 模型名称',
  },
  {
    key: 'embedding_model',
    value: 'Qwen/Qwen3-Embedding-8B',
    category: 'ai',
    is_encrypted: false,
    description: 'Embedding 模型名称',
  },
  {
    key: 'glm_api_key',
    value: '',
    category: 'ai',
    is_encrypted: true,
    description: 'AI API 密钥',
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

export default function SettingsPage() {
  const router = useRouter();
  const [settings, setSettings] = useState<Record<string, SettingFormData>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    // 检查管理员权限
    if (!isAdmin()) {
      router.push('/login');
      return;
    }

    fetchSettings();
  }, [router]);

  const fetchSettings = async () => {
    try {
      setLoading(true);
      const response = await http.get<SystemSetting[]>('/settings');

      const settingsMap: Record<string, SettingFormData> = {};

      // 先填充默认配置
      DEFAULT_SETTINGS.forEach(setting => {
        settingsMap[setting.key] = { ...setting };
      });

      // 用数据库中的配置覆盖默认值
      response.forEach((setting: SystemSetting) => {
        settingsMap[setting.key] = {
          key: setting.key,
          value: setting.value,
          category: setting.category,
          is_encrypted: setting.is_encrypted,
          description: setting.description || '',
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
  };

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
    } catch (error: any) {
      console.error('Failed to save settings:', error);
      setMessage({
        type: 'error',
        text: `保存失败：${error.response?.data?.detail || error.message}`
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
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
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
        <div className={`mx-6 mt-4 p-3 rounded-lg flex items-center gap-2 ${
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

            if (categorySettings.length === 0) return null;

            return (
              <div key={category} className="bg-white border border-gray-200 rounded-xl overflow-hidden">
                <div className="px-6 py-4 bg-gray-50 border-b border-gray-200">
                  <h2 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                    <span>{categoryInfo.icon}</span>
                    <span>{categoryInfo.label}</span>
                  </h2>
                </div>

                <div className="p-6 space-y-4">
                  {categorySettings.map(setting => (
                    <div key={setting.key} className="space-y-2">
                      <label className="block text-sm font-medium text-gray-700">
                        {setting.description || setting.key}
                        {setting.is_encrypted && (
                          <span className="ml-2 text-xs text-gray-500">(加密存储)</span>
                        )}
                      </label>

                      {setting.key === 'smtp_enabled' ? (
                        <select
                          value={setting.value}
                          onChange={(e) => handleChange(setting.key, e.target.value)}
                          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                        >
                          <option value="true">启用</option>
                          <option value="false">禁用</option>
                        </select>
                      ) : (
                        <input
                          type={setting.is_encrypted ? 'password' : 'text'}
                          value={setting.value}
                          onChange={(e) => handleChange(setting.key, e.target.value)}
                          placeholder={`请输入${setting.description || setting.key}`}
                          className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                        />
                      )}

                      <p className="text-xs text-gray-500">配置键：{setting.key}</p>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
