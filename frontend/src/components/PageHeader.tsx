'use client';

import type React from 'react';

interface PageHeaderProps {
  title: string;
  description?: string;
  icon?: React.ReactNode;
  meta?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}

export default function PageHeader({
  title,
  description,
  icon,
  meta,
  actions,
  className = '',
}: PageHeaderProps) {
  return (
    <header className={`shrink-0 border-b border-gray-100 bg-white/95 px-4 py-3 md:px-6 ${className}`}>
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 items-start gap-2.5">
          {icon && (
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-gray-200 bg-gray-50 text-gray-600">
              {icon}
            </span>
          )}
          <div className="min-w-0">
            <h1 className="truncate text-[15px] font-semibold leading-5 text-gray-950">{title}</h1>
            {description && <p className="mt-0.5 text-xs leading-5 text-gray-500">{description}</p>}
            {meta && <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-gray-500">{meta}</div>}
          </div>
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2 lg:justify-end">{actions}</div>}
      </div>
    </header>
  );
}
