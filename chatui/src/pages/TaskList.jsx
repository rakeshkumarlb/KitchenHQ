import { useState } from 'react';
import { Check, Clock3, RefreshCw, RotateCcw, ShieldCheck, X } from 'lucide-react';
import { parseLines, parseIngredientsUsed, formatIngredientLine } from '../services/menuContent';

function scoreClass(score) {
  if (score == null) return 'unaudited';
  if (score >= 80) return 'good';
  if (score >= 50) return 'fair';
  return 'poor';
}

function AuditBadge({ score }) {
  return <span className={`audit-badge ${scoreClass(score)}`}><ShieldCheck size={12} /> {score == null ? 'Unaudited' : `Score ${score}/100`}</span>;
}

const STATUS_LABELS = { assigned: 'Assigned', acknowledged: 'Acknowledged', completed: 'Completed', expired: 'Expired', cancelled: 'Cancelled' };
const STATUS_CLASSES = { acknowledged: 'good', completed: 'good', expired: 'poor', cancelled: 'poor' };

function StatusBadge({ status }) {
  return <span className={`status-badge ${STATUS_CLASSES[status] || 'assigned'}`}>{STATUS_LABELS[status] || status}</span>;
}

export default function TaskList({ data, onToggle, onCancel, onRefresh }) {
  const [refreshing, setRefreshing] = useState(false);
  const refresh = async () => {
    if (refreshing) return;
    setRefreshing(true);
    try { await onRefresh?.(); } finally { setRefreshing(false); }
  };
  const pending = data.tasks.filter((task) => task.status === 'assigned');
  const done = data.tasks.filter((task) => task.status !== 'assigned').slice(-10);
  const renderTask = (task) => {
    const steps = parseLines(task.detailed_instructions);
    const ingredients = parseIngredientsUsed(task.ingredients_used);
    const actionable = task.status === 'assigned';
    return <article className={`task-row soft-outset ${actionable ? '' : 'done'}`} key={task.id}><button className="task-check" onClick={() => onToggle(task)} disabled={!actionable} aria-label={`Mark ${task.task_type} complete`} title={actionable ? 'Confirm done and deduct ingredients' : task.is_completed ? 'Completed — ingredients already deducted' : 'No longer actionable'}>{task.is_completed ? <Check size={16} /> : null}</button><div className="task-time"><b>{task.trigger_time}</b><span>{task.trigger_day}</span></div><div className="task-copy"><div><span className="task-type">{task.task_type}</span><StatusBadge status={task.status} /></div><h3>{steps.join(' ') || 'Prep task'}</h3><p>{ingredients.length ? ingredients.map(formatIngredientLine).join(', ') : 'Kitchen prep'}</p><div title={task.audit_feedback || 'Not yet reviewed by the Food Inspector.'}><AuditBadge score={task.score} /></div></div>{actionable ? <button className="task-cancel" onClick={() => onCancel(task)} aria-label={`Remove ${task.task_type} from the list`} title="Not performed — remove from list"><X size={15} /></button> : <Clock3 size={17} className="task-clock" />}</article>;
  };
  return <div className="page-content">
        <div className="task-summary"><span><b>{pending.length}</b> to do</span><span><b>{done.length}</b> completed</span></div><section className="task-group"><h3>Up next</h3>{pending.length ? pending.map(renderTask) : <div className="empty-state">All clear. The kitchen is caught up.</div>}</section>{done.length ? <section className="task-group completed-group"><h3>Recently completed / expired <RotateCcw size={15} /></h3>{done.map(renderTask)}</section> : null}</div>;
}
