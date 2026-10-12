import {useEffect, useState, type FormEvent} from 'react';
import {useLocation} from 'react-router-dom';
import {FileText, Plus, Save, Trash2} from 'lucide-react';
import {api, errorText, jsonBody} from '../../api/client';
import type {Page} from '../../types/api';
type Report = {id: string; title: string; content: string; updated_at: number};
export function Reports() {
  const location = useLocation();
  const [page, setPage] = useState<Page<Report>>({items:[], total:0});
  const [offset, setOffset] = useState(0);
  const [id, setId] = useState<string | null>(null);
  const [title, setTitle] = useState('本周工作周报');
  const [content, setContent] = useState<string>(location.state?.draft ?? '');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const refresh = async () => setPage(await api(`/weekly-reports?limit=20&offset=${offset}`));
  useEffect(() => {refresh().catch(e => setError(errorText(e)));}, [offset]);
  async function save(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setNotice('');
    try {const row = await api<Report>(id ? `/weekly-reports/${id}` : '/weekly-reports', {method: id ? 'PATCH':'POST', body:jsonBody({title,content})}); setId(row.id); setNotice('周报已保存'); await refresh();}
    catch(error) {setError(errorText(error));} finally {setBusy(false);}
  }
  async function remove() {
    if(!id || !window.confirm('删除这份周报？')) return;
    try {await api(`/weekly-reports/${id}`, {method:'DELETE'}); setId(null); setContent(''); setNotice('周报已删除'); await refresh();}
    catch(error) {setError(errorText(error));}
  }
  return <section className="page-content"><header className="page-heading"><div><span className="section-tag">我的工作成果</span><h1>把一周的进展，整理成清晰的记录。</h1><p className="muted">从聊天中生成草稿，在这里编辑、确认并保存。</p></div><FileText size={28}/></header>
    {error && <div role="alert" className="notice error">{error}</div>}{notice && <div role="status" className="notice success">{notice}</div>}
    <div className="reports-layout"><aside className="report-list"><button className="secondary" onClick={() => {setId(null); setTitle('本周工作周报'); setContent(''); setNotice('');}}><Plus size={16}/> 新建周报</button>{page.items.map(row => <button key={row.id} className={`report-item ${id === row.id ? 'selected' : ''}`} onClick={() => {setId(row.id); setTitle(row.title); setContent(row.content); setNotice('');}}><FileText size={17}/><span>{row.title}<small>{new Date(row.updated_at*1000).toLocaleDateString('zh-CN')}</small></span></button>)}{!page.items.length && <p className="muted">保存的周报会显示在这里。</p>}<div className="pagination"><button disabled={!offset} onClick={() => setOffset(Math.max(0,offset-20))}>上一页</button><button disabled={offset+20>=page.total} onClick={() => setOffset(offset+20)}>下一页</button></div></aside>
    <form className="report-editor" onSubmit={save}><label>周报标题<input aria-label="周报标题" value={title} onChange={e => setTitle(e.target.value)} maxLength={120} required/></label><label>正文<textarea aria-label="周报正文" value={content} onChange={e => setContent(e.target.value)} maxLength={50000} placeholder="可以从对话中的回答创建草稿，也可以直接记录你的工作。" required/></label><footer><span className="muted">请核实内容后保存。</span><div>{id && <button type="button" className="text-button danger" onClick={remove}><Trash2 size={15}/> 删除</button>}<button className="primary" disabled={busy}><Save size={15}/>{busy?'保存中…':'保存周报'}</button></div></footer></form></div>
  </section>;
}
