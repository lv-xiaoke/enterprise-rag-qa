import {useEffect, useRef, useState, type FormEvent} from 'react';
import {useNavigate} from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import {ArrowUp, BookOpen, FileText, MessageSquare, Plus, Square, Trash2, X, Sparkles} from 'lucide-react';
import {api, request, jsonBody, errorText} from '../../api/client';
import {parseSSE} from '../../api/chat-stream';
import type {Conversation, Message, Page, Source} from '../../types/api';

const suggestions = ['年假和请假流程有哪些规定？', '我的报销目前是什么状态？', '根据我的项目记录生成本周周报'];
const toolNames: Record<string, string> = {rag_summarize: '检索知识文档', get_employee_id: '确认当前员工', get_employee_department: '查询所属部门', fetch_employee_records: '查询个人记录', generate_weekly_report_context: '整理周报要求'};

export function Chat() {
  const navigate = useNavigate();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [total, setTotal] = useState(0);
  const [active, setActive] = useState<string | null>(null);
  const activeRef = useRef<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [olderOffset, setOlderOffset] = useState(0);
  const [prompt, setPrompt] = useState('');
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [error, setError] = useState('');
  const [trace, setTrace] = useState<string[]>([]);
  const [source, setSource] = useState<{title: string; content: string; historical: boolean} | null>(null);
  const control = useRef<AbortController | null>(null);
  const runId = useRef<string | null>(null);
  const end = useRef<HTMLDivElement>(null);

  async function refresh() {
    const page = await api<Page<Conversation>>('/conversations?limit=100');
    setConversations(page.items); setTotal(page.total);
  }
  useEffect(() => { refresh().catch(e => setError(errorText(e))); return () => { control.current?.abort(); }; }, []);
  useEffect(() => { end.current?.scrollIntoView({behavior: 'auto'}); }, [messages]);

  async function stop() {
    try { if (runId.current) await api(`/chat-runs/${runId.current}/cancel`, {method: 'POST'}); }
    catch (error) { setError(errorText(error)); }
    finally { control.current?.abort(); }
  }
  async function load(id: string) {
    if (busyRef.current) await stop();
    activeRef.current = id; setActive(id); setMessages([]); setTrace([]); setError('');
    try {
      const head = await api<Page<Message>>(`/conversations/${id}/messages?limit=100`);
      const offset = Math.max(0, head.total - 100);
      const page = offset ? await api<Page<Message>>(`/conversations/${id}/messages?limit=100&offset=${offset}`) : head;
      if (activeRef.current === id) { setMessages(page.items); setOlderOffset(offset); }
    } catch (error) { setError(errorText(error)); }
  }
  async function create() {
    if (busyRef.current) await stop();
    const conversation = await api<Conversation>('/conversations', {method: 'POST', body: '{}'});
    await refresh(); await load(conversation.id);
    return conversation.id;
  }
  async function send(event: FormEvent) {
    event.preventDefault();
    if (!prompt.trim() || busyRef.current) return;
    setError('');
    const question = prompt.trim();
    let id = activeRef.current;
    try { if (!id) id = await create(); } catch (error) { setError(errorText(error)); return; }
    busyRef.current = true; setBusy(true); setPrompt(''); setTrace([]);
    const assistantId = crypto.randomUUID();
    setMessages(previous => [...previous,
      {id: crypto.randomUUID(), role: 'user', content: question, status: 'completed', sources: []},
      {id: assistantId, role: 'assistant', content: '', status: 'running', sources: []},
    ]);
    const controller = new AbortController(); control.current = controller; runId.current = null;
    let ended = false;
    const update = (patch: Partial<Message> | ((message: Message) => Partial<Message>)) => {
      if (activeRef.current !== id) return;
      setMessages(previous => previous.map(message => message.id === assistantId ? {...message, ...(typeof patch === 'function' ? patch(message) : patch)} : message));
    };
    try {
      const response = await request(`/conversations/${id}/chat`, {method: 'POST',
        body: jsonBody({message: question, client_request_id: crypto.randomUUID()}), signal: controller.signal});
      if (!response.body) throw new Error('浏览器未收到响应流');
      for await (const event of parseSSE(response.body)) {
        if (event.type === 'start') runId.current = event.run_id;
        if (event.type === 'token') update(message => ({content: message.content + event.content}));
        if (event.type === 'tool_call' && activeRef.current === id) setTrace(previous => [...previous, toolNames[event.name] ?? event.name]);
        if (event.type === 'sources') update({sources: event.sources});
        if (event.type === 'error' && activeRef.current === id) setError(event.message);
        if (event.type === 'done') { ended = true; update({status: event.status}); }
      }
      if (!ended) throw new Error('连接提前结束，请查看历史状态后重试');
    } catch (error) {
      const aborted = error instanceof DOMException && error.name === 'AbortError';
      update({status: aborted ? 'cancelled' : 'failed'});
      if (!aborted && activeRef.current === id) { setError(errorText(error)); setPrompt(question); }
    } finally {
      busyRef.current = false; setBusy(false); runId.current = null;
      refresh().catch(e => setError(errorText(e)));
    }
  }
  async function openSource(item: Source) {
    try { setSource(await api(`/sources/${item.version_id}/${item.chunk_id}`)); }
    catch (error) { setError(errorText(error)); }
  }
  async function clear() {
    if (!active || !window.confirm('清空当前会话的全部消息？')) return;
    try { await api(`/conversations/${active}/messages`, {method: 'DELETE'}); setMessages([]); setTrace([]); }
    catch (error) { setError(errorText(error)); }
  }
  return <div className="chat-layout"><aside className="conversation-panel">
    <button className="primary new-chat" onClick={() => create().catch(e => setError(errorText(e)))}><Plus size={17}/> 新建对话</button>
    <p className="list-caption">最近对话 <span>{total}</span></p>
    {conversations.map(item => <button key={item.id} className={`conversation ${active === item.id ? 'selected' : ''}`} onClick={() => load(item.id)}><MessageSquare size={16}/><span>{item.title}</span></button>)}
    {total > conversations.length && <button className="text-button" onClick={async () => {try {
      const page = await api<Page<Conversation>>(`/conversations?limit=100&offset=${conversations.length}`);
      setConversations(previous => [...previous, ...page.items]);
    } catch (error) {setError(errorText(error));}}}>加载更多对话</button>}
    <div className="sidebar-note"><ShieldNote/>个人事务仅限本人访问</div>
  </aside><section className="chat-main"><header className="chat-heading"><div><span className="section-tag">AI 工作伙伴</span><h1>{conversations.find(item => item.id === active)?.title ?? '知识与工作，在这里连接'}</h1></div><button className="icon-button" aria-label="清空当前会话" title="清空当前会话" disabled={!active || busy} onClick={clear}><Trash2 size={17}/></button></header>
    <div className="messages">
      {olderOffset > 0 && <button className="text-button" onClick={async () => {if (!active) return; try {
        const offset = Math.max(0, olderOffset - 100);
        const page = await api<Page<Message>>(`/conversations/${active}/messages?limit=${olderOffset - offset}&offset=${offset}`);
        setMessages(previous => [...page.items, ...previous]); setOlderOffset(offset);
      } catch (error) {setError(errorText(error));}}}>加载较早消息</button>}
      {!messages.length && <div className="welcome"><span className="welcome-symbol"><Sparkles size={28}/></span><p className="eyebrow">一个问题，开启更有序的工作</p><h2>今天，有什么想了解的？</h2><p className="muted">查制度、看个人事务，或整理本周的工作成果。</p><div className="suggestions">{suggestions.map((text, index) => <button key={text} onClick={() => setPrompt(text)}><span>{['知识问答', '个人事务', '周报助手'][index]}</span>{text}<ArrowUp size={16}/></button>)}</div></div>}
      {messages.map(message => <article key={message.id} className={`message ${message.role}`}><div className="message-label">{message.role === 'user' ? '你' : <><Sparkles size={15}/>知序</>}</div><div className="message-body"><ReactMarkdown skipHtml>{message.content || (message.status === 'running' ? '正在整理你的问题…' : '本次没有生成正文。')}</ReactMarkdown></div>
        {message.role === 'assistant' && <><div className="sources">{message.sources.map((item, index) => <button key={item.chunk_id} onClick={() => openSource(item)}><BookOpen size={13}/> {index + 1}. {item.title}</button>)}</div><div className="message-actions"><span>{({running: '生成中', completed: '已完成', failed: '生成失败', cancelled: '已停止', interrupted: '服务重启中断'})[message.status]}</span>{message.content && message.status !== 'running' && <button onClick={() => navigate('/reports', {state: {draft: message.content}})}><FileText size={13}/> 编辑并保存为周报</button>}</div></>}
      </article>)}
      {busy && trace.length > 0 && <div className="tool-trace" role="status">{trace.join(' → ')}</div>}<div ref={end}/>
    </div><div className="composer-area">{error && <div className="notice error" role="alert">{error}</div>}<form className="composer" onSubmit={send}><textarea aria-label="输入问题" placeholder="向知序提问，或描述你需要完成的工作…" value={prompt} maxLength={2000} onChange={e => setPrompt(e.target.value)} onKeyDown={e => {if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {e.preventDefault(); e.currentTarget.form?.requestSubmit();}}}/><div className="composer-footer"><span>Enter 发送 · Shift + Enter 换行</span>{busy ? <button type="button" className="stop-button" onClick={stop}><Square size={13}/> 停止生成</button> : <button className="send-button" aria-label="发送问题" disabled={!prompt.trim()}><ArrowUp size={19}/></button>}</div></form><p className="composer-disclaimer">回答请结合引用核实 · 个人业务记录为模拟数据</p></div>
  </section>{source && <div className="modal-backdrop" onClick={() => setSource(null)}><section role="dialog" aria-modal="true" aria-label="引用原文" className="source-dialog" onClick={e => e.stopPropagation()} onKeyDown={e => {if (e.key === 'Escape') setSource(null);}}><header><div><span className="section-tag">引用依据{source.historical ? ' · 历史版本' : ''}</span><h2>{source.title}</h2></div><button autoFocus className="icon-button" aria-label="关闭引用" onClick={() => setSource(null)}><X size={19}/></button></header><p>{source.content}</p></section></div>}</div>;
}
function ShieldNote() {return <span className="small-dot"/>;}
