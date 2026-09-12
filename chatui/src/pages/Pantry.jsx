import { useState } from 'react';
import { Check, LayoutGrid, LoaderCircle, Plus, RefreshCw, ShoppingCart, Sparkles, Store, TrendingDown, X } from 'lucide-react';

const TABS = [
  { id: 'store', label: 'Store', icon: Store },
  { id: 'shopping', label: 'Shopping List', icon: ShoppingCart },
  { id: 'consumption', label: 'Weekly Consumption', icon: TrendingDown },
];
const TILE_TONES = ['green', 'coral', 'yellow', 'blue'];

export default function Pantry({ data, onAcknowledgeShopping, onAddToShopping, onDeleteShoppingItem, onInvokePantryManager, onRefresh }) {
  const shoppingItems = data.shopping_items || [];
  const consumption = data.consumption || [];
  const consumptionPeak = consumption.reduce((max, row) => Math.max(max, row.quantity_consumed), 0);
  const [quantities, setQuantities] = useState({});
  const [refreshing, setRefreshing] = useState(false);
  const [asking, setAsking] = useState(false);
  const [form, setForm] = useState({ item_name: '', proposed_quantity: '', unit: '' });
  const [activeTab, setActiveTab] = useState('store');
  const [activeCategory, setActiveCategory] = useState(null);

  const refresh = async () => {
    if (refreshing) return;
    setRefreshing(true);
    try { await onRefresh?.(); } finally { setRefreshing(false); }
  };
  const askPantryManager = async () => {
    if (asking) return;
    setAsking(true);
    try { await onInvokePantryManager?.(); } catch { /* error surfaces in the page banner */ } finally { setAsking(false); }
  };
  const updateQuantity = (id, value) => setQuantities((current) => ({ ...current, [id]: value }));
  const formQuantity = Number(form.proposed_quantity);
  const canSubmit = form.item_name.trim() && formQuantity > 0;
  const submitItem = (event) => {
    event.preventDefault();
    if (!canSubmit) return;
    onAddToShopping([{ item_name: form.item_name.trim(), proposed_quantity: formQuantity, unit: form.unit.trim() || 'pcs' }]);
    setForm({ item_name: '', proposed_quantity: '', unit: '' });
  };

  const categories = [...new Set(data.inventory.map((item) => item.category))];
  const shownCategories = activeCategory ? categories.filter((category) => category === activeCategory) : categories;

  return <div className="page-content">
    <div className="page-lead">
      <div><p className="eyebrow">The fresh shelf</p><h2>Pantry, <em>in hand.</em></h2><p>Stock only ever changes when a shopping list is acknowledged. Ask the Pantry Manager or add items yourself, then confirm what was bought.</p></div>
      <div className="page-lead-actions">
        <button className="secondary-button" onClick={refresh} disabled={refreshing}><RefreshCw className={refreshing ? 'spin' : undefined} size={16} /> {refreshing ? 'Refreshing...' : 'Refresh'}</button>
        <div className="stock-total soft-inset"><strong>{data.inventory.length}</strong><span>items in stock</span></div>
      </div>
    </div>

    <nav className="pantry-tabs soft-inset">
      {TABS.map(({ id, label, icon: Icon }) => <button key={id} type="button" className={activeTab === id ? 'active' : ''} onClick={() => setActiveTab(id)}><Icon size={15} strokeWidth={1.8} /> {label}</button>)}
    </nav>

    {activeTab === 'shopping' && <>
      <section className="shopping-panel soft-outset">
        <div className="section-heading compact"><h3><Sparkles size={16} /> Pantry Manager suggestions</h3><span>Agent-built proposal</span></div>
        <p className="shopping-intro">The Pantry Manager checks current stock against the upcoming menu and drafts a shopping list. It never changes inventory on its own.</p>
        <button className="shopping-confirm" onClick={askPantryManager} disabled={asking}>{asking ? <LoaderCircle className="spin" size={15} /> : <Sparkles size={15} />} {asking ? 'Asking the Pantry Manager...' : 'Ask the Pantry Manager'}</button>
      </section>

      <section className="shopping-panel soft-outset">
        <div className="section-heading compact"><h3><Plus size={16} /> Add to shopping list</h3><span>Merges into what's already pending</span></div>
        <form className="shopping-add" onSubmit={submitItem}>
          <input type="text" placeholder="Item name" value={form.item_name} onChange={(event) => setForm((current) => ({ ...current, item_name: event.target.value }))} aria-label="Item name" />
          <input type="number" min="0" step="any" placeholder="Qty" value={form.proposed_quantity} onChange={(event) => setForm((current) => ({ ...current, proposed_quantity: event.target.value }))} aria-label="Quantity" />
          <input type="text" placeholder="Unit" value={form.unit} onChange={(event) => setForm((current) => ({ ...current, unit: event.target.value }))} aria-label="Unit" />
          <button type="submit" className="shopping-confirm" disabled={!canSubmit}><Plus size={15} /> Add</button>
        </form>
      </section>

      <section className="shopping-panel soft-outset">
        <div className="section-heading compact"><h3><ShoppingCart size={16} /> Shopping list</h3><span>Enter what was actually bought</span></div>
        {shoppingItems.length ? <>
          {shoppingItems.map((item) => <div className="shopping-row" key={item.id}>
            <div><b>{item.item_name}</b><small>Suggested {item.proposed_quantity} {item.unit}</small></div>
            <input type="number" min="0" step="any" value={quantities[item.id] ?? item.proposed_quantity} onChange={(event) => updateQuantity(item.id, event.target.value)} aria-label={`Purchased quantity for ${item.item_name}`} />
            <span>{item.unit}</span>
            <button className="task-cancel" onClick={() => onDeleteShoppingItem(item.id)} aria-label={`Remove ${item.item_name} from the list`} title="Not needed - remove from list"><X size={15} /></button>
          </div>)}
          <button className="shopping-confirm" onClick={() => onAcknowledgeShopping(shoppingItems.map((item) => ({ shopping_item_id: item.id, actual_quantity: Number(quantities[item.id] ?? item.proposed_quantity) })))}><Check size={15} /> Acknowledge purchase</button>
        </> : <p className="shopping-empty">The shopping list is empty. Add an item above, or ask the Pantry Manager.</p>}
      </section>
    </>}

    {activeTab === 'consumption' && <section className="table-section">
      <div className="section-heading compact"><h3><TrendingDown size={16} /> This week's consumption</h3><span>Last 7 days</span></div>
      <div className="pantry-list soft-outset">
        {consumption.length ? consumption.map((row) => <div className="consumption-row" key={row.inventory_id}>
          <div className="ingredient-name"><b>{row.item_name}</b><small>{row.transaction_count} prep {row.transaction_count === 1 ? 'deduction' : 'deductions'}</small></div>
          <div className="consumption-bar"><span style={{ width: `${consumptionPeak ? Math.max(Math.round((row.quantity_consumed / consumptionPeak) * 100), 4) : 0}%` }} /></div>
          <div className="stock-level"><strong>{row.quantity_consumed}</strong><span>{row.unit}</span></div>
        </div>) : <div className="consumption-empty">Nothing was consumed from the pantry in the last 7 days.</div>}
      </div>
    </section>}

    {activeTab === 'store' && <>
      <div className="category-tiles">
        <button type="button" className={`category-tile green ${!activeCategory ? 'active' : ''}`} onClick={() => setActiveCategory(null)}>
          <span className="category-tile-icon"><LayoutGrid size={16} /></span>
          <strong>{data.inventory.length}</strong>
          <span>All items</span>
        </button>
        {categories.map((category, index) => {
          const items = data.inventory.filter((item) => item.category === category);
          const lowCount = items.filter((item) => item.quantity <= item.minimum_threshold).length;
          return <button type="button" key={category} className={`category-tile ${TILE_TONES[index % TILE_TONES.length]} ${activeCategory === category ? 'active' : ''}`} onClick={() => setActiveCategory(activeCategory === category ? null : category)}>
            <span className="category-tile-icon">{category.charAt(0).toUpperCase()}</span>
            <strong>{items.length}</strong>
            <span>{category}{lowCount > 0 ? ` · ${lowCount} low` : ''}</span>
          </button>;
        })}
      </div>

      {shownCategories.map((category) => <section className="table-section" key={category}>
        {!activeCategory && <div className="section-heading compact"><h3>{category}</h3><span>{data.inventory.filter((item) => item.category === category).length} items</span></div>}
        <div className="pantry-list soft-outset">
          {data.inventory.filter((item) => item.category === category).map((item) => {
            const low = item.quantity <= item.minimum_threshold;
            return <div className="pantry-row read-only compact" key={item.id}>
              <div className="ingredient-name"><b>{item.item_name}</b><small>Reorder threshold {item.minimum_threshold} {item.unit}</small></div>
              <div className={`stock-level ${low ? 'low' : ''}`}><strong>{item.quantity}</strong><span>{item.unit}{low && ' · low stock'}</span></div>
            </div>;
          })}
        </div>
      </section>)}
    </>}
  </div>;
}
