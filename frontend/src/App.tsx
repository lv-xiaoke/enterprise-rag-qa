import {useEffect, useState} from 'react';
import {BrowserRouter, NavLink, Navigate, Route, Routes} from 'react-router-dom';
import {BookOpen, FileText, LogOut, MessageSquare, Sparkles} from 'lucide-react';
import {api, errorText} from './api/client';
import type {User} from './types/api';
import {Login} from './features/auth/Login';
import {Chat} from './features/chat/Chat';
import {Documents} from './features/documents/Documents';
import {Reports} from './features/reports/Reports';

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => {api<User>('/auth/me').then(setUser).catch(() => {}).finally(() => setLoading(false)); const expired=()=>setUser(null); window.addEventListener('auth-expired',expired); return()=>window.removeEventListener('auth-expired',expired);}, []);
  if(loading) return <div className="loading-page" role="status">正在打开工作空间…</div>;
  if(!user) return <Login onLogin={setUser}/>;
  return <BrowserRouter><div className="workspace"><aside className="main-nav"><a className="brand" href="/chat"><span className="brand-icon"><Sparkles size={20}/></span>知序</a><span className="nav-caption">工作空间</span><nav aria-label="主导航"><NavLink to="/chat"><MessageSquare size={18}/><span>智能问答</span></NavLink>{user.role==='admin'&&<NavLink to="/documents"><BookOpen size={18}/><span>知识文档</span></NavLink>}<NavLink to="/reports"><FileText size={18}/><span>我的周报</span></NavLink></nav><div className="nav-bottom"><div className="user-card"><span className="avatar">{user.name.slice(0,1)}</span><div><strong>{user.name}</strong><small>{user.role==='admin'?'管理员':user.employee_id}</small></div><button className="icon-button" aria-label="退出登录" onClick={async()=>{try{await api('/auth/logout',{method:'POST'});setUser(null);}catch(error){setError(errorText(error));}}}><LogOut size={17}/></button></div></div></aside><main id="main-content" className="workspace-content"><header className="workspace-topbar"><span>企业知识与事务助手</span><span className="environment-badge"><span className="small-dot"/>演示工作空间</span></header>{error&&<div className="notice error" role="alert">{error}</div>}<Routes><Route path="/chat" element={<Chat/>}/><Route path="/documents" element={user.role==='admin'?<Documents/>:<Navigate to="/chat" replace/>}/><Route path="/reports" element={<Reports/>}/><Route path="*" element={<Navigate to="/chat" replace/>}/></Routes></main></div></BrowserRouter>;
}
