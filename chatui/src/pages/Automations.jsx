import { useEffect, useState } from 'react';
import { CheckCircle2, Clock3, LoaderCircle, PlayCircle, XCircle } from 'lucide-react';
import { kitchenApi } from '../services/api';

// The agent-api /jobs endpoint only returns job names, so the responsible agent,
// task summary and usual cron time are described here for the tiles.
// `frequency`/`time` drive tile ordering: fixed-time weekday jobs sort first (by
// time of day, morning to evening), then daily jobs, then weekly jobs; a job with
// no single fixed time (e.g. an hourly sweep) sorts last within its frequency.
const JOB_META = {
	weekly_menu: {
		label: 'Weekly menu',
		agent: 'Executive Chef',
		description: "Reads current inventory, the chef note and the household's top-rated recipes, then writes and saves a full Monday–Sunday menu.",
		schedule: 'Saturdays, 10:00',
		frequency: 'weekly',
		time: '10:00',
	},
	sunday_prep: {
		label: 'Sunday prep',
		agent: 'Sous Chef',
		description: 'Turns the saved weekly menu into a Sunday batch-prep plan capped at 60 minutes.',
		schedule: 'Sundays, 14:00',
		frequency: 'weekly',
		time: '14:00',
	},
	nightly_prep: {
		label: 'Nightly prep',
		agent: 'Sous Chef',
		description: "Saves a practical 10-minute head-start task for tomorrow's breakfast and lunch.",
		schedule: 'Daily, 20:00',
		frequency: 'daily',
		time: '20:00',
	},
	morning_cooking: {
		label: 'Morning cooking',
		agent: 'Sous Chef',
		description: "Builds a detailed parallel cooking plan for today's breakfast and lunch, capped at 40 minutes.",
		schedule: 'Weekdays, 06:30',
		frequency: 'weekday',
		time: '06:30',
	},
	dinner_cooking: {
		label: 'Dinner cooking',
		agent: 'Sous Chef',
		description: "Builds a detailed parallel cooking plan for today's snack and dinner, capped at 40 minutes.",
		schedule: 'Weekdays, 18:00',
		frequency: 'weekday',
		time: '18:00',
	},
	pantry_manager: {
		label: 'Pantry manager',
		agent: 'Pantry Manager',
		description: 'Checks stock against the upcoming menu and saves a shopping list proposal. Never changes inventory.',
		schedule: 'Daily, 18:00',
		frequency: 'daily',
		time: '18:00',
	},
	menu_audit: {
		label: 'Menu audit',
		agent: 'Food Inspector',
		description: "Scores every not-yet-audited weekly menu slot against the household's dietary rules and preferences, with written feedback.",
		schedule: 'Daily, 22:30',
		frequency: 'daily',
		time: '22:30',
	},
	weekly_plan_audit: {
		label: 'Weekly plan audit',
		agent: 'Food Inspector',
		description: "Scores each not-yet-audited saved week against week-level rules (like lunch variety) that can't be judged from a single menu slot, with written feedback.",
		schedule: 'Daily, 22:35',
		frequency: 'daily',
		time: '22:35',
	},
	task_audit: {
		label: 'Task audit',
		agent: 'Food Inspector',
		description: "Scores every not-yet-audited prep task against the same rules and preferences the Sous Chef used, with written feedback.",
		schedule: 'Daily, 22:45',
		frequency: 'daily',
		time: '22:45',
	},
	recipe_audit: {
		label: 'Recipe audit',
		agent: 'Food Inspector',
		description: 'Scores every not-yet-audited recipe against the household recipe catalog standards (tags, instructions), with written feedback.',
		schedule: 'Daily, 23:00',
		frequency: 'daily',
		time: '23:00',
	},
	expire_prep_tasks: {
		label: 'Task expiry sweep',
		agent: 'Sous Chef',
		description: 'Expires any prep task still unacknowledged and uncancelled 2 hours after it was assigned.',
		schedule: 'Every 2 hours',
		frequency: 'daily',
		time: null,
	},
};

const RECENT_RUN_LIMIT = 10;
const FREQUENCY_RANK = { weekday: 0, daily: 1, weekly: 2 };

const metaFor = (jobName) => JOB_META[jobName] || { label: jobName, agent: 'Agent', description: 'Runs on demand.', schedule: 'On demand', frequency: 'daily', time: null };

