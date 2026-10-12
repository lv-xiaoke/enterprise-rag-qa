export type User = {id: string; username: string; name: string; role: 'employee' | 'admin'; employee_id: string | null};
export type RunStatus = 'running' | 'completed' | 'failed' | 'cancelled' | 'interrupted';
export type Source = {document_id: string; version_id: string; chunk_id: string; title: string; page: number | null; excerpt: string};
export type Message = {id: string; role: 'user' | 'assistant'; content: string; status: RunStatus; sources: Source[]};
export type Conversation = {id: string; title: string; updated_at: number};
export type Page<T> = {items: T[]; total: number};
export type ChatEvent =
  | {type: 'start'; run_id: string; conversation_id: string}
  | {type: 'token'; content: string}
  | {type: 'tool_call'; name: string; args: Record<string, unknown>}
  | {type: 'tool_result'; name: string; content: string}
  | {type: 'sources'; sources: Source[]}
  | {type: 'error'; code: string; message: string}
  | {type: 'done'; run_id: string; status: RunStatus};
