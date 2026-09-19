import { ArrowRight, BookOpen, CalendarDays, CheckCircle2, Clock3, Leaf, PackageCheck, Sparkles } from 'lucide-react';
import StatCard from '../components/StatCard';
import { previewLine, parseLines } from '../services/menuContent';

const MEAL_ORDER = ['Breakfast', 'Lunch', 'Snack', 'Dinner'];
const MEAL_START_HOUR = { breakfast: 8, lunch: 13, snack: 17, dinner: 20 };
const WEEKDAY_NAMES = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'];

// The meal the household is heading toward right now: the first planned slot
// (by day + rough serving time) that has not passed yet, scanning up to a week
// ahead and falling back to the first planned meal if nothing matches.
function nextMeal(menu, now = new Date()) {
  if (!menu.length) return null;
  const minutesNow = now.getHours() * 60 + now.getMinutes();
  for (let dayOffset = 0; dayOffset < 7; dayOffset += 1) {
    const dayName = WEEKDAY_NAMES[(now.getDay() + dayOffset) % 7];
    for (const mealType of MEAL_ORDER) {
      if (dayOffset === 0 && MEAL_START_HOUR[mealType.toLowerCase()] * 60 <= minutesNow) continue;
      const item = menu.find((meal) => meal.day_of_week?.toLowerCase() === dayName && meal.meal_type?.toLowerCase() === mealType.toLowerCase());
      if (item) return item;
    }
  }
  return menu[0];
}

export default function Dashboard({ data, navigate }) {
  const lowStock = data.inventory.filter((item) => item.quantity <= item.minimum_threshold);
  const pending = data.tasks.filter((task) => task.status === 'assigned');
  const completed = data.tasks.filter((task) => task.status !== 'assigned').length;
  const next = nextMeal(data.menu);
  return <div className="page-content dashboard-page">
    <section className="hero-panel soft-outset"><div><p className="eyebrow">Tuesday, 25 August 2026</p><h2>Make space for<br /><em>good food.</em></h2><p className="hero-copy">Your calm command center for planning the week, keeping the pantry fresh, and turning good intentions into dinner.</p><button className="primary-button" onClick={() => navigate('menu')}>Open this week's menu <ArrowRight size={16} /></button></div><div className="hero-orbit"><div className="orbit-ring" /><div className="hero-bowl">🥗</div><span className="orbit-tag tag-one">Fresh & balanced</span><span className="orbit-tag tag-two">5 days planned</span></div></section>
    <div className="section-heading"><div><p className="eyebrow">At a glance</p><h3>Your kitchen today</h3></div><button className="text-button" onClick={() => navigate('pantry')}>View pantry <ArrowRight size={15} /></button></div>
    <section className="stats-grid"><StatCard label="Menu planned" value={`${data.menu.length} meals`} detail="Monday to Friday" tone="green" icon={CalendarDays} /><StatCard label="Pantry items" value={data.inventory.length} detail={`${lowStock.length} need attention`} tone="coral" icon={Leaf} /><StatCard label="Prep progress" value={`${completed}/${data.tasks.length}`} detail="tasks complete" tone="yellow" icon={CheckCircle2} /><StatCard label="Stock health" value={lowStock.length ? 'Review' : 'Great'} detail="Based on thresholds" tone="blue" icon={PackageCheck} /><StatCard label="Recipe catalog" value={data.recipe_count ?? 0} detail="saved recipes" tone="green" icon={BookOpen} /></section>
    <section className="dashboard-grid"><article className="content-card soft-outset"><div className="card-heading"><div><p className="eyebrow">Next on the table</p><h3>{next?.dish_name || 'No meal planned'}</h3></div><span className="day-chip">{next ? `${next.meal_type} · ${next.day_of_week}` : '—'}</span></div><p className="muted-copy">{previewLine(next?.ingredients, 'Plan a meal from your pantry.')}</p><div className="macro-row">{(next?.macros || 'Balanced macros').split('  /  ').map((macro) => <span key={macro}>{macro}</span>)}</div><button className="text-button" onClick={() => navigate('menu')}>See full recipe <ArrowRight size={15} /></button></article><article className="content-card soft-outset accent-card"><Sparkles size={22} /><p className="eyebrow">A little guidance</p><h3>Small prep, easier evenings.</h3><p className="muted-copy">{pending.length} prep tasks are waiting. A ten-minute head start makes the rest feel lighter.</p><button className="text-button" onClick={() => navigate('tasks')}>View task list <ArrowRight size={15} /></button></article></section>
    <div className="section-heading"><div><p className="eyebrow">Up next</p><h3>Pending tasks</h3></div><button className="text-button" onClick={() => navigate('tasks')}>View task list <ArrowRight size={15} /></button></div>
    <section className="dashboard-task-list">{pending.length ? pending.slice(0, 5).map((task) => {
      const steps = parseLines(task.detailed_instructions);
      return <article className="task-row soft-outset" key={task.id}>
        <div className="task-time"><b>{task.trigger_time}</b><span>{task.trigger_day}</span></div>
        <div className="task-copy"><div><span className="task-type">{task.task_type}</span></div><h3>{steps.join(' ') || 'Prep task'}</h3></div>
        <Clock3 size={17} className="task-clock" />
      </article>;
    }) : <div className="empty-state">All clear. The kitchen is caught up.</div>}</section>
  </div>;
}
