'use client';

import React, { useEffect, useState } from 'react';
import { Table, Upload, Button, message, Tag, Progress, Tooltip, Popconfirm } from 'antd';
import { RefreshCwIcon, ArchiveIcon, DeleteIcon, DownloadIcon } from 'lucide-animated';
import { useRequest } from 'ahooks';
import http from '@/lib/http/axios';
import type { UploadProps } from 'antd';

const { Dragger } = Upload;

const DocumentStatusCell = ({ doc, onComplete }: { doc: any; onComplete: () => void }) => {
  const [statusInfo, setStatusInfo] = useState(doc);

  // 同步外部传入的最新 doc 状态
  useEffect(() => {
    setStatusInfo(doc);
  }, [doc]);

  useEffect(() => {
    if (doc.status === 'indexed' || doc.status === 'failed') {
      return;
    }

    const eventSource = new EventSource(`${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'}/documents/${doc.id}/progress`);

    const handleProgress = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        setStatusInfo((prev: any) => ({ ...prev, ...data }));
      } catch (err) {
        console.error('Event parsing error:', err);
      }
    };

    const handleComplete = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        setStatusInfo((prev: any) => ({ ...prev, ...data }));
        eventSource.close();
        onComplete();
      } catch (err) {
        console.error('Event parsing error:', err);
      }
    };

    const handleFailed = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        setStatusInfo((prev: any) => ({ ...prev, ...data }));
        eventSource.close();
        onComplete();
      } catch (err) {
        console.error('Event parsing error:', err);
      }
    };

    eventSource.addEventListener('progress', handleProgress);
    eventSource.addEventListener('complete', handleComplete);
    eventSource.addEventListener('failed', handleFailed);

    eventSource.onerror = (error) => {
      console.error(`EventSource error for doc ${doc.id}:`, error);
      // EventSource 会自动重连，如果需要可以在此增加重试上限逻辑
    };

    return () => {
      eventSource.close();
    };
  }, [doc.id, doc.status, onComplete]);

  const { status, progress, message: statusMsg, error_message } = statusInfo;
  
  if (status === 'indexed') {
    return <Tag color="green">已就绪</Tag>;
  }
  if (status === 'failed') {
    return (
      <Tooltip title={error_message || '解析失败'}>
        <Tag color="red">解析失败</Tag>
      </Tooltip>
    );
  }
  
  return (
    <div className="flex flex-col gap-1 w-24 md:w-32">
      <div className="flex justify-between items-center text-[10px] md:text-xs">
        <Tag color="blue" className="m-0 text-[10px] md:text-xs">{status === 'uploaded' ? '等待处理' : '处理中'}</Tag>
        <span className="text-gray-400">{progress || 0}%</span>
      </div>
      <Progress percent={progress || 0} showInfo={false} size="small" status="active" />
      <span className="text-[10px] md:text-xs text-gray-400 truncate" title={statusMsg}>{statusMsg || '正在排队...'}</span>
    </div>
  );
};

