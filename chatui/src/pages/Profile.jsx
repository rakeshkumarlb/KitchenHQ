import { Fragment, useEffect, useMemo, useState } from 'react';
import { Bell, CalendarOff, Check, LoaderCircle, Pencil, Plus, Save, ShieldCheck, Star, Tags, Trash2, Users } from 'lucide-react';

const splitTags = (value) => value.split(',').map((part) => part.trim()).filter(Boolean);
const joinTags = (value) => (value || []).join(', ');

const PROFILE_TABS = [
  { id: 'household', label: 'Household & Members', icon: Users },
  { id: 'notifications', label: 'Notifications', icon: Bell },
  { id: 'restrictions', label: 'Restrictions', icon: ShieldCheck },
  { id: 'schedule', label: 'Meal Schedule', icon: CalendarOff },
  { id: 'tags', label: 'Preferences & Tags', icon: Tags },
];

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

function RestrictionsTab({ restrictions, onToggleRestriction, onRestrictionValueChange, allowInvention, allowUnapproved, onToggleInvention, onToggleUnapproved }) {
  return <section className="profile-form soft-outset profile-tab-panel">
    <div className="profile-favorites-head">
      <h3>Menu restrictions</h3>
      <span>Household-editable rules the Executive Chef plans around and the Food Inspector judges against — not hardcoded anywhere.</span>
    </div>
    <div className="restriction-list">
      {restrictions.map((restriction) => <div className="restriction-row soft-inset" key={restriction.id}>
        <label>
          <input type="checkbox" checked={restriction.enabled} onChange={() => onToggleRestriction(restriction.id)} />
          <span className="restriction-copy">
            <b>{restriction.label}</b>
            <small>{restriction.category || 'general'} · {restriction.scope === 'week' ? 'judged across the whole week' : 'judged per meal'}</small>
          </span>
        </label>
        {restriction.value !== undefined && <span className="restriction-value">
          min distinct
          <input
            type="number"
            min={1}
            value={restriction.value}
            onChange={(event) => onRestrictionValueChange(restriction.id, Number(event.target.value) || 1)}
          />
        </span>}
      </div>)}
      {!restrictions.length && <div className="empty-state">No restrictions configured.</div>}
    </div>
    <label className="profile-toggle" style={{ marginTop: 18 }}>
      <input type="checkbox" checked={allowInvention} onChange={(event) => onToggleInvention(event.target.checked)} />
      <span>Allow the Executive Chef to invent new dishes not in the recipe catalog</span>
    </label>
    <label className="profile-toggle">
      <input type="checkbox" checked={allowUnapproved} onChange={(event) => onToggleUnapproved(event.target.checked)} />
      <span>Allow recipes from the catalog that haven't been approved yet</span>
    </label>
    <p className="profile-hint" style={{ color: 'var(--muted)' }}>Recipe approval isn't built yet — this toggle is captured for when it is.</p>
  </section>;
}

function MealScheduleTab({ days, mealTypes, skipMeals, onToggleSkip }) {
  return <section className="profile-form soft-outset profile-tab-panel">
    <div className="profile-favorites-head">
      <h3>Meal schedule</h3>
      <span>Mark a slot skipped (household away, eating out, etc.) so next week's plan leaves it unplanned.</span>
    </div>
    <div className="skip-grid">
      <span />
      {mealTypes.map((meal) => <span className="skip-grid-head" key={meal}>{meal}</span>)}
      {days.map((day) => <Fragment key={day}>
        <span className="skip-day-label">{day}</span>
        {mealTypes.map((meal) => {
          const skipped = (skipMeals[day] || []).includes(meal);
          return <button
            type="button"
            key={`${day}-${meal}`}
            className={`skip-cell${skipped ? ' skipped' : ''}`}
            aria-label={`${skipped ? 'Unskip' : 'Skip'} ${meal} on ${day}`}
            onClick={() => onToggleSkip(day, meal)}
          >
            {skipped ? <CalendarOff size={14} /> : <Check size={14} />}
          </button>;
        })}
      </Fragment>)}
    </div>
  </section>;
}

function PreferencesTagsTab({ tagCategories, preferredTags, excludedTags, onCycleTag }) {
  const stateOf = (tag) => (preferredTags.includes(tag) ? 'preferred' : excludedTags.includes(tag) ? 'excluded' : 'neutral');
  return <section className="profile-form soft-outset profile-tab-panel">
    <div className="profile-favorites-head">
      <h3>Preferences & tags</h3>
      <span>The same tag vocabulary used to describe recipes in the catalog.</span>
    </div>
    <p className="tag-cloud-legend">Click a tag once to prefer it, again to avoid it, again to clear.</p>
    {tagCategories.map(({ category, tags }) => <div className="tag-cloud-category" key={category}>
      <h4>{category}</h4>
      <div className="tag-cloud">
        {tags.map((tag) => {
          const state = stateOf(tag);
          return <button
            type="button"
            key={tag}
            className={`tag-cloud-chip${state !== 'neutral' ? ` ${state}` : ''}`}
            onClick={() => onCycleTag(tag)}
          >
            {tag}
          </button>;
        })}
      </div>
    </div>)}
  </section>;
}

