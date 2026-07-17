export type ChatMode = 'auto' | 'chat' | 'rag' | 'mcp';
export type ToolCallStatus = 'running' | 'completed' | 'failed';

export interface ToolCallState {
  name: string;
  status: ToolCallStatus;
}

export interface ChatMessageItem {
  id: string;
  role: string;
  content: string;
  sources?: string[];
  toolsUsed?: string[];
  toolCalls?: ToolCallState[];
  mode?: ChatMode;
  route?: string;
  loading?: boolean;
  streamStatus?: string;
}

export interface ChatSessionItem {
  id: number;
  title?: string | null;
  updated_at?: string | null;
}

export interface ApiChatMessage {
  id: number;
  role: string;
  content: string;
  message_metadata?: {
    model?: string;
    route?: string;
    sources?: string[];
    tools_used?: string[];
  };
}

export interface MCPAssistantResponse {
  answer: string;
  session_id: number;
  tools_used?: string[];
}
