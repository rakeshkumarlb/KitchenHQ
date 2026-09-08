import { useState } from 'react';
import { Check, Clock3, RefreshCw, RotateCcw, X } from 'lucide-react';
import { parseLines, parseIngredientsUsed, formatIngredientLine } from '../services/menuContent';

export default function TaskList({ data, onToggle, onCancel, onRefresh }) {
  const [refreshing, setRefreshing] = useState(false);
  const refresh = async () => {
    if (refreshing) return;
    setRefreshing(true);
    try { await onRefresh?.(); } finally { setRefreshing(false); }
  };
  const pending = data.tasks.filter((task) => !task.is_completed);
  const done = data.tasks.filter((task) => task.is_completed).slice(-10);
  const renderTask = (task) => {
    const steps = parseLines(task.detailed_instructions);
    const ingredients = parseIngredientsUsed(task.ingredients_used);
    return <article className={`task-row soft-outset ${task.is_completed ? 'done' : ''}`} key={task.id}><button className="task-check" onClick={() => onToggle(task)} disabled={task.is_completed} aria-label={`Mark ${task.task_type} complete`} title={task.is_completed ? 'Completed — ingredients already deducted' : 'Confirm done and deduct ingredients'}>{task.is_completed ? <Check size={16} /> : null}</button><div className="task-time"><b>{task.trigger_time}</b><span>{task.trigger_day}</span></div><div className="task-copy"><div><span className="task-type">{task.task_type}</span>{task.is_completed && <span className="done-label">Completed</span>}</div><h3>{steps.join(' ') || 'Prep task'}</h3><p>{ingredients.length ? ingredients.map(formatIngredientLine).join(', ') : 'Kitchen prep'}</p></div>{task.is_completed ? <Clock3 size={17} className="task-clock" /> : <button className="task-cancel" onClick={() => onCancel(task)} aria-label={`Remove ${task.task_type} from the list`} title="Not performed — remove from list"><X size={15} /></button>}</article>;
  };
  return <div className="page-content"><div className="page-lead"><div><p className="eyebrow">The prep rhythm</p><h2>Task <em>list.</em></h2><p>Keep the invisible work visible. Check things off as you go.</p></div><div className="page-lead-actions"><button className="secondary-button" onClick={refresh} disabled={refreshing}><RefreshCw className={refreshing ? 'spin' : undefined} size={16} /> {refreshing ? 'Refreshing...' : 'Refresh'}</button><div className="progress-ring soft-inset"><strong>{data.tasks.length ? Math.round(done.length / data.tasks.length * 100) : 0}%</strong><span>complete</span></div></div></div><div className="task-summary"><span><b>{pending.length}</b> to do</span><span><b>{done.length}</b> completed</span></div><section className="task-group"><h3>Up next</h3>{pending.length ? pending.map(renderTask) : <div className="empty-state">All clear. The kitchen is caught up.</div>}</section>{done.length ? <section className="task-group completed-group"><h3>Recently completed <RotateCcw size={15} /></h3>{done.map(renderTask)}</section> : null}</div>;
}
