import { useEffect, useMemo, useState } from 'react';
import { Check, LoaderCircle, Save, Star } from 'lucide-react';

const parseFavorites = (raw) => {
  try {
    const value = typeof raw === 'string' ? JSON.parse(raw || '[]') : raw;
    return Array.isArray(value) ? value.filter((entry) => entry && entry.dish_name) : [];
  } catch {
    return [];
  }
};

const formatDate = (value) => {
  if (!value) return '';
  const date = new Date(value.includes('T') ? value : value.replace(' ', 'T') + 'Z');
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
};

export default function Profile({ data, onSave }) {
  const profile = data.profile || {};
  const [form, setForm] = useState({ name: '', email: '', cc_emails: '', notes: '', notify_on_task_creation: true });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setForm({
      name: profile.name || '',
      email: profile.email || '',
      cc_emails: profile.cc_emails || '',
      notes: profile.notes || '',
      notify_on_task_creation: profile.notify_on_task_creation == null ? true : Boolean(profile.notify_on_task_creation),
    });
  }, [profile.name, profile.email, profile.cc_emails, profile.notes, profile.notify_on_task_creation]);

  const favorites = useMemo(() => parseFavorites(profile.favorite_recipes), [profile.favorite_recipes]);

  const set = (key, value) => { setForm((current) => ({ ...current, [key]: value })); setSaved(false); };
  const emailInvalid = form.email.trim() && !form.email.includes('@');

  const submit = async (event) => {
    event.preventDefault();
    if (saving || emailInvalid) return;
    setSaving(true);
    try { await onSave(form); setSaved(true); } catch { /* error surfaces in the page banner */ } finally { setSaving(false); }
  };

  return <div className="page-content">
    <div className="page-lead"><div><p className="eyebrow">Household</p><h2>Your <em>profile.</em></h2><p>Who the kitchen is planning for, and where prep-task alerts are sent.</p></div></div>
    <form className="profile-form soft-outset" onSubmit={submit}>
      <label className="profile-field"><span>Name</span>
        <input type="text" value={form.name} onChange={(event) => set('name', event.target.value)} placeholder="Alex Kim" />
      </label>
      <label className="profile-field"><span>Email for task alerts</span>
        <input type="email" value={form.email} onChange={(event) => set('email', event.target.value)} placeholder="you@example.com" />
      </label>
      <label className="profile-field"><span>Also copy (cc)</span>
        <textarea rows={2} value={form.cc_emails} onChange={(event) => set('cc_emails', event.target.value)} placeholder="partner@example.com, nanny@example.com" />
        <small className="profile-hint">Comma-separated. Everyone here is cc'd on every prep-task alert.</small>
      </label>
      <label className="profile-field"><span>Note for the chef</span>
        <textarea rows={3} value={form.notes} onChange={(event) => set('notes', event.target.value)} placeholder="Dietary notes, household size, dishes to lean on or avoid" />
        <small className="profile-hint">Shared with the Executive Chef as context when the weekly menu is planned.</small>
      </label>
      <label className="profile-toggle">
        <input type="checkbox" checked={form.notify_on_task_creation} onChange={(event) => set('notify_on_task_creation', event.target.checked)} />
        <span>Email me whenever the Sous Chef plans a new prep task</span>
      </label>
      {emailInvalid && <p className="profile-hint">Enter a valid email address to receive alerts.</p>}
      <button type="submit" className="shopping-confirm" disabled={saving || emailInvalid}>
        {saving ? <LoaderCircle className="spin" size={15} /> : saved ? <Check size={15} /> : <Save size={15} />}
        {saving ? 'Saving...' : saved ? 'Saved' : 'Save profile'}
      </button>
    </form>

    <section className="profile-favorites soft-outset">
      <div className="profile-favorites-head">
        <h3>Top 10 favourite recipes</h3>
        <span>Kept from the most recent 4- and 5-star ratings on the weekly menu.</span>
      </div>
      {favorites.length ? <ol className="favorite-list">
        {favorites.map((entry, index) => <li key={`${entry.dish_name}-${index}`}>
          <span className="favorite-rank">{String(index + 1).padStart(2, '0')}</span>
          <span className="favorite-name">{entry.dish_name}</span>
          <span className="favorite-stars">{Array.from({ length: Math.min(5, Math.max(0, entry.rating || 0)) }).map((_, star) => <Star key={star} size={12} fill="currentColor" />)}</span>
          <span className="favorite-date">{formatDate(entry.rated_at)}</span>
        </li>)}
      </ol> : <div className="empty-state">No rated favourites yet. Star a dish 4 or 5 on the weekly menu to build this list.</div>}
    </section>
  </div>;
}
