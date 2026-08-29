import { useEffect, useState } from 'react';
import Sidebar from './components/Sidebar';
import PageHeader from './components/PageHeader';
import Dashboard from './pages/Dashboard';
import Pantry from './pages/Pantry';
import WeeklyMenu from './pages/WeeklyMenu';
import TaskList from './pages/TaskList';
import Chat from './pages/Chat';
import { kitchenApi } from './services/api';

const pageMeta = {
  dashboard: ['Good morning, Alex', 'Your kitchen at a glance'],
  pantry: ['Pantry', 'Keep the good stuff moving'],
  menu: ['Weekly Menu', 'Five days, thoughtfully planned'],
  tasks: ['Task List', 'A little prep goes a long way'],
  chat: ['Chat', 'Your Executive Chef is almost ready'],
};

const fallback = { inventory: [], menu: [], tasks: [], shopping_lists: [] };

export default function App() {
  const [page, setPage] = useState('dashboard');
  const [data, setData] = useState(fallback);
  const [error, setError] = useState('');
  const [mobileNav, setMobileNav] = useState(false);
  const load = async () => { try { setError(''); setData(await kitchenApi.getDashboard()); } catch (requestError) { setError(requestError.message); } };
  useEffect(() => { load(); }, []);
  const update = (next) => setData((current) => ({ ...current, ...next }));
  const adjust = async (id, change) => { try { const item = await kitchenApi.adjustInventory(id, change); update({ inventory: data.inventory.map((entry) => entry.id === id ? item : entry) }); } catch (e) { setError(e.message); } };
  const discard = async (item) => { const amount = Number(prompt(`How much ${item.item_name} should be discarded?`, '1')); if (!amount) return; try { const updated = await kitchenApi.discardInventory(item.id, amount, 'Pantry check'); update({ inventory: data.inventory.map((entry) => entry.id === item.id ? updated : entry) }); } catch (e) { setError(e.message); } };
  const rate = async (id, rating) => { try { const item = await kitchenApi.rateMenuItem(id, rating, ''); update({ menu: data.menu.map((entry) => entry.id === id ? item : entry) }); } catch (e) { setError(e.message); } };
  const toggle = async (task) => { try { const updated = await kitchenApi.updateTask(task.id, !task.is_completed); update({ tasks: data.tasks.map((entry) => entry.id === task.id ? updated : entry) }); } catch (e) { setError(e.message); } };
  const suggestShopping = async (items) => { try { await kitchenApi.createShoppingList(items); await load(); } catch (e) { setError(e.message); } };
  const acknowledgeShopping = async (id, purchasedItems) => { try { await kitchenApi.acknowledgeShopping(id, `purchase-${id}-${Date.now()}`, purchasedItems); await load(); } catch (e) { setError(e.message); } };
  const [title, eyebrow] = pageMeta[page];
  const content = { dashboard: <Dashboard data={data} navigate={setPage} />, pantry: <Pantry data={data} onAdjust={adjust} onDiscard={discard} onSuggestShopping={suggestShopping} onAcknowledgeShopping={acknowledgeShopping} />, menu: <WeeklyMenu data={data} onRate={rate} />, tasks: <TaskList data={data} onToggle={toggle} />, chat: <Chat /> }[page];
  return <div className="app-shell"><Sidebar page={page} onNavigate={(next) => { setPage(next); setMobileNav(false); }} open={mobileNav} /><main className="main"><PageHeader title={title} eyebrow={eyebrow} onRefresh={load} onMenu={() => setMobileNav(!mobileNav)} />{error && <div className="error-banner">Could not refresh kitchen data: {error}</div>}{content}</main></div>;
}
