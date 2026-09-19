import { BookOpen, CalendarOff, Check, ChevronRight, CircleCheck, LoaderCircle, RefreshCw, ShieldCheck, Wand2, X } from 'lucide-react';
import { Fragment, useState } from 'react';
import { kitchenApi } from '../services/api';
import { parseLines, formatMenuDate } from '../services/menuContent';

const CHAT_SESSION_KEY = 'kitchenhq.chat.session';

// Same localStorage key Chat.jsx/Recipes.jsx key their session on, so an "ask chef"
// round-trip from here also lands in that page's chat history rather than starting a
// shadow session.
function chatSessionId() {
	const saved = window.localStorage.getItem(CHAT_SESSION_KEY);
	if (saved) return saved;
	const sessionId = crypto.randomUUID();
	window.localStorage.setItem(CHAT_SESSION_KEY, sessionId);
	return sessionId;
}

const titleCase = (value) => value.charAt(0).toUpperCase() + value.slice(1);

const MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// DD-MMM label (e.g. "15 Sep") for the day `offset` days after the plan's week_start_date.
function dayDateLabel(weekStartDate, offset) {
	if (!weekStartDate) return '';
	const parsed = new Date(String(weekStartDate).replace(' ', 'T'));
	if (Number.isNaN(parsed.getTime())) return '';
	parsed.setDate(parsed.getDate() + offset);
	return `${String(parsed.getDate()).padStart(2, '0')} ${MONTH_ABBR[parsed.getMonth()]}`;
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

function RecipeModal({ item, onClose, asking, onAsk, askReply }) {
	if (!item) return null;
	const ingredients = parseLines(item.ingredients);
	const steps = parseLines(item.full_recipe);
	const tags = parseLines(item.tags);
	const planned = formatMenuDate(item.updated_at);
	return <div className="recipe-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
		<section className="recipe-modal" role="dialog" aria-modal="true" aria-labelledby="recipe-title">
			<button className="recipe-close icon-button" onClick={onClose} aria-label="Close recipe"><X size={19} /></button>
			<p className="eyebrow">{item.day_of_week} · {item.meal_type}{planned ? ` · updated ${planned}` : ''}</p><h2 id="recipe-title">{item.dish_name}</h2>
			{item.description && <p className="muted-copy">{item.description}</p>}
			<div className="recipe-meta">
				<span>{item.macros}</span>
				<span>{item.is_kid_friendly ? 'Family friendly' : 'Chef selection'}</span>
				{tags.map((tag) => <span key={tag}>{tag}</span>)}
			</div>
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
			<div className="recipe-section">
				<h3>Ask the Executive Chef</h3>
				<AskChefActions item={item} asking={asking} onAsk={onAsk} />
				{askReply && <p className="automation-result">{askReply}</p>}
			</div>
		</section>
	</div>;
}

function SkipMealsGrid({ days, mealTypes, skipMeals }) {
	return <div className="skip-grid readonly">
		<span />
		{mealTypes.map((meal) => <span className="skip-grid-head" key={meal}>{titleCase(meal)}</span>)}
		{days.map((day) => <Fragment key={day}>
			<span className="skip-day-label">{day}</span>
			{mealTypes.map((meal) => {
				const skipped = (skipMeals[day] || []).includes(meal);
				return <span
					className={`skip-cell${skipped ? ' skipped' : ''}`}
					key={`${day}-${meal}`}
					aria-label={`${meal} on ${day} ${skipped ? 'skipped' : 'planned'}`}
				>
					{skipped ? <CalendarOff size={14} /> : <Check size={14} />}
				</span>;
			})}
		</Fragment>)}
	</div>;
}

function WeeklyPlanSummary({ plan, days, mealTypes }) {
	if (!plan) return null;
	const start = formatMenuDate(plan.week_start_date);
	const end = formatMenuDate(plan.week_end_date);
	const restrictions = plan.restrictions_snapshot || [];
	return <section className="content-card soft-outset weekly-plan-summary">
		<div className="card-heading">
			<div><p className="eyebrow">This week's plan</p><h3>{start}{end ? ` – ${end}` : ''}</h3></div>
			<AuditBadge score={plan.score} />
		</div>
		<p className="muted-copy">{plan.audit_feedback || 'Not yet reviewed by the Food Inspector.'}</p>
		<div className="plan-snapshot">
			<p className="eyebrow">Planned under</p>
			<p className="muted-copy">{plan.chef_note_snapshot || 'No chef note at plan time.'}</p>
			<div className="macro-row">
				{restrictions.length
					? restrictions.map((restriction) => <span key={restriction.id}>{restriction.label}</span>)
					: <span>No restrictions enabled</span>}
			</div>
			<SkipMealsGrid days={days} mealTypes={mealTypes} skipMeals={plan.skip_meals_snapshot || {}} />
		</div>
	</section>;
}

export default function WeeklyMenu({ data, onRefresh }) {
	// Day / meal vocabulary comes from GET /api/dashboard (source: shared/constants.py).
	const days = data.constants?.days ?? [];
	const mealTypesRaw = data.constants?.meal_types ?? [];
	const mealTypes = mealTypesRaw.map(titleCase);
	// Tracked by id (not the row object itself) so a re-fetch after "ask the chef"
	// naturally refreshes what the modal shows once `data.menu` updates.
	const [selectedId, setSelectedId] = useState(null);
	const selectedRecipe = data.menu.find((item) => item.id === selectedId) ?? null;
	const [refreshing, setRefreshing] = useState(false);
	const [asking, setAsking] = useState('');
	const [askReplies, setAskReplies] = useState({});
	const [error, setError] = useState('');
	// weekly_plans is ordered by week_start_date DESC (see GET /api/dashboard) - the
	// first row is the most recently planned week.
	const currentPlan = data.weekly_plans?.[0] ?? null;
	const refresh = async () => {
		if (refreshing) return;
		setRefreshing(true);
		try { await onRefresh?.(); } finally { setRefreshing(false); }
	};

	// "Recreate instructions"/"Identify tags" from this page name a *weekly_menu* row,
	// not a recipe catalog id - the Executive Chef must not call get_recipe/update_recipe
	// with it. source_recipe_id tells the chef (and it) whether a linked catalog recipe
	// is the authoritative record to edit, or whether this row is the only copy.
	const askChef = async (item, kind) => {
		const askKey = `${item.id}:${kind}`;
		const sourceLine = item.source_recipe_id
			? ` It was adapted from recipe catalog id ${item.source_recipe_id} - that catalog recipe is the authoritative record for its tags/instructions, so update it and then re-save this weekly menu slot to match.`
			: ' It has no linked recipe catalog entry - this weekly menu row is the only copy of its content, so update it directly.';
		const auditContext = kind === 'instructions' && item.score != null
			? ` The Food Inspector previously scored it ${item.score}/100 with this feedback: "${item.audit_feedback}". Address that feedback specifically.`
			: '';
		const message = kind === 'tags'
			? `Please review the weekly menu item id=${item.id} (${item.day_of_week} ${item.meal_type}, "${item.dish_name}") and refresh its tags per the recipe catalog standards, changing nothing else.${sourceLine} Reply in one short sentence with what changed.`
			: `Please review the weekly menu item id=${item.id} (${item.day_of_week} ${item.meal_type}, "${item.dish_name}") and rewrite its instructions for clarity and correctness, keeping the dish and its ingredients the same unless something is clearly wrong.${sourceLine}${auditContext} Reply in one short sentence with what changed.`;
		setAsking(askKey);
		setError('');
		try {
			const response = await kitchenApi.chat(message, chatSessionId());
			setAskReplies((current) => ({ ...current, [item.id]: response.reply }));
			await onRefresh?.();
		} catch (requestError) { setError(requestError.message); }
		finally { setAsking(''); }
	};

	return <div className="page-content">
		{error && <div className="chat-error" role="alert"><span>{error}</span></div>}
		<WeeklyPlanSummary plan={currentPlan} days={days} mealTypes={mealTypesRaw} />
		<div className="day-groups">{days.map((day, dayIndex) => <section className="day-group" key={day}>
			<div className="day-heading">
				<div className="day-number">{dayDateLabel(currentPlan?.week_start_date, dayIndex) || String(dayIndex + 1).padStart(2, '0')}</div>
				<h3>{day}</h3>
				<span>{data.menu.filter((item) => item.day_of_week === day && !item.is_skipped && item.dish_name).length}/4 meals planned</span>
			</div>
			<div className="meal-grid">{mealTypes.map((mealType) => {
				const item = data.menu.find((meal) => meal.day_of_week === day && meal.meal_type.toLowerCase() === mealType.toLowerCase());
				if (item?.is_skipped) return <article className="meal-card soft-outset skipped-meal" key={`${day}-${mealType}`}>
					<div className="meal-card-top"><span className="meal-type">{mealType}</span></div>
					<h3>Skipped</h3>
					<p><CalendarOff size={14} /> Left unplanned this week by household preference.</p>
				</article>;
				const planned = formatMenuDate(item?.updated_at);
				return <article className="meal-card soft-outset" key={`${day}-${mealType}`}>
					<div className="meal-card-top"><span className="meal-type">{mealType}</span>{item?.is_kid_friendly ? <span className="kid-badge"><CircleCheck size={13} /> Family pick</span> : null}</div>
					<h3>{item?.dish_name || 'Open slot'}</h3>
					{planned ? <span className="meal-date">Updated {planned}</span> : null}
					<p>{item?.description || 'No meal planned yet.'}</p>
					<div className="meal-card-actions">
						<button className="recipe-button" onClick={() => item && setSelectedId(item.id)} disabled={!item}><BookOpen size={14} /> View recipe</button>
						{item ? <AuditBadge score={item.score} /> : null}
					</div>
				</article>;
			})}</div>
		</section>)}</div>
		<RecipeModal
			item={selectedRecipe}
			onClose={() => setSelectedId(null)}
			asking={asking}
			onAsk={askChef}
			askReply={selectedRecipe ? askReplies[selectedRecipe.id] : undefined}
		/>
	</div>;
}
