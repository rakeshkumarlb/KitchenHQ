import { ChefHat, ClipboardCheck, LayoutDashboard, MessageCircle, Package, Soup } from 'lucide-react';

const navItems = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'pantry', label: 'Pantry', icon: Package },
  { id: 'menu', label: 'Weekly Menu', icon: Soup },
  { id: 'tasks', label: 'Task List', icon: ClipboardCheck },
  { id: 'chat', label: 'Chat', icon: MessageCircle },
];

export default function Sidebar({ page, onNavigate, open }) {
  return <aside className={`sidebar ${open ? 'is-open' : ''}`}>
    <div className="logo"><span className="logo-mark"><ChefHat size={19} /></span><span>KITCHEN<span className="logo-light">HQ</span></span></div>
    <div className="workspace-card soft-inset"><span className="avatar">EC</span><span><b>Executive kitchen</b><small>Home workspace</small></span><span className="online-dot" /></div>
    <p className="nav-label">Workspace</p>
    <nav>{navItems.map(({ id, label, icon: Icon }) => <button key={id} className={`nav-link ${page === id ? 'active' : ''}`} onClick={() => onNavigate(id)}><Icon size={18} strokeWidth={1.8} /><span>{label}</span>{id === 'tasks' && <em>2</em>}</button>)}</nav>
    <div className="sidebar-note soft-outset"><span className="spark">✦</span><div><b>Kitchen rhythm</b><small>Plan, prep, enjoy.</small></div></div>
    <div className="sidebar-foot"><span className="online-dot" /> Systems connected</div>
  </aside>;
}
