const request = async (path, options = {}) => {
  const response = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || 'Kitchen service unavailable');
  return data;
};

export const kitchenApi = {
  getDashboard: () => request('/dashboard'),
  chat: (message, sessionId) => request('/chat', { method: 'POST', body: JSON.stringify({ message, ...(sessionId ? { session_id: sessionId } : {}) }) }),
  validateMenu: (menuItems) => request('/weekly-menu/validate', { method: 'POST', body: JSON.stringify({ menu_items: menuItems }) }),
  saveMenuPlan: (menuItems) => request('/weekly-menu/plan', { method: 'POST', body: JSON.stringify({ menu_items: menuItems }) }),
  createShoppingList: (items) => request('/shopping-lists', { method: 'POST', body: JSON.stringify({ items }) }),
  acknowledgeShopping: (id, acknowledgementKey, purchasedItems) => request(`/shopping-lists/${id}/acknowledge`, { method: 'POST', body: JSON.stringify({ acknowledgement_key: acknowledgementKey, purchased_items: purchasedItems }) }),
  adjustInventory: (id, quantityChange) => request(`/inventory/${id}`, { method: 'PATCH', body: JSON.stringify({ quantity_change: quantityChange }) }),
  discardInventory: (id, quantity, reason) => request(`/inventory/${id}/discard`, { method: 'POST', body: JSON.stringify({ quantity, reason }) }),
  rateMenuItem: (id, kidRating, humanFeedback) => request(`/weekly-menu/${id}/rating`, { method: 'POST', body: JSON.stringify({ kid_rating: kidRating, human_feedback: humanFeedback }) }),
  updateTask: (id, isCompleted, humanNotes = '') => request(`/prep-schedule/${id}/completion`, { method: 'PATCH', body: JSON.stringify({ is_completed: isCompleted, human_notes: humanNotes }) }),
};
