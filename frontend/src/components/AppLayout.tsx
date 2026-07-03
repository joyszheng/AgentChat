'use client';

import React, { useState, useEffect } from 'react';
import { MessageSquareIcon, BookTextIcon, PanelLeftCloseIcon, PanelLeftOpenIcon } from 'lucide-animated';
import { useRouter, usePathname } from 'next/navigation';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const [mounted, setMounted] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    setMounted(true);
  }, []);

  const menuItems = [
    {
      key: '/chat',
      icon: <MessageSquareIcon size={20} />,
      label: 'AI 问答',
    },
    {
      key: '/knowledge',
      icon: <BookTextIcon size={20} />,
      label: '知识库管理',
    }
  ];

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
          {menuItems.map(item => {
            const isActive = pathname === item.key;
            return (
              <div 
                key={item.key}
                onClick={() => router.push(item.key)}
                className={`flex items-center ${collapsed ? 'justify-center' : 'gap-3 px-4'} py-3 rounded-lg cursor-pointer transition-all duration-200 ${isActive ? 'bg-blue-600 text-white shadow-md' : 'text-gray-300 hover:bg-gray-800 hover:text-white'}`}
                title={collapsed ? item.label : undefined}
              >
                <div className="shrink-0">{item.icon}</div>
                {!collapsed && <span className="font-medium truncate">{item.label}</span>}
              </div>
            );
          })}
        </div>
        
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
                  {React.cloneElement(item.icon, { size: 22 })}
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
