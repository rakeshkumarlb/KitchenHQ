import { Bell, Menu, RefreshCw } from 'lucide-react';

export default function PageHeader({ title, eyebrow, onRefresh, onMenu }) {
  return <header className="page-header"><button className="mobile-menu icon-button" onClick={onMenu} aria-label="Open navigation"><Menu size={20} /></button><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1></div><div className="header-actions"><button className="icon-button" onClick={onRefresh} title="Refresh data" aria-label="Refresh data"><RefreshCw size={18} /></button><button className="icon-button" title="Notifications" aria-label="Notifications"><Bell size={18} /></button><div className="profile"><span className="avatar">AK</span><span><b>Alex Kim</b><small>Head of home</small></span></div></div></header>;
}
