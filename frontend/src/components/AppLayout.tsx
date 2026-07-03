'use client';

import React, { useState, useEffect, useRef } from 'react';
import { MessageSquareIcon, BookTextIcon, PanelLeftCloseIcon, PanelLeftOpenIcon, SettingsIcon, LogoutIcon, UserIcon } from 'lucide-animated';
import type { MessageSquareIconHandle, BookTextIconHandle, SettingsIconHandle } from 'lucide-animated';
import { useRouter, usePathname } from 'next/navigation';
import { isAuthenticated, isAdmin, getCurrentUser, logout } from '@/lib/auth';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const [mounted, setMounted] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [authState, setAuthState] = useState({
    isLoggedIn: false,
    isAdminUser: false,
    username: '',
  });
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    setMounted(true);
    // 检查登录状态
    setAuthState({
      isLoggedIn: isAuthenticated(),
      isAdminUser: isAdmin(),
      username: getCurrentUser()?.username || '',
    });
  }, [pathname]);

  const menuItems = [
    {
      key: '/chat',
      IconComponent: MessageSquareIcon,
      label: 'AI 问答',
      requireAuth: false,
    },
    {
      key: '/knowledge',
      IconComponent: BookTextIcon,
      label: '知识库管理',
      requireAuth: false,
    },
    {
      key: '/settings',
      IconComponent: SettingsIcon,
      label: '系统设置',
      requireAuth: true,
      requireAdmin: true,
    }
  ];

  const iconRefs = useRef<{ [key: string]: any }>({});

  // 过滤菜单项：只显示有权限的菜单
  const visibleMenuItems = menuItems.filter(item => {
    if (item.requireAdmin && !authState.isAdminUser) {
      return false;
    }
    return true;
  });

  if (!mounted) {
    return <div className="h-screen w-screen bg-gray-50" />;
  }

  return (
    <div className="flex flex-col md:flex-row h-screen w-full bg-gray-50 md:bg-gray-100 overflow-hidden text-sm">
      {/* Desktop Sidebar */}
      <div className={`hidden md:flex flex-col bg-gray-900 text-white shadow-xl z-20 transition-all duration-300 ${collapsed ? 'w-20' : 'w-64'}`}>
        <div className="h-16 flex items-center justify-center font-bold text-xl cursor-pointer hover:text-blue-400 transition-colors overflow-hidden whitespace-nowrap" onClick={() => router.push('/')}>
          {collapsed ? 'AC' : 'AgentChat'}
        </div>
        <div className="flex-1 py-4 flex flex-col gap-2 px-3 overflow-y-auto overflow-x-hidden">
          {visibleMenuItems.map(item => {
            const isActive = pathname === item.key;
            return (
              <div
                key={item.key}
                onClick={() => router.push(item.key)}
                onMouseEnter={() => {
                  const icon = iconRefs.current[item.key];
                  if (icon) {
                    icon.stopAnimation?.();
                    setTimeout(() => icon.startAnimation?.(), 10);
                  }
                }}
                onMouseLeave={() => iconRefs.current[item.key]?.stopAnimation?.()}
                className={`flex items-center ${collapsed ? 'justify-center' : 'gap-3 px-4'} py-3 rounded-lg cursor-pointer transition-all duration-200 ${isActive ? 'bg-blue-600 text-white shadow-md' : 'text-gray-300 hover:bg-gray-800 hover:text-white'}`}
                title={collapsed ? item.label : undefined}
              >
                <item.IconComponent
                  ref={(el: any) => iconRefs.current[item.key] = el}
                  size={20}
                />
                {!collapsed && <span className="font-medium truncate">{item.label}</span>}
              </div>
            );
          })}
        </div>

        {/* User Info / Login */}
        {!collapsed && (
          <div className="border-t border-gray-800 px-3 py-3">
            {authState.isLoggedIn ? (
              <div className="flex items-center justify-between text-gray-300">
                <div className="flex items-center gap-2 min-w-0">
                  <UserIcon size={18} className="shrink-0" />
                  <span className="text-sm truncate">{authState.username}</span>
                </div>
                <button
                  onClick={logout}
                  className="shrink-0 p-1.5 hover:bg-gray-800 rounded transition-colors"
                  title="登出"
                >
                  <LogoutIcon size={18} />
                </button>
              </div>
            ) : (
              <button
                onClick={() => router.push('/login')}
                className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors text-white"
              >
                <UserIcon size={18} />
                <span>登录</span>
              </button>
            )}
          </div>
        )}

        {/* Collapse Button */}
        <div
          className="h-12 border-t border-gray-800 flex items-center justify-center cursor-pointer hover:bg-gray-800 transition-colors text-gray-400 hover:text-white shrink-0"
          onClick={() => setCollapsed(!collapsed)}
        >
          {collapsed ? <PanelLeftOpenIcon size={20} /> : <PanelLeftCloseIcon size={20} />}
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden relative">
        <main className="flex-1 overflow-hidden relative flex flex-col md:p-4 pb-0">
          <div className="flex-1 bg-white md:rounded-xl shadow-none md:shadow-sm overflow-hidden flex flex-col relative z-10">
            {children}
          </div>
        </main>
        
        {/* Mobile Bottom Navigation */}
        <div className="md:hidden flex bg-white border-t border-gray-100 pb-[env(safe-area-inset-bottom)] shadow-[0_-2px_10px_rgba(0,0,0,0.03)] z-50">
          {menuItems.map(item => {
            const isActive = pathname === item.key;
            return (
              <div
                key={item.key}
                onClick={() => router.push(item.key)}
                className={`flex-1 flex flex-col items-center justify-center py-2 gap-1 cursor-pointer transition-colors ${isActive ? 'text-blue-600' : 'text-gray-400'}`}
              >
                <div className={`p-1 rounded-full ${isActive ? 'bg-blue-50' : ''}`}>
                  <item.IconComponent size={22} />
                </div>
                <span className="text-[10px] font-medium leading-none">{item.label}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
