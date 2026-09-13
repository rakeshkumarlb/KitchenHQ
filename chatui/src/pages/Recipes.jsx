import { useEffect, useState } from 'react';
import { BookOpen, Plus, Search, Star, Trash2, X } from 'lucide-react';
import { kitchenApi } from '../services/api';
import { formatIngredientLine, parseIngredientsUsed } from '../services/menuContent';

const MEAL_TYPES = ['breakfast', 'lunch', 'snack', 'dinner'];
const TOP_LIST_SIZE = 10;

const emptyForm = {
  name: '', origin: '', serves: '4', prep_time_minutes: '', cook_time_minutes: '',
  ingredientsText: '', instructionsText: '', calories: '', protein_g: '', carbs_g: '', fat_g: '', fiber_g: '',
  dietary_flags: '', meal_types: [], tags: '',
};

function parseIngredientLines(text) {
  return text.split('\n').map((line) => line.trim()).filter(Boolean).map((line) => {
    const [name, quantity, unit] = line.split(',').map((part) => part.trim());
    return { item_name: name, quantity: Number(quantity) || 1, unit: unit || 'pcs' };
  });
}

function StarRating({ value, onRate }) {
  return <div className="star-row">
    {[1, 2, 3, 4, 5].map((n) => <button type="button" key={n} className={value >= n ? 'selected' : ''} onClick={() => onRate(n)} aria-label={`Rate ${n} star${n > 1 ? 's' : ''}`}><Star size={14} fill={value >= n ? 'currentColor' : 'none'} /></button>)}
  </div>;
}

