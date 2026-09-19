import { useEffect, useState } from 'react';
import { kitchenApi } from '../services/api';

const ROLE_LABELS = {
	executive_chef: 'Executive Chef',
	sous_chef: 'Sous Chef',
	pantry_manager: 'Pantry Manager',
	food_inspector: 'Food Inspector',
};
const roleLabel = (role) => ROLE_LABELS[role] || role;

const METRICS = [
	{ key: 'context_length', label: 'Context length', hint: 'peak prompt size per run' },
	{ key: 'input_tokens', label: 'Input tokens', hint: 'prompt tokens per run' },
	{ key: 'output_tokens', label: 'Output tokens', hint: 'completion tokens per run' },
	{ key: 'total_tokens', label: 'Total tokens', hint: 'input + output per run' },
];

const formatNumber = (value) => (value == null ? '—' : Math.round(Number(value)).toLocaleString());

const formatDayLabel = (isoDay) => {
	if (!isoDay) return '—';
	const date = new Date(`${isoDay}T00:00:00`);
	if (Number.isNaN(date.getTime())) return isoDay;
	return date.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric' });
};

const emptyStat = { min: null, max: null, avg: null, count: 0 };

export default function UsageStats() {
	const [daily, setDaily] = useState([]);
	const [breakdown, setBreakdown] = useState({ overall: {}, by_agent: {} });
	const [error, setError] = useState('');
	const [loaded, setLoaded] = useState(false);

	useEffect(() => {
		(async () => {
			try {
				setError('');
				const [dailyList, usageBreakdown] = await Promise.all([kitchenApi.getUsageStatsDaily(), kitchenApi.getUsageStatsBreakdown()]);
				setDaily(dailyList);
				setBreakdown(usageBreakdown);
			} catch (requestError) {
				setError(requestError.message);
			} finally {
				setLoaded(true);
			}
		})();
	}, []);

	const maxDayTokens = Math.max(1, ...daily.map((day) => day.total_tokens || 0));
	const agentRoles = Object.keys(breakdown.by_agent || {});

	return <div className="page-content">
		<div className="page-lead">
			<div><p className="eyebrow">Agent telemetry</p><h2>Usage <em>stats.</em></h2><p>Token usage and context size across every scheduled and on-demand agent run.</p></div>
		</div>
		{error && <div className="chat-error" role="alert"><span>{error}</span></div>}

		<section className="task-group">
			<h3>Weekly usage (last 7 days)</h3>
			<div className="usage-chart-card soft-outset">
				{daily.length ? <>
					<div className="usage-bar-chart">
						{daily.map((day) => <div className="usage-bar-col" key={day.day} title={`${formatDayLabel(day.day)}: ${formatNumber(day.total_tokens)} tokens, ${day.total_runs} runs`}>
							<span className="usage-bar-value">{formatNumber(day.total_tokens)}</span>
							<div className="usage-bar-track"><div className="usage-bar-fill" style={{ height: `${Math.max(4, Math.round(((day.total_tokens || 0) / maxDayTokens) * 100))}%` }} /></div>
							<span className="usage-bar-label">{formatDayLabel(day.day)}</span>
						</div>)}
					</div>
					<p className="usage-chart-caption">Bar height is total tokens (input + output) per day; hover a bar for run counts.</p>
				</> : loaded && <div className="empty-state">No runs in the last 7 days.</div>}
			</div>
		</section>

		<section className="task-group">
			<h3>Usage summary &middot; min / max / average</h3>
			<div className="usage-metrics-grid">
				{METRICS.map((metric) => <article className="usage-metric-card soft-outset" key={metric.key}>
					<h4>{metric.label}</h4>
					<div className="usage-metric-head">
						<span>Scope</span><span>Min</span><span>Max</span><span>Avg</span><span>Runs</span>
					</div>
					<div className="usage-metric-row overall-row">
						<b>Overall</b>
						<span>{formatNumber((breakdown.overall?.[metric.key] || emptyStat).min)}</span>
						<span>{formatNumber((breakdown.overall?.[metric.key] || emptyStat).max)}</span>
						<span>{formatNumber((breakdown.overall?.[metric.key] || emptyStat).avg)}</span>
						<span>{(breakdown.overall?.[metric.key] || emptyStat).count}</span>
					</div>
					{agentRoles.map((role) => {
						const stat = breakdown.by_agent[role]?.[metric.key] || emptyStat;
						return <div className="usage-metric-row" key={role}>
							<span>{roleLabel(role)}</span>
							<span>{formatNumber(stat.min)}</span>
							<span>{formatNumber(stat.max)}</span>
							<span>{formatNumber(stat.avg)}</span>
							<span>{stat.count}</span>
						</div>;
					})}
					{!agentRoles.length && loaded && <p className="usage-metric-empty">No usage data recorded yet.</p>}
				</article>)}
			</div>
		</section>
	</div>;
}
