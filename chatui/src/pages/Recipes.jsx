import { useEffect, useState } from 'react';
import { BookOpen, LoaderCircle, RefreshCw, Search, ShieldCheck, Star, Trash2, Wand2, X } from 'lucide-react';
import { kitchenApi } from '../services/api';
import { formatIngredientLine, parseIngredientsUsed } from '../services/menuContent';

const TOP_LIST_SIZE = 10;
const TAG_PREVIEW_COUNT = 3;
const CHAT_SESSION_KEY = 'kitchenhq.chat.session';

// Same localStorage key Chat.jsx keys its session on, so an "ask chef" round-trip from
// here also lands in that page's chat history rather than starting a shadow session.
function chatSessionId() {
  const saved = window.localStorage.getItem(CHAT_SESSION_KEY);
  if (saved) return saved;
  const sessionId = crypto.randomUUID();
  window.localStorage.setItem(CHAT_SESSION_KEY, sessionId);
  return sessionId;
}

function scoreClass(score) {
  if (score == null) return 'unaudited';
  if (score >= 80) return 'good';
  if (score >= 50) return 'fair';
  return 'poor';
}

function AuditBadge({ score }) {
  return <span className={`audit-badge ${scoreClass(score)}`}><ShieldCheck size={12} /> {score == null ? 'Unaudited' : `Score ${score}/100`}</span>;
}

function TagChips({ tags }) {
  if (!tags?.length) return <span className="tag-chip muted">No tags yet</span>;
  const shown = tags.slice(0, TAG_PREVIEW_COUNT);
  const rest = tags.length - shown.length;
  return <div className="tag-chip-row">
    {shown.map((tag) => <span className="tag-chip" key={tag}>{tag}</span>)}
    {rest > 0 && <span className="tag-chip muted">+{rest}</span>}
  </div>;
}

function StarRating({ value, onRate }) {
  return <div className="star-row">
    {[1, 2, 3, 4, 5].map((n) => <button type="button" key={n} className={value >= n ? 'selected' : ''} onClick={() => onRate(n)} aria-label={`Rate ${n} star${n > 1 ? 's' : ''}`}><Star size={14} fill={value >= n ? 'currentColor' : 'none'} /></button>)}
  </div>;
}

function AskChefActions({ item, asking, onAsk }) {
  const busyTags = asking === `${item.id}:tags`;
  const busyInstructions = asking === `${item.id}:instructions`;
  return <div className="ask-chef-actions">
    <button type="button" className="recipe-button" disabled={Boolean(asking)} onClick={() => onAsk(item, 'tags')}>
      {busyTags ? <LoaderCircle className="spin" size={14} /> : <Wand2 size={14} />} Identify tags
    </button>
    <button type="button" className="recipe-button" disabled={Boolean(asking)} onClick={() => onAsk(item, 'instructions')}>
      {busyInstructions ? <LoaderCircle className="spin" size={14} /> : <RefreshCw size={14} />} Recreate instructions
    </button>
  </div>;
}

function RecipeDetail({ item, onClose, onRate, asking, onAsk, askReply }) {
  if (!item) return null;
  const recipe = item.recipe;
  const ingredients = parseIngredientsUsed(recipe.ingredients);
  const macros = recipe.macros_per_serving || {};
  return <div className="recipe-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
    <section className="recipe-modal" role="dialog" aria-modal="true" aria-labelledby="catalog-recipe-title">
      <button className="recipe-close icon-button" onClick={onClose} aria-label="Close recipe"><X size={19} /></button>
      <p className="eyebrow">{recipe.origin || 'Household recipe'} · serves {recipe.serves || 1}</p>
      <h2 id="catalog-recipe-title">{recipe.name}</h2>
      {recipe.description && <p className="muted-copy">{recipe.description}</p>}
      <StarRating value={item.rating || 0} onRate={(rating) => onRate(item.id, rating)} />
      <div className="recipe-meta">
        {recipe.prep_time_minutes ? <span>Prep {recipe.prep_time_minutes} min</span> : null}
        {recipe.cook_time_minutes ? <span>Cook {recipe.cook_time_minutes} min</span> : null}
        {macros.calories ? <span>{macros.calories} kcal / serving</span> : null}
        {(recipe.tags || []).map((tag) => <span key={tag}>{tag}</span>)}
      </div>
      <div className="recipe-section"><h3>Ingredients</h3>{ingredients.length
        ? <ul className="recipe-list">{ingredients.map((ing, index) => <li key={`${ing.item_name}-${index}`}>{formatIngredientLine(ing)}</li>)}</ul>
        : <p>No ingredients listed.</p>}</div>
      <div className="recipe-section"><h3>Method</h3>{(recipe.instructions || []).length
        ? <ol className="recipe-list">{recipe.instructions.map((step, index) => <li key={index}>{step}</li>)}</ol>
        : <p>No steps listed.</p>}</div>
      <div className="recipe-section">
        <h3>Food Inspector audit</h3>
        <AuditBadge score={item.score} />
        <p>{item.audit_feedback || 'Not yet reviewed by the Food Inspector.'}</p>
      </div>
      <div className="recipe-section">
        <h3>Ask the Executive Chef</h3>
        <AskChefActions item={item} asking={asking} onAsk={onAsk} />
        {askReply && <p className="automation-result">{askReply}</p>}
      </div>
    </section>
  </div>;
}