const timeToMinutes = (time) => {
	if (!time) return Infinity;
	const [hours, minutes] = time.split(':').map(Number);
	return hours * 60 + minutes;
};

const byExecutionTime = (jobNameA, jobNameB) => {
	const metaA = metaFor(jobNameA);
	const metaB = metaFor(jobNameB);
	const rankDiff = FREQUENCY_RANK[metaA.frequency] - FREQUENCY_RANK[metaB.frequency];
	return rankDiff !== 0 ? rankDiff : timeToMinutes(metaA.time) - timeToMinutes(metaB.time);
};

function statusIcon(status) {
	if (status === 'completed') return <CheckCircle2 size={15} />;
	if (status === 'failed') return <XCircle size={15} />;
	return <Clock3 size={15} />;
}

export default function Automations() {
	const [jobs, setJobs] = useState([]);
	const [runs, setRuns] = useState([]);
	const [running, setRunning] = useState('');
	const [results, setResults] = useState({});
	const [error, setError] = useState('');

	const load = async () => {
		try {
			setError('');
			const [jobList, runList] = await Promise.all([kitchenApi.listAutomationJobs(), kitchenApi.listAutomationRuns()]);
			setJobs(jobList);
			setRuns(runList);
		} catch (requestError) {
			setError(requestError.message);
		}
	};

	useEffect(() => { load(); }, []);

	const invoke = async (jobName) => {
		setRunning(jobName);
		setError('');
		try {
			const outcome = await kitchenApi.invokeAutomation(jobName);
			setResults((current) => ({ ...current, [jobName]: outcome }));
			await load();
		} catch (requestError) {
			setError(requestError.message);
		} finally {
			setRunning('');
		}
	};

	const recentRuns = runs.slice(0, RECENT_RUN_LIMIT);

	const jobsByAgent = jobs.reduce((groups, jobName) => {
		const agent = metaFor(jobName).agent;
		const group = groups.find((entry) => entry.agent === agent);
		if (group) group.jobs.push(jobName);
		else groups.push({ agent, jobs: [jobName] });
		return groups;
	}, []);
	jobsByAgent.forEach((group) => group.jobs.sort(byExecutionTime));

	return <div className="page-content">
		<div className="page-lead">
			<div><p>Trigger any scheduled job on demand and see exactly what the agent did.</p></div>
		</div>
		{error && <div className="chat-error" role="alert"><span>{error}</span></div>}
		<section className="task-group">
			<h3>Run now</h3>
			{jobsByAgent.map(({ agent, jobs: agentJobs }) => (
				<div className="automation-agent-group" key={agent}>
					<h4>{agent}</h4>
					<div className="automation-jobs">
						{agentJobs.map((jobName) => {
							const meta = metaFor(jobName);
							return <article className="automation-job soft-outset" key={jobName}>
								<div className="automation-job-head">
									<b>{meta.label}</b>
								</div>
								<p className="automation-job-desc">{meta.description}</p>
								<p className="automation-job-schedule"><Clock3 size={13} /> {meta.schedule}</p>
								<button type="button" className="secondary-button automation-job-run" disabled={running === jobName} onClick={() => invoke(jobName)}>
									{running === jobName ? <LoaderCircle className="spin" size={15} /> : <PlayCircle size={15} />}
									{running === jobName ? 'Running...' : 'Run now'}
								</button>
								{results[jobName] && <p className="automation-result">{results[jobName].result}</p>}
							</article>;
						})}
					</div>
				</div>
			))}
			{!jobs.length && <div className="empty-state">No automations registered.</div>}
		</section>
		<section className="task-group">
			<h3>Recent runs</h3>
			{recentRuns.length ? recentRuns.map((run) => <article className="automation-run soft-outset" key={run.id}>
				<span className={`automation-status ${run.status}`}>{statusIcon(run.status)} {run.status}</span>
				<div className="automation-run-copy">
					<b>{metaFor(run.job_name).label}</b>
					<small>{run.agent_role} &middot; {run.finished_at}</small>
					<p>{run.status === 'failed' ? run.error : run.result}</p>
				</div>
			</article>) : <div className="empty-state">No automation runs yet.</div>}
		</section>
	</div>;
}
