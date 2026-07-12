'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { LockKeyholeIcon, UserIcon } from 'lucide-animated';
import axios from 'axios';
import http from '@/lib/http/axios';

const DEFAULT_LOGIN_USERNAME = process.env.NEXT_PUBLIC_DEFAULT_LOGIN_USERNAME || 'admin';
const DEFAULT_LOGIN_PASSWORD = process.env.NEXT_PUBLIC_DEFAULT_LOGIN_PASSWORD || 'admin123';

interface LoginResponse {
  access_token: string;
  user: unknown;
}

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState(DEFAULT_LOGIN_USERNAME);
  const [password, setPassword] = useState(DEFAULT_LOGIN_PASSWORD);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const response = await http.post<LoginResponse, LoginResponse>('/auth/login', {
        username,
        password,
      });

      const { access_token, user } = response;

      // 保存 token 和用户信息到 localStorage
      localStorage.setItem('access_token', access_token);
      localStorage.setItem('user', JSON.stringify(user));

      // 跳转到首页
      router.push('/chat');
    } catch (err: unknown) {
      console.error('Login failed:', err);
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : undefined;
      setError(typeof detail === 'string' ? detail : '登录失败，请检查用户名和密码');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100 px-4">
      <div className="w-full max-w-md">
        {/* Logo 和标题 */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-blue-600 rounded-2xl mb-4">
            <LockKeyholeIcon size={32} className="text-white" />
          </div>
          <h1 className="text-3xl font-bold text-gray-900 mb-2">欢迎回来</h1>
          <p className="text-gray-600">登录 AgentChat 管理系统</p>
        </div>

        {/* 登录表单 */}
        <div className="bg-white rounded-2xl shadow-xl p-8">
          <form onSubmit={handleLogin} className="space-y-6">
            {/* 错误提示 */}
            {error && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-800 text-sm">
                {error}
              </div>
            )}

            {/* 用户名 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                用户名
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <UserIcon size={20} className="text-gray-400" />
                </div>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  className="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="请输入用户名"
                  disabled={loading}
                />
              </div>
            </div>

            {/* 密码 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                密码
              </label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <LockKeyholeIcon size={20} className="text-gray-400" />
                </div>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  placeholder="请输入密码"
                  disabled={loading}
                />
              </div>
            </div>

            {/* 登录按钮 */}
            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium"
            >
              {loading ? (
                <span>登录中...</span>
              ) : (
                <>
                  <UserIcon size={20} />
                  <span>登录</span>
                </>
              )}
            </button>
          </form>

          {/* 提示信息 */}
          <div className="mt-6 text-center text-sm text-gray-600">
            <p>默认管理员账号</p>
            <p className="mt-1 text-xs text-gray-500">
              用户名: <span className="font-mono text-blue-600">admin</span> /
              密码: <span className="font-mono text-blue-600">admin123</span>
            </p>
          </div>
        </div>

        {/* 返回首页 */}
        <div className="text-center mt-6">
          <button
            onClick={() => router.push('/chat')}
            className="text-gray-600 hover:text-gray-900 text-sm"
          >
            返回首页 →
          </button>
        </div>
      </div>
    </div>
  );
}