export default function Recipes() {
  const [recipes, setRecipes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [searched, setSearched] = useState(false);
  const [selected, setSelected] = useState(null);
  const [asking, setAsking] = useState('');
  const [askReplies, setAskReplies] = useState({});

  const loadTop = async () => {
    setLoading(true);
    try { setError(''); setSearched(false); setRecipes(await kitchenApi.listRecipes(TOP_LIST_SIZE)); }
    catch (requestError) { setError(requestError.message); }
    finally { setLoading(false); }
  };

  useEffect(() => { loadTop(); }, []);

  const runSearch = async (event) => {
    event.preventDefault();
    if (!query.trim()) { loadTop(); return; }
    setLoading(true);
    try { setError(''); setSearched(true); setRecipes(await kitchenApi.searchRecipes(query.trim())); }
    catch (requestError) { setError(requestError.message); }
    finally { setLoading(false); }
  };

  const clearSearch = () => { setQuery(''); loadTop(); };

  const rate = async (id, rating) => {
    try {
      const updated = await kitchenApi.rateRecipe(id, rating);
      setRecipes((current) => current.map((r) => (r.id === id ? { ...r, rating: updated.rating } : r)));
      setSelected((current) => (current && current.id === id ? { ...current, rating: updated.rating } : current));
    } catch (requestError) { setError(requestError.message); }
  };

  const remove = async (id) => {
    if (!window.confirm('Remove this recipe from the catalog?')) return;
    try { await kitchenApi.deleteRecipe(id); setSelected(null); await (searched ? runSearch({ preventDefault() {} }) : loadTop()); }
    catch (requestError) { setError(requestError.message); }
  };

  const askChef = async (item, kind) => {
    const askKey = `${item.id}:${kind}`;
    // Recreating instructions should address whatever the Food Inspector already
    // flagged, not just produce a generic rewrite - tags refreshes don't carry this
    // context since they aren't judged on the same axis.
    const auditContext = item.score != null
      ? ` The Food Inspector previously scored these instructions ${item.score}/100 with this feedback: "${item.audit_feedback}". Address that feedback specifically.`
      : '';
    const message = kind === 'tags'
      ? `Please review recipe #${item.id} ("${item.recipe.name}") in the catalog and refresh its tags per the recipe catalog standards, changing nothing else. Reply in one short sentence with what changed.`
      : `Please review recipe #${item.id} ("${item.recipe.name}") in the catalog and rewrite its instructions for clarity and correctness, keeping the dish and its ingredients the same unless something is clearly wrong.${auditContext} Reply in one short sentence with what changed.`;
    setAsking(askKey);
    setError('');
    try {
      const response = await kitchenApi.chat(message, chatSessionId());
      setAskReplies((current) => ({ ...current, [item.id]: response.reply }));
      const refreshed = await kitchenApi.getRecipe(item.id);
      setRecipes((current) => current.map((r) => (r.id === item.id ? refreshed : r)));
      setSelected((current) => (current && current.id === item.id ? refreshed : current));
    } catch (requestError) { setError(requestError.message); }
    finally { setAsking(''); }
  };

  return <div className="page-content">
    <div className="page-lead">
      <div><p className="eyebrow">The household catalog</p><h2>Recipe <em>catalog.</em></h2><p>Search by ingredient or vibe. Paste a recipe to the Executive Chef in chat to add it here.</p></div>
    </div>

    {error && <div className="chat-error" role="alert"><span>{error}</span></div>}

    <form className="recipe-search" onSubmit={runSearch}>
      <input type="text" placeholder="Search recipes semantically, e.g. 'quick spicy vegetarian dinner'" value={query} onChange={(event) => setQuery(event.target.value)} aria-label="Search recipes" />
      <button type="submit" className="secondary-button"><Search size={15} /> Search</button>
      {searched && <button type="button" className="secondary-button" onClick={clearSearch}><X size={15} /> Clear</button>}
    </form>

    <section className="table-section">
      <div className="section-heading compact"><h3>{searched ? `Results for "${query}"` : 'Top recipes'}</h3><span>{recipes.length} shown</span></div>
      {loading ? <div className="empty-state">Loading…</div> : recipes.length ? <div className="recipe-catalog-list soft-outset">
        {recipes.map((item) => {
          const recipe = item.recipe;
          return <div key={item.id}>
            <div className="recipe-row">
              <div className="recipe-row-name">
                <b>{recipe.name}</b>
                <small>{recipe.origin || 'Household'} · serves {recipe.serves || 1}</small>
                <TagChips tags={recipe.tags} />
              </div>
              <div className="recipe-row-meta">
                <StarRating value={item.rating || 0} onRate={(rating) => rate(item.id, rating)} />
              </div>
              <AuditBadge score={item.score} />
              <div className="recipe-row-actions">
                {searched && item.match_score !== undefined && <span className="automation-job-agent">match {(item.match_score * 100).toFixed(0)}%</span>}
                <button className="recipe-button" onClick={() => setSelected(item)}><BookOpen size={14} /> View</button>
                <button className="task-cancel" onClick={() => remove(item.id)} aria-label={`Delete ${recipe.name}`} title="Remove from catalog"><Trash2 size={14} /></button>
              </div>
            </div>
            {askReplies[item.id] && <p className="automation-result recipe-row-result">{askReplies[item.id]}</p>}
          </div>;
        })}
      </div> : <div className="empty-state">{searched ? 'No recipes matched that search.' : 'No recipes yet — paste one to the Executive Chef in chat to get started.'}</div>}
    </section>

    <RecipeDetail
      item={selected}
      onClose={() => setSelected(null)}
      onRate={rate}
      asking={asking}
      onAsk={askChef}
      askReply={selected ? askReplies[selected.id] : undefined}
    />
  </div>;
}