function RecipeDetail({ item, onClose, onRate }) {
  if (!item) return null;
  const recipe = item.recipe;
  const ingredients = parseIngredientsUsed(recipe.ingredients);
  const macros = recipe.macros_per_serving || {};
  return <div className="recipe-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
    <section className="recipe-modal" role="dialog" aria-modal="true" aria-labelledby="catalog-recipe-title">
      <button className="recipe-close icon-button" onClick={onClose} aria-label="Close recipe"><X size={19} /></button>
      <p className="eyebrow">{recipe.origin || 'Household recipe'} · serves {recipe.serves || 1}</p>
      <h2 id="catalog-recipe-title">{recipe.name}</h2>
      <StarRating value={item.rating || 0} onRate={(rating) => onRate(item.id, rating)} />
      <div className="recipe-meta">
        {recipe.prep_time_minutes ? <span>Prep {recipe.prep_time_minutes} min</span> : null}
        {recipe.cook_time_minutes ? <span>Cook {recipe.cook_time_minutes} min</span> : null}
        {macros.calories ? <span>{macros.calories} kcal / serving</span> : null}
        {(recipe.dietary_flags || []).map((flag) => <span key={flag}>{flag}</span>)}
      </div>
      <div className="recipe-section"><h3>Ingredients</h3>{ingredients.length
        ? <ul className="recipe-list">{ingredients.map((ing, index) => <li key={`${ing.item_name}-${index}`}>{formatIngredientLine(ing)}</li>)}</ul>
        : <p>No ingredients listed.</p>}</div>
      <div className="recipe-section"><h3>Method</h3>{(recipe.instructions || []).length
        ? <ol className="recipe-list">{recipe.instructions.map((step, index) => <li key={index}>{step}</li>)}</ol>
        : <p>No steps listed.</p>}</div>
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
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyForm);

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

  const toggleMealType = (mealType) => setForm((current) => ({
    ...current,
    meal_types: current.meal_types.includes(mealType) ? current.meal_types.filter((m) => m !== mealType) : [...current.meal_types, mealType],
  }));

  const canSubmit = form.name.trim() && form.ingredientsText.trim() && form.instructionsText.trim();

  const submitForm = async (event) => {
    event.preventDefault();
    if (!canSubmit) return;
    const recipe = {
      name: form.name.trim(),
      origin: form.origin.trim(),
      serves: Number(form.serves) || 1,
      prep_time_minutes: form.prep_time_minutes ? Number(form.prep_time_minutes) : null,
      cook_time_minutes: form.cook_time_minutes ? Number(form.cook_time_minutes) : null,
      ingredients: parseIngredientLines(form.ingredientsText),
      instructions: form.instructionsText.split('\n').map((line) => line.trim()).filter(Boolean),
      macros_per_serving: {
        calories: Number(form.calories) || undefined,
        protein_g: Number(form.protein_g) || undefined,
        carbs_g: Number(form.carbs_g) || undefined,
        fat_g: Number(form.fat_g) || undefined,
        fiber_g: Number(form.fiber_g) || undefined,
      },
      dietary_flags: form.dietary_flags.split(',').map((s) => s.trim()).filter(Boolean),
      meal_types: form.meal_types,
      tags: form.tags.split(',').map((s) => s.trim()).filter(Boolean),
    };
    try {
      setError('');
      await kitchenApi.addRecipe(recipe);
      setForm(emptyForm);
      setShowForm(false);
      await loadTop();
    } catch (requestError) { setError(requestError.message); }
  };

  return <div className="page-content">
    <div className="page-lead">
      <div><p className="eyebrow">The household catalog</p><h2>Recipe <em>catalog.</em></h2><p>Search by ingredient or vibe, or add your own recipes for the chefs to draw from.</p></div>
      <div className="page-lead-actions"><button className="secondary-button" onClick={() => setShowForm((v) => !v)}><Plus size={16} /> {showForm ? 'Close' : 'Add recipe'}</button></div>
    </div>

    {error && <div className="chat-error" role="alert"><span>{error}</span></div>}

    <form className="recipe-search" onSubmit={runSearch}>
      <input type="text" placeholder="Search recipes semantically, e.g. 'quick spicy vegetarian dinner'" value={query} onChange={(event) => setQuery(event.target.value)} aria-label="Search recipes" />
      <button type="submit" className="secondary-button"><Search size={15} /> Search</button>
      {searched && <button type="button" className="secondary-button" onClick={clearSearch}><X size={15} /> Clear</button>}
    </form>

    {showForm && <form className="recipe-form soft-outset" onSubmit={submitForm}>
      <div className="recipe-form-row">
        <input type="text" placeholder="Recipe name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} aria-label="Recipe name" />
        <input type="text" placeholder="Origin (e.g. North Indian)" value={form.origin} onChange={(event) => setForm({ ...form, origin: event.target.value })} aria-label="Origin" />
        <input type="number" min="1" placeholder="Serves" value={form.serves} onChange={(event) => setForm({ ...form, serves: event.target.value })} aria-label="Serves" />
      </div>
      <div className="recipe-form-row">
        <input type="number" min="0" placeholder="Prep time (min)" value={form.prep_time_minutes} onChange={(event) => setForm({ ...form, prep_time_minutes: event.target.value })} aria-label="Prep time in minutes" />
        <input type="number" min="0" placeholder="Cook time (min)" value={form.cook_time_minutes} onChange={(event) => setForm({ ...form, cook_time_minutes: event.target.value })} aria-label="Cook time in minutes" />
      </div>
      <textarea placeholder="Ingredients, one per line: item name, quantity, unit&#10;e.g. Paneer, 250, g" value={form.ingredientsText} onChange={(event) => setForm({ ...form, ingredientsText: event.target.value })} aria-label="Ingredients" />
      <textarea placeholder="Instructions, one step per line" value={form.instructionsText} onChange={(event) => setForm({ ...form, instructionsText: event.target.value })} aria-label="Instructions" />
      <div className="recipe-form-row">
        <input type="number" min="0" placeholder="Calories/serving" value={form.calories} onChange={(event) => setForm({ ...form, calories: event.target.value })} aria-label="Calories per serving" />
        <input type="number" min="0" placeholder="Protein (g)" value={form.protein_g} onChange={(event) => setForm({ ...form, protein_g: event.target.value })} aria-label="Protein grams" />
        <input type="number" min="0" placeholder="Carbs (g)" value={form.carbs_g} onChange={(event) => setForm({ ...form, carbs_g: event.target.value })} aria-label="Carbs grams" />
        <input type="number" min="0" placeholder="Fat (g)" value={form.fat_g} onChange={(event) => setForm({ ...form, fat_g: event.target.value })} aria-label="Fat grams" />
      </div>
      <div className="recipe-form-row">
        <input type="text" placeholder="Dietary flags, comma separated" value={form.dietary_flags} onChange={(event) => setForm({ ...form, dietary_flags: event.target.value })} aria-label="Dietary flags" />
        <input type="text" placeholder="Tags, comma separated" value={form.tags} onChange={(event) => setForm({ ...form, tags: event.target.value })} aria-label="Tags" />
      </div>
      <div className="recipe-form-checks">{MEAL_TYPES.map((mealType) => <label key={mealType}><input type="checkbox" checked={form.meal_types.includes(mealType)} onChange={() => toggleMealType(mealType)} /> {mealType}</label>)}</div>
      <button type="submit" className="shopping-confirm" disabled={!canSubmit}><Plus size={15} /> Save recipe</button>
    </form>}

    <section className="table-section">
      <div className="section-heading compact"><h3>{searched ? `Results for "${query}"` : 'Top recipes'}</h3><span>{recipes.length} shown</span></div>
      {loading ? <div className="empty-state">Loading…</div> : recipes.length ? <div className="recipe-catalog-grid">
        {recipes.map((item) => {
          const recipe = item.recipe;
          const macros = recipe.macros_per_serving || {};
          return <article className="recipe-catalog-card soft-outset" key={item.id}>
            <div className="recipe-catalog-card-top"><span className="meal-type">{recipe.origin || 'Household'}</span>{item.score !== undefined && <span className="automation-job-agent">match {(item.score * 100).toFixed(0)}%</span>}</div>
            <h3>{recipe.name}</h3>
            <div className="recipe-catalog-card-meta">
              <span>Serves {recipe.serves || 1}</span>
              {recipe.prep_time_minutes ? <span>Prep {recipe.prep_time_minutes}m</span> : null}
              {recipe.cook_time_minutes ? <span>Cook {recipe.cook_time_minutes}m</span> : null}
              {macros.calories ? <span>{macros.calories} kcal</span> : null}
            </div>
            <StarRating value={item.rating || 0} onRate={(rating) => rate(item.id, rating)} />
            <div className="recipe-catalog-card-actions">
              <button className="recipe-button" onClick={() => setSelected(item)}><BookOpen size={14} /> View recipe</button>
              <button className="task-cancel" onClick={() => remove(item.id)} aria-label={`Delete ${recipe.name}`} title="Remove from catalog"><Trash2 size={14} /></button>
            </div>
          </article>;
        })}
      </div> : <div className="empty-state">{searched ? 'No recipes matched that search.' : 'No recipes yet — add the first one above.'}</div>}
    </section>

    <RecipeDetail item={selected} onClose={() => setSelected(null)} onRate={rate} />
  </div>;
}
