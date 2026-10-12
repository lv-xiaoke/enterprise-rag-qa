import {useState, type FormEvent} from 'react';
import {ArrowRight, BookOpen, ShieldCheck, Sparkles} from 'lucide-react';
import {api, errorText, jsonBody} from '../../api/client';
import type {User} from '../../types/api';

export function Login({onLogin}: {onLogin: (user: User) => void}) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError('');
    try { onLogin(await api<User>('/auth/login', {method: 'POST', body: jsonBody({username, password})})); }
    catch (error) { setError(errorText(error)); }
    finally { setBusy(false); }
  }
  return <main className="login-shell"><section className="login-intro">
    <div className="brand"><span className="brand-icon"><Sparkles size={21}/></span>知序 <span className="brand-en">WORKSPACE</span></div>
    <div><p className="eyebrow">让知识，连接每一天的工作</p><h1>少一点查找。<br/>多一点专注。</h1><p className="intro-copy">企业制度、个人事务与工作周报，<br/>在一个有据可循的工作空间里完成。</p></div>
    <div className="intro-features"><span><BookOpen size={18}/> 回答有依据</span><span><ShieldCheck size={18}/> 数据有边界</span></div>
  </section><section className="login-panel"><form onSubmit={submit} className="login-form">
    <span className="section-tag">欢迎回来</span><h2>登录你的工作空间</h2><p className="muted">使用已初始化的员工或管理员账号。</p>
    <label>账号<input name="username" autoComplete="username" required maxLength={80} value={username} onChange={e => setUsername(e.target.value)} placeholder="例如 E1001"/></label>
    <label>密码<input name="password" type="password" autoComplete="current-password" required maxLength={256} value={password} onChange={e => setPassword(e.target.value)}/></label>
    {error && <div role="alert" className="notice error">{error}</div>}
    <button className="primary" disabled={busy}>{busy ? '正在登录…' : '进入工作空间'}<ArrowRight size={18}/></button>
    <p className="fine-print">演示项目 · 员工记录均为模拟数据</p>
  </form></section></main>;
}
