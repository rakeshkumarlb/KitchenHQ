import { useEffect, useMemo, useState } from 'react';
import { Check, LoaderCircle, Pencil, Plus, Save, Star, Trash2 } from 'lucide-react';

const splitTags = (value) => value.split(',').map((part) => part.trim()).filter(Boolean);
const joinTags = (value) => (value || []).join(', ');

function MemberRow({ member, onUpdate, onDelete }) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(() => ({ name: member.name, preferences: joinTags(member.dietary_preferences), conditions: joinTags(member.health_conditions) }));
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (!form.name.trim() || saving) return;
    setSaving(true);
    try {
      await onUpdate(member.id, { name: form.name.trim(), dietary_preferences: splitTags(form.preferences), health_conditions: splitTags(form.conditions) });
      setEditing(false);
    } finally { setSaving(false); }
  };

  if (editing) {
    return <div className="household-member soft-inset">
      <input type="text" value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} placeholder="Name" />
      <input type="text" value={form.preferences} onChange={(event) => setForm((current) => ({ ...current, preferences: event.target.value }))} placeholder="Dietary preferences" />
      <input type="text" value={form.conditions} onChange={(event) => setForm((current) => ({ ...current, conditions: event.target.value }))} placeholder="Health conditions" />
      <button type="button" className="icon-button member-remove" onClick={save} disabled={saving} aria-label="Save member">{saving ? <LoaderCircle className="spin" size={15} /> : <Check size={15} />}</button>
    </div>;
  }
  return <div className="household-member soft-inset">
    <div><b>{member.name}</b><p className="profile-hint">Preferences: {member.dietary_preferences.length ? member.dietary_preferences.join(', ') : 'none noted'}</p></div>
    <div><p className="profile-hint">Health conditions: {member.health_conditions.length ? member.health_conditions.join(', ') : 'none noted'}</p></div>
    <div style={{ display: 'flex', gap: 6 }}>
      <button type="button" className="icon-button" onClick={() => setEditing(true)} aria-label={`Edit ${member.name}`}><Pencil size={15} /></button>
      <button type="button" className="icon-button member-remove" onClick={() => onDelete(member.id)} aria-label={`Remove ${member.name}`}><Trash2 size={15} /></button>
    </div>
  </div>;
}

function HouseholdMembers({ members, onAdd, onUpdate, onDelete }) {
  const [name, setName] = useState('');
  const [preferences, setPreferences] = useState('');
  const [conditions, setConditions] = useState('');
  const [adding, setAdding] = useState(false);

  const addMember = async (event) => {
    event.preventDefault();
    if (!name.trim() || adding) return;
    setAdding(true);
    try {
      await onAdd({ name: name.trim(), dietary_preferences: splitTags(preferences), health_conditions: splitTags(conditions) });
      setName(''); setPreferences(''); setConditions('');
    } finally { setAdding(false); }
  };

  return <section className="profile-favorites soft-outset">
    <div className="profile-favorites-head">
      <h3>Household members</h3>
      <span>Preferences and health conditions considered when picking recipes and prep tasks.</span>
    </div>
    <div className="household-members">
      {members.map((member) => <MemberRow member={member} onUpdate={onUpdate} onDelete={onDelete} key={member.id} />)}
      {!members.length && <div className="empty-state">No household members added yet.</div>}
    </div>
    <form className="household-member-add" onSubmit={addMember} style={{ display: 'grid', gap: 10, marginTop: 14 }}>
      <label className="profile-field"><span>Name</span>
        <input type="text" value={name} onChange={(event) => setName(event.target.value)} placeholder="Jordan Kim" />
      </label>
      <label className="profile-field"><span>Dietary preferences</span>
        <input type="text" value={preferences} onChange={(event) => setPreferences(event.target.value)} placeholder="vegetarian, no nuts" />
      </label>
      <label className="profile-field"><span>Health conditions</span>
        <input type="text" value={conditions} onChange={(event) => setConditions(event.target.value)} placeholder="diabetic, lactose intolerant" />
      </label>
      <button type="submit" className="secondary-button" disabled={!name.trim() || adding} style={{ justifySelf: 'start' }}>
        {adding ? <LoaderCircle className="spin" size={15} /> : <Plus size={15} />} Add member
      </button>
    </form>
  </section>;
}

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

export default function Profile({ data, onSave, onAddMember, onUpdateMember, onDeleteMember }) {
  const profile = data.profile || {};
  const householdMembers = data.household_members || [];
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

    <HouseholdMembers members={householdMembers} onAdd={onAddMember} onUpdate={onUpdateMember} onDelete={onDeleteMember} />

    {favorites.length > 0 && <section className="profile-favorites soft-outset">
      <div className="profile-favorites-head">
        <h3>Top 10 favourite recipes</h3>
        <span>Recipes the household starred highly in the past.</span>
      </div>
      <ol className="favorite-list">
        {favorites.map((entry, index) => <li key={`${entry.dish_name}-${index}`}>
          <span className="favorite-rank">{String(index + 1).padStart(2, '0')}</span>
          <span className="favorite-name">{entry.dish_name}</span>
          <span className="favorite-stars">{Array.from({ length: Math.min(5, Math.max(0, entry.rating || 0)) }).map((_, star) => <Star key={star} size={12} fill="currentColor" />)}</span>
          <span className="favorite-date">{formatDate(entry.rated_at)}</span>
        </li>)}
      </ol>
    </section>}
  </div>;
}
