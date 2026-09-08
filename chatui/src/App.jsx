import { useEffect, useState } from 'react';
import Sidebar from './components/Sidebar';
import PageHeader from './components/PageHeader';
import AccessGate from './components/AccessGate';
import Dashboard from './pages/Dashboard';
import Pantry from './pages/Pantry';
import WeeklyMenu from './pages/WeeklyMenu';
import TaskList from './pages/TaskList';
import Chat from './pages/Chat';
import Automations from './pages/Automations';
import Profile from './pages/Profile';
import { kitchenApi, getApiKey, setApiKey } from './services/api';

const pageMeta = {
  dashboard: ['Good morning, Alex', 'Your kitchen at a glance'],
  pantry: ['Pantry', 'Keep the good stuff moving'],
  menu: ['Weekly Menu', 'Five days, thoughtfully planned'],
  tasks: ['Task List', 'A little prep goes a long way'],
  chat: ['Chat', 'Your Executive Chef is almost ready'],
  automations: ['Automations', 'Run the autonomous agents on demand'],
  profile: ['Profile', 'Your household details'],
};

const fallback = { inventory: [], menu: [], tasks: [], shopping_items: [], consumption: [], profile: {} };

export default function App() {
  const [unlocked, setUnlocked] = useState(() => Boolean(getApiKey()));
  const [gateError, setGateError] = useState('');
  const [page, setPage] = useState('dashboard');
  const [data, setData] = useState(fallback);
  const [error, setError] = useState('');
  const [mobileNav, setMobileNav] = useState(false);
  const load = async () => {
    try {
      setError('');
      setData(await kitchenApi.getDashboard());
    } catch (requestError) {
      if (!getApiKey()) { setUnlocked(false); setGateError('That access key was not accepted.'); return; }
      setError(requestError.message);
    }
  };
  useEffect(() => { if (unlocked) load(); }, [unlocked]);
  const unlock = (key) => { setApiKey(key); setGateError(''); setUnlocked(true); };
  if (!unlocked) return <AccessGate onSubmit={unlock} error={gateError} />;
  const update = (next) => setData((current) => ({ ...current, ...next }));
  const rate = async (id, rating) => { try { const item = await kitchenApi.rateMenuItem(id, rating, ''); update({ menu: data.menu.map((entry) => entry.id === id ? item : entry) }); await load(); } catch (e) { setError(e.message); } };
  const toggle = async (task) => { if (task.is_completed) return; try { await kitchenApi.updateTask(task.id, true); await load(); } catch (e) { setError(e.message); } };
  const cancelTask = async (task) => { if (!window.confirm(`Remove "${task.task_type}" from the list? This marks it as not performed.`)) return; try { await kitchenApi.cancelTask(task.id); await load(); } catch (e) { setError(e.message); } };
  const addToShopping = async (items) => { try { await kitchenApi.addShoppingItems(items); await load(); } catch (e) { setError(e.message); } };
  const deleteShoppingItem = async (id) => { try { await kitchenApi.deleteShoppingItem(id); await load(); } catch (e) { setError(e.message); } };
  const invokePantryManager = async () => { try { setError(''); await kitchenApi.invokeAutomation('pantry_manager'); await load(); } catch (e) { setError(e.message); throw e; } };
  const acknowledgeShopping = async (purchasedItems) => { try { await kitchenApi.acknowledgeShopping(`purchase-${Date.now()}`, purchasedItems); await load(); } catch (e) { setError(e.message); } };
  const saveProfile = async (profile) => { try { setError(''); await kitchenApi.updateProfile(profile); await load(); } catch (e) { setError(e.message); throw e; } };
  const firstName = (data.profile?.name || '').trim().split(/\s+/)[0];
  const [rawTitle, eyebrow] = pageMeta[page];
  const title = page === 'dashboard' && firstName ? `Good morning, ${firstName}` : rawTitle;
  const content = { dashboard: <Dashboard data={data} navigate={setPage} />, pantry: <Pantry data={data} onAddToShopping={addToShopping} onDeleteShoppingItem={deleteShoppingItem} onInvokePantryManager={invokePantryManager} onAcknowledgeShopping={acknowledgeShopping} onRefresh={load} />, menu: <WeeklyMenu data={data} onRate={rate} onRefresh={load} />, tasks: <TaskList data={data} onToggle={toggle} onCancel={cancelTask} onRefresh={load} />, chat: <Chat />, automations: <Automations />, profile: <Profile data={data} onSave={saveProfile} /> }[page];
  return <div className="app-shell"><Sidebar page={page} onNavigate={(next) => { setPage(next); setMobileNav(false); }} open={mobileNav} /><main className="main"><PageHeader title={title} eyebrow={eyebrow} profileName={data.profile?.name} onRefresh={load} onMenu={() => setMobileNav(!mobileNav)} />{error && <div className="error-banner">Could not refresh kitchen data: {error}</div>}{content}</main></div>;
}
