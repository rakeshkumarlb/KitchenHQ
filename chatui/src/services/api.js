const API_KEY_STORAGE_KEY = 'kitchenhq.api_key';

export const getApiKey = () => window.localStorage.getItem(API_KEY_STORAGE_KEY) || '';
export const setApiKey = (key) => window.localStorage.setItem(API_KEY_STORAGE_KEY, key);
export const clearApiKey = () => window.localStorage.removeItem(API_KEY_STORAGE_KEY);

const request = async (path, options = {}) => {
  const response = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json', 'X-API-Key': getApiKey(), ...options.headers },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401) clearApiKey();
    throw new Error(data.detail || 'Kitchen service unavailable');
  }
  return data;
};

export const kitchenApi = {
  getDashboard: () => request('/dashboard'),
  getProfile: () => request('/profile'),
  updateProfile: (profile) => request('/profile', { method: 'PUT', body: JSON.stringify(profile) }),
  addHouseholdMember: (member) => request('/household-members', { method: 'POST', body: JSON.stringify(member) }),
  updateHouseholdMember: (id, member) => request(`/household-members/${id}`, { method: 'PUT', body: JSON.stringify(member) }),
  deleteHouseholdMember: (id) => request(`/household-members/${id}`, { method: 'DELETE' }),
  chat: (message, sessionId) => request('/chat', { method: 'POST', body: JSON.stringify({ message, ...(sessionId ? { session_id: sessionId } : {}) }) }),
  listChatSessions: () => request('/chat-sessions'),
  getChatSession: (sessionId) => request(`/chat-sessions/${sessionId}`),
  // soft-deleted: no caller, and chatui/app.py never proxied these. The dbmcp
  // routes POST /api/weekly-menu/{validate,plan} are commented out too.
  // validateMenu: (menuItems) => request('/weekly-menu/validate', { method: 'POST', body: JSON.stringify({ menu_items: menuItems }) }),
  // saveMenuPlan: (menuItems) => request('/weekly-menu/plan', { method: 'POST', body: JSON.stringify({ menu_items: menuItems }) }),
  addShoppingItems: (items) => request('/shopping-items', { method: 'POST', body: JSON.stringify({ items }) }),
  deleteShoppingItem: (id) => request(`/shopping-items/${id}`, { method: 'DELETE' }),
  acknowledgeShopping: (acknowledgementKey, purchasedItems) => request('/shopping-items/acknowledge', { method: 'POST', body: JSON.stringify({ acknowledgement_key: acknowledgementKey, purchased_items: purchasedItems }) }),
  updateTask: (id, isCompleted, humanNotes = '') => request(`/prep-schedule/${id}/completion`, { method: 'PATCH', body: JSON.stringify({ is_completed: isCompleted, human_notes: humanNotes }) }),
  cancelTask: (id, humanNotes = '') => request(`/prep-schedule/${id}/cancel`, { method: 'POST', body: JSON.stringify({ human_notes: humanNotes }) }),
  listAutomationJobs: () => request('/automations/jobs'),
  listAutomationRuns: () => request('/automations/runs'),
  invokeAutomation: (jobName) => request(`/automations/invoke/${jobName}`, { method: 'POST' }),
};
