import { useState } from 'react';
import { Check, Minus, Plus, ShoppingCart, Sparkles, Trash2 } from 'lucide-react';

export default function Pantry({ data, onAdjust, onDiscard, onSuggestShopping, onAcknowledgeShopping }) {
  const openList = data.shopping_lists?.find((list) => list.status !== 'purchased');
  const [quantities, setQuantities] = useState({});
  const [selectedSuggestions, setSelectedSuggestions] = useState([]);
  const shoppingItems = openList?.items || [];
  const suggestedItems = data.inventory.filter((item) => item.quantity <= item.minimum_threshold && !shoppingItems.some((shoppingItem) => shoppingItem.item_name.toLowerCase() === item.item_name.toLowerCase()));
  const categories = [...new Set(data.inventory.map((item) => item.category))];
  const updateQuantity = (id, value) => setQuantities((current) => ({ ...current, [id]: value }));
  const toggleSuggestion = (item) => setSelectedSuggestions((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id]);
  const proposedQuantity = (item) => Math.max(item.minimum_threshold * 2 - item.quantity, 1);
  const createSuggestion = () => {
    const items = suggestedItems.filter((item) => selectedSuggestions.includes(item.id)).map((item) => ({ item_name: item.item_name, proposed_quantity: proposedQuantity(item), unit: item.unit }));
    if (items.length) onSuggestShopping(items);
  };

  return <div className="page-content">
    <div className="page-lead"><div><p className="eyebrow">The fresh shelf</p><h2>Pantry, <em>in hand.</em></h2><p>Know what you have, use what is freshest, and keep waste visible.</p></div><div className="stock-total soft-inset"><strong>{data.inventory.length}</strong><span>items in stock</span></div></div>
    {!openList && <section className="shopping-panel suggestion-panel soft-outset"><div className="section-heading compact"><h3><Sparkles size={16} /> Shopping suggestions</h3><span>{suggestedItems.length} low-stock items</span></div>{suggestedItems.length ? <><p className="shopping-intro">Build a proposal from ingredients that need attention.</p>{suggestedItems.map((item) => <label className="shopping-suggestion" key={item.id}><input type="checkbox" checked={selectedSuggestions.includes(item.id)} onChange={() => toggleSuggestion(item)} /><span><b>{item.item_name}</b><small>{item.quantity} {item.unit} left · threshold {item.minimum_threshold}</small></span><strong>{proposedQuantity(item)} {item.unit}</strong></label>)}<button className="shopping-confirm" disabled={!selectedSuggestions.length} onClick={createSuggestion}><ShoppingCart size={15} /> Create shopping list</button></> : <p className="shopping-empty">There are no items in your shopping list suggestions right now.</p>}</section>}
    {openList && <section className="shopping-panel soft-outset"><div className="section-heading compact"><h3><ShoppingCart size={16} /> Shopping list</h3><span>Review actual purchases</span></div>{shoppingItems.length ? <>{shoppingItems.map((item) => <div className="shopping-row" key={item.id}><div><b>{item.item_name}</b><small>Suggested {item.proposed_quantity} {item.unit}</small></div><input type="number" min="0" step="any" value={quantities[item.id] ?? item.proposed_quantity} onChange={(event) => updateQuantity(item.id, event.target.value)} aria-label={`Purchased quantity for ${item.item_name}`} /><span>{item.unit}</span></div>)}<button className="shopping-confirm" onClick={() => onAcknowledgeShopping(openList.id, shoppingItems.map((item) => ({ shopping_item_id: item.id, actual_quantity: Number(quantities[item.id] ?? item.proposed_quantity) })))}><Check size={15} /> Acknowledge purchase</button></> : <p className="shopping-empty">There are no items in your shopping list yet.</p>}</section>}
    {categories.map((category) => <section className="table-section" key={category}><div className="section-heading compact"><h3>{category}</h3><span>{data.inventory.filter((item) => item.category === category).length} items</span></div><div className="pantry-list soft-outset">{data.inventory.filter((item) => item.category === category).map((item) => { const low = item.quantity <= item.minimum_threshold; return <div className="pantry-row" key={item.id}><div className="ingredient-mark">{item.item_name.slice(0, 1)}</div><div className="ingredient-name"><b>{item.item_name}</b><small>Updated just now</small></div><div className={`stock-level ${low ? 'low' : ''}`}><strong>{item.quantity}</strong><span>{item.unit}{low && ' · low stock'}</span></div><div className="quantity-actions"><button onClick={() => onAdjust(item.id, -1)} aria-label={`Decrease ${item.item_name}`}><Minus size={15} /></button><button onClick={() => onAdjust(item.id, 1)} aria-label={`Increase ${item.item_name}`}><Plus size={15} /></button><button className="discard-button" onClick={() => onDiscard(item)} aria-label={`Discard ${item.item_name}`}><Trash2 size={15} /></button></div></div>; })}</div></section>)}
  </div>;
}
