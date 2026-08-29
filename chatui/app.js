const conversation = document.querySelector('#conversation');
const form = document.querySelector('#chat-form');
const input = document.querySelector('#message');
const connectionText = document.querySelector('#connection-text');
const pageTitle = document.querySelector('#page-title');
const pageEyebrow = document.querySelector('#page-eyebrow');
const pageNames = {
  chat: ['KITCHENHQ / COMMAND CENTER', 'Executive Chef'],
  menu: ['KITCHENHQ / WEEKLY MENU', 'Weekly Menu'],
  tasks: ['KITCHENHQ / PREP SCHEDULE', 'Tasks'],
};

function showPage(page) {
  document.querySelectorAll('.page-view').forEach((view) => view.classList.toggle('active', view.id === `${page}-page`));
  document.querySelectorAll('.nav-item').forEach((item) => item.classList.toggle('active', item.dataset.page === page));
  [pageEyebrow.textContent, pageTitle.textContent] = pageNames[page];
}

function addMessage(role, text) {
  const message = document.createElement('div');
  message.className = `message ${role}`;
  const label = document.createElement('div');
  label.className = 'message-label';
  label.textContent = role === 'user' ? 'YOU' : 'CHEF';
  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  bubble.textContent = text;
  message.append(role === 'user' ? bubble : label, role === 'user' ? label : bubble);
  conversation.append(message);
  message.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

async function sendMessage(text) {
  const clean = text.trim();
  if (!clean) return;
  document.querySelector('.welcome')?.remove();
  addMessage('user', clean);
  input.value = '';
  input.disabled = true;
  connectionText.textContent = 'Chef is thinking';
  try {
    const response = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message: clean }) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'The chef could not respond.');
    addMessage('assistant', data.reply);
    connectionText.textContent = 'Connected';
  } catch (error) {
    addMessage('assistant', `I could not reach the kitchen service. ${error.message}`);
    connectionText.textContent = 'Service issue';
  } finally {
    input.disabled = false;
    input.focus();
  }
}

form.addEventListener('submit', (event) => { event.preventDefault(); sendMessage(input.value); });
input.addEventListener('keydown', (event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); form.requestSubmit(); } });
document.querySelectorAll('.nav-item').forEach((button) => button.addEventListener('click', () => showPage(button.dataset.page)));
document.querySelectorAll('[data-prompt]').forEach((button) => button.addEventListener('click', () => {
  showPage('chat');
  sendMessage(button.dataset.prompt);
}));

fetch('/api/health').then((response) => { if (response.ok) connectionText.textContent = 'Connected'; }).catch(() => { connectionText.textContent = 'Offline'; });
