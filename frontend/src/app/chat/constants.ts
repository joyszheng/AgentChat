import { ChatMode } from './types';

export const CHAT_MODE_OPTIONS: { label: string; value: ChatMode }[] = [
  { label: '智能助手', value: 'auto' },
  { label: '大模型问答', value: 'chat' },
  { label: '知识库', value: 'rag' },
  { label: 'MCP 工具', value: 'mcp' },
];

export const MODE_PLACEHOLDER: Record<ChatMode, string> = {
  auto: '直接提问，智能选择知识库或工具...',
  chat: '请输入问题...',
  rag: '向知识库提问...',
  mcp: '问我需要调用 MCP 工具的问题...',
};
