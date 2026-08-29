import { BookOpen, ChevronRight, CircleCheck, Star, X } from 'lucide-react';
import { useState } from 'react';

const days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
const mealTypes = ['Breakfast', 'Lunch', 'Snack', 'Dinner'];

function RecipeModal({ item, onClose }) {
	if (!item) return null;
	const recipeLines = (item.full_recipe || 'Recipe details are not available for this older menu entry.').split('\n').filter(Boolean);
	return <div className="recipe-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
		<section className="recipe-modal" role="dialog" aria-modal="true" aria-labelledby="recipe-title">
			<button className="recipe-close icon-button" onClick={onClose} aria-label="Close recipe"><X size={19} /></button>
			<p className="eyebrow">{item.day_of_week} · {item.meal_type}</p><h2 id="recipe-title">{item.dish_name}</h2>
			<div className="recipe-meta"><span>{item.macros}</span><span>{item.is_kid_friendly ? 'Family friendly' : 'Chef selection'}</span></div>
			<div className="recipe-section"><h3>Ingredients</h3><p>{item.ingredients}</p></div>
			<div className="recipe-section"><h3>Detailed method</h3><div className="recipe-text">{recipeLines.map((line, index) => <p key={`${line}-${index}`} className={line.endsWith(':') ? 'recipe-label' : ''}>{line}</p>)}</div></div>
		</section>
	</div>;
}

export default function WeeklyMenu({ data, onRate }) {
	const [selectedRecipe, setSelectedRecipe] = useState(null);
	return <div className="page-content"><div className="page-lead"><div><p className="eyebrow">The week ahead</p><h2>Weekly <em>menu.</em></h2><p>Four thoughtful moments each day, built around what is already in your pantry.</p></div><button className="secondary-button">Export menu <ChevronRight size={16} /></button></div><div className="day-groups">{days.map((day, dayIndex) => <section className="day-group" key={day}><div className="day-heading"><div className="day-number">{String(dayIndex + 1).padStart(2, '0')}</div><div><p className="eyebrow">Day {dayIndex + 1}</p><h3>{day}</h3></div><span>{data.menu.filter((item) => item.day_of_week === day).length}/4 meals planned</span></div><div className="meal-grid">{mealTypes.map((mealType) => { const item = data.menu.find((meal) => meal.day_of_week === day && meal.meal_type.toLowerCase() === mealType.toLowerCase()); return <article className="meal-card soft-outset" key={`${day}-${mealType}`}><div className="meal-card-top"><span className="meal-type">{mealType}</span>{item?.is_kid_friendly ? <span className="kid-badge"><CircleCheck size={13} /> Family pick</span> : null}</div><h3>{item?.dish_name || 'Open slot'}</h3><p>{item?.ingredients || 'No meal planned yet.'}</p><div className="macro-row">{(item?.macros || '').split('  /  ').map((macro) => <span key={macro}>{macro}</span>)}</div><div className="meal-card-actions"><button className="recipe-button" onClick={() => item && setSelectedRecipe(item)} disabled={!item}><BookOpen size={14} /> View recipe</button><div className="star-row">{[1, 2, 3, 4, 5].map((rating) => <button key={rating} className={rating <= (item?.kid_rating || 0) ? 'selected' : ''} onClick={() => item && onRate(item.id, rating)} aria-label={`Rate ${rating} stars`}><Star size={14} fill="currentColor" /></button>)}</div></div></article>; })}</div></section>)}</div><RecipeModal item={selectedRecipe} onClose={() => setSelectedRecipe(null)} /></div>;
}
