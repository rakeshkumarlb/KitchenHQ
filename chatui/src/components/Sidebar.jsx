import { ChefHat, ClipboardCheck, LayoutDashboard, MessageCircle, Package, PanelLeftClose, PanelLeftOpen, Soup, UserRound, Workflow } from 'lucide-react';

const navItems = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'pantry', label: 'Pantry', icon: Package },
  { id: 'menu', label: 'Weekly Menu', icon: Soup },
  { id: 'tasks', label: 'Task List', icon: ClipboardCheck },
  { id: 'chat', label: 'Chat', icon: MessageCircle },
  { id: 'automations', label: 'Automations', icon: Workflow },
  { id: 'profile', label: 'Profile', icon: UserRound },
];

export default function Sidebar({ page, onNavigate, open, collapsed, onToggleCollapse }) {
  return <aside className={`sidebar ${open ? 'is-open' : ''} ${collapsed ? 'is-collapsed' : ''}`}>
    <div className="sidebar-top">
      <div className="logo"><span className="logo-mark"><ChefHat size={19} /></span><span className="logo-text">KITCHEN<span className="logo-light">HQ</span></span></div>
      <button type="button" className="collapse-toggle" onClick={onToggleCollapse} aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'} title={collapsed ? 'Expand navigation' : 'Collapse navigation'}>
        {collapsed ? <PanelLeftOpen size={16} strokeWidth={1.8} /> : <PanelLeftClose size={16} strokeWidth={1.8} />}
      </button>
    </div>
    <p className="nav-label">Workspace</p>
    <nav>{navItems.map(({ id, label, icon: Icon }) => <button key={id} className={`nav-link ${page === id ? 'active' : ''}`} onClick={() => onNavigate(id)} title={label}><Icon size={18} strokeWidth={1.8} /><span>{label}</span></button>)}</nav>
    <div className="sidebar-foot"><span className="online-dot" /> <span className="sidebar-foot-text">Systems connected</span></div>
  </aside>;
}