export default function KnowledgePage() {
  const [documents, setDocuments] = useState<any[]>([]);

  const { run: fetchDocuments, loading } = useRequest(async () => {
    const res: any = await http.get('/documents');
    setDocuments(res);
  });

  useEffect(() => {
    fetchDocuments();
  }, []);

  const deleteDocument = async (id: number) => {
    try {
      await http.delete(`/documents/${id}`);
      message.success('删除成功');
      fetchDocuments();
    } catch (e) {
      message.error('删除失败');
    }
  };

  const [downloadingDocs, setDownloadingDocs] = useState<Record<number, number>>({});

  const handleDownload = async (doc: any) => {
    try {
      setDownloadingDocs(prev => ({ ...prev, [doc.id]: 0 }));
      
      const data: any = await http.get(`/documents/${doc.id}/download`, {
        responseType: 'blob',
        onDownloadProgress: (progressEvent) => {
          if (progressEvent.total) {
            const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            setDownloadingDocs(prev => ({ ...prev, [doc.id]: percentCompleted }));
          } else {
            setDownloadingDocs(prev => ({ ...prev, [doc.id]: progressEvent.loaded > 0 ? 50 : 0 }));
          }
        },
      });

      const url = window.URL.createObjectURL(data);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', doc.original_filename);
      document.body.appendChild(link);
      link.click();
      link.parentNode?.removeChild(link);
      window.URL.revokeObjectURL(url);
      
      message.success(`${doc.original_filename} 下载成功`);
    } catch (e) {
      message.error(`${doc.original_filename} 下载失败`);
    } finally {
      setDownloadingDocs(prev => {
        const newState = { ...prev };
        delete newState[doc.id];
        return newState;
      });
    }
  };

  const uploadProps: UploadProps = {
    name: 'file',
    multiple: true,
    accept: '.pdf,.docx,.md,.txt',
    action: `${process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'}/upload`,
    beforeUpload: (file) => {
      const isSupported = ['.pdf', '.docx', '.md', '.txt'].some(ext => file.name.toLowerCase().endsWith(ext));
      if (!isSupported) {
        message.error(`${file.name} 格式不支持，仅支持 PDF, DOCX, MD, TXT`);
      }
      return isSupported || Upload.LIST_IGNORE;
    },
    onChange(info) {
      if (info.file.status === 'done') {
        message.success(`${info.file.name} 上传成功，正在后台解析`);
        fetchDocuments();
      } else if (info.file.status === 'error') {
        message.error(`${info.file.name} 上传失败.`);
      }
    },
  };

  const columns = [
    {
      title: '文件名',
      dataIndex: 'original_filename',
      key: 'original_filename',
    },
    {
      title: '大小',
      dataIndex: 'size_bytes',
      key: 'size_bytes',
      render: (size: number) => size ? `${(size / 1024).toFixed(2)} KB` : '-',
    },
    {
      title: '状态',
      key: 'status',
      render: (_: any, record: any) => <DocumentStatusCell doc={record} onComplete={fetchDocuments} />,
    },
    {
      title: '上传时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (date: string) => date ? new Date(date).toLocaleString() : '-',
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: any) => (
        <div className="flex gap-2 items-center">
          {downloadingDocs[record.id] !== undefined ? (
            <Progress type="circle" percent={downloadingDocs[record.id]} size={20} showInfo={false} />
          ) : (
            <Tooltip title="下载原文件">
              <div 
                className="flex items-center justify-center w-8 h-8 rounded-md hover:bg-black/5 cursor-pointer text-gray-600 transition-colors"
                onClick={() => handleDownload(record)}
              >
                <DownloadIcon size={16} />
              </div>
            </Tooltip>
          )}
          <Popconfirm
            title="确认删除该文档吗？"
            description="删除后不可恢复，对应的知识库向量也将被清理。"
            onConfirm={() => deleteDocument(record.id)}
            okText="确认"
            cancelText="取消"
          >
            <div className="flex items-center justify-center px-2 py-1 rounded-md hover:bg-red-50 cursor-pointer text-red-500 transition-colors">
              <DeleteIcon size={16} />
              <span className="ml-1 text-sm">删除</span>
            </div>
          </Popconfirm>
        </div>
      ),
    }
  ];

  const renderMobileCard = (doc: any) => (
    <div key={doc.id} className="bg-white p-4 rounded-xl border border-gray-100 shadow-sm flex flex-col gap-3">
      <div className="flex justify-between items-start">
        <div className="font-medium text-gray-800 break-all pr-2 text-sm">{doc.original_filename}</div>
        <div className="flex items-center gap-1 shrink-0 -mt-1 -mr-2">
          {downloadingDocs[doc.id] !== undefined ? (
            <div className="mr-2">
              <Progress type="circle" percent={downloadingDocs[doc.id]} size={20} showInfo={false} />
            </div>
          ) : (
            <div 
              className="flex items-center justify-center w-6 h-6 rounded-md hover:bg-black/5 cursor-pointer text-gray-600 transition-colors"
              onClick={() => handleDownload(doc)}
            >
              <DownloadIcon size={14} />
            </div>
          )}
          <Popconfirm
            title="确认删除？"
            onConfirm={() => deleteDocument(doc.id)}
            okText="确认"
            cancelText="取消"
          >
            <div className="flex items-center justify-center w-6 h-6 rounded-md hover:bg-red-50 cursor-pointer text-red-500 transition-colors">
              <DeleteIcon size={14} />
            </div>
          </Popconfirm>
        </div>
      </div>
      <div className="flex justify-between items-end">
        <div className="text-xs text-gray-400 flex flex-col gap-1">
          <span>{doc.size_bytes ? `${(doc.size_bytes / 1024).toFixed(2)} KB` : '-'}</span>
          <span>{doc.created_at ? new Date(doc.created_at).toLocaleString() : '-'}</span>
        </div>
        <div>
          <DocumentStatusCell doc={doc} onComplete={fetchDocuments} />
        </div>
      </div>
    </div>
  );

  return (
    <div className="p-4 md:p-6 h-full flex flex-col bg-gray-50/50">
      <div className="flex justify-between items-center mb-4 md:mb-6">
        <h1 className="text-xl md:text-2xl font-bold text-gray-800">知识库管理</h1>
        <div 
          onClick={loading ? undefined : fetchDocuments}
          className={`flex items-center gap-1.5 px-3 md:px-4 h-7 md:h-8 rounded-md bg-[#1677ff] hover:bg-[#4096ff] text-white cursor-pointer transition-colors text-sm ${loading ? 'opacity-70 cursor-not-allowed' : ''}`}
        >
          <RefreshCwIcon size={16} className={loading ? 'animate-spin' : ''} />
          <span>刷新状态</span>
        </div>
      </div>
      
      <div className="mb-4 md:mb-6 bg-white rounded-xl overflow-hidden shadow-sm border border-gray-100 p-2">
        <Dragger {...uploadProps} showUploadList={false} className="py-2 md:py-8">
          <div className="ant-upload-drag-icon text-blue-500 mb-2 md:mb-4 flex justify-center">
            <ArchiveIcon className="w-8 h-8 md:w-12 md:h-12" />
          </div>
          <p className="ant-upload-text font-medium text-gray-700 text-sm md:text-base">点击或将文件拖拽到这里上传</p>
          <p className="ant-upload-hint text-gray-400 text-xs md:text-sm mt-1">
            支持 PDF, DOCX, MD, TXT
          </p>
        </Dragger>
      </div>

      <div className="flex-1 overflow-auto">
        {/* Desktop Table */}
        <div className="hidden md:block bg-white rounded-xl p-2 border border-gray-100 shadow-sm h-full">
          <Table 
            columns={columns} 
            dataSource={documents} 
            rowKey="id" 
            loading={loading}
            pagination={{ pageSize: 10 }}
            scroll={{ x: 'max-content' }}
          />
        </div>
        
        {/* Mobile List */}
        <div className="md:hidden flex flex-col gap-3 pb-6">
          {documents.map(renderMobileCard)}
          {documents.length === 0 && !loading && (
            <div className="text-center py-10 text-gray-400 text-sm bg-white rounded-xl border border-gray-100">
              暂无文档
            </div>
          )}
          {loading && documents.length === 0 && (
            <div className="text-center py-10 text-gray-400 text-sm bg-white rounded-xl border border-gray-100">
              加载中...
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