export default function Profile({ data, onSave, onAddMember, onUpdateMember, onDeleteMember }) {
  const profile = data.profile || {};
  const householdMembers = data.household_members || [];
  const days = data.constants?.days ?? [];
  const mealTypes = data.constants?.meal_types ?? [];
  const tagCategories = data.constants?.tags ?? [];
  const [activeTab, setActiveTab] = useState('household');
  const [form, setForm] = useState({
    name: '', email: '', cc_emails: '', notes: '', notify_on_task_creation: true,
    restrictions: [], allow_recipe_invention: true, allow_unapproved_recipes: true,
    skip_meals: {}, preferred_tags: [], excluded_tags: [],
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setForm({
      name: profile.name || '',
      email: profile.email || '',
      cc_emails: profile.cc_emails || '',
      notes: profile.notes || '',
      notify_on_task_creation: profile.notify_on_task_creation == null ? true : Boolean(profile.notify_on_task_creation),
      restrictions: profile.restrictions || [],
      allow_recipe_invention: profile.allow_recipe_invention == null ? true : Boolean(profile.allow_recipe_invention),
      allow_unapproved_recipes: profile.allow_unapproved_recipes == null ? true : Boolean(profile.allow_unapproved_recipes),
      skip_meals: profile.skip_meals || {},
      preferred_tags: profile.preferred_tags || [],
      excluded_tags: profile.excluded_tags || [],
    });
  }, [profile]);

  const favorites = useMemo(() => parseFavorites(profile.favorite_recipes), [profile.favorite_recipes]);

  const set = (key, value) => { setForm((current) => ({ ...current, [key]: value })); setSaved(false); };
  const emailInvalid = form.email.trim() && !form.email.includes('@');

  const toggleRestriction = (id) => set('restrictions', form.restrictions.map((r) => (r.id === id ? { ...r, enabled: !r.enabled } : r)));
  const setRestrictionValue = (id, value) => set('restrictions', form.restrictions.map((r) => (r.id === id ? { ...r, value } : r)));
  const toggleSkipMeal = (day, meal) => {
    const current = form.skip_meals[day] || [];
    const next = current.includes(meal) ? current.filter((m) => m !== meal) : [...current, meal];
    const skip_meals = { ...form.skip_meals };
    if (next.length) skip_meals[day] = next; else delete skip_meals[day];
    set('skip_meals', skip_meals);
  };
  const cycleTag = (tag) => {
    const preferred = form.preferred_tags.includes(tag);
    const excluded = form.excluded_tags.includes(tag);
    const preferred_tags = form.preferred_tags.filter((t) => t !== tag);
    const excluded_tags = form.excluded_tags.filter((t) => t !== tag);
    if (!preferred && !excluded) preferred_tags.push(tag);
    else if (preferred) excluded_tags.push(tag);
    setForm((current) => ({ ...current, preferred_tags, excluded_tags }));
    setSaved(false);
  };

  const submit = async (event) => {
    event.preventDefault();
    if (saving || emailInvalid) return;
    setSaving(true);
    try { await onSave(form); setSaved(true); } catch { /* error surfaces in the page banner */ } finally { setSaving(false); }
  };

  return <div className="page-content">
    <div className="page-lead"><div><p>Who the kitchen is planning for, what it should avoid, and when to skip a meal.</p></div></div>

    <nav className="pantry-tabs soft-inset">
      {PROFILE_TABS.map(({ id, label, icon: Icon }) => <button key={id} type="button" className={activeTab === id ? 'active' : ''} onClick={() => setActiveTab(id)}><Icon size={15} strokeWidth={1.8} /> {label}</button>)}
    </nav>

    <form onSubmit={submit}>
      {activeTab === 'household' && <HouseholdMembers members={householdMembers} onAdd={onAddMember} onUpdate={onUpdateMember} onDelete={onDeleteMember} />}

      {activeTab === 'notifications' && <>
        <div className="profile-form soft-outset profile-tab-panel">
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
        </div>

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
      </>}

      {activeTab === 'restrictions' && <RestrictionsTab
        restrictions={form.restrictions}
        onToggleRestriction={toggleRestriction}
        onRestrictionValueChange={setRestrictionValue}
        allowInvention={form.allow_recipe_invention}
        allowUnapproved={form.allow_unapproved_recipes}
        onToggleInvention={(value) => set('allow_recipe_invention', value)}
        onToggleUnapproved={(value) => set('allow_unapproved_recipes', value)}
      />}

      {activeTab === 'schedule' && <MealScheduleTab days={days} mealTypes={mealTypes} skipMeals={form.skip_meals} onToggleSkip={toggleSkipMeal} />}

      {activeTab === 'tags' && <PreferencesTagsTab
        tagCategories={tagCategories}
        preferredTags={form.preferred_tags}
        excludedTags={form.excluded_tags}
        onCycleTag={cycleTag}
      />}

      <button type="submit" className="shopping-confirm" disabled={saving || emailInvalid} style={{ marginTop: 20 }}>
        {saving ? <LoaderCircle className="spin" size={15} /> : saved ? <Check size={15} /> : <Save size={15} />}
        {saving ? 'Saving...' : saved ? 'Saved' : 'Save profile'}
      </button>
    </form>
  </div>;
}
