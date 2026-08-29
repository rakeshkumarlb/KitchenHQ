import { useEffect, useRef, useState } from 'react';
import { ArrowUp, Bot, LoaderCircle, RotateCcw } from 'lucide-react';
import { kitchenApi } from '../services/api';

const SESSION_KEY = 'kitchenhq.chat.session';

function getSessionId() {
	const saved = window.localStorage.getItem(SESSION_KEY);
	if (saved) return saved;
	const sessionId = crypto.randomUUID();
	window.localStorage.setItem(SESSION_KEY, sessionId);
	return sessionId;
}

export default function Chat() {
	const [sessionId] = useState(getSessionId);
	const [messages, setMessages] = useState([]);
	const [draft, setDraft] = useState('');
	const [sending, setSending] = useState(false);
	const [error, setError] = useState('');
	const inputRef = useRef(null);

	useEffect(() => inputRef.current?.focus(), []);

	const send = async (event) => {
		event.preventDefault();
		const message = draft.trim();
		if (!message || sending) return;
		setDraft('');
		setError('');
		setMessages((current) => [...current, { role: 'user', content: message }]);
		setSending(true);
		try {
			const response = await kitchenApi.chat(message, sessionId);
			setMessages((current) => [...current, { role: 'assistant', content: response.reply }]);
		} catch (requestError) {
			setError(requestError.message);
		} finally {
			setSending(false);
			inputRef.current?.focus();
		}
	};

	return <div className="chat-page page-content">
		<div className="chat-placeholder">
			<div className="chat-orb"><Bot size={30} /></div>
			<p className="eyebrow">Your kitchen intelligence</p>
			<h2>Chat with your<br /><em>Executive Chef.</em></h2>
			{!messages.length && <p className="chat-copy">Ask about recipes, substitutions, meal plans, or how to use what is already in your pantry.</p>}
		</div>
		{messages.length > 0 && <section className="chat-transcript" aria-live="polite">{messages.map((item, index) => <article className={`chat-message ${item.role}`} key={`${item.role}-${index}`}><span>{item.role === 'assistant' ? 'Executive Chef' : 'You'}</span><p>{item.content}</p></article>)}{sending && <div className="chat-message assistant"><span>Executive Chef</span><p className="chat-thinking"><LoaderCircle size={15} /> Thinking...</p></div>}</section>}
		{error && <div className="chat-error" role="alert"><span>{error}</span><button type="button" onClick={() => setError('')} aria-label="Dismiss error"><RotateCcw size={15} /></button></div>}
		<form className="chat-composer soft-inset" onSubmit={send}><input ref={inputRef} value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Ask anything about your kitchen..." maxLength={4000} aria-label="Message Executive Chef" disabled={sending} /><button type="submit" disabled={!draft.trim() || sending} aria-label="Send message">{sending ? <LoaderCircle className="spin" size={18} /> : <ArrowUp size={18} />}</button></form>
	</div>;
}
