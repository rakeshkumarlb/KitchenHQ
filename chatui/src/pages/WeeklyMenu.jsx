import { BookOpen, ChevronRight, CircleCheck, RefreshCw, ShieldCheck, X } from 'lucide-react';
import { useState } from 'react';
import { parseLines, previewLine, formatMenuDate } from '../services/menuContent';

const titleCase = (value) => value.charAt(0).toUpperCase() + value.slice(1);

function scoreClass(score) {
	if (score == null) return 'unaudited';
	if (score >= 80) return 'good';
	if (score >= 50) return 'fair';
	return 'poor';
}

function AuditBadge({ score }) {
	return <span className={`audit-badge ${scoreClass(score)}`}><ShieldCheck size={12} /> {score == null ? 'Unaudited' : `Score ${score}/100`}</span>;
}

function RecipeModal({ item, onClose }) {
	if (!item) return null;
	const ingredients = parseLines(item.ingredients);
	const steps = parseLines(item.full_recipe);
	const planned = formatMenuDate(item.updated_at);
	return <div className="recipe-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
		<section className="recipe-modal" role="dialog" aria-modal="true" aria-labelledby="recipe-title">
			<button className="recipe-close icon-button" onClick={onClose} aria-label="Close recipe"><X size={19} /></button>
			<p className="eyebrow">{item.day_of_week} · {item.meal_type}{planned ? ` · updated ${planned}` : ''}</p><h2 id="recipe-title">{item.dish_name}</h2>
			<div className="recipe-meta"><span>{item.macros}</span><span>{item.is_kid_friendly ? 'Family friendly' : 'Chef selection'}</span></div>
			<div className="recipe-section"><h3>Ingredients</h3>{ingredients.length
				? <ul className="recipe-list">{ingredients.map((line, index) => <li key={`${line}-${index}`}>{line}</li>)}</ul>
				: <p>No ingredients listed for this dish.</p>}</div>
			<div className="recipe-section"><h3>Detailed method</h3>{steps.length
				? <ol className="recipe-list">{steps.map((line, index) => <li key={`${line}-${index}`}>{line}</li>)}</ol>
				: <p>Recipe details are not available for this older menu entry.</p>}</div>
			<div className="recipe-section"><h3>Food Inspector audit</h3>
				<AuditBadge score={item.score} />
				<p>{item.audit_feedback || 'Not yet reviewed by the Food Inspector.'}</p>
			</div>
		</section>
	</div>;
}

export default function WeeklyMenu({ data, onRefresh }) {
	// Day / meal vocabulary comes from GET /api/dashboard (source: shared/constants.py).
	const days = data.constants?.days ?? [];
	const mealTypes = (data.constants?.meal_types ?? []).map(titleCase);
	const [selectedRecipe, setSelectedRecipe] = useState(null);
	const [refreshing, setRefreshing] = useState(false);
	const refresh = async () => {
		if (refreshing) return;
		setRefreshing(true);
		try { await onRefresh?.(); } finally { setRefreshing(false); }
	};
	return <div className="page-content"><div className="page-lead"><div><p className="eyebrow">The week ahead</p><h2>Weekly <em>menu.</em></h2><p>Four thoughtful moments each day, built around what is already in your pantry.</p></div><div className="page-lead-actions"><button className="secondary-button" onClick={refresh} disabled={refreshing}><RefreshCw className={refreshing ? 'spin' : undefined} size={16} /> {refreshing ? 'Refreshing...' : 'Refresh'}</button><button className="secondary-button">Export menu <ChevronRight size={16} /></button></div></div><div className="day-groups">{days.map((day, dayIndex) => <section className="day-group" key={day}><div className="day-heading"><div className="day-number">{String(dayIndex + 1).padStart(2, '0')}</div><div><p className="eyebrow">Day {dayIndex + 1}</p><h3>{day}</h3></div><span>{data.menu.filter((item) => item.day_of_week === day).length}/4 meals planned</span></div><div className="meal-grid">{mealTypes.map((mealType) => { const item = data.menu.find((meal) => meal.day_of_week === day && meal.meal_type.toLowerCase() === mealType.toLowerCase()); const planned = formatMenuDate(item?.updated_at); return <article className="meal-card soft-outset" key={`${day}-${mealType}`}><div className="meal-card-top"><span className="meal-type">{mealType}</span>{item?.is_kid_friendly ? <span className="kid-badge"><CircleCheck size={13} /> Family pick</span> : null}</div><h3>{item?.dish_name || 'Open slot'}</h3>{planned ? <span className="meal-date">Updated {planned}</span> : null}<p>{previewLine(item?.ingredients, 'No meal planned yet.')}</p><div className="macro-row">{(item?.macros || '').split('  /  ').map((macro) => <span key={macro}>{macro}</span>)}</div><div className="meal-card-actions"><button className="recipe-button" onClick={() => item && setSelectedRecipe(item)} disabled={!item}><BookOpen size={14} /> View recipe</button>{item ? <AuditBadge score={item.score} /> : null}</div></article>; })}</div></section>)}</div><RecipeModal item={selectedRecipe} onClose={() => setSelectedRecipe(null)} /></div>;
}
