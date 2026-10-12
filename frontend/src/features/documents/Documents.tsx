import {useEffect, useRef, useState, type FormEvent} from 'react';
import {BookOpen, FileUp, RefreshCw, Upload} from 'lucide-react';
import {api, errorText, jsonBody} from '../../api/client';
import type {Page} from '../../types/api';
type Version = {id: string; number: number; status: string; error_code: string | null};
type Document = {id: string; title: string; enabled: boolean; versions: Version[]; active_version_id: string | null};
const statuses: Record<string, string> = {queued: '等待处理', processing: '正在处理', ready: '处理完成', failed: '处理失败'};
export function Documents() {
  const [page, setPage] = useState<Page<Document>>({items: [], total: 0});
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  async function refresh() {setPage(await api(`/documents?limit=20&offset=${offset}`));}
  useEffect(() => {refresh().catch(e => setError(errorText(e))); const timer = window.setInterval(() => {refresh().catch(e => setError(errorText(e)));}, 3000); return () => clearInterval(timer);}, [offset]);
  async function upload(file: File, id?: string) {
    if (file.size > 10 * 1024 * 1024) {setError('文件不能超过 10 MiB'); return;}
    setBusy(true); setError('');
    const body = new FormData(); body.append('file', file);
    try {await api(id ? `/documents/${id}/versions` : '/documents', {method: 'POST', body}); await refresh();}
    catch (error) {setError(errorText(error));} finally {setBusy(false); if(input.current) input.current.value = '';}
  }
  async function action(path: string, options: RequestInit) {
    setError(''); try {await api(path, options); await refresh();} catch(error) {setError(errorText(error));}
  }
  function submit(event: FormEvent) {event.preventDefault(); const file = input.current?.files?.[0]; if(file) upload(file);}
  return <section className="page-content"><header className="page-heading"><div><span className="section-tag">知识库管理</span><h1>让每一次回答，都有可靠依据。</h1><p className="muted">上传与维护企业文档，更新成功后自动启用新版本。</p></div><BookOpen size={28}/></header>
    {error && <div role="alert" className="notice error">{error}</div>}
    <form onSubmit={submit} className="upload-card"><div className="upload-symbol"><FileUp size={28}/></div><div><h2>添加知识文档</h2><p className="muted">TXT / PDF · 最大 10 MiB · 扫描版 PDF 暂不支持</p><label className="file-label">选择文档<input aria-label="选择知识文档" ref={input} type="file" accept=".txt,.pdf" required/></label></div><button className="primary" disabled={busy}><Upload size={16}/>{busy ? '上传中…' : '上传并处理'}</button></form>
    <div className="table-heading"><h2>全部文档 <span>{page.total}</span></h2><button className="text-button" onClick={() => refresh().catch(e => setError(errorText(e)))}><RefreshCw size={15}/> 刷新</button></div>
    <div className="document-list">{!page.items.length && <div className="empty-card">还没有知识文档。上传第一份制度或流程说明，开始构建知识库。</div>}{page.items.map(item => {const latest = item.versions.at(-1); const pending = latest && ['queued','processing'].includes(latest.status); return <article key={item.id} className="document-row"><span className="document-icon"><BookOpen size={20}/></span><div className="document-detail"><h3>{item.title}</h3><p className="muted">{latest ? `版本 ${latest.number} · ${statuses[latest.status] ?? latest.status}` : '尚无版本'}{!item.enabled && ' · 已停用'}{item.active_version_id && latest?.id !== item.active_version_id && ' · 旧版继续生效'}</p>{latest?.error_code && <p className="inline-error">{({INVALID_UTF8:'请使用 UTF-8 编码保存 TXT', EMPTY_TEXT:'没有可提取文本，请上传文本版文档', INTERRUPTED:'处理被服务重启中断，可以重试', INGEST_FAILED:'处理失败，请检查向量模型配置后重试'})[latest.error_code] ?? latest.error_code}</p>}</div><div className="row-actions"><label className={`button secondary ${pending || busy ? 'disabled' : ''}`}><Upload size={14}/> 更新<input aria-label={`更新 ${item.title}`} type="file" accept=".txt,.pdf" disabled={!!pending || busy} hidden onChange={e => {const file = e.target.files?.[0]; if(file) upload(file, item.id); e.target.value = '';}}/></label>{latest?.status === 'failed' && <button className="secondary" onClick={() => action(`/documents/${item.id}/retry`, {method:'POST'})}>重试</button>}<button className="text-button" onClick={() => action(`/documents/${item.id}`, {method:'PATCH', body:jsonBody({enabled:!item.enabled})})}>{item.enabled ? '停用' : '启用'}</button></div></article>;})}</div>
    <div className="pagination"><button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))}>上一页</button><span>{Math.floor(offset / 20) + 1}</span><button disabled={offset + 20 >= page.total} onClick={() => setOffset(offset + 20)}>下一页</button></div>
  </section>;
}
