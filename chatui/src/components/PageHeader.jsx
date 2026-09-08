import { Bell, Menu, RefreshCw } from 'lucide-react';

export default function PageHeader({ title, eyebrow, profileName, onRefresh, onMenu }) {
  const name = (profileName || '').trim() || 'Alex Kim';
  const initials = name.split(/\s+/).map((part) => part[0]).slice(0, 2).join('').toUpperCase() || 'AK';
  return <header className="page-header"><button className="mobile-menu icon-button" onClick={onMenu} aria-label="Open navigation"><Menu size={20} /></button><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1></div><div className="header-actions"><button className="icon-button" onClick={onRefresh} title="Refresh data" aria-label="Refresh data"><RefreshCw size={18} /></button><button className="icon-button" title="Notifications" aria-label="Notifications"><Bell size={18} /></button><div className="profile"><span className="avatar">{initials}</span><span><b>{name}</b><small>Head of home</small></span></div></div></header>;
}
